#!/usr/bin/env python3
"""
ACAPE: Adaptive Condition-Aware Packet Engine
Amritha S — VIT Chennai 2026

Single-file implementation. BPF source embedded as string.
Enters ns1 network namespace via setns() before BCC loads.
No external .c file needed.

Run: sudo python3 acape_final.py --ns ns1 --iface veth1
"""

import subprocess, re, time, csv, os, sys, signal, argparse, ctypes
from collections import deque
from datetime import datetime

VERSION = "4.0.0"

# ═══════════════════════════════════════════════════════════════
# BPF source — embedded as string, zero #includes
# BCC provides all built-ins (u32, u64, BPF_HASH, etc.) automatically
# ═══════════════════════════════════════════════════════════════
BPF_SOURCE = r"""
#define ETH_P_IP    0x0800
#define IPPROTO_TCP 6
#define IPPROTO_UDP 17
#define TC_ACT_OK   0
#define ELEPHANT_B  10000000ULL

struct eth_t { u8 dst[6]; u8 src[6]; u16 proto; } __attribute__((packed));
struct ip_t  { u8 ihl_ver; u8 tos; u16 tot; u16 id; u16 frag;
               u8 ttl; u8 proto; u16 csum; u32 saddr; u32 daddr;
             } __attribute__((packed));
struct port_t { u16 src; u16 dst; } __attribute__((packed));

struct fkey { u32 sip; u32 dip; u16 sp; u16 dp; u8 proto; };
struct fval { u64 pkts; u64 bytes; u64 last_ns; u64 gap_ns; u32 elephant; };
struct gval { u64 pkts; u64 bytes; };

BPF_HASH(flow_map, struct fkey, struct fval, 65536);
BPF_ARRAY(global_map, struct gval, 1);
BPF_ARRAY(size_hist, u64, 4);

int tc_mon(struct __sk_buff *skb) {
    void *data     = (void *)(long)skb->data;
    void *data_end = (void *)(long)skb->data_end;

    struct eth_t *eth = data;
    if ((void *)(eth+1) > data_end) return TC_ACT_OK;
    if (bpf_ntohs(eth->proto) != ETH_P_IP) return TC_ACT_OK;

    struct ip_t *ip = (void *)(eth+1);
    if ((void *)(ip+1) > data_end) return TC_ACT_OK;

    struct fkey k = {}; k.sip=ip->saddr; k.dip=ip->daddr; k.proto=ip->proto;
    if (ip->proto==IPPROTO_TCP || ip->proto==IPPROTO_UDP) {
        struct port_t *p = (void *)(ip+1);
        if ((void *)(p+1) > data_end) return TC_ACT_OK;
        k.sp = bpf_ntohs(p->src); k.dp = bpf_ntohs(p->dst);
    }

    u64 now = bpf_ktime_get_ns();
    u32 len = skb->len;

    struct fval *fv = flow_map.lookup(&k);
    if (!fv) {
        struct fval nv = {}; nv.pkts=1; nv.bytes=len; nv.last_ns=now;
        flow_map.insert(&k, &nv);
    } else {
        u64 gap = now - fv->last_ns;
        fv->gap_ns = fv->gap_ns ? (fv->gap_ns*7+gap)>>3 : gap;
        fv->pkts++; fv->bytes+=len; fv->last_ns=now;
        if (fv->bytes > ELEPHANT_B) fv->elephant=1;
    }

    u32 z=0; struct gval *gv = global_map.lookup(&z);
    if (gv) { gv->pkts++; gv->bytes+=len; }

    u32 b = len<128?0:len<512?1:len<1500?2:3;
    u64 *c = size_hist.lookup(&b); if(c) (*c)++;
    return TC_ACT_OK;
}
"""

