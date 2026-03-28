#!/usr/bin/env python3
"""
ACAPE: Adaptive Condition-Aware Packet Engine
Amritha S — VIT Chennai 2026

eBPF pipeline:
  1. clang compiles tc_monitor.c → tc_monitor.o  (with -g for BTF)
  2. tc attaches BPF prog to veth1 egress inside ns1
  3. bpftool reads BPF maps from HOST (maps are kernel-global, not ns-scoped)

Key insight: BPF programs and maps are kernel-global objects.
Even if loaded from inside ns1, their IDs are visible from the host.
tc filter show (inside ns1) gives the prog ID.
bpftool prog/map (on host) reads them by ID.

Run:
    sudo python3 acape_complete.py --ns ns1 --iface veth1
"""

import subprocess, re, time, csv, os, sys, signal, argparse, json, struct
from collections import deque
from datetime import datetime

VERSION = "6.0.0"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
EBPF_DIR   = os.path.join(SCRIPT_DIR, "../ebpf")
EBPF_SRC   = os.path.join(EBPF_DIR, "tc_monitor.c")
EBPF_OBJ   = os.path.join(EBPF_DIR, "tc_monitor.o")

# ── Controller constants ──────────────────────────────────────
T_MIN,T_MAX   = 1, 20
I_MIN,I_MAX   = 50, 300
L_MIN,L_MAX   = 256, 4096
BETA          = 0.9
ALPHA_T       = 0.5
ALPHA_L       = 64
DR_LIGHT,DR_MOD,DR_HEAVY = 1, 10, 30
BL_LIGHT,BL_MOD,BL_HEAVY = 20, 100, 300
GRAD_WINDOW   = 10
STABLE_ROUNDS = 5
T2_INTERVAL   = 0.5   # seconds between tc polls
T3_EVERY_N    = 10    # adjust every N * T2_INTERVAL seconds
EBPF_EVERY_N  = 4     # read eBPF maps every N ticks (every 2s)

WORKLOAD_Q = {"MICE": 300, "MIXED": 1514, "ELEPHANT": 3000}


# ═══════════════════════════════════════════════════════════════
# eBPF Layer: compile → attach → read via bpftool
# ═══════════════════════════════════════════════════════════════

