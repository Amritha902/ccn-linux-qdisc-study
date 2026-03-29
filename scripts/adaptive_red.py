#!/usr/bin/env python3
"""
adaptive_red.py — Adaptive RED Controller for fq_codel
Amritha S — VIT Chennai 2026

Implements Floyd et al. (2001) Adaptive RED algorithm adapted to tune
fq_codel parameters. This is the comparison baseline against ACAPE.

Adaptive RED logic:
  - Computes EWMA of queue occupancy (avg_q)
  - Adapts max_p (drop probability) → maps to fq_codel target
  - Uses same thresholds: min_th=20, max_th=300
  - α=0.01 (cautious increase), β=0.9 (aggressive decrease)

Key difference from ACAPE:
  - Only reacts to CURRENT queue state (no gradient prediction)
  - Only adapts one effective parameter (target via max_p mapping)
  - No eBPF flow telemetry
  - No workload-aware profiles

Run: sudo python3 adaptive_red.py --ns ns1 --iface veth1 --logdir ../logs
"""

import subprocess, re, time, csv, os, sys, argparse
from datetime import datetime

# ── Adaptive RED Parameters (Floyd 2001) ──────────────────────
MIN_TH   = 20     # min queue threshold (packets)
MAX_TH   = 300    # max queue threshold (packets)
MAX_P    = 0.5    # max drop probability
W_Q      = 0.002  # EWMA weight for queue average
ALPHA    = 0.01   # gentle increase factor
BETA     = 0.9    # multiplicative decrease factor
TARGET_INTERVAL = 0.5   # check every 500ms

# ── fq_codel parameter mapping from max_p ─────────────────────
# max_p high (heavy congestion) → lower target
# max_p low  (light congestion) → higher target
TARGET_MIN = 1.0   # ms
TARGET_MAX = 5.0   # ms
LIMIT_MIN  = 256
LIMIT_MAX  = 1024

def run(cmd):
    try:
        return subprocess.check_output(cmd, stderr=subprocess.DEVNULL,
                                        text=True, timeout=3)
    except:
        return ""

def rns(ns, cmd):
    try:
        return subprocess.check_output(
            ["ip", "netns", "exec", ns] + cmd,
            stderr=subprocess.DEVNULL, text=True, timeout=3)
    except:
        return ""

def get_tc_stats(ns, iface):
    out = rns(ns, ["tc", "-s", "qdisc", "show", "dev", iface])
    stats = {"drops": 0, "backlog": 0, "bytes": 0, "ts": time.time()}
    if not out:
        return stats
    m = re.search(r"dropped (\d+)", out)
    if m: stats["drops"] = int(m.group(1))
    m = re.search(r"backlog \d+b (\d+)p", out)
    if m: stats["backlog"] = int(m.group(1))
    m = re.search(r"Sent (\d+) bytes", out)
    if m: stats["bytes"] = int(m.group(1))
    return stats

def apply_params(ns, iface, target_ms, limit):
    """Apply fq_codel parameters via tc qdisc change"""
    target_us = int(target_ms * 1000)  # ms → us
    interval_us = max(int(target_us * 10), 50000)  # interval ≥ target × 10
    rns(ns, [
        "tc", "qdisc", "change", "dev", iface,
        "parent", "1:1", "handle", "10:", "fq_codel",
        f"target", f"{target_us}us",
        f"interval", f"{interval_us}us",
        f"limit", f"{limit}"
    ])

def maxp_to_target(max_p):
    """Map max_p [0,0.5] → target_ms [TARGET_MAX, TARGET_MIN]"""
    # Higher max_p = more dropping needed = lower target (tighter)
    ratio = max_p / MAX_P
    return TARGET_MAX - ratio * (TARGET_MAX - TARGET_MIN)

def maxp_to_limit(max_p):
    """Map max_p [0,0.5] → limit [LIMIT_MAX, LIMIT_MIN]"""
    ratio = max_p / MAX_P
    return int(LIMIT_MAX - ratio * (LIMIT_MAX - LIMIT_MIN))

