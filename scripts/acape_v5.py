#!/usr/bin/env python3
"""
ACAPE v5: Adaptive Condition-Aware Packet Engine
Amritha S — VIT Chennai 2026

eBPF pipeline that WORKS on Ubuntu 24 + kernel 6.8:
  1. clang compiles tc_monitor.o (with -g for BTF)
  2. tc attaches to veth1 egress inside ns1
  3. bpftool reads BPF maps → per-flow stats
  4. Python controller uses stats for AIMD decisions

No BCC. No pyroute2. No nsenter. Just standard tools.

Run:
  sudo python3 acape_v5.py --ns ns1 --iface veth1 --logdir ../logs
"""

import subprocess, re, time, csv, os, sys, signal, argparse, json, struct
from collections import deque
from datetime import datetime

VERSION = "5.0.0"

# ── Constants ─────────────────────────────────────────────────
T_MIN,T_MAX   = 1, 20
I_MIN,I_MAX   = 50, 300
L_MIN,L_MAX   = 256, 4096
BETA          = 0.9
ALPHA_T,ALPHA_L = 0.5, 64
DR_LIGHT,DR_MOD,DR_HEAVY = 1, 10, 30
BL_LIGHT,BL_MOD,BL_HEAVY = 20, 100, 300
GRAD_WINDOW   = 10
STABLE_ROUNDS = 5
T2_INTERVAL   = 0.5
T3_EVERY_N    = 10

WORKLOAD_Q = {"MICE":300, "MIXED":1514, "ELEPHANT":3000}

# Path to compiled eBPF object
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
EBPF_OBJ   = os.path.join(SCRIPT_DIR, "../ebpf/tc_monitor.o")
EBPF_SRC   = os.path.join(SCRIPT_DIR, "../ebpf/tc_monitor.c")

