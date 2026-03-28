#!/usr/bin/env bash
# =============================================================================
#  run_all.sh — Master Orchestrator (FIXED — uses tmux, not gnome-terminal)
#  CCN Linux Qdisc Study — Amritha S, VIT Chennai 2026
#
#  FIXES in this version:
#   1. Uses tmux instead of gnome-terminal (works under sudo, no dbus)
#   2. Embeds tc_monitor.c directly — no file-not-found errors
#   3. Fixes HOME path when running under sudo
#   4. All controllers written fresh to scripts/ directory
#
#  Usage:
#    sudo bash run_all.sh
#  Then in another terminal:
#    tmux attach -t ccn          (watch all 5 windows live)
#    Ctrl+B then 0/1/2/3/4       (switch windows)
# =============================================================================
set -euo pipefail

REAL_USER="${SUDO_USER:-$USER}"
REAL_HOME=$(getent passwd "$REAL_USER" | cut -d: -f6)
PROJECT_DIR="$REAL_HOME/ccn-linux-qdisc-study"
SCRIPTS="$PROJECT_DIR/scripts"
EBPF_DIR="$PROJECT_DIR/ebpf"
LOGS="$PROJECT_DIR/logs"
PLOTS="$PROJECT_DIR/plots"
PART3_DUR=90; PART4_DUR=90
NS1=ns1; NS2=ns2; VETH1=veth1; VETH2=veth2
IP1=10.0.0.1; IP2=10.0.0.2