def run_adaptive_red(ns, iface, logdir, duration=120):
    """
    Main Adaptive RED control loop.
    Implements Floyd et al. 2001 Section 3.
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    metrics_file = os.path.join(logdir, f"ared_metrics_{ts}.csv")
    adj_file     = os.path.join(logdir, f"ared_adj_{ts}.csv")
    os.makedirs(logdir, exist_ok=True)

    with open(metrics_file, "w", newline="") as mf, \
         open(adj_file,     "w", newline="") as af:

        mw = csv.writer(mf)
        mw.writerow(["timestamp", "elapsed", "avg_q", "drop_rate",
                     "backlog", "throughput_mbps", "max_p", "target_ms", "limit"])
        aw = csv.writer(af)
        aw.writerow(["timestamp", "elapsed", "avg_q", "old_maxp",
                     "new_maxp", "old_target", "new_target", "old_limit",
                     "new_limit", "reason"])

        # ── State variables ────────────────────────────────────
        avg_q      = 0.0    # EWMA queue estimate
        max_p      = 0.1    # initial drop probability
        prev_stats = get_tc_stats(ns, iface)
        start_time = time.time()
        adj_count  = 0

        # Initial parameters
        cur_target = TARGET_MAX   # 5ms
        cur_limit  = LIMIT_MAX    # 1024

        print("=" * 68)
        print("  Adaptive RED Controller — Floyd et al. 2001")
        print(f"  ns={ns}  iface={iface}  duration={duration}s")
        print(f"  min_th={MIN_TH}  max_th={MAX_TH}  max_p={MAX_P}")
        print(f"  wq={W_Q}  alpha={ALPHA}  beta={BETA}")
        print("=" * 68)
        print(f"{'t(s)':>6} {'avg_q':>8} {'drop/s':>10} {'backlog':>8}"
              f" {'tput':>6} {'max_p':>6} {'target':>8} {'lim':>5} {'adj':>4}")
        print("─" * 68)

        t_check_start = time.time()
        last_adjust   = time.time()

        while True:
            elapsed = time.time() - start_time
            if elapsed > duration:
                break

            time.sleep(TARGET_INTERVAL)
            cur_stats = get_tc_stats(ns, iface)
            dt = max(cur_stats["ts"] - prev_stats["ts"], 1e-6)

            # ── Compute metrics ────────────────────────────────
            drop_rate  = max(0, cur_stats["drops"] - prev_stats["drops"]) / dt
            throughput = max(0, cur_stats["bytes"]  - prev_stats["bytes"]) * 8 / (dt * 1e6)
            backlog    = cur_stats["backlog"]

            # ── Adaptive RED EWMA queue estimate ──────────────
            # avg_q = (1-wq)*avg_q + wq*backlog
            avg_q = (1 - W_Q) * avg_q + W_Q * backlog

            # ── Adaptive RED max_p update (Floyd 2001 Eq 2-4) ──
            old_max_p = max_p
            reason    = "stable"

            if avg_q < MIN_TH:
                # Below min threshold: no action needed, gently recover
                if max_p > 0.01:
                    max_p = max(max_p - ALPHA * 0.5, 0.01)
                    reason = "below_min_th"
            elif avg_q > MAX_TH:
                # Above max threshold: aggressive decrease
                max_p = min(max_p / BETA, MAX_P)
                reason = "above_max_th"
            else:
                # Between thresholds: proportional adjustment
                # max_p increases as avg_q increases
                target_p = MAX_P * (avg_q - MIN_TH) / (MAX_TH - MIN_TH)
                if target_p > max_p:
                    max_p = min(max_p + ALPHA, MAX_P)
                    reason = "proportional_increase"
                elif target_p < max_p - 0.05:
                    max_p = max(max_p - ALPHA * 2, 0.01)
                    reason = "proportional_decrease"

            # ── Map max_p to fq_codel parameters ──────────────
            new_target = round(maxp_to_target(max_p), 2)
            new_limit  = maxp_to_limit(max_p)

            # Apply only if changed significantly
            if (abs(new_target - cur_target) > 0.1 or
                abs(new_limit  - cur_limit)  > 20):
                apply_params(ns, iface, new_target, new_limit)
                adj_count += 1
                aw.writerow([
                    time.time(), round(elapsed, 1),
                    round(avg_q, 1), round(old_max_p, 4),
                    round(max_p, 4), cur_target, new_target,
                    cur_limit, new_limit, reason
                ])
                af.flush()
                cur_target = new_target
                cur_limit  = new_limit

            # ── Log metrics ────────────────────────────────────
            mw.writerow([
                time.time(), round(elapsed, 1),
                round(avg_q, 1), round(drop_rate, 1),
                backlog, round(throughput, 3),
                round(max_p, 4), cur_target, cur_limit
            ])
            mf.flush()

            # ── Print to terminal ──────────────────────────────
            print(f"{elapsed:>6.1f} {avg_q:>8.1f} {drop_rate:>10.1f}"
                  f" {backlog:>8} {throughput:>6.2f} {max_p:>6.3f}"
                  f" {cur_target:>6.1f}ms {cur_limit:>5} {adj_count:>4}",
                  flush=True)

            prev_stats = cur_stats

    print("\n" + "=" * 68)
    print(f"  Done — {adj_count} adjustments")
    print(f"  Metrics: {metrics_file}")
    print(f"  Adj log: {adj_file}")
    print(f"  Run: python3 plot_acape.py --logdir {logdir}")

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Adaptive RED Controller")
    p.add_argument("--ns",       default="ns1")
    p.add_argument("--iface",    default="veth1")
    p.add_argument("--logdir",   default="../logs")
    p.add_argument("--duration", type=int, default=120)
    args = p.parse_args()
    if os.geteuid() != 0:
        sys.exit("Run as root: sudo python3 adaptive_red.py")
    run_adaptive_red(args.ns, args.iface, args.logdir, args.duration)
