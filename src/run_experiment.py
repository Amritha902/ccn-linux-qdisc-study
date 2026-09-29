#!/usr/bin/env python3
"""Run one experiment: one AQM, one seed, one workload profile.

Captures, for every run:
  - iperf3 JSON (per-flow throughput -> Jain's index, retransmits)
  - a 500 ms time series of the AQM's OWN queue statistics
  - concurrent ping RTT through the bottleneck (real queue delay, not a proxy)
  - the ACAPE adjustment log, when the adaptive controller is enabled

The workload is staged (few flows -> many -> few) so the congestion regime
actually changes. Under the original constant 8-flow overload the classifier
sat in HEAVY for 81% of ticks and the controller simply ratcheted target to its
floor in every run, which is why all 24 usable runs logged exactly 15
adjustments -- log(1/5)/log(0.9) = 15.3 steps from 5 ms to the 1 ms floor.
"""
import argparse, json, os, re, shutil, signal, statistics, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

SERVER_IP = "192.168.2.2"
PORT = 5201

AQM_SPECS = {
    "pfifo":      ("pfifo",     "limit 1000"),
    "fq_codel":   ("fq_codel",  "target 5ms interval 100ms limit 1024 quantum 1514"),
    "codel":      ("codel",     "target 5ms interval 100ms limit 1024"),
    "red":        ("red",       "limit 1000000 avpkt 1000 bandwidth 10mbit "
                                "min 30000 max 90000 burst 55 ecn adaptive"),
    "pie":        ("pie",       "limit 1000 target 15ms tupdate 15ms alpha 2 beta 20"),
    "fq_pie":     ("fq_pie",    "limit 1024 target 15ms tupdate 15ms"),
    "cake":       ("cake",      "bandwidth 10mbit besteffort"),
    "sfq":        ("sfq",       "perturb 10"),
}


def sh(cmd, **kw):
    return subprocess.run(cmd, shell=isinstance(cmd, str), **kw)


def nsx(ns, *args):
    return ["ip", "netns", "exec", ns, *args]


def jain(xs):
    if not xs:
        return 0.0
    s2 = sum(v * v for v in xs)
    return (sum(xs) ** 2) / (len(xs) * s2) if s2 > 0 else 0.0


def build_testbed(aqm, rate, rtt_ms):
    kind, aqm_args = AQM_SPECS[aqm]
    env = dict(os.environ, RATE_MBIT=str(rate), AQM=kind,
               AQM_ARGS=aqm_args, BASE_RTT_MS=str(rtt_ms))
    r = subprocess.run(["bash", os.path.join(HERE, "testbed.sh"), "setup"],
                       env=env, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"testbed setup failed:\n{r.stdout}\n{r.stderr}")
    return kind, aqm_args, r.stdout


