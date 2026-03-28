#!/usr/bin/env python3
"""
ACAPE eBPF Live Dashboard
Amritha S — VIT Chennai 2026

Visually shows all 3 eBPF layers running in real time:
  Layer 1: eBPF TC hook status (attached / jited / prog id)
  Layer 2: BPF map contents (flow_map entries live)
  Layer 3: Derived stats (active flows, elephant ratio, RTT proxy)

Run: sudo python3 ebpf_dashboard.py --ns ns1 --iface veth1
Requires: bpftool, iproute2
"""

import subprocess, json, time, os, sys, argparse, struct
from datetime import datetime

# ── ANSI colours ─────────────────────────────────────────────
R="\033[0m"; BOLD="\033[1m"; DIM="\033[2m"
GREEN="\033[92m"; RED="\033[91m"; YELLOW="\033[93m"
CYAN="\033[96m"; MAGENTA="\033[95m"; BLUE="\033[94m"
WHITE="\033[97m"; BG_DARK="\033[48;5;234m"

def clr(text, colour): return f"{colour}{text}{R}"
def box(title, width=72):
    print(f"\n{clr('┌' + '─'*(width-2) + '┐', CYAN)}")
    pad = (width - 2 - len(title)) // 2
    print(f"{clr('│', CYAN)}{' '*pad}{clr(BOLD+title+R, WHITE)}{' '*(width-2-pad-len(title))}{clr('│', CYAN)}")
    print(f"{clr('└' + '─'*(width-2) + '┘', CYAN)}")

def run(cmd):
    try: return subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True, timeout=3)
    except: return ""

def rns(ns, cmd):
    try: return subprocess.check_output(["ip","netns","exec",ns]+cmd,
                                         stderr=subprocess.DEVNULL, text=True, timeout=3)
    except: return ""

def bpftool(*args):
    out = run(["bpftool"]+list(args))
    if not out: out = run(["/usr/sbin/bpftool"]+list(args))
    return out

def clear(): print("\033[2J\033[H", end="")

# ── Layer 1: TC hook status ───────────────────────────────────
def get_layer1(ns, iface):
    out = rns(ns, ["tc","filter","show","dev",iface,"egress"])
    if not out or "bpf" not in out:
        return None, None
    prog_id = None
    jited   = False
    tag     = ""
    for line in out.splitlines():
        if "id" in line:
            import re
            m = re.search(r'\bid (\d+)\b', line)
            if m: prog_id = int(m.group(1))
        if "jited" in line: jited = True
        if "tag" in line:
            import re
            m = re.search(r'tag ([0-9a-f]+)', line)
            if m: tag = m.group(1)
    return prog_id, {"jited": jited, "tag": tag, "raw": out.strip()}

# ── Layer 2: Map IDs from prog ────────────────────────────────
def get_map_ids(prog_id):
    if prog_id is None: return {}
    out = bpftool("prog","show","id",str(prog_id),"--json")
    if not out: return {}
    try:
        d = json.loads(out)
        maps = {}
        for mid in d.get("map_ids", []):
            mout = bpftool("map","show","id",str(mid),"--json")
            try:
                md = json.loads(mout)
                name = md.get("name","")
                maps[name] = mid
            except: pass
        return maps
    except: return {}

# ── Layer 3: Flow map data ────────────────────────────────────
def read_flow_map(map_id):
    if map_id is None: return []
    out = bpftool("map","dump","id",str(map_id),"--json")
    if not out or out.strip() in ("[]",""): return []
    try:
        entries = json.loads(out)
    except: return []
    now_ns = time.time_ns()
    flows = []
    for entry in entries:
        raw = entry.get("value", [])
        parsed = None
        if isinstance(raw, dict):
            parsed = {
                "packets":  int(raw.get("packets",  raw.get("pkts", 0))),
                "bytes":    int(raw.get("bytes",    0)),
                "last_ns":  int(raw.get("last_ns",  raw.get("last_seen_ns", 0))),
                "gap_ns":   int(raw.get("gap_ns",   raw.get("interpacket_gap_ns", 0))),
                "elephant": int(raw.get("elephant", raw.get("is_elephant", 0))),
            }
        elif isinstance(raw, list) and len(raw) >= 36:
            try:
                b = bytes(int(x,16) if isinstance(x,str) else x for x in raw)
                pkts,bts,last_ns,gap_ns,elephant = struct.unpack_from('<QQQQi',b)
                parsed = {"packets":pkts,"bytes":bts,"last_ns":last_ns,
                          "gap_ns":gap_ns,"elephant":elephant}
            except: pass
        if parsed and parsed["packets"] > 0:
            age = (now_ns - parsed["last_ns"]) / 1e9 if parsed["last_ns"] > 0 else 999
            parsed["age_s"] = round(age, 2)
            parsed["active"] = age < 2.0
            parsed["rtt_ms"] = round(parsed["gap_ns"] / 1e6, 3)
            parsed["bytes_mb"] = round(parsed["bytes"] / 1e6, 3)
            flows.append(parsed)
    return flows

