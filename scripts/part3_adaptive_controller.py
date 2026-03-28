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
