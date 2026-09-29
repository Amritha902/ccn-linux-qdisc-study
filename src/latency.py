#!/usr/bin/env python3
"""Latency instrumentation.

Three independent measurements per run, because no single one is sufficient
for a latency claim:

1. **Sparse-flow OWD/RTT** (`ping`, 20 Hz). ICMP hashes to its own fq_codel
   flow queue and benefits from the new-flow heuristic, so this is the
   "latency under load" a latency-sensitive application would see. It is NOT
   the latency the bulk flows experience.

2. **In-band bulk-flow RTT** (iperf3's per-interval `rtt`, from TCP_INFO).
   The kernel's smoothed RTT for each bulk connection. This is what the bulk
   flows actually experience, including time behind their own queued data.

   The two differ substantially and the difference is the point: fq_codel's
   new-flow heuristic gives the sparse ICMP probe preferential service, so the
   probe reports ~22 ms while the bulk flows it shares the link with report
   ~37 ms. Quoting only the probe overstates the AQM's benefit for bulk
   traffic.

3. **Queue sojourn** (derived from the AQM's backlog and the drain rate).
   backlog_bytes / rate gives the delay of a packet arriving at that instant.

Reporting only (1) overstates how well an AQM is doing for bulk traffic;
reporting only (3) ignores everything outside the queue. The three together
let a reader see which component any difference came from.
"""
import json, re, statistics as st


def parse_ping(out):
    """RTT samples from ping stdout."""
    return [float(m) for m in re.findall(r"time=([\d.]+)\s*ms", out)]


def summarise(samples, prefix):
    if not samples:
        return {}
    s = sorted(samples)
    q = lambda p: s[min(len(s) - 1, int(len(s) * p))]
    d = {
        f"{prefix}_n": len(s),
        f"{prefix}_mean_ms": round(st.fmean(s), 3),
        f"{prefix}_min_ms": round(s[0], 3),
        f"{prefix}_p50_ms": round(q(0.50), 3),
        f"{prefix}_p90_ms": round(q(0.90), 3),
        f"{prefix}_p95_ms": round(q(0.95), 3),
        f"{prefix}_p99_ms": round(q(0.99), 3),
        f"{prefix}_max_ms": round(s[-1], 3),
    }
    if len(s) > 1:
        d[f"{prefix}_stdev_ms"] = round(st.stdev(s), 3)
        # jitter: mean absolute successive difference (RFC 3550 spirit)
        d[f"{prefix}_jitter_ms"] = round(
            st.fmean(abs(samples[i + 1] - samples[i])
                     for i in range(len(samples) - 1)), 3)
    return d


def iperf_inband_rtt(path):
    """Per-stream smoothed RTT from an iperf3 JSON log, in milliseconds.

    iperf3 records `rtt` (microseconds, from TCP_INFO) for every stream in
    every reporting interval, so a 60 s 8-flow run yields ~480 samples. This is
    the RTT the BULK FLOWS experience -- time spent behind their own queued
    data included.

    It is preferred over sampling `ss` for three reasons: iperf3 already
    collects it, so no extra process competes for CPU (which would confound a
    latency comparison against a run that has a controller running); it is
    per-stream rather than an average over a sweep; and `ss` reports no rtt
    field at all on some kernel builds, including the one used here.
    """
    try:
        d = json.load(open(path))
    except Exception:
        return []
    return [strm["rtt"] / 1000.0
            for iv in d.get("intervals", [])
            for strm in iv.get("streams", [])
            if strm.get("rtt")]


def iperf_cwnd(path):
    """Per-stream congestion window (bytes) from an iperf3 JSON log."""
    try:
        d = json.load(open(path))
    except Exception:
        return []
    return [strm["snd_cwnd"]
            for iv in d.get("intervals", [])
            for strm in iv.get("streams", [])
            if strm.get("snd_cwnd")]