def parse_ping(out):
    rtts = [float(m) for m in re.findall(r"time=([\d.]+) ms", out)]
    if not rtts:
        return {}
    rtts.sort()
    q = lambda p: rtts[min(len(rtts) - 1, int(len(rtts) * p))]
    return {"rtt_n": len(rtts), "rtt_mean_ms": round(statistics.fmean(rtts), 3),
            "rtt_min_ms": rtts[0], "rtt_p50_ms": q(0.50), "rtt_p95_ms": q(0.95),
            "rtt_p99_ms": q(0.99), "rtt_max_ms": rtts[-1]}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--aqm", required=True, choices=sorted(AQM_SPECS))
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--rate-mbit", type=float, default=10.0)
    p.add_argument("--rtt-ms", type=int, default=20)
    p.add_argument("--duration", type=int, default=120)
    p.add_argument("--flows", type=int, default=8)
    p.add_argument("--workload", default="steady", choices=["steady", "staged"])
    p.add_argument("--adapt", action="store_true", help="run the ACAPE controller")
    p.add_argument("--ebpf", action="store_true")
    p.add_argument("--outdir", default=os.path.join(ROOT, "results"))
    a = p.parse_args()

    label = f"{a.aqm}{'_acape' if a.adapt else ''}_{a.workload}_s{a.seed}"
    outdir = os.path.join(a.outdir, label)
    os.makedirs(outdir, exist_ok=True)

    kind, aqm_args, setup_out = build_testbed(a.aqm, a.rate_mbit, a.rtt_ms)
    with open(os.path.join(outdir, "00_setup.txt"), "w") as fh:
        fh.write(setup_out)

    procs = []
    try:
        srv = subprocess.Popen(nsx("ns_server", "iperf3", "-s", "-p", str(PORT)),
                               stdout=open(os.path.join(outdir, "iperf_server.log"), "w"),
                               stderr=subprocess.STDOUT)
        procs.append(srv)
        time.sleep(1.5)

        rec = subprocess.Popen(
            [sys.executable, os.path.join(HERE, "recorder.py"),
             "--ns", "ns_router", "--iface", "veth_rs", "--handle", "10:",
             "--kind", kind, "--rate-mbit", str(a.rate_mbit),
             "--out", os.path.join(outdir, "qdisc_timeseries.csv")],
            stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        procs.append(rec)

        ping = subprocess.Popen(
            nsx("ns_client", "ping", "-i", "0.2", "-w", str(a.duration + 5), SERVER_IP),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        procs.append(ping)

        ctl = None
        if a.adapt:
            ctl = subprocess.Popen(
                [sys.executable, os.path.join(HERE, "acape.py"),
                 "--ns", "ns_router", "--iface", "veth_rs", "--handle", "10:",
                 "--kind", kind, "--parent", "1:1", "--adapt",
                 "--rate-mbit", str(a.rate_mbit),
                 "--logdir", outdir, "--tag", "ctl",
                 "--duration", str(a.duration)]
                + (["--ebpf"] if a.ebpf else []),
                stdout=open(os.path.join(outdir, "controller.log"), "w"),
                stderr=subprocess.STDOUT)
            procs.append(ctl)

        # ── traffic ──────────────────────────────────────────────────────
        ijson = os.path.join(outdir, "iperf_client.json")
        if a.workload == "steady":
            subprocess.run(
                nsx("ns_client", "iperf3", "-c", SERVER_IP, "-p", str(PORT),
                    "-P", str(a.flows), "-t", str(a.duration), "-i", "1",
                    "-J", "--logfile", ijson), check=False)
        else:
            # staged: 1/3 at few flows, 1/3 at many, 1/3 back to few
            seg = a.duration // 3
            stages = [(max(2, a.flows // 4), seg),
                      (a.flows * 3, seg),
                      (max(2, a.flows // 4), a.duration - 2 * seg)]
            for i, (nf, dur) in enumerate(stages):
                subprocess.run(
                    nsx("ns_client", "iperf3", "-c", SERVER_IP, "-p", str(PORT),
                        "-P", str(nf), "-t", str(dur), "-i", "1", "-J",
                        "--logfile", os.path.join(outdir, f"iperf_stage{i}.json")),
                    check=False)
            shutil.copy(os.path.join(outdir, "iperf_stage1.json"), ijson)

        if ctl:
            ctl.wait(timeout=30)
        rec.send_signal(signal.SIGTERM); rec.wait(timeout=10)
        ping.send_signal(signal.SIGTERM)
        ping_out = ping.communicate(timeout=10)[0] or ""
        with open(os.path.join(outdir, "ping.log"), "w") as fh:
            fh.write(ping_out)

        # ── summarise ────────────────────────────────────────────────────
        summary = {"aqm": a.aqm, "qdisc_kind": kind, "qdisc_args": aqm_args,
                   "adaptive": a.adapt, "ebpf": a.ebpf, "seed": a.seed,
                   "rate_mbit": a.rate_mbit, "base_rtt_ms": a.rtt_ms,
                   "duration_s": a.duration, "flows": a.flows,
                   "workload": a.workload, "label": label}
        try:
            d = json.load(open(ijson))
            streams = [s["sender"]["bits_per_second"] / 1e6
                       for s in d["end"]["streams"] if "sender" in s]
            summary.update({
                "throughput_mbps": round(d["end"]["sum_sent"]["bits_per_second"] / 1e6, 4),
                "retransmits": d["end"]["sum_sent"].get("retransmits"),
                "n_flows_measured": len(streams),
                "jain": round(jain(streams), 6),
                "per_flow_mbps": [round(x, 4) for x in streams],
            })
        except Exception as e:
            summary["iperf_error"] = str(e)
        summary.update(parse_ping(ping_out))

        import csv as _csv
        try:
            rows = list(_csv.DictReader(open(os.path.join(outdir, "qdisc_timeseries.csv"))))
            rows = rows[1:]
            bl = [float(r["backlog_pkts"]) for r in rows]
            soj = [float(r["sojourn_est_ms"]) for r in rows]
            drp = [float(r["drop_rate_per_s"]) for r in rows]
            tp = [float(r["throughput_mbps"]) for r in rows]
            summary.update({
                "samples": len(rows),
                "backlog_mean_pkts": round(statistics.fmean(bl), 2),
                "backlog_p95_pkts": round(sorted(bl)[int(len(bl) * .95)], 2),
                "backlog_max_pkts": max(bl),
                "sojourn_mean_ms": round(statistics.fmean(soj), 4),
                "sojourn_p95_ms": round(sorted(soj)[int(len(soj) * .95)], 4),
                "drop_rate_mean_per_s": round(statistics.fmean(drp), 2),
                "qdisc_throughput_mean_mbps": round(statistics.fmean(tp), 4),
            })
        except Exception as e:
            summary["timeseries_error"] = str(e)

        with open(os.path.join(outdir, "summary.json"), "w") as fh:
            json.dump(summary, fh, indent=2)
        print(json.dumps(summary, indent=2))
    finally:
        for pr in procs:
            try:
                pr.kill()
            except Exception:
                pass
        subprocess.run(["bash", os.path.join(HERE, "testbed.sh"), "teardown"],
                       capture_output=True)


if __name__ == "__main__":
    if os.geteuid() != 0:
        sys.exit("must run as root")
    main()