# ── Constants ─────────────────────────────────────────────────
T_MIN,T_MAX   = 1, 20
I_MIN,I_MAX   = 50, 300
L_MIN,L_MAX   = 256, 4096
Q_MIN,Q_MAX   = 300, 4000
BETA          = 0.9
ALPHA_T, ALPHA_L = 0.5, 64
DR_LIGHT,DR_MOD,DR_HEAVY = 1, 10, 30
BL_LIGHT,BL_MOD,BL_HEAVY = 20, 100, 300
GRAD_WINDOW   = 10
STABLE_ROUNDS = 5
T2_INTERVAL   = 0.5
T3_EVERY_N    = 10

WORKLOAD_PROFILES = {
    "MICE":     {"quantum": 300},
    "MIXED":    {"quantum": 1514},
    "ELEPHANT": {"quantum": 3000},
}

# ── Enter network namespace ───────────────────────────────────
def enter_netns(ns_name):
    """
    Enter network namespace using setns() syscall.
    Must be called BEFORE BCC loads so TC attach goes to right ns.
    """
    ns_path = f"/var/run/netns/{ns_name}"
    if not os.path.exists(ns_path):
        print(f"[NS] ERROR: {ns_path} not found. Run setup_ns.sh first.")
        sys.exit(1)
    try:
        CLONE_NEWNET = 0x40000000
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        fd = os.open(ns_path, os.O_RDONLY)
        ret = libc.setns(fd, CLONE_NEWNET)
        os.close(fd)
        if ret != 0:
            err = ctypes.get_errno()
            print(f"[NS] setns() failed: errno={err}")
            sys.exit(1)
        print(f"[NS] ✅ Entered network namespace: {ns_name}")
        return True
    except Exception as e:
        print(f"[NS] setns() error: {e}")
        sys.exit(1)

# ── eBPF layer ────────────────────────────────────────────────
class EBPFLayer:
    def __init__(self, iface):
        self.iface = iface
        self.b = None
        self.active = False
        self._load()

    def _load(self):
        try:
            from bcc import BPF
        except ImportError:
            print("[eBPF] ❌ python3-bpfcc missing")
            print("       sudo apt install python3-bpfcc bpfcc-tools")
            return

        print("[eBPF] Layer 1: Compiling BPF source...")
        try:
            # Pass source as string — no file needed
            self.b = BPF(text=BPF_SOURCE)
            print("[eBPF] Layer 1: ✅ Compiled")
        except Exception as e:
            print(f"[eBPF] ❌ Compile failed: {e}")
            return

        fn = self.b.load_func("tc_mon", BPF.SCHED_CLS)
        print(f"[eBPF] Layer 1: ✅ Loaded (fd={fn.fd})")

        # Attach via tc commands (we are inside the right ns via setns)
        subprocess.run(["tc","qdisc","del","dev",self.iface,"clsact"],
                       stderr=subprocess.DEVNULL)
        r1 = subprocess.run(["tc","qdisc","add","dev",self.iface,"clsact"],
                             capture_output=True)
        if r1.returncode != 0:
            print(f"[eBPF] qdisc add clsact: {r1.stderr.decode().strip()}")

        r2 = subprocess.run([
            "tc","filter","add","dev",self.iface,"egress",
            "bpf","direct-action","fd",str(fn.fd),"name","tc_mon"
        ], capture_output=True)

        if r2.returncode == 0:
            self.active = True
            print(f"[eBPF] Layer 1: ✅ Attached to {self.iface} egress")
            print(f"[eBPF] Layer 2: ✅ Maps: flow_map | global_map | size_hist")
            print(f"[eBPF] Layer 3: ✅ Userspace polling every {T2_INTERVAL}s")
        else:
            print(f"[eBPF] ❌ Filter attach failed: {r2.stderr.decode().strip()}")
            print("[eBPF] Continuing in tc-only mode")

    def read_flows(self):
        if not self.active or not self.b:
            return {"active":0,"elephant":0,"mice":0,"rtt_ms":0.0,"ratio":0.0}
        try:
            now_ns = time.time_ns()
            active = elephant = mice = 0
            total_gap = 0
            for k, v in self.b["flow_map"].items():
                if (now_ns - v.last_ns) / 1e9 < 2.0:
                    active += 1
                    total_gap += v.gap_ns
                    if v.elephant: elephant += 1
                    else: mice += 1
            rtt = (total_gap / max(active,1)) / 1e6
            ratio = elephant / max(active, 1)
            return {"active":active,"elephant":elephant,
                    "mice":mice,"rtt_ms":round(rtt,3),"ratio":round(ratio,3)}
        except:
            return {"active":0,"elephant":0,"mice":0,"rtt_ms":0.0,"ratio":0.0}

    def read_global(self):
        if not self.active or not self.b:
            return {"pkts":0,"bytes":0}
        try:
            g = self.b["global_map"][0]
            return {"pkts":g.pkts,"bytes":g.bytes}
        except:
            return {"pkts":0,"bytes":0}

    def detach(self):
        subprocess.run(["tc","qdisc","del","dev",self.iface,"clsact"],
                       stderr=subprocess.DEVNULL)
        print(f"[eBPF] Detached from {self.iface}")

