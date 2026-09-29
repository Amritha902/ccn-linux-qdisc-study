import csv, glob, os, json, statistics as st
L="/home/user/ccn-linux-qdisc-study/logs/"

def rows(f):
    with open(f) as fh: return list(csv.DictReader(fh))

print("="*78); print("A. ACAPE ADJUSTMENT LOGS — predictive claim"); print("="*78)
tot_p=tot_r=0; runs=[]
for f in sorted(glob.glob(L+"acape_adj_*.csv")):
    rs=rows(f)
    if not rs: continue
    p=sum(1 for r in rs if "[PREDICTIVE]" in r.get("reason",""))
    r_=sum(1 for r in rs if "[REACTIVE]" in r.get("reason",""))
    tot_p+=p; tot_r+=r_
    # did prediction EVER change the applied action? eff regime differs
    diff=sum(1 for r in rs if r.get("regime")!=r.get("predicted"))
    runs.append((os.path.basename(f),len(rs),p,r_,diff))
for n,a,p,r_,d in runs:
    print(f"  {n:38s} adj={a:3d} PRED={p:2d} REACT={r_:2d} regime!=pred:{d:2d}")
print(f"\n  TOTAL adjustments={tot_p+tot_r}  PREDICTIVE={tot_p}  REACTIVE={tot_r}")

print("\n"+"="*78); print("B. Does prediction EVER change the control action?"); print("="*78)
acts=set()
for f in sorted(glob.glob(L+"acape_adj_*.csv")):
    for r in rows(f):
        reason=r.get("reason","")
        act=reason.split("|")[0].replace("[PREDICTIVE]","").replace("[REACTIVE]","").strip()
        acts.add(act)
print("  Distinct control actions applied across ALL runs:")
for a in sorted(acts): print(f"    - {a}")

print("\n"+"="*78); print("C. eBPF flow telemetry (contribution C3)"); print("="*78)
tot=nz_flows=nz_eleph=nz_rtt=nz_ebpfpkts=0
for f in sorted(glob.glob(L+"acape_metrics_*.csv")):
    for r in rows(f):
        tot+=1
        if float(r.get("active_flows",0) or 0)>0: nz_flows+=1
        if float(r.get("elephant_flows",0) or 0)>0: nz_eleph+=1
        if float(r.get("rtt_proxy_ms",0) or 0)>0: nz_rtt+=1
        if float(r.get("ebpf_pkts",0) or 0)>0: nz_ebpfpkts+=1
print(f"  total ticks across all ACAPE runs : {tot}")
print(f"  ticks with active_flows  > 0      : {nz_flows}  ({100*nz_flows/tot:.2f}%)")
print(f"  ticks with elephant_flows> 0      : {nz_eleph}  ({100*nz_eleph/tot:.2f}%)")
print(f"  ticks with rtt_proxy_ms  > 0      : {nz_rtt}  ({100*nz_rtt/tot:.2f}%)")
print(f"  ticks with ebpf_pkts     > 0      : {nz_ebpfpkts}  ({100*nz_ebpfpkts/tot:.2f}%)")
wl={}
for f in sorted(glob.glob(L+"acape_metrics_*.csv")):
    for r in rows(f): wl[r.get("workload_profile")]=wl.get(r.get("workload_profile"),0)+1
print(f"  workload profile distribution     : {wl}")

print("\n"+"="*78); print("D. Drop-rate plausibility (10 Mbit link, 1514B pkts => ~826 pkt/s)"); print("="*78)
MAXPPS=10e6/(1514*8)
for f in sorted(glob.glob(L+"acape_metrics_*.csv"))[:40]:
    drs=[float(r["drop_rate_per_s"]) for r in rows(f) if r.get("drop_rate_per_s")]
    if not drs: continue
    over=sum(1 for d in drs if d>MAXPPS)
    if over:
        print(f"  {os.path.basename(f):40s} max={max(drs):12.1f}/s  median={st.median(drs):9.1f}  ticks_over_link_rate={over}/{len(drs)} ({100*over/len(drs):.0f}%)")
print(f"\n  Physical max packet rate at 10 Mbit = {MAXPPS:.0f} pkt/s")
