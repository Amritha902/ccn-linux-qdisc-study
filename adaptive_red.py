#!/usr/bin/env python3
"""
adaptive_red.py — Adaptive RED Controller (Floyd et al. 2001)
Adapted to tune fq_codel parameters on Linux tc subsystem.

This is the comparison baseline for ACAPE.

Algorithm (Floyd 2001):
  1. Compute EWMA queue estimate: avg_q = (1-wq)*avg_q + wq*backlog
  2. If avg_q < min_th: gently reduce max_p (recovery)
  3. If avg_q > max_th: aggressively increase max_p (congestion)
  4. Between thresholds: proportional max_p adjustment
  5. Map max_p -> fq_codel target and limit (our extension)

Key differences from ACAPE:
  - Reacts to CURRENT avg_q only (no gradient, no prediction)
  - Adapts max_p, which we map to target — not native fq_codel params
  - No eBPF telemetry, no flow classification, no workload profiles
  - No predictive (C2), no gradient (C1), no eBPF (C3)

Amritha S — VIT Chennai 2026
Run: sudo python3 adaptive_red.py --ns ns1 --iface veth1 --logdir ../logs
"""

import subprocess, re, time, csv, os, sys, argparse, math
from datetime import datetime

# ── Adaptive RED parameters (Floyd 2001 defaults) ─────────────
MIN_TH   = 20     # packets — minimum queue threshold
MAX_TH   = 300    # packets — maximum queue threshold
MAX_P    = 0.50   # maximum drop probability
W_Q      = 0.002  # queue weight for EWMA
ALPHA    = 0.01   # gentle increase step
BETA     = 0.90   # multiplicative decrease factor (same as ACAPE AIMD)

# ── fq_codel parameter mapping ────────────────────────────────
# max_p in [0, MAX_P] → target_ms in [TARGET_MAX, TARGET_MIN]
TARGET_MIN  = 1.0    # ms
TARGET_MAX  = 5.0    # ms
LIMIT_MIN   = 256    # packets
LIMIT_MAX   = 1024   # packets
INTERVAL_MS = 100.0  # fixed (ARED doesn't tune this)
POLL_S      = 0.5    # polling interval (same as ACAPE)


def rns(ns, cmd):
    try:
        return subprocess.check_output(
            ["ip", "netns", "exec", ns] + cmd,
            stderr=subprocess.DEVNULL, text=True, timeout=3)
    except:
        return ""


def get_stats(ns, iface):
    out = rns(ns, ["tc", "-s", "qdisc", "show", "dev", iface])
    ts   = time.time()
    drops, backlog, sent_bytes = 0, 0, 0
    if out:
        m = re.search(r"dropped (\d+)", out)
        if m: drops = int(m.group(1))
        m = re.search(r"backlog \d+b (\d+)p", out)
        if m: backlog = int(m.group(1))
        m = re.search(r"Sent (\d+) bytes", out)
        if m: sent_bytes = int(m.group(1))
    return {"ts": ts, "drops": drops, "backlog": backlog, "bytes": sent_bytes}


def apply_fqcodel(ns, iface, target_ms, limit):
    target_us   = max(1000, int(target_ms * 1000))
    interval_us = max(int(target_us * 10), 50000)
    rns(ns, [
        "tc", "qdisc", "change", "dev", iface,
        "parent", "1:1", "handle", "10:", "fq_codel",
        f"target", f"{target_us}us",
        f"interval", f"{interval_us}us",
        f"limit", str(limit)
    ])


def maxp_to_target(max_p):
    """Linear mapping: max_p high → target low (tighter AQM)."""
    ratio = min(max_p / MAX_P, 1.0)
    return round(TARGET_MAX - ratio * (TARGET_MAX - TARGET_MIN), 2)


def maxp_to_limit(max_p):
    """Linear mapping: max_p high → limit low (smaller queue)."""
    ratio = min(max_p / MAX_P, 1.0)
    return max(LIMIT_MIN, int(LIMIT_MAX - ratio * (LIMIT_MAX - LIMIT_MIN)))