def read_global_map(map_id):
    if map_id is None: return {}
    out = bpftool("map","dump","id",str(map_id),"--json")
    if not out: return {}
    try:
        entries = json.loads(out)
        if entries:
            raw = entries[0].get("value", {})
            if isinstance(raw, dict):
                return {"packets": int(raw.get("packets", raw.get("total_packets",0))),
                        "bytes":   int(raw.get("bytes",   raw.get("total_bytes",0)))}
    except: pass
    return {}

def read_hist(map_id):
    if map_id is None: return [0,0,0,0]
    out = bpftool("map","dump","id",str(map_id),"--json")
    if not out: return [0,0,0,0]
    try:
        entries = json.loads(out)
        hist = [0,0,0,0]
        for e in entries:
            k = e.get("key")
            v = e.get("value")
            try:
                idx = int(k) if not isinstance(k,list) else int(k[0])
                val = int(v) if not isinstance(v,list) else int(v[0])
                if 0 <= idx < 4: hist[idx] = val
            except: pass
        return hist
    except: return [0,0,0,0]

def bar(val, total, width=30, colour=GREEN):
    if total == 0: return "[" + " "*width + "]"
    filled = int((val / total) * width)
    return "[" + clr("█"*filled, colour) + " "*(width-filled) + "]"