class EBPFPipeline:
    def __init__(self, ns, iface):
        self.ns      = ns
        self.iface   = iface
        self.prog_id = None
        self.flow_map_id   = None
        self.global_map_id = None
        self.active  = False
        self._setup()

    # ── shell helpers ──────────────────────────────────────────
    def _run(self, cmd, timeout=5):
        """Run on HOST."""
        try:
            return subprocess.check_output(
                cmd, stderr=subprocess.DEVNULL, text=True, timeout=timeout)
        except:
            return ""

    def _rns(self, cmd, timeout=5):
        """Run inside namespace."""
        try:
            return subprocess.check_output(
                ["ip","netns","exec",self.ns] + cmd,
                stderr=subprocess.DEVNULL, text=True, timeout=timeout)
        except:
            return ""

    def _runp(self, cmd, timeout=5):
        """Run on host, return (returncode, stderr)."""
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            return r.returncode, r.stderr
        except Exception as e:
            return -1, str(e)

    # ── Step 1: Compile ────────────────────────────────────────
    def _compile(self):
        if not os.path.exists(EBPF_SRC):
            print(f"[eBPF] ❌ Source not found: {EBPF_SRC}")
            return False
        if (os.path.exists(EBPF_OBJ) and
                os.path.getmtime(EBPF_OBJ) > os.path.getmtime(EBPF_SRC)):
            print(f"[eBPF] Layer 1: ✅ Using cached {EBPF_OBJ}")
            return True

        print("[eBPF] Layer 1: Compiling tc_monitor.c...")
        arch = os.uname().machine
        r = subprocess.run([
            "clang", "-O2", "-g", "-target", "bpf", "-Wall",
            "-Wno-unused-value", "-Wno-pointer-sign",
            "-Wno-compare-distinct-pointer-types",
            f"-I/usr/include/{arch}-linux-gnu",
            "-c", EBPF_SRC, "-o", EBPF_OBJ
        ], capture_output=True, text=True)
        if r.returncode != 0:
            print(f"[eBPF] ❌ Compile failed:\n{r.stderr[:300]}")
            return False
        print("[eBPF] Layer 1: ✅ Compiled with BTF (-g)")
        return True

    # ── Step 2: Attach via tc inside ns ───────────────────────
    def _attach(self):
        print(f"[eBPF] Layer 2: Attaching to {self.ns}/{self.iface} egress...")

        # Clean up first
        self._rns(["tc","filter","del","dev",self.iface,"egress"])
        self._rns(["tc","qdisc","del","dev",self.iface,"clsact"])
        time.sleep(0.2)

        # Add clsact
        rc, err = self._runp(["ip","netns","exec",self.ns,
                               "tc","qdisc","add","dev",self.iface,"clsact"])
        if rc != 0 and "already" not in err:
            print(f"[eBPF]   clsact: {err.strip()}")

        # Attach BPF prog
        rc, err = self._runp(["ip","netns","exec",self.ns,
                               "tc","filter","add","dev",self.iface,"egress",
                               "bpf","direct-action","obj",EBPF_OBJ,"sec","tc_egress"])
        if rc != 0:
            print(f"[eBPF] ❌ Attach failed: {err.strip()}")
            return False

        # Verify and get prog ID
        time.sleep(0.3)
        out = self._rns(["tc","filter","show","dev",self.iface,"egress"])
        m = re.search(r'\bid (\d+)\b', out)
        if not m:
            print(f"[eBPF] ❌ Cannot find prog ID in: {out[:200]}")
            return False

        self.prog_id = int(m.group(1))
        print(f"[eBPF] Layer 2: ✅ Attached  (prog id={self.prog_id})")
        return True

    # ── Step 3: Find map IDs via bpftool on HOST ──────────────
    def _find_maps(self):
        """
        BPF maps are kernel-global.
        Even though the prog was loaded from inside ns1,
        bpftool on the HOST can see it by prog_id.
        """
        if self.prog_id is None:
            return False

        print(f"[eBPF] Layer 3: Finding maps for prog id={self.prog_id}...")

        # Get map IDs from prog
        out = self._run(["bpftool","prog","show","id",
                         str(self.prog_id),"--json"])
        if not out:
            # Try with full path
            out = self._run(["/usr/sbin/bpftool","prog","show","id",
                              str(self.prog_id),"--json"])
        if not out:
            print("[eBPF] ❌ bpftool not found. Install with:")
            print("       sudo apt install linux-tools-$(uname -r) bpftool")
            return False

        try:
            pdata   = json.loads(out)
            map_ids = pdata.get("map_ids", [])
        except json.JSONDecodeError:
            print(f"[eBPF] ❌ bpftool JSON parse failed: {out[:100]}")
            return False

        if not map_ids:
            print("[eBPF] ❌ No map IDs found for prog")
            return False

        # Identify maps by name
        for mid in map_ids:
            mout = self._run(["bpftool","map","show","id",str(mid),"--json"])
            if not mout:
                mout = self._run(["/usr/sbin/bpftool","map","show",
                                   "id",str(mid),"--json"])
            try:
                mdata = json.loads(mout)
                name  = mdata.get("name","")
                if "flow_map" in name:
                    self.flow_map_id = mid
                    print(f"[eBPF] Layer 3: ✅ flow_map   id={mid}")
                elif "global_map" in name:
                    self.global_map_id = mid
                    print(f"[eBPF] Layer 3: ✅ global_map id={mid}")
            except:
                pass

        return self.flow_map_id is not None

    def _setup(self):
        if not self._compile():
            return
        if not self._attach():
            return
        if not self._find_maps():
            print("[eBPF] ⚠️  Map lookup failed — tc-only mode")
            self.active = True  # attach succeeded, just no map reads
            return
        self.active = True
        print("[eBPF] ✅ All 3 layers active")
        print(f"         Layer 1 (clang) : tc_monitor.o compiled with BTF")
        print(f"         Layer 2 (tc)    : prog attached to {self.ns}/{self.iface}")
        print(f"         Layer 3 (bpftool): flow_map id={self.flow_map_id}")

    # ── Map read ───────────────────────────────────────────────
    def _bpftool_dump(self, map_id):
        out = self._run(["bpftool","map","dump","id",str(map_id),"--json"],
                        timeout=3)
        if not out:
            out = self._run(["/usr/sbin/bpftool","map","dump","id",
                              str(map_id),"--json"], timeout=3)
        return out

    def _parse_val_bytes(self, raw):
        """
        Parse value from bpftool JSON.
        With BTF (-g): raw is a dict with field names.
        Without BTF:   raw is a list of hex strings ["0x01","0x02",...].
        """
        if isinstance(raw, dict):
            # BTF formatted — field names available
            return {
                "packets":  int(raw.get("packets", 0)),
                "bytes":    int(raw.get("bytes", 0)),
                "last_ns":  int(raw.get("last_ns", 0)),
                "gap_ns":   int(raw.get("gap_ns", 0)),
                "elephant": int(raw.get("elephant", 0)),
            }
        elif isinstance(raw, list) and len(raw) >= 36:
            # Raw bytes — parse by struct layout
            # struct flow_val: packets(8) bytes(8) last_ns(8) gap_ns(8) elephant(4) _pad(4)
            try:
                b = bytes(int(x,16) if isinstance(x,str) else x for x in raw)
                pkts, bts, last_ns, gap_ns, elephant = struct.unpack_from('<QQQQi', b)
                return {
                    "packets":  pkts,
                    "bytes":    bts,
                    "last_ns":  last_ns,
                    "gap_ns":   gap_ns,
                    "elephant": elephant,
                }
            except:
                return None
        return None

    def read_flows(self):
        """Read flow_map and compute active/elephant/mice/rtt stats."""
        empty = {"active":0,"elephant":0,"mice":0,"rtt_ms":0.0,"ratio":0.0}
        if not self.active or self.flow_map_id is None:
            return empty

        out = self._bpftool_dump(self.flow_map_id)
        if not out or out.strip() in ("[]", ""):
            return empty

        try:
            entries = json.loads(out)
        except:
            return empty

        now_ns = time.time_ns()
        active = elephant = mice = 0
        total_gap = 0

        for entry in entries:
            # bpftool with BTF: {"key":{...},"value":{...},"formatted":{...}}
            # bpftool without BTF: {"key":[...],"value":[...]}
            val_raw = entry.get("formatted", {}).get("value") or \
                      entry.get("value")
            if val_raw is None:
                continue

            parsed = self._parse_val_bytes(val_raw)
            if parsed is None:
                continue

            age_s = (now_ns - parsed["last_ns"]) / 1e9
            if age_s < 2.0 and parsed["packets"] > 0:
                active += 1
                total_gap += parsed["gap_ns"]
                if parsed["elephant"]: elephant += 1
                else:                  mice += 1

        if active == 0:
            return empty

        rtt_ms = (total_gap / active) / 1e6
        ratio  = elephant / active
        return {
            "active":   active,
            "elephant": elephant,
            "mice":     mice,
            "rtt_ms":   round(rtt_ms, 3),
            "ratio":    round(ratio, 3),
        }

    def detach(self):
        self._rns(["tc","filter","del","dev",self.iface,"egress"])
        self._rns(["tc","qdisc","del","dev",self.iface,"clsact"])
        print(f"[eBPF] Detached from {self.ns}/{self.iface}")