# ── eBPF: compile + attach + read ────────────────────────────
class EBPFPipeline:
    """
    Three-layer pipeline:
      Layer 1 (clang):   compiles tc_monitor.c → tc_monitor.o with BTF
      Layer 2 (tc):      attaches BPF prog to veth1 egress inside ns1
      Layer 3 (bpftool): reads flow_map from kernel → userspace stats
    """
    def __init__(self, ns, iface):
        self.ns    = ns
        self.iface = iface
        self.active = False
        self.flow_map_id   = None
        self.global_map_id = None
        self._setup()

    def _rns(self, cmd):
        """Run command inside namespace."""
        try:
            return subprocess.check_output(
                ["ip","netns","exec",self.ns] + cmd,
                stderr=subprocess.DEVNULL, text=True, timeout=3)
        except: return ""

    def _run(self, cmd):
        try:
            return subprocess.check_output(
                cmd, stderr=subprocess.DEVNULL, text=True, timeout=5)
        except: return ""

    def _setup(self):
        # Step 1: Compile if needed
        if not os.path.exists(EBPF_OBJ) or \
           (os.path.exists(EBPF_SRC) and
            os.path.getmtime(EBPF_SRC) > os.path.getmtime(EBPF_OBJ)):
            print("[eBPF] Layer 1: Compiling tc_monitor.c...")
            arch = os.uname().machine
            r = subprocess.run([
                "clang","-O2","-g","-target","bpf","-Wall",
                f"-I/usr/include/{arch}-linux-gnu",
                "-c", EBPF_SRC, "-o", EBPF_OBJ
            ], capture_output=True)
            if r.returncode != 0:
                print(f"[eBPF] ❌ Compile failed:\n{r.stderr.decode()[:200]}")
                return
            print("[eBPF] Layer 1: ✅ Compiled tc_monitor.o")
        else:
            print(f"[eBPF] Layer 1: ✅ Using existing {EBPF_OBJ}")

        # Step 2: Attach via tc inside ns
        print(f"[eBPF] Layer 2: Attaching to {self.ns}/{self.iface}...")
        self._rns(["tc","qdisc","del","dev",self.iface,"clsact"])
        time.sleep(0.1)
        r1 = subprocess.run(
            ["ip","netns","exec",self.ns,"tc","qdisc","add","dev",
             self.iface,"clsact"], capture_output=True)
        r2 = subprocess.run(
            ["ip","netns","exec",self.ns,"tc","filter","add","dev",
             self.iface,"egress","bpf","direct-action",
             "obj",EBPF_OBJ,"sec","tc_egress"], capture_output=True)

        if r2.returncode != 0:
            print(f"[eBPF] ❌ Attach failed: {r2.stderr.decode().strip()}")
            return

        # Verify attachment
        verify = self._rns(["tc","filter","show","dev",self.iface,"egress"])
        if "bpf" in verify:
            print(f"[eBPF] Layer 2: ✅ Attached — {verify.split(chr(10))[1].strip()[:60]}")
        else:
            print("[eBPF] ❌ Verification failed"); return

        # Step 3: Find map IDs via bpftool
        print("[eBPF] Layer 3: Locating BPF maps via bpftool...")
        time.sleep(0.5)
        self._find_maps()

        if self.flow_map_id:
            print(f"[eBPF] Layer 3: ✅ flow_map id={self.flow_map_id}")
            if self.global_map_id:
                print(f"[eBPF] Layer 3: ✅ global_map id={self.global_map_id}")
            self.active = True
        else:
            print("[eBPF] ⚠️  Maps not found — check bpftool installed")
            print("       sudo apt install linux-tools-$(uname -r) bpftool")
            # Still mark active=True since attach succeeded
            self.active = True

    def _find_maps(self):
        """Find BPF map IDs by listing all maps and matching by name."""
        # List all BPF maps
        out = self._run(["bpftool","map","list","--json"])
        if not out:
            # Try with full path
            out = self._run(["/usr/sbin/bpftool","map","list","--json"])
        if not out:
            return

        try:
            maps = json.loads(out)
            for m in maps:
                name = m.get("name","")
                mid  = m.get("id")
                if "flow_map" in name or name.startswith("flow_ma"):
                    self.flow_map_id = mid
                elif "global_ma" in name:
                    self.global_map_id = mid
        except:
            pass

    def _bpftool(self, *args):
        cmd = ["bpftool"] + list(args)
        out = self._run(cmd)
        if not out:
            out = self._run(["/usr/sbin/bpftool"] + list(args))
        return out

    def read_flows(self):
        if not self.active:
            return {"active":0,"elephant":0,"mice":0,"rtt_ms":0.0,"ratio":0.0}

        if self.flow_map_id is None:
            self._find_maps()
        if self.flow_map_id is None:
            return {"active":0,"elephant":0,"mice":0,"rtt_ms":0.0,"ratio":0.0}

        out = self._bpftool("map","dump","id",str(self.flow_map_id),"--json")
        if not out:
            return {"active":0,"elephant":0,"mice":0,"rtt_ms":0.0,"ratio":0.0}

        try:
            entries = json.loads(out)
        except:
            return {"active":0,"elephant":0,"mice":0,"rtt_ms":0.0,"ratio":0.0}

        now_ns = time.time_ns()
        active = elephant = mice = 0
        total_gap = 0

        for entry in entries:
            raw = entry.get("value", [])
            if isinstance(raw, list) and len(raw) >= 36:
                # struct fval layout:
                # pkts(8) bytes(8) last_ns(8) gap_ns(8) elephant(4)
                try:
                    last_ns = struct.unpack_from('<Q', bytes(raw[16:24]))[0]
                    gap_ns  = struct.unpack_from('<Q', bytes(raw[24:32]))[0]
                    pkts    = struct.unpack_from('<Q', bytes(raw[0:8]))[0]
                    is_e    = struct.unpack_from('<I', bytes(raw[32:36]))[0]
                    age     = (now_ns - last_ns) / 1e9
                    if age < 2.0 and pkts > 0:
                        active += 1
                        total_gap += gap_ns
                        if is_e: elephant += 1
                        else: mice += 1
                except: pass
            elif isinstance(raw, dict):
                # Formatted output
                try:
                    last_ns = int(raw.get("last_seen_ns", raw.get("last_ns", 0)))
                    gap_ns  = int(raw.get("interpacket_gap_ns", raw.get("gap_ns", 0)))
                    pkts    = int(raw.get("packets", raw.get("pkts", 0)))
                    is_e    = int(raw.get("is_elephant", raw.get("elephant", 0)))
                    age     = (now_ns - last_ns) / 1e9
                    if age < 2.0 and pkts > 0:
                        active += 1
                        total_gap += gap_ns
                        if is_e: elephant += 1
                        else: mice += 1
                except: pass

        rtt_ms = (total_gap / max(active,1)) / 1e6
        ratio  = elephant / max(active,1)
        return {"active":active,"elephant":elephant,"mice":mice,
                "rtt_ms":round(rtt_ms,3),"ratio":round(ratio,3)}

    def detach(self):
        subprocess.run(
            ["ip","netns","exec",self.ns,"tc","filter","del",
             "dev",self.iface,"egress"], stderr=subprocess.DEVNULL)
        subprocess.run(
            ["ip","netns","exec",self.ns,"tc","qdisc","del",
             "dev",self.iface,"clsact"], stderr=subprocess.DEVNULL)
        print(f"[eBPF] Detached from {self.ns}/{self.iface}")

