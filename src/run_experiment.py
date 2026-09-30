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
import argparse, glob, json, os, re, shutil, signal, statistics, subprocess, sys, time

from latency import parse_ping, summarise, iperf_inband_rtt, iperf_cwnd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

SERVER_IP = "192.168.2.2"
BASE_PORT = 5201

AQM_SPECS = {
    "pfifo":      ("pfifo",     "limit 1000"),
    "fq_codel":   ("fq_codel",  "target 5ms interval 100ms limit 1024 quantum 1514"),
    "codel":      ("codel",     "target 5ms interval 100ms limit 1024"),
    "red":        ("red",       "limit 1000000 avpkt 1000 bandwidth 10mbit "
                                "min 30000 max 90000 burst 55 ecn adaptive"),
    "pie":        ("pie",       "limit 1000 target 15ms tupdate 15ms alpha 2 beta 20"),
    "fq_pie":     ("fq_pie",    "limit 1024 target 15ms tupdate 15ms"),
    "cake":       ("cake",      "besteffort"),
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


def build_testbed(aqm, rate, rtt_ms, target_ms=None, scale_interval=True):
    kind, aqm_args = AQM_SPECS[aqm]
    # Override the AQM's delay target, to test whether the benefit of
    # adaptation is governed by target/RTT rather than by RTT alone.
    #
    # The interval is scaled with it by default, and that matters. CoDel has
    # two time parameters, and the configuration's shape is set by their ratio
    # as much as by the target. Rewriting the target alone moved
    # target/interval from 0.05 at the 5 ms default to 0.20 at 20 ms and 0.80
    # at 80 ms, so cells that were supposed to differ only in target/RTT
    # differed in a second dimensionless group as well, and the 80 ms cell sat
    # far outside the 5 to 10 percent envelope CoDel is designed around. A
    # ratio-invariance test has to scale the whole configuration, holding
    # target/interval fixed, or it is not holding the configuration's shape
    # fixed at all.
    #
    # P1 is unaffected: it varied RTT alone at the 5 ms target and 100 ms
    # interval, so target/interval was constant at 0.05 across that sweep.
    if target_ms is not None and "target" in aqm_args:
        m = re.search(r"target (\d+(?:\.\d+)?)", aqm_args)
        base_target = float(m.group(1)) if m else 5.0
        aqm_args = re.sub(r"target \S+", f"target {target_ms}ms", aqm_args)
        if scale_interval and base_target > 0:
            mi = re.search(r"interval (\d+(?:\.\d+)?)", aqm_args)
            if mi:
                scaled = float(mi.group(1)) * (target_ms / base_target)
                aqm_args = re.sub(r"interval \S+", f"interval {scaled:g}ms",
                                  aqm_args)
    env = dict(os.environ, RATE_MBIT=str(rate), AQM=kind,
               AQM_ARGS=aqm_args, BASE_RTT_MS=str(rtt_ms))
    r = subprocess.run(["bash", os.path.join(HERE, "testbed.sh"), "setup"],
                       env=env, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"testbed setup failed:\n{r.stdout}\n{r.stderr}")
    return kind, aqm_args, r.stdout


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--aqm", required=True, choices=sorted(AQM_SPECS))
    p.add_argument("--seed", type=int, default=1,
                   help="independent repetition index (not a PRNG seed)")
    p.add_argument("--rate-mbit", type=float, default=10.0)
    p.add_argument("--rtt-ms", type=int, default=20)
    p.add_argument("--aqm-target-ms", type=float, default=None,
                   help="override the AQM delay target (ms); the interval is "
                        "scaled with it so target/interval stays fixed")
    p.add_argument("--no-scale-interval", action="store_true",
                   help="rewrite the target without scaling the interval, "
                        "which changes the configuration's shape as well as "
                        "its scale")
    p.add_argument("--duration", type=int, default=120)
    p.add_argument("--flows", type=int, default=8)
    p.add_argument("--workload", default="steady",
                   choices=["steady", "staged", "mixed"])
    p.add_argument("--sparse-flows", type=int, default=3,
                   help="latency-sensitive UDP flows in the mixed workload")
    p.add_argument("--sparse-kbit", type=int, default=200,
                   help="per-flow rate of each sparse flow")
    p.add_argument("--adapt", action="store_true", help="run the ACAPE controller")
    p.add_argument("--sham", action="store_true",
                   help="run the controller but never apply changes "
                        "(isolates its CPU cost from its control decisions)")
    p.add_argument("--ebpf", action="store_true")
    p.add_argument("--outdir", default=os.path.join(ROOT, "results"))
    a = p.parse_args()

    # --ebpf MUST appear in the label. Without it an eBPF run and a plain
    # adaptive run with the same aqm/workload/seed resolve to the same output
    # directory, and the second silently overwrites the first -- which is what
    # happened on the first full suite, losing the plain staged ACAPE runs and
    # leaving the staged comparison confounded by eBPF polling load.
    suffix = "_acape" if a.adapt else ("_sham" if a.sham else "")
    if a.ebpf:
        suffix += "_ebpf"
    if a.aqm_target_ms is not None:
        suffix += f"_t{a.aqm_target_ms:g}"
    label = f"{a.aqm}{suffix}_{a.workload}_s{a.seed}"
    outdir = os.path.join(a.outdir, label)
    os.makedirs(outdir, exist_ok=True)

    # `--seed` indexes an INDEPENDENT REPETITION, not a PRNG seed. iperf3
    # exposes no seed and the qdiscs are deterministic given the traffic, so
    # nothing here is pseudo-randomised; repetitions differ only through real
    # timing variation in the system. The confidence intervals therefore
    # describe run-to-run variance, which is the quantity of interest, but the
    # word "seed" should be read as "repetition" throughout.
    port = BASE_PORT
    start_jitter = 0.0

    kind, aqm_args, setup_out = build_testbed(a.aqm, a.rate_mbit, a.rtt_ms,
                                              a.aqm_target_ms,
                                              not a.no_scale_interval)
    with open(os.path.join(outdir, "00_setup.txt"), "w") as fh:
        fh.write(setup_out)

    procs = []
    try:
        srv = subprocess.Popen(nsx("ns_server", "iperf3", "-s", "-p", str(port)),
                               stdout=open(os.path.join(outdir, "iperf_server.log"), "w"),
                               stderr=subprocess.STDOUT)
        procs.append(srv)
        time.sleep(1.5 + start_jitter)

        rec = subprocess.Popen(
            [sys.executable, os.path.join(HERE, "recorder.py"),
             "--ns", "ns_router", "--iface", "veth_rs", "--handle", "10:",
             "--kind", kind, "--rate-mbit", str(a.rate_mbit),
             "--out", os.path.join(outdir, "qdisc_timeseries.csv")],
            stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        procs.append(rec)

        # 20 Hz sparse-flow probe: ~1200 samples over 60 s, enough for a
        # stable p99. 0.2 s gave ~300, too few for tail statistics.
        ping = subprocess.Popen(
            nsx("ns_client", "ping", "-i", "0.05", "-w", str(a.duration + 5),
                SERVER_IP),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        procs.append(ping)


        ctl = None
        ctl_note = None
        if a.sham:
            # Control condition: the controller runs and polls at the same
            # cadence but never applies a parameter change. Any latency
            # difference between sham and static is the controller's own CPU
            # cost, not its control decisions -- without this, the two are
            # confounded.
            ctl = subprocess.Popen(
                [sys.executable, os.path.join(HERE, "acape.py"),
                 "--ns", "ns_router", "--iface", "veth_rs", "--handle", "10:",
                 "--kind", kind, "--parent", "1:1",
                 "--rate-mbit", str(a.rate_mbit),
                 "--logdir", outdir, "--tag", "sham",
                 "--duration", str(a.duration)]
                + (["--ebpf"] if a.ebpf else []),
                stdout=open(os.path.join(outdir, "controller.log"), "w"),
                stderr=subprocess.STDOUT)
            procs.append(ctl)
        elif a.adapt:
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
        if a.workload == "mixed":
            # Bulk TCP alongside sparse, latency-sensitive UDP flows.
            #
            # This is the condition in which fq_codel's new-flow heuristic and
            # the `quantum` parameter are supposed to matter: sparse flows are
            # given priority on arrival, and `quantum` sets how many bytes a
            # flow is served per round. A bulk-only workload cannot exercise
            # either, so a null result on bulk-only traffic says nothing about
            # them. The UDP flows report their own one-way delay variation and
            # loss, which is what a latency-sensitive application experiences.
            usrv = subprocess.Popen(
                nsx("ns_server", "iperf3", "-s", "-p", str(port + 1)),
                stdout=open(os.path.join(outdir, "iperf_udp_server.log"), "w"),
                stderr=subprocess.STDOUT)
            procs.append(usrv)
            time.sleep(1.0)
            bulk_p = subprocess.Popen(
                nsx("ns_client", "iperf3", "-c", SERVER_IP, "-p", str(port),
                    "-P", str(a.flows), "-t", str(a.duration), "-i", "1",
                    "-J", "--logfile", ijson),
                stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
            time.sleep(2.0)          # let the bulk flows fill the queue first
            subprocess.run(
                nsx("ns_client", "iperf3", "-c", SERVER_IP, "-p", str(port + 1),
                    "-u", "-b", f"{a.sparse_kbit}k", "-l", "300",
                    "-P", str(a.sparse_flows), "-t", str(max(5, a.duration - 4)),
                    "-i", "1", "-J",
                    "--logfile", os.path.join(outdir, "iperf_sparse.json")),
                check=False)
            bulk_p.wait(timeout=a.duration + 30)
        elif a.workload == "steady":
            subprocess.run(
                nsx("ns_client", "iperf3", "-c", SERVER_IP, "-p", str(port),
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
                    nsx("ns_client", "iperf3", "-c", SERVER_IP, "-p", str(port),
                        "-P", str(nf), "-t", str(dur), "-i", "1", "-J",
                        "--logfile", os.path.join(outdir, f"iperf_stage{i}.json")),
                    check=False)
            shutil.copy(os.path.join(outdir, "iperf_stage1.json"), ijson)

        if ctl:
            try:
                ctl.wait(timeout=30)
            except subprocess.TimeoutExpired:
                # Never let a slow controller abort the summary; the run's
                # measurements are already on disk.
                ctl_note = "controller did not exit within 30s"
                ctl.terminate()
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
                   "workload": a.workload, "label": label,
                   "sham": a.sham, "port": port,
                   "aqm_target_ms": a.aqm_target_ms,
                   "target_rtt_ratio": (round(a.aqm_target_ms / a.rtt_ms, 4)
                                        if a.aqm_target_ms else
                                        round(5.0 / a.rtt_ms, 4)),
                   "start_jitter_s": round(start_jitter, 3),
                   "seed_semantics": "independent repetition index, "
                                     "not a PRNG seed"}
        if ctl_note:
            summary["controller_note"] = ctl_note
        # Goodput must come from sum_RECEIVED, not sum_sent. With a large
        # unmanaged buffer (pfifo) the sender dumps into the queue faster than
        # the link drains, so sum_sent reports more than the link can carry --
        # in a 20s pfifo run it read 17.95 Mbps on a 10 Mbit link. sum_received
        # counts only what actually crossed the bottleneck.
        stage_files = sorted(glob.glob(os.path.join(outdir, "iperf_stage*.json"))) \
            or [ijson]
        stages, jains, tot_bytes, tot_time, tot_rtx = [], [], 0.0, 0.0, 0
        for sf in stage_files:
            try:
                d = json.load(open(sf))
                end = d["end"]
                recv = end.get("sum_received", {})
                sent = end.get("sum_sent", {})
                streams = [st["receiver"]["bits_per_second"] / 1e6
                           for st in end.get("streams", []) if "receiver" in st]
                stages.append({
                    "file": os.path.basename(sf),
                    "goodput_mbps": round(recv.get("bits_per_second", 0) / 1e6, 4),
                    "sent_mbps": round(sent.get("bits_per_second", 0) / 1e6, 4),
                    "flows": len(streams),
                    "jain": round(jain(streams), 6),
                    "retransmits": sent.get("retransmits"),
                })
                if streams:
                    jains.append(jain(streams))
                tot_bytes += recv.get("bytes", 0)
                tot_time += recv.get("seconds", 0) or 0
                tot_rtx += sent.get("retransmits") or 0
            except Exception as e:
                summary.setdefault("iperf_errors", []).append(f"{os.path.basename(sf)}: {e}")
        if tot_time > 0:
            summary["throughput_mbps"] = round(tot_bytes * 8 / tot_time / 1e6, 4)
        if stages:
            summary["stages"] = stages
            summary["retransmits"] = tot_rtx
            summary["jain"] = round(statistics.fmean(jains), 6) if jains else None
            summary["jain_per_stage"] = [st["jain"] for st in stages]
            summary["n_flows_measured"] = stages[0]["flows"]
            summary["sent_mbps"] = stages[0]["sent_mbps"]
        # (1) sparse-flow probe
        sparse = parse_ping(ping_out)
        summary.update(summarise(sparse, "rtt"))          # canonical names
        summary.update(summarise(sparse, "sparse_rtt"))
        # (2) in-band bulk-flow RTT, from iperf3's TCP_INFO samples
        bulk_samples = []
        for sf in stage_files:
            bulk_samples.extend(iperf_inband_rtt(sf))
        summary.update(summarise(bulk_samples, "bulk_rtt"))

        # sparse latency-sensitive flows (mixed workload only)
        sp = os.path.join(outdir, "iperf_sparse.json")
        if os.path.exists(sp):
            try:
                sd = json.load(open(sp))
                streams = sd["end"].get("streams", [])
                jit = [st["udp"]["jitter_ms"] for st in streams if "udp" in st]
                lost = [st["udp"]["lost_percent"] for st in streams if "udp" in st]
                rates = [st["udp"]["bits_per_second"] / 1e6
                         for st in streams if "udp" in st]
                iv = [s2["jitter_ms"] for i2 in sd.get("intervals", [])
                      for s2 in i2.get("streams", []) if "jitter_ms" in s2]
                summary.update({
                    "sparse_n_flows": len(jit),
                    "sparse_jitter_mean_ms": round(statistics.fmean(jit), 4) if jit else None,
                    "sparse_jitter_max_ms": round(max(jit), 4) if jit else None,
                    "sparse_loss_mean_pct": round(statistics.fmean(lost), 4) if lost else None,
                    "sparse_loss_max_pct": round(max(lost), 4) if lost else None,
                    "sparse_goodput_mbps": round(sum(rates), 4) if rates else None,
                })
                summary.update(summarise(iv, "sparse_jitter"))
            except Exception as e:
                summary["sparse_error"] = str(e)
        cwnds = []
        for sf in stage_files:
            cwnds.extend(iperf_cwnd(sf))
        if cwnds:
            summary["cwnd_mean_bytes"] = round(statistics.fmean(cwnds), 1)
        with open(os.path.join(outdir, "bulk_rtt.json"), "w") as fh:
            json.dump({"samples": bulk_samples}, fh)
        # (3) queueing delay above the configured base RTT
        if sparse:
            summary["queue_delay_mean_ms"] = round(
                statistics.fmean(sparse) - a.rtt_ms, 4)
            summary["queue_delay_p95_ms"] = round(
                sorted(sparse)[int(len(sparse) * .95)] - a.rtt_ms, 4)

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