def run(args):
    ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs(args.logdir, exist_ok=True)
    mfile = os.path.join(args.logdir, f"ared_metrics_{ts_str}.csv")
    afile = os.path.join(args.logdir, f"ared_adj_{ts_str}.csv")

    with open(mfile, "w", newline="") as mf, \
         open(afile, "w", newline="") as af:

        mw = csv.writer(mf)
        mw.writerow(["t_s", "avg_q", "drop_rate_per_s", "backlog_pkts",
                     "throughput_mbps", "max_p", "target_ms", "limit_pkts"])
        aw = csv.writer(af)
        aw.writerow(["t_s", "avg_q", "old_maxp", "new_maxp",
                     "old_target_ms", "new_target_ms",
                     "old_limit", "new_limit", "reason"])

        # State
        avg_q      = 0.0
        max_p      = 0.05
        cur_target = TARGET_MAX
        cur_limit  = LIMIT_MAX
        adj_count  = 0
        prev       = get_stats(args.ns, args.iface)
        t_start    = time.time()

        print("=" * 72)
        print("  Adaptive RED Controller  —  Floyd, Gummadi & Shenker (ICSI 2001)")
        print(f"  ns={args.ns}  iface={args.iface}  duration={args.duration}s")
        print(f"  min_th={MIN_TH}  max_th={MAX_TH}  max_p={MAX_P}")
        print(f"  W_Q={W_Q}  alpha={ALPHA}  beta={BETA}")
        print("=" * 72)
        print(f"  NOTE: Adaptive RED adapts max_p (drop prob) mapped to target/limit")
        print(f"  It does NOT use gradient prediction, eBPF, or workload profiles")
        print("=" * 72)
        print(f"{'t(s)':>6}  {'avg_q':>7}  {'dr/s':>9}  "
              f"{'bl':>6}  {'tput':>6}  "
              f"{'max_p':>6}  {'target':>7}  {'limit':>5}  {'adj':>4}")
        print("─" * 72)

        while True:
            elapsed = time.time() - t_start
            if elapsed > args.duration:
                break
            time.sleep(POLL_S)

            cur  = get_stats(args.ns, args.iface)
            dt   = max(cur["ts"] - prev["ts"], 1e-6)
            dr   = max(0, cur["drops"] - prev["drops"]) / dt
            tput = max(0, cur["bytes"]  - prev["bytes"]) * 8 / (dt * 1e6)
            bl   = cur["backlog"]

            # ── Floyd 2001: EWMA queue estimate ───────────────
            avg_q = (1 - W_Q) * avg_q + W_Q * bl

            # ── Floyd 2001: max_p adaptation ──────────────────
            old_max_p = max_p
            reason    = "stable"

            if avg_q < MIN_TH:
                # Below minimum: gently relax
                if max_p > 0.01:
                    max_p = max(max_p - ALPHA * 0.5, 0.01)
                    reason = "below_min_th_relax"
            elif avg_q >= MAX_TH:
                # Above maximum: aggressive increase
                max_p = min(max_p + ALPHA * 4, MAX_P)
                reason = "above_max_th_increase"
            else:
                # Between thresholds: proportional
                target_p = MAX_P * (avg_q - MIN_TH) / (MAX_TH - MIN_TH)
                if target_p > max_p + 0.01:
                    max_p = min(max_p + ALPHA, MAX_P)
                    reason = "proportional_increase"
                elif target_p < max_p - 0.02:
                    max_p = max(max_p - ALPHA, 0.01)
                    reason = "proportional_decrease"

            # ── Map max_p to fq_codel parameters ──────────────
            new_target = maxp_to_target(max_p)
            new_limit  = maxp_to_limit(max_p)

            changed = (abs(new_target - cur_target) > 0.09 or
                       abs(new_limit  - cur_limit)  > 15)
            if changed:
                apply_fqcodel(args.ns, args.iface, new_target, new_limit)
                adj_count += 1
                aw.writerow([round(elapsed,2), round(avg_q,1),
                             round(old_max_p,4), round(max_p,4),
                             cur_target, new_target,
                             cur_limit,  new_limit, reason])
                af.flush()
                cur_target = new_target
                cur_limit  = new_limit

            mw.writerow([round(elapsed,2), round(avg_q,1), round(dr,1),
                         bl, round(tput,3), round(max_p,4),
                         cur_target, cur_limit])
            mf.flush()

            print(f"{elapsed:>6.1f}  {avg_q:>7.1f}  {dr:>9.1f}  "
                  f"{bl:>6}  {tput:>6.2f}  "
                  f"{max_p:>6.3f}  {cur_target:>5.1f}ms  "
                  f"{cur_limit:>5}  {adj_count:>4}", flush=True)
            prev = cur

    print("\n" + "=" * 72)
    print(f"  Done — {adj_count} adjustments in {args.duration}s")
    print(f"  Metrics : {mfile}")
    print(f"  Adj log : {afile}")
    print()
    print("  Now run: python3 scripts/plot_comparison.py --logdir logs/")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Adaptive RED controller")
    p.add_argument("--ns",       default="ns1")
    p.add_argument("--iface",    default="veth1")
    p.add_argument("--logdir",   default="../logs")
    p.add_argument("--duration", type=int, default=120)
    args = p.parse_args()
    if os.geteuid() != 0:
        sys.exit("Run as root: sudo python3 adaptive_red.py")
    run(args)