# ── tc helpers ────────────────────────────────────────────────
def _r(cmd):
    try: return subprocess.check_output(cmd,stderr=subprocess.DEVNULL,text=True,timeout=2)
    except: return ""

def read_tc(ns,iface):
    out=_r(["ip","netns","exec",ns,"tc","-s","qdisc","show","dev",iface])
    if not out: return None
    d={"ts":time.time()}
    m=re.search(r"Sent (\d+) bytes",out); d["bytes"]=int(m.group(1)) if m else 0
    m=re.search(r"dropped (\d+)",out);    d["drops"]=int(m.group(1)) if m else 0
    m=re.search(r"backlog \d+b (\d+)p",out); d["backlog"]=int(m.group(1)) if m else 0
    return d

def get_params(ns,iface):
    out=_r(["ip","netns","exec",ns,"tc","qdisc","show","dev",iface])
    p={"target":5.0,"interval":100.0,"limit":1024,"quantum":1514}
    for k,pat in [("target",r"target (\d+)ms"),("interval",r"interval (\d+)ms"),
                  ("limit",r"limit (\d+)p?"),("quantum",r"quantum (\d+)")]:
        m=re.search(pat,out)
        if m: p[k]=float(m.group(1)) if k in("target","interval") else int(m.group(1))
    return p

def apply_params(ns,iface,p,dry=False):
    cmd=["ip","netns","exec",ns,"tc","qdisc","change","dev",iface,
         "parent","1:1","handle","10:","fq_codel",
         "target",f"{int(round(p['target']))}ms",
         "interval",f"{int(round(p['interval']))}ms",
         "limit",f"{int(p['limit'])}","quantum",f"{int(p['quantum'])}"]
    if dry: print(f"  [DRY] {' '.join(cmd)}"); return True
    try: subprocess.run(cmd,check=True,capture_output=True,timeout=3); return True
    except subprocess.CalledProcessError as e:
        print(f"  [ERR] {e.stderr.decode().strip()}"); return False

# ── Classification & AIMD ─────────────────────────────────────
def gradient(history, attr):
    vals=[(s["ts"],s.get(attr,0)) for s in history]
    if len(vals)<3: return 0.0
    n=len(vals); t0=vals[0][0]
    xs=[v[0]-t0 for v in vals]; ys=[v[1] for v in vals]
    xm=sum(xs)/n; ym=sum(ys)/n
    num=sum((xi-xm)*(yi-ym) for xi,yi in zip(xs,ys))
    den=sum((xi-xm)**2 for xi in xs)
    return num/den if den>1e-9 else 0.0

def classify(dr,bl):
    if dr>DR_HEAVY  or bl>BL_HEAVY:  return "HEAVY"
    if dr>DR_MOD    or bl>BL_MOD:    return "MODERATE"
    if dr>DR_LIGHT  or bl>BL_LIGHT:  return "LIGHT"
    return "NORMAL"

REGIMES=["NORMAL","LIGHT","MODERATE","HEAVY"]

def predict(regime,dr_g,bl_g):
    idx=REGIMES.index(regime)
    c=0.6*dr_g/max(DR_HEAVY,1)+0.4*bl_g/max(BL_HEAVY,1)
    if c>0.5 and idx<3:  return REGIMES[idx+1],"WORSENING"
    if c<-0.5 and idx>0: return REGIMES[idx-1],"RECOVERING"
    return regime,"STABLE"

