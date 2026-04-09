#!/usr/bin/env python3
"""
record_metrics.py — Records live tc stats to CSV every second.
Run this in background during any experiment phase.
Saves: logs/{label}_recorded.csv

Usage:
  sudo python3 scripts/record_metrics.py \
    --ns ns_router --iface veth_rs \
    --label acape --duration 600
"""

import subprocess, re, time, argparse, os, sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LOGS = REPO / "logs"

def sh(cmd, ns=None):
    if ns: cmd = ["ip","netns","exec",ns] + cmd
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
        return r.stdout + r.stderr
    except: return ""

def read_tick(ns, iface, prev):
    out = sh(["tc","-s","qdisc","show","dev",iface], ns=ns)
    now = time.time()
    dt  = max(now - prev["t"], 0.1)
    prev["t"] = now

    bl_m  = re.search(r"backlog (\d+)b (\d+)p", out)
    tgt_m = re.search(r"target (\d+)(us|ms)", out)
    lim_m = re.search(r"limit (\d+)p", out)
    q_m   = re.search(r"quantum (\d+)", out)
    snt_m = re.search(r"Sent (\d+) bytes", out)
    drp_m = re.search(r"dropped (\d+)", out)

    bl_bytes = int(bl_m.group(1)) if bl_m else 0
    bl_pkts  = int(bl_m.group(2)) if bl_m else 0

    if tgt_m:
        v,u = int(tgt_m.group(1)), tgt_m.group(2)
        tgt = round(v/1000.0,3) if u=="us" else float(v)
    else:
        tgt = prev.get("tgt", 5.0)
    prev["tgt"] = tgt

    lim = int(lim_m.group(1)) if lim_m else prev.get("lim",1024)
    prev["lim"] = lim
    q   = int(q_m.group(1))   if q_m   else prev.get("q",1514)
    prev["q"]   = q

    sent  = int(snt_m.group(1)) if snt_m else 0
    drops = int(drp_m.group(1)) if drp_m else 0

    delta_bytes  = max(sent  - prev.get("sent",0),  0); prev["sent"]  = sent
    delta_drops  = max(drops - prev.get("drops",0), 0); prev["drops"] = drops

    tput_mbps  = round(delta_bytes * 8 / 1e6 / dt, 3)
    drop_rate  = round(delta_drops / dt, 1)

    # Sojourn estimate (Little's law)
    pps = tput_mbps * 1e6 / (1400 * 8) if tput_mbps > 0.01 else 1.0
    sojourn_ms = round(bl_pkts / pps * 1000, 2) if pps > 0 else 0.0

    return {
        "t_s":           round(now - prev.get("t0", now), 1),
        "backlog_pkts":  bl_pkts,
        "backlog_bytes": bl_bytes,
        "target_ms":     tgt,
        "limit_pkts":    lim,
        "quantum_bytes": q,
        "drop_rate":     drop_rate,
        "throughput_mbps": tput_mbps,
        "sojourn_ms":    sojourn_ms,
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ns",       default="ns_router")
    ap.add_argument("--iface",    default="veth_rs")
    ap.add_argument("--label",    required=True,
                    help="Name: acape | ared | pie | cake | static_fqcodel")
    ap.add_argument("--duration", type=int, default=600)
    ap.add_argument("--interval", type=float, default=1.0)
    args = ap.parse_args()

    LOGS.mkdir(exist_ok=True)
    out_file = LOGS / (args.label + "_recorded.csv")
    cols = ["t_s","backlog_pkts","backlog_bytes","target_ms",
            "limit_pkts","quantum_bytes","drop_rate",
            "throughput_mbps","sojourn_ms"]

    prev = {"t": time.time(), "t0": time.time(),
            "sent": 0, "drops": 0, "tgt": 5.0, "lim": 1024, "q": 1514}

    print("[recorder] Starting: label="+args.label+" ns="+args.ns+
          " iface="+args.iface+" duration="+str(args.duration)+"s",
          flush=True)
    print("[recorder] Writing to: "+str(out_file), flush=True)

    with open(str(out_file), "w") as f:
        f.write(",".join(cols) + "\n")
        f.flush()
        t0 = time.time()
        tick = 0
        while time.time() - t0 < args.duration:
            try:
                row = read_tick(args.ns, args.iface, prev)
                row["t_s"] = round(time.time() - t0, 1)
                line = ",".join(str(row[c]) for c in cols)
                f.write(line + "\n")
                f.flush()
                if tick % 10 == 0:
                    print("[recorder] t="+str(row["t_s"])+"s"+
                          " bl="+str(row["backlog_pkts"])+"p"+
                          " tgt="+str(row["target_ms"])+"ms"+
                          " tp="+str(row["throughput_mbps"])+"Mbps"+
                          " dr="+str(row["drop_rate"])+"/s",
                          flush=True)
                tick += 1
            except Exception as e:
                print("[recorder] err: "+str(e), flush=True)
            time.sleep(args.interval)

    print("[recorder] Done. Saved "+str(tick)+" rows -> "+str(out_file), flush=True)

if __name__ == "__main__":
    main()