# ── tc helpers (no 'ip netns exec' — already inside ns) ───────
def _r(cmd):
    try: return subprocess.check_output(cmd,stderr=subprocess.DEVNULL,
                                        text=True,timeout=2)
    except: return ""

def read_tc(iface):
    out = _r(["tc","-s","qdisc","show","dev",iface])
    if not out: return None
    d = {"ts":time.time()}
    m = re.search(r"Sent (\d+) bytes",out); d["bytes"]   = int(m.group(1)) if m else 0
    m = re.search(r"dropped (\d+)",out);    d["drops"]   = int(m.group(1)) if m else 0
    m = re.search(r"backlog \d+b (\d+)p",out); d["backlog"] = int(m.group(1)) if m else 0
    return d

def get_params(iface):
    out = _r(["tc","qdisc","show","dev",iface])
    p = {"target":5.0,"interval":100.0,"limit":1024,"quantum":1514}
    for k,pat in [("target",r"target (\d+)ms"),("interval",r"interval (\d+)ms"),
                  ("limit",r"limit (\d+)p?"),("quantum",r"quantum (\d+)")]:
        m = re.search(pat,out)
        if m: p[k] = float(m.group(1)) if k in("target","interval") else int(m.group(1))
    return p

def apply_params(iface, p, dry=False):
    cmd = ["tc","qdisc","change","dev",iface,
           "parent","1:1","handle","10:","fq_codel",
           "target",  f"{int(round(p['target']))}ms",
           "interval",f"{int(round(p['interval']))}ms",
           "limit",   f"{int(p['limit'])}",
           "quantum", f"{int(p['quantum'])}"]
    if dry: print(f"  [DRY] {' '.join(cmd)}"); return True
    try:
        subprocess.run(cmd,check=True,capture_output=True,timeout=3)
        return True
    except subprocess.CalledProcessError as e:
        print(f"  [ERR] {e.stderr.decode().strip()}"); return False

# ── Classification ────────────────────────────────────────────
def gradient(history, attr):
    vals = [(s["ts"], s.get(attr,0)) for s in history]
    if len(vals) < 3: return 0.0
    n=len(vals); t0=vals[0][0]
    xs=[v[0]-t0 for v in vals]; ys=[v[1] for v in vals]
    xm=sum(xs)/n; ym=sum(ys)/n
    num=sum((xi-xm)*(yi-ym) for xi,yi in zip(xs,ys))
    den=sum((xi-xm)**2 for xi in xs)
    return num/den if den>1e-9 else 0.0

def classify(dr, bl):
    if dr>DR_HEAVY  or bl>BL_HEAVY:  return "HEAVY"
    if dr>DR_MOD    or bl>BL_MOD:    return "MODERATE"
    if dr>DR_LIGHT  or bl>BL_LIGHT:  return "LIGHT"
    return "NORMAL"

REGIMES = ["NORMAL","LIGHT","MODERATE","HEAVY"]