def select_workload(ratio):
    if ratio<0.2: return "MICE"
    if ratio>0.6: return "ELEPHANT"
    return "MIXED"

def aimd(regime,traj,pred,params,workload):
    p=dict(params)
    eff=pred if traj=="WORSENING" else regime
    pfx="[PREDICTIVE]" if traj=="WORSENING" and pred!=regime else "[REACTIVE]"
    if   eff=="HEAVY":    p["target"]*=BETA; p["interval"]*=BETA; p["limit"]*=BETA; r=f"{pfx} mult-decrease β={BETA}"
    elif eff=="MODERATE": p["target"]-=0.2;  p["limit"]-=32;                        r=f"{pfx} additive-decrease"
    elif eff=="LIGHT":    p["target"]+=ALPHA_T; p["interval"]+=5; p["limit"]+=ALPHA_L; r=f"{pfx} additive-increase"
    else:
        if traj=="RECOVERING": p["target"]+=0.2; p["limit"]+=16; r="gentle-increase"
        else: return params,"stable"
    p["quantum"]=WORKLOAD_Q[workload]
    p["target"]  =max(T_MIN,min(T_MAX,  p["target"]))
    p["interval"]=max(I_MIN,min(I_MAX,  p["interval"]))
    p["limit"]   =max(L_MIN,min(L_MAX,  int(p["limit"])))
    if p["interval"]<=p["target"]: p["interval"]=p["target"]*10
    return p,f"{r} | wkld={workload}"

