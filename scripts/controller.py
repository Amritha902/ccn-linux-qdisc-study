#!/usr/bin/env python3
"""
Part 3: Adaptive fq_codel Controller
Amritha S — VIT Chennai 2026

Closed-loop AIMD-based runtime parameter tuning of fq_codel.
Inspired by Adaptive RED (Floyd, Gummadi, Shenker 2001).

Correctness guarantees:
  - drop_rate = instantaneous (delta_drops / delta_t), NOT cumulative ramp
  - drops_experiment zeroed at t=0 (eliminates boot-time counter offset)
  - throughput from byte delta per interval (accurate Mbps)
  - state must be stable for STABLE_ROUNDS_NEEDED before any adjustment
"""

import subprocess, re, time, csv, os, sys, signal, argparse
from collections import deque
from datetime import datetime

# ── tuneable constants ───────────────────────────────────────

TARGET_MIN_MS   = 1
TARGET_MAX_MS   = 20
INTERVAL_MIN_MS = 50
INTERVAL_MAX_MS = 300
LIMIT_MIN       = 256
LIMIT_MAX       = 2048

# AIMD factors (Adaptive RED Section 4)
BETA         = 0.9    # multiplicative decrease (HEAVY)
ALPHA_TARGET = 0.5    # ms additive increase (LIGHT)
ALPHA_LIMIT  = 64     # pkts additive increase (LIGHT)

# Classification thresholds — drop_rate in pkts/sec, backlog in pkts
DR_LIGHT    = 1
DR_MODERATE = 10
DR_HEAVY    = 30
BL_LIGHT    = 20
BL_MODERATE = 100
BL_HEAVY    = 300

MONITOR_INTERVAL_S   = 0.5
STABLE_ROUNDS_NEEDED = 3
ADJUST_EVERY_N_TICKS = 10   # adjust at most every ~5 s


# ── tc helpers ───────────────────────────────────────────────

def _run(cmd):
    try:
        return subprocess.check_output(cmd, stderr=subprocess.DEVNULL,
                                       text=True, timeout=2)
    except Exception:
        return ""


def tc_stats(ns, iface):
    """Read raw tc -s qdisc counters. Returns absolute cumulative values."""
    out = _run(["ip", "netns", "exec", ns,
                "tc", "-s", "qdisc", "show", "dev", iface])
    if not out:
        return None

    d = {"ts": time.time()}

    m = re.search(r"Sent (\d+) bytes (\d+) pkt", out)
    if m:
        d["bytes"]   = int(m.group(1))
        d["packets"] = int(m.group(2))
    else:
        d["bytes"] = d["packets"] = 0

    m = re.search(r"dropped (\d+)", out)
    d["drops_abs"] = int(m.group(1)) if m else 0

    m = re.search(r"overlimits (\d+)", out)
    d["overlimits"] = int(m.group(1)) if m else 0

    # "backlog Xb Yp" — Y is packet count
    m = re.search(r"backlog \d+b (\d+)p", out)
    d["backlog"] = int(m.group(1)) if m else 0

    return d


def get_params(ns, iface):
    """Read current fq_codel target / interval / limit from tc."""
    out = _run(["ip", "netns", "exec", ns,
                "tc", "qdisc", "show", "dev", iface])
    p = {"target": 5.0, "interval": 100.0, "limit": 1024}
    if not out:
        return p
    m = re.search(r"target (\d+)ms",   out)
    if m: p["target"]   = float(m.group(1))
    m = re.search(r"interval (\d+)ms", out)
    if m: p["interval"] = float(m.group(1))
    m = re.search(r"limit (\d+)p?",    out)
    if m: p["limit"]    = int(m.group(1))
    return p


def apply_params(ns, iface, target, interval, limit, dry=False):
    """Apply fq_codel params at runtime — zero traffic interruption."""
    cmd = [
        "ip", "netns", "exec", ns,
        "tc", "qdisc", "change", "dev", iface,
        "parent", "1:1", "handle", "10:", "fq_codel",
        "target",   f"{int(round(target))}ms",
        "interval", f"{int(round(interval))}ms",
        "limit",    f"{int(limit)}",
    ]
    if dry:
        print(f"  [DRY] {' '.join(cmd)}")
        return True
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=3)
        return True
    except subprocess.CalledProcessError as e:
        print(f"  [ERR] tc change failed: {e.stderr.decode().strip()}", flush=True)
        return False