def predict(regime, dr_g, bl_g):
    idx = REGIMES.index(regime)
    c = 0.6*dr_g/max(DR_HEAVY,1) + 0.4*bl_g/max(BL_HEAVY,1)
    if c > 0.5 and idx < 3: return REGIMES[idx+1],"WORSENING"
    if c < -0.5 and idx > 0: return REGIMES[idx-1],"RECOVERING"
    return regime,"STABLE"

def select_workload(ratio):
    if ratio < 0.2: return "MICE"
    if ratio > 0.6: return "ELEPHANT"
    return "MIXED"

def aimd(regime, traj, pred, params, workload):
    p = dict(params)
    eff = pred if traj=="WORSENING" else regime
    pfx = "[PREDICTIVE]" if traj=="WORSENING" and pred!=regime else "[REACTIVE]"
    if   eff=="HEAVY":    p["target"]*=BETA; p["interval"]*=BETA; p["limit"]*=BETA; r=f"{pfx} mult-decrease β={BETA}"
    elif eff=="MODERATE": p["target"]-=0.2;  p["limit"]-=32;                        r=f"{pfx} additive-decrease"
    elif eff=="LIGHT":    p["target"]+=ALPHA_T; p["interval"]+=5; p["limit"]+=ALPHA_L; r=f"{pfx} additive-increase"
    else:
        if traj=="RECOVERING": p["target"]+=0.2; p["limit"]+=16; r="gentle-increase"
        else: return params,"stable"
    p["quantum"] = WORKLOAD_PROFILES[workload]["quantum"]
    p["target"]   = max(T_MIN,min(T_MAX,  p["target"]))
    p["interval"] = max(I_MIN,min(I_MAX,  p["interval"]))
    p["limit"]    = max(L_MIN,min(L_MAX,  int(p["limit"])))
    if p["interval"] <= p["target"]: p["interval"] = p["target"]*10
    return p, f"{r} | wkld={workload}"