# ═══════════════════════════════════════════════════════════════
# tc helpers
# ═══════════════════════════════════════════════════════════════

def _r(cmd):
    try:
        return subprocess.check_output(
            cmd, stderr=subprocess.DEVNULL, text=True, timeout=2)
    except:
        return ""

def read_tc(ns, iface):
    out = _r(["ip","netns","exec",ns,"tc","-s","qdisc","show","dev",iface])
    if not out: return None
    d = {"ts": time.time()}
    m = re.search(r"Sent (\d+) bytes", out);   d["bytes"]   = int(m.group(1)) if m else 0
    m = re.search(r"dropped (\d+)",    out);   d["drops"]   = int(m.group(1)) if m else 0
    m = re.search(r"backlog \d+b (\d+)p", out); d["backlog"] = int(m.group(1)) if m else 0
    return d

def get_params(ns, iface):
    out = _r(["ip","netns","exec",ns,"tc","qdisc","show","dev",iface])
    p = {"target":5.0,"interval":100.0,"limit":1024,"quantum":1514}
    for k,pat in [("target",  r"target (\d+)ms"),
                  ("interval",r"interval (\d+)ms"),
                  ("limit",   r"limit (\d+)p?"),
                  ("quantum", r"quantum (\d+)")]:
        m = re.search(pat, out)
        if m:
            p[k] = float(m.group(1)) if k in ("target","interval") else int(m.group(1))
    return p