# ── Main display loop ─────────────────────────────────────────
def display(args):
    tick = 0
    while True:
        tick += 1
        clear()

        now = datetime.now().strftime("%H:%M:%S")
        print(f"\n{clr(BOLD+'ACAPE eBPF Live Dashboard'+R, WHITE)}  "
              f"{clr(now, DIM)}  "
              f"{clr(f'tick={tick}  refresh=2s', DIM)}")
        print(clr("═"*72, CYAN))

        # ── LAYER 1 ───────────────────────────────────────────
        prog_id, l1 = get_layer1(args.ns, args.iface)
        print(f"\n{clr(BOLD+'[ LAYER 1 ]  eBPF TC Hook', CYAN)}")
        print(f"  {'namespace':12} {clr(args.ns, GREEN)}")
        print(f"  {'interface':12} {clr(args.iface, GREEN)}")

        if prog_id:
            print(f"  {'status':12} {clr('✅ ATTACHED', GREEN)}")
            print(f"  {'prog id':12} {clr(str(prog_id), YELLOW)}")
            print(f"  {'jited':12} {clr('YES (JIT compiled for speed)', GREEN) if l1.get('jited') else clr('no', RED)}")
            if l1.get("tag"):
                print(f"  {'tag':12} {clr(l1['tag'], DIM)}")
        else:
            print(f"  {'status':12} {clr('❌ NOT ATTACHED', RED)}")
            print(f"  {clr('Run: cd ebpf && make && make attach', YELLOW)}")

        # ── LAYER 2 ───────────────────────────────────────────
        print(f"\n{clr(BOLD+'[ LAYER 2 ]  BPF Maps', CYAN)}")
        map_ids = get_map_ids(prog_id) if prog_id else {}

        flow_map_id   = None
        global_map_id = None
        hist_map_id   = None

        for name, mid in map_ids.items():
            icon = "✅"
            if "flow" in name:   flow_map_id   = mid
            if "global" in name: global_map_id = mid
            if "hist" in name or "size" in name: hist_map_id = mid
            print(f"  {icon} {clr(name, YELLOW):30} id={clr(str(mid), GREEN)}")

        if not map_ids:
            print(f"  {clr('⚠️  No maps found — bpftool may need prog id', YELLOW)}")
            print(f"  {clr('Try: bpftool prog show id '+str(prog_id)+' --json', DIM)}")

        # ── LAYER 3 ───────────────────────────────────────────
        print(f"\n{clr(BOLD+'[ LAYER 3 ]  Live Telemetry', CYAN)}")

        flows   = read_flow_map(flow_map_id)
        gstats  = read_global_map(global_map_id)
        hist    = read_hist(hist_map_id)

        active   = [f for f in flows if f.get("active")]
        elephant = [f for f in active if f["elephant"]]
        mice     = [f for f in active if not f["elephant"]]
        ratio    = len(elephant)/max(len(active),1)
        avg_rtt  = sum(f["rtt_ms"] for f in active)/max(len(active),1) if active else 0

        print(f"  {'active flows':20} {clr(str(len(active)), GREEN if active else RED)}")
        print(f"  {'elephant flows':20} {clr(str(len(elephant)), MAGENTA)}")
        print(f"  {'mice flows':20} {clr(str(len(mice)), BLUE)}")
        print(f"  {'elephant ratio':20} {clr(f'{ratio:.3f}', YELLOW)}")
        print(f"  {'avg RTT proxy':20} {clr(f'{avg_rtt:.3f} ms', CYAN)}")

        if gstats:
            tp = gstats.get("bytes",0)
            print(f"  {'total packets':20} {clr(f\"{gstats.get('packets',0):,}\", WHITE)}")
            print(f"  {'total bytes':20} {clr(f\"{tp/1e6:.1f} MB\", WHITE)}")

        # Workload profile bar
        print(f"\n  Workload Profile:")
        if ratio < 0.2:
            wkld = clr("MICE    (target=2ms, quantum=300B)", BLUE)
        elif ratio > 0.6:
            wkld = clr("ELEPHANT (target=10ms, quantum=3000B)", MAGENTA)
        else:
            wkld = clr("MIXED   (target=5ms, quantum=1514B)", CYAN)
        print(f"  → {wkld}")

        # Packet size histogram
        if any(h > 0 for h in hist):
            total_pkts = max(sum(hist), 1)
            labels = ["<128B  ","128-512B","512-1500B",">1500B "]
            colours = [BLUE, GREEN, YELLOW, MAGENTA]
            print(f"\n  Packet Size Distribution:")
            for i,(label,count,c) in enumerate(zip(labels,hist,colours)):
                pct = count/total_pkts*100
                b = bar(count, total_pkts, 24, c)
                print(f"  {label} {b} {clr(f'{count:>8,}', c)} ({pct:4.1f}%)")

        # Active flow table
        if active:
            print(f"\n  Active Flows (last 2s):")
            print(f"  {clr('  pkts      bytes     RTT proxy   type', DIM)}")
            print(f"  {clr('  ────────  ────────  ──────────  ────', DIM)}")
            for f in sorted(active, key=lambda x: x["bytes"], reverse=True)[:8]:
                ftype = clr("ELEPHANT🐘", MAGENTA) if f["elephant"] else clr("mice    ", BLUE)
                print(f"  {f['packets']:>8,}  {f['bytes_mb']:>6.2f}MB"
                      f"  {f['rtt_ms']:>7.3f}ms  {ftype}")
        else:
            print(f"\n  {clr('No active flows in map', YELLOW)}")
            if not prog_id:
                print(f"  {clr('→ Attach eBPF first', RED)}")
            else:
                print(f"  {clr('→ Start iperf3 traffic to see flows', YELLOW)}")

        # Current fq_codel params
        print(f"\n{clr(BOLD+'[ fq_codel CURRENT PARAMETERS ]', CYAN)}")
        qout = rns(args.ns, ["tc","qdisc","show","dev",args.iface])
        if qout and "fq_codel" in qout:
            import re
            params = {}
            for k,pat in [("target",r"target (\S+)"),("interval",r"interval (\S+)"),
                          ("limit",r"limit (\S+)"),("quantum",r"quantum (\S+)")]:
                m = re.search(pat, qout)
                if m: params[k] = m.group(1)
            for k,v in params.items():
                print(f"  {k:12} {clr(v, GREEN)}")
        else:
            print(f"  {clr('fq_codel not found on '+args.iface, RED)}")

        print(f"\n{clr('─'*72, DIM)}")
        print(f"  {clr('Ctrl+C to quit  │  Updates every 2s  │  ACAPE eBPF Dashboard', DIM)}")
        time.sleep(2)

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="ACAPE eBPF Live Dashboard")
    p.add_argument("--ns",    default="ns1")
    p.add_argument("--iface", default="veth1")
    args = p.parse_args()
    if os.geteuid() != 0:
        sys.exit("Run as root: sudo python3 ebpf_dashboard.py")
    try:
        display(args)
    except KeyboardInterrupt:
        print(f"\n{clr('Dashboard stopped.', YELLOW)}")
