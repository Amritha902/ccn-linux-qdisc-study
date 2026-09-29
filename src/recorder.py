#!/usr/bin/env python3
"""Sample the AQM qdisc's statistics at a fixed interval.

Uses acape.read_tc(), which selects the qdisc by handle/kind. The original
record_metrics.py used a bare re.search() over the whole `tc -s qdisc show`
output and therefore recorded the TBF root's counters, not the AQM's.
"""
import argparse, csv, json, os, signal, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from acape import read_tc  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--ns", default="ns_router")
    p.add_argument("--iface", default="veth_rs")
    p.add_argument("--handle", default="10:")
    p.add_argument("--kind", default="fq_codel")
    p.add_argument("--out", required=True)
    p.add_argument("--interval", type=float, default=0.5)
    p.add_argument("--duration", type=float, default=0)
    p.add_argument("--rate-mbit", type=float, default=10.0)
    a = p.parse_args()

    stop = {"v": False}
    signal.signal(signal.SIGINT, lambda *_: stop.update(v=True))
    signal.signal(signal.SIGTERM, lambda *_: stop.update(v=True))

    first = read_tc(a.ns, a.iface, a.handle, a.kind)
    if not first:
        sys.exit("recorder: cannot read qdisc stats")
    t0 = time.time()
    prev = first
    drops0, bytes0 = first["drops"], first["bytes"]

    with open(a.out, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["t_s", "backlog_pkts", "backlog_bytes", "drops_cum",
                    "drop_rate_per_s", "throughput_mbps", "sojourn_est_ms",
                    "pkts_cum", "root_drops", "root_overlimits"])
        while not stop["v"]:
            time.sleep(a.interval)
            cur = read_tc(a.ns, a.iface, a.handle, a.kind)
            if not cur:
                continue
            t = cur["ts"] - t0
            if a.duration and t >= a.duration:
                break
            dt = max(cur["ts"] - prev["ts"], 1e-6)
            dr = max(0, cur["drops"] - prev["drops"]) / dt
            tp = (max(0, cur["bytes"] - prev["bytes"]) * 8) / (dt * 1e6)
            soj = cur["backlog_b"] * 8 / (a.rate_mbit * 1e6) * 1000
            w.writerow([f"{t:.3f}", cur["backlog_p"], cur["backlog_b"],
                        cur["drops"] - drops0, f"{dr:.4f}", f"{tp:.4f}",
                        f"{soj:.4f}", cur["pkts"],
                        cur["root"]["drops"], cur["root"]["overlimits"]])
            fh.flush()
            prev = cur


if __name__ == "__main__":
    main()