def apply_params(ns, iface, p, dry=False):
    cmd = ["ip","netns","exec",ns,
           "tc","qdisc","change","dev",iface,
           "parent","1:1","handle","10:","fq_codel",
           "target",  f"{int(round(p['target']))}ms",
           "interval",f"{int(round(p['interval']))}ms",
           "limit",   f"{int(p['limit'])}",
           "quantum", f"{int(p['quantum'])}"]
    if dry:
        print(f"  [DRY] {' '.join(cmd)}")
        return True
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=3)
        return True
    except subprocess.CalledProcessError as e:
        print(f"  [ERR] {e.stderr.decode().strip()}")
        return False


# ═══════════════════════════════════════════════════════════════
# Classification & prediction
# ═══════════════════════════════════════════════════════════════

def gradient(history, attr):
    vals = [(s["ts"], s.get(attr, 0)) for s in history]
    if len(vals) < 3: return 0.0
    n  = len(vals); t0 = vals[0][0]
    xs = [v[0]-t0 for v in vals]; ys = [v[1] for v in vals]
    xm = sum(xs)/n; ym = sum(ys)/n
    num = sum((xi-xm)*(yi-ym) for xi,yi in zip(xs,ys))
    den = sum((xi-xm)**2 for xi in xs)
    return num/den if den > 1e-9 else 0.0

def classify(dr, bl):
    if dr > DR_HEAVY or bl > BL_HEAVY:   return "HEAVY"
    if dr > DR_MOD   or bl > BL_MOD:     return "MODERATE"
    if dr > DR_LIGHT or bl > BL_LIGHT:   return "LIGHT"
    return "NORMAL"

REGIMES = ["NORMAL","LIGHT","MODERATE","HEAVY"]

def predict(regime, dr_g, bl_g):
    idx = REGIMES.index(regime)
    c   = 0.6*dr_g/max(DR_HEAVY,1) + 0.4*bl_g/max(BL_HEAVY,1)
    if c >  0.5 and idx < 3: return REGIMES[idx+1], "WORSENING"
    if c < -0.5 and idx > 0: return REGIMES[idx-1], "RECOVERING"
    return regime, "STABLE"

def select_workload(ratio):
    if ratio < 0.2: return "MICE"
    if ratio > 0.6: return "ELEPHANT"
    return "MIXED"

def aimd(regime, traj, pred, params, workload):
    p   = dict(params)
    eff = pred if traj == "WORSENING" else regime
    pfx = "[PREDICTIVE]" if (traj=="WORSENING" and pred!=regime) else "[REACTIVE]"

    if   eff == "HEAVY":
        p["target"]   *= BETA
        p["interval"] *= BETA
        p["limit"]    *= BETA
        r = f"{pfx} mult-decrease β={BETA}"
    elif eff == "MODERATE":
        p["target"] -= 0.2
        p["limit"]  -= 32
        r = f"{pfx} additive-decrease"
    elif eff == "LIGHT":
        p["target"]   += ALPHA_T
        p["interval"] += 5.0
        p["limit"]    += ALPHA_L
        r = f"{pfx} additive-increase α={ALPHA_T}ms"
    else:
        if traj == "RECOVERING":
            p["target"] += 0.2
            p["limit"]  += 16
            r = "gentle-increase (recovering)"
        else:
            return params, "stable"

    p["quantum"]  = WORKLOAD_Q[workload]
    p["target"]   = max(T_MIN, min(T_MAX,   p["target"]))
    p["interval"] = max(I_MIN, min(I_MAX,   p["interval"]))
    p["limit"]    = max(L_MIN, min(L_MAX,   int(p["limit"])))
    if p["interval"] <= p["target"]:
        p["interval"] = p["target"] * 10
    return p, f"{r} | wkld={workload}"