# ── classification ───────────────────────────────────────────

def classify(drop_rate_per_s, backlog_pkts):
    if drop_rate_per_s > DR_HEAVY or backlog_pkts > BL_HEAVY:
        return "HEAVY"
    if drop_rate_per_s > DR_MODERATE or backlog_pkts > BL_MODERATE:
        return "MODERATE"
    if drop_rate_per_s > DR_LIGHT or backlog_pkts > BL_LIGHT:
        return "LIGHT"
    return "NORMAL"


# ── AIMD adjustment ──────────────────────────────────────────

def _clamp(p):
    p["target"]   = max(TARGET_MIN_MS,   min(TARGET_MAX_MS,   p["target"]))
    p["interval"] = max(INTERVAL_MIN_MS, min(INTERVAL_MAX_MS, p["interval"]))
    p["limit"]    = max(LIMIT_MIN,       min(LIMIT_MAX,       int(p["limit"])))
    if p["interval"] <= p["target"]:   # CoDel: interval must exceed target
        p["interval"] = p["target"] * 10
    return p


def aimd_adjust(state, params):
    """
    AIMD policy — mirrors Adaptive RED (Floyd et al. 2001):
      HEAVY    → multiplicative decrease β=0.9   (fast response)
      MODERATE → slow additive decrease          (fine-grained)
      LIGHT    → additive increase α             (gentle recovery)
      NORMAL   → no change                       (stability)
    """
    p = dict(params)

    if state == "HEAVY":
        p["target"]   *= BETA
        p["interval"] *= BETA
        p["limit"]    *= BETA
        reason = f"mult-decrease β={BETA}"

    elif state == "MODERATE":
        p["target"] -= 0.2
        p["limit"]  -= 32
        reason = "additive-decrease (slow)"

    elif state == "LIGHT":
        p["target"]   += ALPHA_TARGET
        p["interval"] += 5.0
        p["limit"]    += ALPHA_LIMIT
        reason = f"additive-increase α={ALPHA_TARGET}ms"

    else:
        return params, "stable — no change"

    return _clamp(p), reason


# ── main loop ────────────────────────────────────────────────