RED='\033[0;31m';GREEN='\033[0;32m';YELLOW='\033[1;33m'
CYAN='\033[0;36m';BOLD='\033[1m';NC='\033[0m'
info()    { echo -e "${CYAN}[INFO]${NC} $*"; }
success() { echo -e "${GREEN}[OK]${NC}   $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
die()     { echo -e "${RED}[ERR]${NC}  $*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "Run with: sudo bash run_all.sh"

echo -e "${BOLD}${CYAN}"
echo "╔══════════════════════════════════════════════════╗"
echo "║   CCN Linux Qdisc Study — Master Orchestrator   ║"
echo "║   Amritha S, VIT Chennai 2026                   ║"
echo "╚══════════════════════════════════════════════════╝"
echo -e "${NC}"
info "Project : $PROJECT_DIR"
info "User    : $REAL_USER"

mkdir -p "$SCRIPTS" "$EBPF_DIR" "$LOGS" "$PLOTS"

# ── DEPENDENCIES ─────────────────────────────────────────────────────────────
info "Installing dependencies..."
apt-get update -qq 2>/dev/null
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    iperf3 iproute2 clang llvm libbpf-dev tmux xterm \
    linux-headers-"$(uname -r)" \
    python3-pip 2>/dev/null || true
pip3 install matplotlib pandas --quiet 2>/dev/null || true
apt-get install -y -qq bpftool 2>/dev/null || \
    apt-get install -y -qq linux-tools-generic 2>/dev/null || true
success "Dependencies ready"

# ── EMBED tc_monitor.c ────────────────────────────────────────────────────────
info "Writing ebpf/tc_monitor.c..."
cat > "$EBPF_DIR/tc_monitor.c" << 'CEOF'
#include <linux/bpf.h>
#include <linux/pkt_cls.h>
#include <linux/if_ether.h>
#include <linux/ip.h>
#include <linux/tcp.h>
#include <linux/udp.h>
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_endian.h>
struct flow_key { __u32 src_ip,dst_ip; __u16 src_port,dst_port; __u8 protocol,_pad[3]; };
struct flow_stats { __u64 packets,bytes,last_seen_ns; };
struct { __uint(type,BPF_MAP_TYPE_LRU_HASH); __type(key,struct flow_key);
         __type(value,struct flow_stats); __uint(max_entries,4096); } flow_map SEC(".maps");
struct { __uint(type,BPF_MAP_TYPE_ARRAY); __type(key,__u32);
         __type(value,__u64); __uint(max_entries,4); } global_map SEC(".maps");
SEC("classifier")
int tc_flow_monitor(struct __sk_buff *skb) {
    void *data=(void*)(long)skb->data, *data_end=(void*)(long)skb->data_end;
    struct ethhdr *eth=data;
    if((void*)(eth+1)>data_end) return TC_ACT_OK;
    if(eth->h_proto!=bpf_htons(ETH_P_IP)) return TC_ACT_OK;
    struct iphdr *ip=(void*)(eth+1);
    if((void*)(ip+1)>data_end) return TC_ACT_OK;
    struct flow_key key={}; key.src_ip=ip->saddr; key.dst_ip=ip->daddr; key.protocol=ip->protocol;
    if(ip->protocol==IPPROTO_TCP){
        struct tcphdr *t=(void*)(ip+1); if((void*)(t+1)>data_end) return TC_ACT_OK;
        key.src_port=bpf_ntohs(t->source); key.dst_port=bpf_ntohs(t->dest);
    } else if(ip->protocol==IPPROTO_UDP){
        struct udphdr *u=(void*)(ip+1); if((void*)(u+1)>data_end) return TC_ACT_OK;
        key.src_port=bpf_ntohs(u->source); key.dst_port=bpf_ntohs(u->dest);
    }
    struct flow_stats *fs=bpf_map_lookup_elem(&flow_map,&key);
    if(fs){ __sync_fetch_and_add(&fs->packets,1); __sync_fetch_and_add(&fs->bytes,skb->len);
            fs->last_seen_ns=bpf_ktime_get_ns(); }
    else { struct flow_stats n={1,skb->len,0}; n.last_seen_ns=bpf_ktime_get_ns();
           bpf_map_update_elem(&flow_map,&key,&n,BPF_ANY); }
    __u32 idx=0; __u64 *p=bpf_map_lookup_elem(&global_map,&idx);
    if(p) __sync_fetch_and_add(p,1);
    idx=1; p=bpf_map_lookup_elem(&global_map,&idx);
    if(p) __sync_fetch_and_add(p,(unsigned long long)skb->len);
    return TC_ACT_OK;
}
char _license[] SEC("license") = "GPL";
CEOF
success "tc_monitor.c written"

# ── COMPILE eBPF ──────────────────────────────────────────────────────────────
info "Compiling eBPF..."
ARCH=$(uname -m)
if clang -O2 -target bpf \
    -I/usr/include/${ARCH}-linux-gnu \
    -c "$EBPF_DIR/tc_monitor.c" \
    -o "$EBPF_DIR/tc_monitor.o" 2>&1; then
    success "Compiled → $EBPF_DIR/tc_monitor.o"
else
    warn "eBPF compile failed — Part 4 will run in tc-only mode"
fi

# ── WRITE Part 3 controller ───────────────────────────────────────────────────
info "Writing Part 3 controller..."
cat > "$SCRIPTS/part3_adaptive_controller.py" << 'PYEOF'
#!/usr/bin/env python3
"""Part 3: Adaptive fq_codel Controller (AIMD) — Amritha S, VIT Chennai 2026"""
import subprocess,re,time,csv,os,argparse,sys
from datetime import datetime
ALPHA=0.5;BETA=0.9;TARGET_MIN=1.0;TARGET_MAX=5.0;LIMIT_MIN=256;LIMIT_MAX=1024
DROP_HEAVY=1000;DROP_MODERATE=200;DROP_LIGHT=50
BACKLOG_HEAVY=300;BACKLOG_MODERATE=150;BACKLOG_LIGHT=50
LOG_DIR=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..","logs")
def tc(args,ns=None):
    cmd=(["ip","netns","exec",ns] if ns else [])+args
    try: return subprocess.run(cmd,capture_output=True,text=True,timeout=3)
    except: return None
def stats(iface,ns=None):
    r=tc(["tc","-s","qdisc","show","dev",iface],ns)
    if not r: return None
    s={"bytes":0,"drops":0,"overlimits":0,"backlog":0,"timestamp":time.time()}
    for line in r.stdout.splitlines():
        m=re.search(r"Sent\s+(\d+)\s+bytes",line);
        if m: s["bytes"]=int(m.group(1))
        m=re.search(r"dropped\s+(\d+)",line);
        if m: s["drops"]=int(m.group(1))
        m=re.search(r"overlimits\s+(\d+)",line);
        if m: s["overlimits"]=int(m.group(1))
        m=re.search(r"backlog\s+\S+\s+(\d+)p",line);
        if m: s["backlog"]=int(m.group(1))
    return s
def parent(iface,ns=None):
    r=tc(["tc","qdisc","show","dev",iface],ns)
    if not r: return "root"
    for l in r.stdout.splitlines():
        if "fq_codel" in l:
            m=re.search(r"parent\s+(\S+)",l)
            if m: return f"parent {m.group(1)}"
    return "root"
def apply(iface,target,limit,ns=None):
    p=parent(iface,ns)
    r=tc(["tc","qdisc","change","dev",iface,p,"fq_codel",
          f"target {target:.2f}ms",f"limit {int(limit)}"],ns)
    if r and r.returncode!=0: print(f"  [WARN] {r.stderr.strip()}")
def classify(dr,bl):
    if dr>=DROP_HEAVY or bl>=BACKLOG_HEAVY: return "HEAVY"
    if dr>=DROP_MODERATE or bl>=BACKLOG_MODERATE: return "MODERATE"
    if dr>=DROP_LIGHT or bl>=BACKLOG_LIGHT: return "LIGHT"
    return "NORMAL"
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--interface","-i",default="veth1")
    ap.add_argument("--netns","-n",default="ns1")
    ap.add_argument("--monitor-interval",type=float,default=0.5)
    ap.add_argument("--adjust-every",type=int,default=6)
    ap.add_argument("--stability-window",type=int,default=3)
    a=ap.parse_args()
    os.makedirs(LOG_DIR,exist_ok=True)
    tag=datetime.now().strftime("%Y%m%d_%H%M%S")
    mf=os.path.join(LOG_DIR,f"metrics_{tag}.csv")
    af=os.path.join(LOG_DIR,f"adjustments_{tag}.csv")
    with open(mf,"w",newline="") as f:
        csv.writer(f).writerow(["t","wall","drop_rate","backlog","throughput_mbps","state","target_ms","limit_pkts"])
    with open(af,"w",newline="") as f:
        csv.writer(f).writerow(["t","state","reason","old_target","new_target","old_limit","new_limit"])
    print(f"[P3] {mf}")
    print(f"{'t':>6}  {'State':>8}  {'Drop/s':>8}  {'Backlog':>7}  {'Mbps':>6}  {'target':>7}  {'limit':>6}")
    print("-"*60)
    prev=None;target=TARGET_MAX;limit=float(LIMIT_MAX)
    sn=0;ps=None;pn=0;t0=time.time()
    while True:
        now=stats(a.interface,a.netns);tick=time.time()-t0
        if prev and now:
            dt=max(now["timestamp"]-prev["timestamp"],0.01)
            dr=max(0,now["drops"]-prev["drops"])/dt
            tp=max(0,now["bytes"]-prev["bytes"])*8/1e6/dt
            st=classify(dr,now["backlog"])
            if st==ps: sn+=1
            else: sn=0
            ps=st;pn+=1;changed=False;ot=target;ol=limit
            if pn>=a.adjust_every and sn>=a.stability_window:
                pn=0
                if st in("HEAVY","MODERATE"):
                    target=max(TARGET_MIN,target*BETA);limit=max(LIMIT_MIN,limit*BETA)
                    reason=f"mult-decrease β={BETA}";changed=True
                elif st=="NORMAL":
                    target=min(TARGET_MAX,target+ALPHA);limit=min(LIMIT_MAX,limit+32)
                    reason=f"add-increase α={ALPHA}";changed=True
                if changed:
                    apply(a.interface,target,limit,a.netns)
                    with open(af,"a",newline="") as f:
                        csv.writer(f).writerow([f"{tick:.2f}",st,reason,f"{ot:.2f}",f"{target:.2f}",int(ol),int(limit)])
            wall=datetime.now().strftime("%H:%M:%S")
            print(f"{tick:>6.1f}  {st:>8}  {dr:>7.0f}/s  {now['backlog']:>7}  {tp:>5.1f}M  {target:>6.2f}ms  {int(limit):>6}"+(" ◀" if changed else ""))
            with open(mf,"a",newline="") as f:
                csv.writer(f).writerow([f"{tick:.2f}",wall,f"{dr:.1f}",now["backlog"],f"{tp:.3f}",st,f"{target:.2f}",int(limit)])
        prev=now;time.sleep(a.monitor_interval)
if __name__=="__main__":
    try: main()
    except KeyboardInterrupt: print("\n[P3] Done")
PYEOF

# ── WRITE Part 4 controller ───────────────────────────────────────────────────
info "Writing Part 4 controller..."
cat > "$SCRIPTS/part4_ebpf_controller.py" << 'PYEOF'
#!/usr/bin/env python3
"""Part 4: eBPF-Enhanced Adaptive Controller — Amritha S, VIT Chennai 2026"""
import subprocess,re,time,csv,os,argparse,sys,struct,json
from datetime import datetime
ALPHA=0.5;BETA=0.9;TARGET_MIN=1.0;TARGET_MAX=5.0;LIMIT_MIN=256;LIMIT_MAX=1024
DROP_HEAVY=1000;DROP_MODERATE=200;DROP_LIGHT=50
BACKLOG_HEAVY=300;BACKLOG_MODERATE=150;BACKLOG_LIGHT=50
ELEPHANT_RATIO=0.20
LOG_DIR=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..","logs")

class BPFReader:
    def __init__(self):
        self.ok=subprocess.run(["bpftool","version"],capture_output=True).returncode==0
        self.fid=None;self.gid=None
    def find(self):
        if not self.ok: return False
        try:
            r=subprocess.run(["bpftool","map","list"],capture_output=True,text=True,timeout=5)
            for line in r.stdout.splitlines():
                if "flow_map" in line:
                    m=re.match(r"^\s*(\d+):",line);
                    if m: self.fid=int(m.group(1))
                if "global_map" in line:
                    m=re.match(r"^\s*(\d+):",line);
                    if m: self.gid=int(m.group(1))
            return self.fid is not None
        except: return False
    def flows(self):
        if not self.ok or self.fid is None: return []
        try:
            r=subprocess.run(["bpftool","map","dump","id",str(self.fid),"--json"],
                capture_output=True,text=True,timeout=5)
            if r.returncode!=0: return []
            out=[]
            for e in json.loads(r.stdout):
                v=e.get("value",[])
                if len(v)<16: continue
                out.append({"bytes":struct.unpack_from("<Q",bytes(v[8:16]))[0]})
            return out
        except: return []
    def analyse(self,flows):
        if not flows: return 0,0,0.0
        total=sum(f["bytes"] for f in flows)
        if not total: return len(flows),0,0.0
        th=total*ELEPHANT_RATIO
        el=[f for f in flows if f["bytes"]>th]
        return len(flows),len(el),sum(f["bytes"] for f in el)/total

def tc(args,ns=None):
    cmd=(["ip","netns","exec",ns] if ns else [])+args
    try: return subprocess.run(cmd,capture_output=True,text=True,timeout=3)
    except: return None
def stats(iface,ns=None):
    r=tc(["tc","-s","qdisc","show","dev",iface],ns)
    if not r: return None
    s={"bytes":0,"drops":0,"overlimits":0,"backlog":0,"timestamp":time.time()}
    for line in r.stdout.splitlines():
        m=re.search(r"Sent\s+(\d+)\s+bytes",line);
        if m: s["bytes"]=int(m.group(1))
        m=re.search(r"dropped\s+(\d+)",line);
        if m: s["drops"]=int(m.group(1))
        m=re.search(r"overlimits\s+(\d+)",line);
        if m: s["overlimits"]=int(m.group(1))
        m=re.search(r"backlog\s+\S+\s+(\d+)p",line);
        if m: s["backlog"]=int(m.group(1))
    return s
def parent(iface,ns=None):
    r=tc(["tc","qdisc","show","dev",iface],ns)
    if not r: return "root"
    for l in r.stdout.splitlines():
        if "fq_codel" in l:
            m=re.search(r"parent\s+(\S+)",l)
            if m: return f"parent {m.group(1)}"
    return "root"
def apply(iface,target,limit,ns=None):
    p=parent(iface,ns)
    r=tc(["tc","qdisc","change","dev",iface,p,"fq_codel",
          f"target {target:.2f}ms",f"limit {int(limit)}"],ns)
    if r and r.returncode!=0: print(f"  [WARN] {r.stderr.strip()}")
def attach_ebpf(iface,obj,ns=None):
    def t(*a):
        cmd=(["ip","netns","exec",ns] if ns else [])+["tc"]+list(a)
        return subprocess.run(cmd,capture_output=True,text=True,timeout=5)
    t("filter","del","dev",iface,"egress")
    t("qdisc","del","dev",iface,"clsact")
    time.sleep(0.3)
    t("qdisc","add","dev",iface,"clsact")
    r=t("filter","add","dev",iface,"egress","bpf","direct-action","obj",obj,"sec","classifier")
    if r.returncode!=0: print(f"[eBPF] FAILED: {r.stderr.strip()}"); return False
    print(f"[eBPF] attached ✓"); return True
def detach_ebpf(iface,ns=None):
    def t(*a):
        cmd=(["ip","netns","exec",ns] if ns else [])+["tc"]+list(a)
        subprocess.run(cmd,capture_output=True,text=True)
    t("filter","del","dev",iface,"egress"); t("qdisc","del","dev",iface,"clsact")
def classify(dr,bl,el=0):
    s=0.7 if el>0 else 1.0
    if dr>=DROP_HEAVY*s or bl>=BACKLOG_HEAVY*s: return "HEAVY"
    if dr>=DROP_MODERATE*s or bl>=BACKLOG_MODERATE*s: return "MODERATE"
    if dr>=DROP_LIGHT*s or bl>=BACKLOG_LIGHT*s: return "LIGHT"
    return "NORMAL"
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--interface","-i",default="veth1")
    ap.add_argument("--netns","-n",default="ns1")
    ap.add_argument("--ebpf-obj",default="ebpf/tc_monitor.o")
    ap.add_argument("--poll",type=float,default=0.5)
    ap.add_argument("--stability",type=int,default=3)
    a=ap.parse_args()
    base=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    obj=a.ebpf_obj if os.path.isabs(a.ebpf_obj) else os.path.join(base,a.ebpf_obj)
    ebpf_ok=False;reader=BPFReader()
    if os.path.exists(obj):
        ebpf_ok=attach_ebpf(a.interface,obj,a.netns)
        if ebpf_ok:
            time.sleep(1.0); ebpf_ok=reader.find()
            if not ebpf_ok: print("[eBPF] maps not visible — tc-only mode")
    else: print(f"[eBPF] not found: {obj}")
    mode="ebpf+tc" if ebpf_ok else "tc-only"
    print(f"\n[MODE] {mode}\n")
    os.makedirs(LOG_DIR,exist_ok=True)
    tag=datetime.now().strftime("%Y%m%d_%H%M%S")
    mf=os.path.join(LOG_DIR,f"ebpf_metrics_{tag}.csv")
    af=os.path.join(LOG_DIR,f"ebpf_adj_{tag}.csv")
    with open(mf,"w",newline="") as f:
        csv.writer(f).writerow(["t","wall","drop_rate","backlog","throughput_mbps",
                                 "active_flows","elephant_flows","elephant_ratio",
                                 "state","target_ms","limit_pkts","mode"])
    with open(af,"w",newline="") as f:
        csv.writer(f).writerow(["t","state","reason","old_target","new_target","old_limit","new_limit"])
    print(f"[P4] {mf}")
    print(f"{'t':>6}  {'State':>8}  {'Drop/s':>7}  {'Backlog':>7}  {'Mbps':>5}  {'Flows':>5}  {'Eleph':>5}  {'target':>7}  {'limit':>6}")
    print("-"*75)
    prev=None;target=TARGET_MAX;limit=float(LIMIT_MAX)
    sn=0;ps=None;pn=0;t0=time.time()
    try:
        while True:
            now=stats(a.interface,a.netns);tick=time.time()-t0
            if prev and now:
                dt=max(now["timestamp"]-prev["timestamp"],0.01)
                dr=max(0,now["drops"]-prev["drops"])/dt
                tp=max(0,now["bytes"]-prev["bytes"])*8/1e6/dt
                active=eleph=0;erat=0.0
                if ebpf_ok:
                    fl=reader.flows(); active,eleph,erat=reader.analyse(fl)
                st=classify(dr,now["backlog"],eleph)
                if st==ps: sn+=1
                else: sn=0
                ps=st;pn+=1;changed=False;ot=target;ol=limit
                if pn>=6 and sn>=a.stability:
                    pn=0
                    if st in("HEAVY","MODERATE"):
                        b=BETA*(0.95 if eleph>0 else 1.0)
                        target=max(TARGET_MIN,target*b);limit=max(LIMIT_MIN,limit*b)
                        reason=f"mult-decrease β={b:.2f}";changed=True
                    elif st=="NORMAL":
                        target=min(TARGET_MAX,target+ALPHA);limit=min(LIMIT_MAX,limit+32)
                        reason=f"add-increase α={ALPHA}";changed=True
                    if changed:
                        apply(a.interface,target,limit,a.netns)
                        with open(af,"a",newline="") as f:
                            csv.writer(f).writerow([f"{tick:.2f}",st,reason,f"{ot:.2f}",f"{target:.2f}",int(ol),int(limit)])
                wall=datetime.now().strftime("%H:%M:%S")
                print(f"{tick:>6.1f}  {st:>8}  {dr:>6.0f}/s  {now['backlog']:>7}  {tp:>4.1f}M  {active:>5}  {eleph:>5}  {target:>6.2f}ms  {int(limit):>6}"+(" ◀" if changed else ""))
                with open(mf,"a",newline="") as f:
                    csv.writer(f).writerow([f"{tick:.2f}",wall,f"{dr:.1f}",now["backlog"],f"{tp:.3f}",
                        active,eleph,f"{erat:.3f}",st,f"{target:.2f}",int(limit),mode])
            prev=now;time.sleep(a.poll)
    except KeyboardInterrupt: print(f"\n[P4] Done. mode={mode}")
    finally:
        if ebpf_ok: detach_ebpf(a.interface,a.netns)
if __name__=="__main__": main()
PYEOF

# ── WRITE PLOT SCRIPTS ────────────────────────────────────────────────────────
info "Writing plot scripts..."
cat > "$SCRIPTS/plot_part3.py" << 'PYEOF'
#!/usr/bin/env python3
import pandas as pd,matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt,glob,os,sys
BASE=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LD=os.path.join(BASE,"logs");PD=os.path.join(BASE,"plots");os.makedirs(PD,exist_ok=True)
SC={"NORMAL":"#00bfa5","LIGHT":"#2979ff","MODERATE":"#ffd600","HEAVY":"#e53935"}
def lat(p): f=sorted(glob.glob(os.path.join(LD,p))); return f[-1] if f else None
def col(df,*k):
    for kw in k:
        c=next((x for x in df.columns if kw in x),None)
        if c: return c
    return None
mf=lat("metrics_*.csv")
if not mf: sys.exit("[P3 plot] no metrics CSV")
df=pd.read_csv(mf); df.columns=[c.strip().lower() for c in df.columns]
if "t" not in df.columns and "timestamp" in df.columns:
    df["t"]=df["timestamp"]-df["timestamp"].iloc[0]
af=lat("adjustments_*.csv")
adj=None
if af: adj=pd.read_csv(af); adj.columns=[c.strip().lower() for c in adj.columns]
fig,axes=plt.subplots(2,2,figsize=(14,9))
fig.suptitle("Part 3 — Adaptive fq_codel Controller (AIMD)\nAmritha S, VIT Chennai 2026",
             fontsize=13,fontweight="bold",color="white")
fig.patch.set_facecolor("#0d1117")
def shade(ax):
    if "state" not in df.columns: return
    ps=df["state"].iloc[0];pt=df["t"].iloc[0]
    for _,r in df.iterrows():
        if r["state"]!=ps: ax.axvspan(pt,r["t"],alpha=0.12,color=SC.get(ps,"grey")); ps,pt=r["state"],r["t"]
    ax.axvspan(pt,df["t"].iloc[-1],alpha=0.12,color=SC.get(ps,"grey"))
def vadj(ax):
    if adj is None: return
    tc2=col(adj,"t","time")
    if tc2:
        for v in adj[tc2]: ax.axvline(v,color="white",ls="--",lw=0.7,alpha=0.6)
def fmt(ax,ti,yl):
    ax.set_facecolor("#0d1117");ax.set_title(ti,color="white")
    ax.set_ylabel(yl,color="white");ax.set_xlabel("Time (s)",color="white")
    ax.tick_params(colors="white")
    for sp in ax.spines.values(): sp.set_edgecolor("#444")
tc2=col(df,"throughput");bc=col(df,"backlog");dc=col(df,"drop");tmc=col(df,"target");lmc=col(df,"limit")
ax=axes[0,0];shade(ax);vadj(ax)
if tc2: ax.plot(df["t"],df[tc2],color="#00e5ff",lw=1.2);ax.axhline(10,color="white",ls="--",lw=0.8,alpha=0.5)
fmt(ax,"(a) Throughput","Mbps")
ax=axes[0,1];shade(ax);vadj(ax)
if dc: ax.fill_between(df["t"],df[dc],color="#e53935",alpha=0.75)
fmt(ax,"(b) Drop Rate","drops/sec")
ax=axes[1,0];shade(ax);vadj(ax)
if bc: ax.fill_between(df["t"],df[bc],color="#ffd600",alpha=0.8)
fmt(ax,"(c) Queue Backlog","packets")
ax=axes[1,1];vadj(ax)
if tmc: ax.plot(df["t"],df[tmc],color="#7c4dff",lw=1.5,label="target ms")
if lmc:
    ax2=ax.twinx();ax2.plot(df["t"],df[lmc],color="#ff4081",lw=1.5,ls="--")
    ax2.set_ylabel("limit (pkts)",color="#ff4081");ax2.tick_params(colors="#ff4081")
ax.legend(fontsize=8);fmt(ax,"(d) AIMD Parameter Evolution","target (ms)")
plt.tight_layout()
out=os.path.join(PD,"part3_overview.png")
plt.savefig(out,dpi=150,facecolor="#0d1117");print(f"[PLOT] {out}")
PYEOF

cat > "$SCRIPTS/plot_part4.py" << 'PYEOF'
#!/usr/bin/env python3
import pandas as pd,matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt,glob,os,sys
BASE=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LD=os.path.join(BASE,"logs");PD=os.path.join(BASE,"plots");os.makedirs(PD,exist_ok=True)
SC={"NORMAL":"#00bfa5","LIGHT":"#2979ff","MODERATE":"#ffd600","HEAVY":"#e53935"}
def lat(p): f=sorted(glob.glob(os.path.join(LD,p))); return f[-1] if f else None
def col(df,*k):
    for kw in k:
        c=next((x for x in df.columns if kw in x),None)
        if c: return c
    return None
def load(pat):
    f=lat(pat)
    if not f: return None
    df=pd.read_csv(f);df.columns=[c.strip().lower() for c in df.columns]
    if "t" not in df.columns and "timestamp" in df.columns:
        df["t"]=df["timestamp"]-df["timestamp"].iloc[0]
    return df
def fmt(ax,ti,yl):
    ax.set_facecolor("#0d1117");ax.set_title(ti,color="white")
    ax.set_ylabel(yl,color="white");ax.set_xlabel("Time (s)",color="white")
    ax.tick_params(colors="white")
    for sp in ax.spines.values(): sp.set_edgecolor("#444")
p3=load("metrics_*.csv");p4=load("ebpf_metrics_*.csv")
if p4 is None: sys.exit("[P4 plot] no ebpf_metrics CSV")
fig,axes=plt.subplots(2,3,figsize=(18,10))
fig.suptitle("Part 4 — eBPF-Enhanced Adaptive Controller\nAmritha S, VIT Chennai 2026",
             fontsize=13,fontweight="bold",color="white")
fig.patch.set_facecolor("#0d1117")
tc4=col(p4,"throughput");dc4=col(p4,"drop");bc4=col(p4,"backlog")
tmc4=col(p4,"target");lmc4=col(p4,"limit");fc4=col(p4,"active_flow","flow");ec4=col(p4,"elephant")
ax=axes[0,0]
if tc4: ax.plot(p4["t"],p4[tc4],color="#00e5ff",lw=1.2);ax.axhline(10,color="white",ls="--",lw=0.8,alpha=0.5)
fmt(ax,"(a) Throughput","Mbps")
ax=axes[0,1]
if dc4: ax.fill_between(p4["t"],p4[dc4],color="#e53935",alpha=0.75)
fmt(ax,"(b) Drop Rate","drops/sec")
ax=axes[1,0]
if bc4: ax.fill_between(p4["t"],p4[bc4],color="#ffd600",alpha=0.8)
fmt(ax,"(c) Queue Backlog","packets")
ax=axes[1,1]
if tmc4: ax.plot(p4["t"],p4[tmc4],color="#7c4dff",lw=1.5,label="target ms")
if lmc4:
    ax2=ax.twinx();ax2.plot(p4["t"],p4[lmc4],color="#ff4081",lw=1.5,ls="--")
    ax2.set_ylabel("limit",color="#ff4081");ax2.tick_params(colors="#ff4081")
ax.legend(fontsize=8);fmt(ax,"(d) AIMD Parameter Evolution","target (ms)")
ax=axes[0,2]
if fc4 and fc4 in p4.columns: ax.plot(p4["t"],p4[fc4],color="#69f0ae",lw=1.5,label="active flows")
if ec4 and ec4 in p4.columns: ax.plot(p4["t"],p4[ec4],color="#ff6d00",lw=1.5,label="elephant flows")
if not(fc4 and fc4 in p4.columns):
    ax.text(0.5,0.5,"eBPF flow data\nnot available\n(tc-only mode)",ha="center",va="center",
            transform=ax.transAxes,color="#888",fontsize=11)
ax.legend(fontsize=8);fmt(ax,"(e) Per-Flow Visibility (eBPF)","flows")
ax=axes[1,2]
if "state" in p4.columns:
    sm={"NORMAL":0,"LIGHT":1,"MODERATE":2,"HEAVY":3}
    ax.scatter(p4["t"],p4["state"].map(sm),c=[SC.get(s,"grey") for s in p4["state"]],s=12,zorder=3)
    ax.set_yticks([0,1,2,3]);ax.set_yticklabels(["NORMAL","LIGHT","MODERATE","HEAVY"],color="white")
fmt(ax,"(f) Congestion State Timeline","")
plt.tight_layout()
out=os.path.join(PD,"part4_ebpf_overview.png")
plt.savefig(out,dpi=150,facecolor="#0d1117");print(f"[PLOT] {out}")
if p3 is not None:
    fig2,axes2=plt.subplots(1,3,figsize=(18,5))
    fig2.suptitle("Part 3 vs Part 4 — tc-only vs eBPF-Enhanced",fontsize=13,fontweight="bold",color="white")
    fig2.patch.set_facecolor("#0d1117")
    def cmp(ax,kw,yl,ti):
        c3=col(p3,kw);c4=col(p4,kw)
        if c3 and c3 in p3.columns: ax.fill_between(p3["t"],p3[c3],alpha=0.6,color="#ffd600",label="Part3 tc-only")
        if c4 and c4 in p4.columns: ax.fill_between(p4["t"],p4[c4],alpha=0.5,color="#7c4dff",label="Part4 eBPF")
        ax.legend(fontsize=8);fmt(ax,ti,yl)
    cmp(axes2[0],"backlog","pkts","Queue Backlog Comparison")
    cmp(axes2[1],"drop","drops/sec","Drop Rate Comparison")
    ax=axes2[2];tmc3=col(p3,"target")
    if tmc3 and tmc3 in p3.columns: ax.plot(p3["t"],p3[tmc3],color="#ffd600",lw=1.5,label="Part3")
    if tmc4 and tmc4 in p4.columns: ax.plot(p4["t"],p4[tmc4],color="#7c4dff",lw=1.5,label="Part4")
    ax.legend(fontsize=8);fmt(ax,"AIMD Target Evolution","target (ms)")
    plt.tight_layout()
    out2=os.path.join(PD,"part4_vs_part3_comparison.png")
    plt.savefig(out2,dpi=150,facecolor="#0d1117");print(f"[PLOT] {out2}")
PYEOF

chmod +x "$SCRIPTS"/*.py
success "All scripts written"

# ── NAMESPACE + QDISC SETUP ───────────────────────────────────────────────────
info "Setting up namespaces..."
ip netns del "$NS1" 2>/dev/null||true; ip netns del "$NS2" 2>/dev/null||true
ip link del "$VETH1" 2>/dev/null||true; sleep 0.5
ip netns add "$NS1"; ip netns add "$NS2"
ip link add "$VETH1" type veth peer name "$VETH2"
ip link set "$VETH1" netns "$NS1"; ip link set "$VETH2" netns "$NS2"
ip netns exec "$NS1" ip addr add "${IP1}/24" dev "$VETH1"
ip netns exec "$NS2" ip addr add "${IP2}/24" dev "$VETH2"
ip netns exec "$NS1" ip link set "$VETH1" up; ip netns exec "$NS1" ip link set lo up
ip netns exec "$NS2" ip link set "$VETH2" up; ip netns exec "$NS2" ip link set lo up
success "Namespaces: $NS1($IP1) ↔ $NS2($IP2)"

info "Applying TBF + fq_codel..."
ip netns exec "$NS1" tc qdisc del dev "$VETH1" root 2>/dev/null||true
ip netns exec "$NS1" tc qdisc add dev "$VETH1" root handle 1: tbf rate 10mbit burst 32kbit latency 100ms
ip netns exec "$NS1" tc qdisc add dev "$VETH1" parent 1:1 fq_codel target 5ms interval 100ms limit 1024
success "Qdisc: TBF(10mbit) → fq_codel"

# ── LAUNCH WITH TMUX ──────────────────────────────────────────────────────────
PY=$(command -v python3)
P3="$SCRIPTS/part3_adaptive_controller.py"
P4="$SCRIPTS/part4_ebpf_controller.py"
OBJ="$EBPF_DIR/tc_monitor.o"

info "Launching tmux session 'ccn'..."
tmux kill-session -t ccn 2>/dev/null||true; sleep 0.5

# Window 0: iperf server (persistent — serves both P3 and P4 traffic)
tmux new-session -d -s ccn -n "Server" \
    "bash -c 'echo [SERVER] iperf3 server in ns1; \
    ip netns exec $NS1 iperf3 -s --logfile $LOGS/iperf_server.log; \
    exec bash'"

# Window 1: Part 1 — pfifo_fast static characterisation (runs immediately)
tmux new-window -t ccn -n "Part1" \
    "bash -c 'echo === PART 1: pfifo_fast static characterisation ===; \
    sleep 2; \
    ip netns exec $NS1 tc qdisc del dev $VETH1 root 2>/dev/null; \
    ip netns exec $NS1 tc qdisc add dev $VETH1 root pfifo_fast; \
    ip netns exec $NS2 iperf3 -c $IP1 -P 8 -t 30 --logfile $LOGS/phase1_iperf.log; \
    echo [DONE] Part 1; \
    ip netns exec $NS1 tc qdisc del dev $VETH1 root 2>/dev/null; \
    ip netns exec $NS1 tc qdisc add dev $VETH1 root handle 1: tbf rate 10mbit burst 32kbit latency 100ms; \
    ip netns exec $NS1 tc qdisc add dev $VETH1 parent 1:1 fq_codel target 5ms interval 100ms limit 1024; \
    exec bash'"

# Window 2: Part 2 — namespace testbed (starts after Part 1 clears)
tmux new-window -t ccn -n "Part2" \
    "bash -c 'echo === PART 2: Namespace testbed ===; \
    sleep 35; \
    ip netns exec $NS2 iperf3 -c $IP1 -P 8 -t 30 \
        --json --logfile $LOGS/phase2_iperf.log; \
    echo [DONE] Part 2; exec bash'"

# Window 3: Part 3 — AIMD controller (starts after Part 1+2)
tmux new-window -t ccn -n "Part3-AIMD" \
    "bash -c 'echo === PART 3: Adaptive AIMD Controller ===; \
    sleep 70; \
    $PY $P3 --interface $VETH1 --netns $NS1 --monitor-interval 0.5 --adjust-every 6 --stability-window 3; \
    echo [DONE] Part 3; exec bash'"

# Window 4: Part 3 traffic (synced with Part 3 controller)
tmux new-window -t ccn -n "Traffic-P3" \
    "bash -c 'echo === Part 3 Traffic ===; \
    sleep 72; \
    ip netns exec $NS2 iperf3 -c $IP1 -P 8 -t $PART3_DUR \
        --logfile $LOGS/iperf_p3_traffic.log; \
    echo [DONE] Part 3 traffic; exec bash'"

# Window 5: Part 4 — eBPF controller
tmux new-window -t ccn -n "Part4-eBPF" \
    "bash -c 'echo === PART 4: eBPF-Enhanced Controller ===; \
    sleep $((70 + PART3_DUR + 10)); \
    $PY $P4 --interface $VETH1 --netns $NS1 \
        --ebpf-obj $OBJ --poll 0.5 --stability 3; \
    echo [DONE] Part 4; exec bash'"

# Window 6: Part 4 traffic
tmux new-window -t ccn -n "Traffic-P4" \
    "bash -c 'echo === Part 4 Traffic ===; \
    sleep $((70 + PART3_DUR + 12)); \
    ip netns exec $NS2 iperf3 -c $IP1 -P 8 -t $PART4_DUR \
        --logfile $LOGS/iperf_p4_traffic.log; \
    echo [DONE] Part 4 traffic; exec bash'"

success "tmux session 'ccn' started — 7 windows"
echo ""
echo -e "${BOLD}  ┌─────────────────────────────────────────┐"
echo -e "  │  To watch live:  tmux attach -t ccn    │"
echo -e "  │  Switch windows: Ctrl+B then 0-6       │"
echo -e "  │  Detach (keep running): Ctrl+B then d  │"
echo -e "  └─────────────────────────────────────────┘${NC}"
echo ""

TOTAL=$((70 + PART3_DUR + PART4_DUR + 30))
info "Waiting ${TOTAL}s for experiments... (you can attach tmux now)"
sleep "$TOTAL"

info "Generating plots..."
cd "$PROJECT_DIR"
$PY "$SCRIPTS/plot_part3.py" && success "Part 3 plots done" || warn "Part 3 plot failed (run manually later)"
$PY "$SCRIPTS/plot_part4.py" && success "Part 4 plots done" || warn "Part 4 plot failed (run manually later)"

echo ""
echo -e "${BOLD}${GREEN}═══════════════════════════════════════════════════${NC}"
echo -e "${BOLD}  COMPLETE — Amritha S, VIT Chennai 2026${NC}"
echo -e "  Logs  → ${CYAN}$LOGS${NC}"
echo -e "  Plots → ${CYAN}$PLOTS${NC}"
ls "$PLOTS"/*.png 2>/dev/null | while read f; do echo -e "    ${GREEN}✓${NC} $(basename "$f")"; done
echo -e "${GREEN}═══════════════════════════════════════════════════${NC}"