# ── Main loop ─────────────────────────────────────────────────
def run(args):
    os.makedirs(args.logdir,exist_ok=True)
    ts=datetime.now().strftime("%Y%m%d_%H%M%S")
    mpath=os.path.join(args.logdir,f"acape_metrics_{ts}.csv")
    apath=os.path.join(args.logdir,f"acape_adj_{ts}.csv")
    spath=os.path.join(args.logdir,f"acape_state_{ts}.csv")
    mf=open(mpath,"w",newline=""); af=open(apath,"w",newline="")
    sf=open(spath,"w",newline="")
    mw=csv.writer(mf); aw=csv.writer(af); sw=csv.writer(sf)
    mw.writerow(["t_s","drop_rate_per_s","drops_exp","backlog_pkts",
                 "throughput_mbps","rtt_proxy_ms","active_flows",
                 "elephant_flows","mice_flows","elephant_ratio",
                 "regime","trajectory","predicted_regime","workload_profile",
                 "target_ms","interval_ms","limit_pkts","quantum_bytes",
                 "ebpf_pkts","ebpf_bytes"])
    aw.writerow(["t_s","regime","trajectory","predicted",
                 "old_target","new_target","old_limit","new_limit","workload","reason"])
    sw.writerow(["t_s","dr_gradient","bl_gradient","rtt_gradient",
                 "regime","trajectory","predicted","workload"])
    for f in (mf,af,sf): f.flush()

    ebpf=EBPFPipeline(args.ns,args.iface) if not args.dry else None
    ebpf_on=ebpf.active if ebpf else False
    params=get_params(args.ns,args.iface)
    history=deque(maxlen=GRAD_WINDOW)
    sbuf=deque(maxlen=8)
    stable_cnt=adj_count=tick=0
    t0=time.time()

    first=read_tc(args.ns,args.iface)
    if not first: sys.exit("ERROR: cannot read tc stats")
    drops_base=first["drops"]; prev=first

    mode = "eBPF (clang+tc+bpftool)" if ebpf_on else "tc-only"
    print(f"\n{'═'*72}")
    print(f"  ACAPE v{VERSION}  |  mode: {mode}")
    print(f"  metrics → {mpath}")
    print(f"{'═'*72}")
    H=(f"{'t':>7}  {'regime':>10}  {'traj':>11}  {'pred':>10}  "
       f"{'dr/s':>8}  {'bl':>5}  {'flows':>6}  {'eleph':>5}  "
       f"{'rtt':>7}  {'wkld':>8}  {'tgt':>6}  {'lim':>5}  {'adj':>4}")
    print(H); print("─"*len(H))

    def shutdown(sig=None,f=None):
        if ebpf: ebpf.detach()
        for x in (mf,af,sf): x.close()
        print(f"\nDone — {tick} ticks, {adj_count} adj | mode: {mode}")
        print("Run: python3 plot_acape.py")
        sys.exit(0)
    signal.signal(signal.SIGINT,shutdown); signal.signal(signal.SIGTERM,shutdown)

    while True:
        time.sleep(T2_INTERVAL); tick+=1
        tc=read_tc(args.ns,args.iface)
        if not tc: continue
        elapsed=tc["ts"]-t0
        dt=max(tc["ts"]-prev["ts"],1e-6)
        drops_exp=tc["drops"]-drops_base
        dr=max(0,tc["drops"]-prev["drops"])/dt
        tp=(max(0,tc["bytes"]-prev.get("bytes",0))*8)/(dt*1e6)
        bl=tc["backlog"]

        ed=ebpf.read_flows() if ebpf_on else {"active":0,"elephant":0,"mice":0,"rtt_ms":0.0,"ratio":0.0}
        rtt=ed["rtt_ms"]; ratio=ed["ratio"]
        workload=select_workload(ratio); regime=classify(dr,bl)

        history.append({"ts":elapsed,"drop_rate":dr,"backlog":float(bl),"rtt_proxy_ms":rtt})
        dr_g=gradient(list(history),"drop_rate")
        bl_g=gradient(list(history),"backlog")
        rtt_g=gradient(list(history),"rtt_proxy_ms")
        pred,traj=predict(regime,dr_g,bl_g)

        sbuf.append(regime)
        stable_cnt=(stable_cnt+1 if len(sbuf)>=STABLE_ROUNDS and
                    len(set(list(sbuf)[-STABLE_ROUNDS:]))==1 else 0)

        mw.writerow([f"{elapsed:.3f}",f"{dr:.4f}",drops_exp,bl,
                     f"{tp:.4f}",f"{rtt:.3f}",
                     ed["active"],ed["elephant"],ed["mice"],f"{ratio:.3f}",
                     regime,traj,pred,workload,
                     f"{params['target']:.2f}",f"{params['interval']:.1f}",
                     params["limit"],params["quantum"],0,0])
        mf.flush()

        if tick%5==0:
            sw.writerow([f"{elapsed:.3f}",f"{dr_g:.4f}",f"{bl_g:.4f}",
                         f"{rtt_g:.4f}",regime,traj,pred,workload])
            sf.flush()

        if tick%T3_EVERY_N==0 and stable_cnt>=STABLE_ROUNDS:
            old=dict(params); new_p,reason=aimd(regime,traj,pred,params,workload)
            if (abs(new_p["target"]-old["target"])>0.05 or abs(new_p["limit"]-old["limit"])>1):
                if apply_params(args.ns,args.iface,new_p,args.dry):
                    params=new_p; adj_count+=1
                    aw.writerow([f"{elapsed:.2f}",regime,traj,pred,
                                 f"{old['target']:.2f}",f"{new_p['target']:.2f}",
                                 int(old["limit"]),int(new_p["limit"]),workload,reason])
                    af.flush()

        print(f"{elapsed:>7.1f}  {regime:>10}  {traj:>11}  {pred:>10}  "
              f"{dr:>8.1f}  {bl:>5d}  {ed['active']:>6d}  {ed['elephant']:>5d}  "
              f"{rtt:>6.2f}ms  {workload:>8}  {params['target']:>5.1f}ms  "
              f"{params['limit']:>5d}  {adj_count:>4d}",flush=True)
        prev=tc

if __name__=="__main__":
    p=argparse.ArgumentParser(description="ACAPE v5 — clang+tc+bpftool pipeline")
    p.add_argument("--ns",     default="ns1")
    p.add_argument("--iface",  default="veth1")
    p.add_argument("--logdir", default="../logs")
    p.add_argument("--dry",    action="store_true")
    args=p.parse_args()
    if os.geteuid()!=0 and not args.dry:
        sys.exit("sudo python3 acape_v5.py")
    run(args)