def run(args):
    os.makedirs(args.logdir, exist_ok=True)
    ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")

    metrics_path = os.path.join(args.logdir, f"metrics_{ts_str}.csv")
    adj_path     = os.path.join(args.logdir, f"adjustments_{ts_str}.csv")

    mf = open(metrics_path, "w", newline="")
    af = open(adj_path,     "w", newline="")
    mw = csv.writer(mf)
    aw = csv.writer(af)

    mw.writerow([
        "t_s",
        "drop_rate_per_s",   # INSTANTANEOUS: Δdrops / Δt  ← correct
        "drops_experiment",  # zeroed at t=0  ← no boot offset
        "backlog_pkts",
        "throughput_mbps",   # from byte Δ per interval
        "state",
        "target_ms",
        "interval_ms",
        "limit_pkts",
    ])
    aw.writerow([
        "t_s", "state",
        "old_target_ms", "new_target_ms",
        "old_interval_ms", "new_interval_ms",
        "old_limit_pkts", "new_limit_pkts",
        "reason",
    ])
    mf.flush(); af.flush()

    params    = get_params(args.ns, args.iface)
    state_buf = deque(maxlen=6)
    stable_cnt = adj_count = tick = 0
    t0 = time.time()

    # ── Zero the drop counter at experiment start ──────────────
    # tc dropped counter is cumulative from boot — subtract baseline
    # so all logged values are experiment-relative (start at 0)
    first = tc_stats(args.ns, args.iface)
    if first is None:
        sys.exit("[ERR] Cannot read tc stats — is the namespace running?")
    drops_baseline = first["drops_abs"]
    print(f"\n  Drop counter zeroed at baseline = {drops_baseline}")

    prev = first

    # ── header ────────────────────────────────────────────────
    print(f"\n  Controller running: ns={args.ns}  iface={args.iface}  dry={args.dry}")
    print(f"  metrics  → {metrics_path}")
    print(f"  adj log  → {adj_path}\n")
    HDR = f"{'t(s)':>7}  {'state':>10}  {'dr/s':>8}  {'backlog':>7}  {'Mbps':>6}  {'target':>7}  {'limit':>6}  {'#adj':>4}"
    print(HDR)
    print("─" * len(HDR))

    def shutdown(sig=None, frame=None):
        mf.close(); af.close()
        print(f"\n  Finished: {tick} ticks, {adj_count} adjustments.")
        print(f"  Run:  python3 plot_part3.py")
        sys.exit(0)

    signal.signal(signal.SIGINT,  shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    while True:
        time.sleep(args.interval)
        tick += 1

        now = tc_stats(args.ns, args.iface)
        if now is None:
            continue

        elapsed = now["ts"] - t0
        dt      = max(now["ts"] - prev["ts"], 1e-6)

        # ── Experiment-relative drops (zero-based) ──────────────
        drops_exp = now["drops_abs"] - drops_baseline

        # ── Instantaneous drop rate ─────────────────────────────
        delta_drops = max(0, now["drops_abs"] - prev["drops_abs"])
        drop_rate   = delta_drops / dt

        # ── Throughput from byte delta ──────────────────────────
        delta_bytes = max(0, now.get("bytes", 0) - prev.get("bytes", 0))
        throughput  = (delta_bytes * 8) / (dt * 1e6)

        backlog = now.get("backlog", 0)
        state   = classify(drop_rate, backlog)

        # Stability tracking
        state_buf.append(state)
        if len(state_buf) >= STABLE_ROUNDS_NEEDED:
            recent = list(state_buf)[-STABLE_ROUNDS_NEEDED:]
            stable_cnt = stable_cnt + 1 if len(set(recent)) == 1 else 0
        else:
            stable_cnt = 0

        # ── Log every tick ──────────────────────────────────────
        mw.writerow([
            f"{elapsed:.2f}",
            f"{drop_rate:.4f}",
            drops_exp,
            backlog,
            f"{throughput:.4f}",
            state,
            f"{params['target']:.2f}",
            f"{params['interval']:.1f}",
            params["limit"],
        ])
        mf.flush()

        # ── Adjust parameters ───────────────────────────────────
        # Only when: scheduled tick AND state has been stable
        if tick % ADJUST_EVERY_N_TICKS == 0 and stable_cnt >= STABLE_ROUNDS_NEEDED:
            old   = dict(params)
            new_p, reason = aimd_adjust(state, params)

            changed = (
                abs(new_p["target"]   - old["target"])   > 0.05 or
                abs(new_p["interval"] - old["interval"]) > 0.5  or
                abs(new_p["limit"]    - old["limit"])    > 1
            )

            if changed:
                ok = apply_params(
                    args.ns, args.iface,
                    new_p["target"], new_p["interval"], new_p["limit"],
                    args.dry,
                )
                if ok:
                    params = new_p
                    adj_count += 1
                    aw.writerow([
                        f"{elapsed:.2f}", state,
                        f"{old['target']:.2f}",    f"{new_p['target']:.2f}",
                        f"{old['interval']:.1f}",  f"{new_p['interval']:.1f}",
                        int(old["limit"]),          int(new_p["limit"]),
                        reason,
                    ])
                    af.flush()

        # ── Print row ───────────────────────────────────────────
        print(
            f"{elapsed:>7.1f}  {state:>10}  {drop_rate:>8.1f}  "
            f"{backlog:>7d}  {throughput:>6.2f}  "
            f"{params['target']:>6.1f}ms  {params['limit']:>6d}  {adj_count:>4d}",
            flush=True,
        )

        prev = now


# ── entry point ──────────────────────────────────────────────

if __name__ == "__main__":
    p = argparse.ArgumentParser(
        description="Part 3: Adaptive fq_codel controller — Amritha S, VIT Chennai 2026",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--ns",       default="ns1",     help="Network namespace")
    p.add_argument("--iface",    default="veth1",   help="Interface inside ns")
    p.add_argument("--logdir",   default="../logs", help="CSV log directory")
    p.add_argument("--interval", type=float, default=MONITOR_INTERVAL_S,
                   help="Poll interval in seconds")
    p.add_argument("--dry",      action="store_true",
                   help="Classify and log only — do NOT apply tc changes")
    args = p.parse_args()

    if os.geteuid() != 0 and not args.dry:
        print("ERROR: must run as root — sudo python3 controller.py")
        print("       Dry run available: python3 controller.py --dry")
        sys.exit(1)

    run(args)
