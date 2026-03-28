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