# ═══════════════════════════════════════════════════════════════
# Main loop
# ═══════════════════════════════════════════════════════════════

def run(args):
    os.makedirs(args.logdir, exist_ok=True)
    ts    = datetime.now().strftime("%Y%m%d_%H%M%S")
    mpath = os.path.join(args.logdir, f"acape_metrics_{ts}.csv")
    apath = os.path.join(args.logdir, f"acape_adj_{ts}.csv")
    spath = os.path.join(args.logdir, f"acape_state_{ts}.csv")

    mf = open(mpath,"w",newline="")
    af = open(apath,"w",newline="")
    sf = open(spath,"w",newline="")
    mw = csv.writer(mf); aw = csv.writer(af); sw = csv.writer(sf)

    mw.writerow(["t_s","drop_rate_per_s","drops_exp","backlog_pkts",
                 "throughput_mbps","rtt_proxy_ms",
                 "active_flows","elephant_flows","mice_flows","elephant_ratio",
                 "regime","trajectory","predicted_regime","workload_profile",
                 "target_ms","interval_ms","limit_pkts","quantum_bytes"])
    aw.writerow(["t_s","regime","trajectory","predicted",
                 "old_target","new_target","old_interval","new_interval",
                 "old_limit","new_limit","workload","reason"])
    sw.writerow(["t_s","dr_gradient","bl_gradient","rtt_gradient",
                 "regime","trajectory","predicted","workload"])
    for f in (mf,af,sf): f.flush()

    # ── eBPF setup ─────────────────────────────────────────────
    ebpf    = EBPFPipeline(args.ns, args.iface) if not args.dry else None
    ebpf_on = (ebpf.active and ebpf.flow_map_id is not None) if ebpf else False
    maps_ok = ebpf_on

    # ── Controller state ───────────────────────────────────────
    params  = get_params(args.ns, args.iface)
    history = deque(maxlen=GRAD_WINDOW)
    sbuf    = deque(maxlen=8)
    stable_cnt = adj_count = tick = 0
    t0 = time.time()
    ed = {"active":0,"elephant":0,"mice":0,"rtt_ms":0.0,"ratio":0.0}

    first = read_tc(args.ns, args.iface)
    if not first:
        sys.exit("ERROR: Cannot read tc stats. Is namespace set up?")
    drops_base = first["drops"]
    prev = first

    mode = ("eBPF ACTIVE (clang+tc+bpftool)" if maps_ok else
            ("eBPF attached (no map reads)" if (ebpf and ebpf.active) else
             "tc-only"))

    print(f"\n{'═'*75}")
    print(f"  ACAPE v{VERSION}  |  {mode}")
    print(f"  ns={args.ns}  iface={args.iface}")
    print(f"  metrics    → {mpath}")
    print(f"  adj log    → {apath}")
    print(f"{'═'*75}")
    H = (f"{'t(s)':>7}  {'regime':>10}  {'traj':>11}  {'pred':>10}  "
         f"{'dr/s':>8}  {'bl':>5}  {'flows':>6}  {'eleph':>5}  "
         f"{'rtt':>7}  {'wkld':>8}  {'tgt':>6}  {'lim':>5}  {'adj#':>4}")
    print(H); print("─" * len(H))

    def shutdown(sig=None, f=None):
        if ebpf: ebpf.detach()
        for x in (mf, af, sf): x.close()
        print(f"\n{'═'*60}")
        print(f"  Done — {tick} ticks, {adj_count} adj | {mode}")
        print(f"  Run: python3 plot_acape.py --logdir {args.logdir}")
        print(f"{'═'*60}")
        sys.exit(0)
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    while True:
        time.sleep(T2_INTERVAL)
        tick += 1

        # ── tc stats ──────────────────────────────────────────
        tc = read_tc(args.ns, args.iface)
        if not tc: continue

        elapsed   = tc["ts"] - t0
        dt        = max(tc["ts"] - prev["ts"], 1e-6)
        drops_exp = tc["drops"] - drops_base
        dr        = max(0, tc["drops"] - prev["drops"]) / dt
        tp        = (max(0, tc["bytes"] - prev.get("bytes",0)) * 8) / (dt * 1e6)
        bl        = tc["backlog"]

        # ── eBPF map read (every EBPF_EVERY_N ticks) ─────────
        if maps_ok and tick % EBPF_EVERY_N == 0:
            ed = ebpf.read_flows()

        rtt      = ed["rtt_ms"]
        ratio    = ed["ratio"]
        workload = select_workload(ratio)
        regime   = classify(dr, bl)

        # ── Gradient estimation ───────────────────────────────
        history.append({"ts":elapsed,"drop_rate":dr,
                        "backlog":float(bl),"rtt_proxy_ms":rtt})
        dr_g  = gradient(list(history), "drop_rate")
        bl_g  = gradient(list(history), "backlog")
        rtt_g = gradient(list(history), "rtt_proxy_ms")
        pred, traj = predict(regime, dr_g, bl_g)

        # ── Stability tracking ────────────────────────────────
        sbuf.append(regime)
        stable_cnt = (stable_cnt + 1
                      if len(sbuf) >= STABLE_ROUNDS and
                         len(set(list(sbuf)[-STABLE_ROUNDS:])) == 1
                      else 0)

        # ── Log metrics ───────────────────────────────────────
        mw.writerow([f"{elapsed:.3f}", f"{dr:.4f}", drops_exp, bl,
                     f"{tp:.4f}", f"{rtt:.3f}",
                     ed["active"], ed["elephant"], ed["mice"], f"{ratio:.3f}",
                     regime, traj, pred, workload,
                     f"{params['target']:.2f}", f"{params['interval']:.1f}",
                     params["limit"], params["quantum"]])
        mf.flush()

        if tick % 5 == 0:
            sw.writerow([f"{elapsed:.3f}", f"{dr_g:.4f}", f"{bl_g:.4f}",
                         f"{rtt_g:.4f}", regime, traj, pred, workload])
            sf.flush()

        # ── AIMD adjustment ───────────────────────────────────
        if tick % T3_EVERY_N == 0 and stable_cnt >= STABLE_ROUNDS:
            old    = dict(params)
            new_p, reason = aimd(regime, traj, pred, params, workload)
            changed = (abs(new_p["target"]   - old["target"])   > 0.05 or
                       abs(new_p["interval"] - old["interval"]) > 0.5  or
                       abs(new_p["limit"]    - old["limit"])    > 1)
            if changed:
                ok = apply_params(args.ns, args.iface, new_p, args.dry)
                if ok:
                    params = new_p
                    adj_count += 1
                    aw.writerow([f"{elapsed:.2f}", regime, traj, pred,
                                 f"{old['target']:.2f}",    f"{new_p['target']:.2f}",
                                 f"{old['interval']:.1f}",  f"{new_p['interval']:.1f}",
                                 int(old["limit"]),          int(new_p["limit"]),
                                 workload, reason])
                    af.flush()

        # ── Print row ─────────────────────────────────────────
        print(f"{elapsed:>7.1f}  {regime:>10}  {traj:>11}  {pred:>10}  "
              f"{dr:>8.1f}  {bl:>5d}  {ed['active']:>6d}  {ed['elephant']:>5d}  "
              f"{rtt:>6.2f}ms  {workload:>8}  {params['target']:>5.1f}ms  "
              f"{params['limit']:>5d}  {adj_count:>4d}", flush=True)
        prev = tc


# ═══════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    p = argparse.ArgumentParser(
        description="ACAPE v6 — proper eBPF: clang+tc+bpftool pipeline",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument("--ns",     default="ns1",     help="Network namespace")
    p.add_argument("--iface",  default="veth1",   help="Interface in ns")
    p.add_argument("--logdir", default="../logs",  help="Log directory")
    p.add_argument("--dry",    action="store_true",help="No tc changes")
    args = p.parse_args()
    if os.geteuid() != 0 and not args.dry:
        sys.exit("Run as root: sudo python3 acape_complete.py")
    run(args)