# ── Main ──────────────────────────────────────────────────────
def run(args):
    os.makedirs(args.logdir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    mpath = os.path.join(args.logdir, f"acape_metrics_{ts}.csv")
    apath = os.path.join(args.logdir, f"acape_adj_{ts}.csv")
    spath = os.path.join(args.logdir, f"acape_state_{ts}.csv")

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
                 "old_target","new_target","old_limit","new_limit",
                 "workload","reason"])
    sw.writerow(["t_s","dr_gradient","bl_gradient","rtt_gradient",
                 "regime","trajectory","predicted","workload"])
    for f in (mf,af,sf): f.flush()

    ebpf    = EBPFLayer(args.iface) if not args.dry else None
    ebpf_on = ebpf.active if ebpf else False
    params  = get_params(args.iface)
    history = deque(maxlen=GRAD_WINDOW)
    sbuf    = deque(maxlen=8)
    stable_cnt = adj_count = tick = 0
    t0 = time.time()

    first = read_tc(args.iface)
    if not first: sys.exit("ERROR: cannot read tc stats — is namespace set up?")
    drops_base = first["drops"]; prev = first

    print(f"\n{'═'*72}")
    print(f"  ACAPE v{VERSION}  |  eBPF: {'✅ ACTIVE — 3-layer telemetry' if ebpf_on else '⚠️  tc-only'}")
    print(f"  Interface: {args.iface}  |  metrics → {mpath}")
    print(f"{'═'*72}")
    H=(f"{'t':>7}  {'regime':>10}  {'traj':>11}  {'pred':>10}  "
       f"{'dr/s':>8}  {'bl':>5}  {'flows':>6}  {'eleph':>5}  "
       f"{'rtt_ms':>7}  {'wkld':>8}  {'tgt':>6}  {'lim':>5}  {'adj':>4}")
    print(H); print("─"*len(H))

    def shutdown(sig=None,f=None):
        if ebpf: ebpf.detach()
        for x in (mf,af,sf): x.close()
        print(f"\nDone — {tick} ticks, {adj_count} adj")
        print("Run: python3 plot_acape.py --logdir <path>")
        sys.exit(0)
    signal.signal(signal.SIGINT,shutdown)
    signal.signal(signal.SIGTERM,shutdown)

    while True:
        time.sleep(T2_INTERVAL); tick+=1
        tc = read_tc(args.iface)
        if not tc: continue

        elapsed = tc["ts"]-t0
        dt      = max(tc["ts"]-prev["ts"],1e-6)
        drops_exp = tc["drops"]-drops_base
        dr   = max(0,tc["drops"]-prev["drops"])/dt
        tp   = (max(0,tc["bytes"]-prev.get("bytes",0))*8)/(dt*1e6)
        bl   = tc["backlog"]

        ed = ebpf.read_flows()  if ebpf_on else {"active":0,"elephant":0,"mice":0,"rtt_ms":0.0,"ratio":0.0}
        gd = ebpf.read_global() if ebpf_on else {"pkts":0,"bytes":0}

        rtt=ed["rtt_ms"]; ratio=ed["ratio"]
        workload=select_workload(ratio); regime=classify(dr,bl)

        history.append({"ts":elapsed,"drop_rate":dr,"backlog":float(bl),"rtt_proxy_ms":rtt})
        dr_g  = gradient(list(history),"drop_rate")
        bl_g  = gradient(list(history),"backlog")
        rtt_g = gradient(list(history),"rtt_proxy_ms")
        pred,traj = predict(regime,dr_g,bl_g)

        sbuf.append(regime)
        stable_cnt = (stable_cnt+1 if len(sbuf)>=STABLE_ROUNDS and
                      len(set(list(sbuf)[-STABLE_ROUNDS:]))==1 else 0)

        mw.writerow([f"{elapsed:.3f}",f"{dr:.4f}",drops_exp,bl,
                     f"{tp:.4f}",f"{rtt:.3f}",
                     ed["active"],ed["elephant"],ed["mice"],f"{ratio:.3f}",
                     regime,traj,pred,workload,
                     f"{params['target']:.2f}",f"{params['interval']:.1f}",
                     params["limit"],params["quantum"],gd["pkts"],gd["bytes"]])
        mf.flush()

        if tick%5==0:
            sw.writerow([f"{elapsed:.3f}",f"{dr_g:.4f}",f"{bl_g:.4f}",
                         f"{rtt_g:.4f}",regime,traj,pred,workload])
            sf.flush()

        if tick%T3_EVERY_N==0 and stable_cnt>=STABLE_ROUNDS:
            old=dict(params); new_p,reason=aimd(regime,traj,pred,params,workload)
            if (abs(new_p["target"]-old["target"])>0.05 or
                    abs(new_p["limit"]-old["limit"])>1):
                if apply_params(args.iface,new_p,args.dry):
                    params=new_p; adj_count+=1
                    aw.writerow([f"{elapsed:.2f}",regime,traj,pred,
                                 f"{old['target']:.2f}",f"{new_p['target']:.2f}",
                                 int(old["limit"]),int(new_p["limit"]),
                                 workload,reason])
                    af.flush()

        print(f"{elapsed:>7.1f}  {regime:>10}  {traj:>11}  {pred:>10}  "
              f"{dr:>8.1f}  {bl:>5d}  {ed['active']:>6d}  {ed['elephant']:>5d}  "
              f"{rtt:>7.3f}  {workload:>8}  {params['target']:>5.1f}ms  "
              f"{params['limit']:>5d}  {adj_count:>4d}",flush=True)
        prev = tc

if __name__=="__main__":
    p = argparse.ArgumentParser(description="ACAPE v4 — self-contained, BPF embedded")
    p.add_argument("--ns",     default="ns1",    help="Network namespace to enter")
    p.add_argument("--iface",  default="veth1",  help="Interface inside namespace")
    p.add_argument("--logdir", default="../logs", help="Log directory")
    p.add_argument("--dry",    action="store_true")
    args = p.parse_args()

    if os.geteuid() != 0 and not args.dry:
        sys.exit("Run as root: sudo python3 acape_final.py")

    # Enter the network namespace BEFORE anything else
    if not args.dry:
        enter_netns(args.ns)

    run(args)
