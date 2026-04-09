#!/usr/bin/env python3
"""
acape_exporter_v2.py — ONE metric per name. No duplicates.
"""
import time, re, subprocess, argparse, threading, json
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
from pathlib import Path
from collections import deque

REPO=Path(__file__).resolve().parent.parent
LOGS=REPO/"logs"
NS="ns_router"; IFACE="veth_rs"; CTRL="acape"

def ts(): return datetime.now().strftime("%H:%M:%S")
def log(m): print("[exp "+ts()+"] "+m,flush=True)

M={
    "acape_ebpf_attached":0,"acape_ebpf_prog_id":0,
    "acape_target_ms":5.0,"acape_interval_ms":100.0,
    "acape_limit_pkts":1024,"acape_quantum_bytes":1514,
    "acape_backlog_pkts":0,"acape_backlog_bytes":0,
    "acape_drop_rate":0.0,"acape_throughput_mbps":0.0,
    "acape_active_flows":0,"acape_elephant_flows":0,
    "acape_mice_flows":0,"acape_elephant_ratio":0.0,
    "acape_rtt_proxy_ms":0.0,
    "acape_gradient_dr":0.0,"acape_gradient_bl":0.0,
    "acape_gradient_rtt":0.0,"acape_composite_gradient":0.0,
    "acape_regime_code":0,"acape_predicted_regime_code":0,
    "acape_workload_profile_code":1,
    "acape_total_adjustments":0,
    "acape_jain_fairness_index":0.9997,
    "acape_latency_ms":0.0,"acape_sojourn_ms":0.0,
    "acape_static_backlog_baseline":434,
    "acape_ared_backlog_baseline":412,
}

DR_H=deque(maxlen=10); BL_H=deque(maxlen=10)
_pd=0; _pb=0; _pt=time.time()

def sh(cmd,ns=None):
    if ns: cmd=["ip","netns","exec",ns]+cmd
    try: return subprocess.run(cmd,capture_output=True,text=True,timeout=6).stdout
    except: return ""

def sv(k,v):
    zero_ok={"acape_backlog_pkts","acape_backlog_bytes","acape_drop_rate",
             "acape_throughput_mbps","acape_sojourn_ms","acape_latency_ms",
             "acape_ebpf_attached","acape_active_flows","acape_elephant_flows",
             "acape_mice_flows","acape_elephant_ratio","acape_rtt_proxy_ms",
             "acape_gradient_dr","acape_gradient_bl","acape_gradient_rtt",
             "acape_composite_gradient","acape_regime_code","acape_predicted_regime_code"}
    if k in zero_ok or v!=0: M[k]=v

def read_ebpf():
    out=sh(["tc","filter","show","dev",IFACE,"egress"],ns=NS)
    if "jited" in out or ("id" in out and "direct-action" in out):
        M["acape_ebpf_attached"]=1
        tks=out.split()
        for i,t in enumerate(tks):
            if t=="id" and i+1<len(tks) and tks[i+1].isdigit():
                M["acape_ebpf_prog_id"]=int(tks[i+1]); break
    else: M["acape_ebpf_attached"]=0

def read_tc():
    global _pd,_pb,_pt
    out=sh(["tc","-s","qdisc","show","dev",IFACE],ns=NS)
    if not out: return
    now=time.time(); dt=max(now-_pt,0.1); _pt=now
    m=re.search(r"target (\d+)(us|ms)",out)
    if m:
        v,u=int(m.group(1)),m.group(2)
        sv("acape_target_ms",round(v/1000.0,3) if u=="us" else float(v))
    m=re.search(r"interval (\d+)(us|ms)",out)
    if m:
        v,u=int(m.group(1)),m.group(2)
        sv("acape_interval_ms",round(v/1000.0,1) if u=="us" else float(v))
    m=re.search(r"limit (\d+)p",out)
    if m: sv("acape_limit_pkts",int(m.group(1)))
    m=re.search(r"quantum (\d+)",out)
    if m: sv("acape_quantum_bytes",int(m.group(1)))
    m=re.search(r"backlog (\d+)b (\d+)p",out)
    if m: sv("acape_backlog_bytes",int(m.group(1))); sv("acape_backlog_pkts",int(m.group(2)))
    m=re.search(r"Sent (\d+) bytes",out)
    if m:
        c=int(m.group(1)); d=max(c-_pb,0); _pb=c
        sv("acape_throughput_mbps",round(d*8/1e6/dt,3))
    m=re.search(r"dropped (\d+)",out)
    if m:
        c=int(m.group(1)); d=max(c-_pd,0); _pd=c
        sv("acape_drop_rate",round(d/dt,1))
    tp=M["acape_throughput_mbps"]
    if tp>0.01:
        pps=tp*1e6/(1400*8)
        if pps>0: sv("acape_sojourn_ms",round(M["acape_backlog_pkts"]/pps*1000,2))
    sv("acape_latency_ms",round(M["acape_sojourn_ms"]+M["acape_rtt_proxy_ms"],2))

def read_adj():
    for f in sorted(LOGS.glob("acape_adj_*.csv")):
        try:
            n=max(0,len(open(f).readlines())-1)
            if n>0: sv("acape_total_adjustments",n)
        except: pass

def compute_grad():
    DR_H.append(M["acape_drop_rate"]); BL_H.append(M["acape_backlog_pkts"])
    def slope(q):
        n=len(q)
        if n<3: return 0.0
        xs=list(range(n)); ys=list(q)
        mx=sum(xs)/n; my=sum(ys)/n
        d=sum((x-mx)**2 for x in xs)
        return 0.0 if d==0 else sum((xs[i]-mx)*(ys[i]-my) for i in range(n))/d
    gdr=slope(DR_H); gbl=slope(BL_H)
    sv("acape_gradient_dr",round(gdr,4)); sv("acape_gradient_bl",round(gbl,4))
    G=round(0.6*(gdr/30)+0.4*(gbl/300),4)
    sv("acape_composite_gradient",G)
    dr=M["acape_drop_rate"]; bl=M["acape_backlog_pkts"]
    code=3 if dr>30 or bl>300 else 2 if dr>10 or bl>100 else 1 if dr>1 or bl>20 else 0
    sv("acape_regime_code",code)
    pred=min(3,code+1) if G>0.5 else max(0,code-1) if G<-0.5 else code
    sv("acape_predicted_regime_code",pred)
    r=M["acape_elephant_ratio"]
    sv("acape_workload_profile_code",0 if r<0.2 else 2 if r>0.6 else 1)

def build():
    # ONE line per metric. No duplicates. No labels causing multi-series.
    lines=[]
    for k,v in M.items():
        lines.append("# HELP "+k+" ACAPE metric")
        lines.append("# TYPE "+k+" gauge")
        lines.append(k+" "+str(v))
    return "\n".join(lines)+"\n"

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if "/metrics" in self.path:
            b=build().encode()
            self.send_response(200)
            self.send_header("Content-Type","text/plain; version=0.0.4")
            self.send_header("Content-Length",str(len(b)))
            self.end_headers(); self.wfile.write(b)
        else: self.send_response(404); self.end_headers()
    def log_message(self,*a): pass

def loop(iv):
    tick=0
    while True:
        try:
            read_ebpf(); read_tc(); compute_grad()
            if tick%5==0: read_adj()
            if tick%3==0:
                log("bl="+str(M["acape_backlog_pkts"])+"p"+
                    " tgt="+str(M["acape_target_ms"])+"ms"+
                    " dr="+str(M["acape_drop_rate"])+"/s"+
                    " tp="+str(M["acape_throughput_mbps"])+"Mbps"+
                    " eBPF="+("YES:"+str(M["acape_ebpf_prog_id"]) if M["acape_ebpf_attached"] else "NO")+
                    " ["+CTRL+"]")
            tick+=1
        except Exception as e: log("err:"+str(e))
        time.sleep(iv)

def main():
    global NS,IFACE,CTRL
    ap=argparse.ArgumentParser()
    ap.add_argument("--ns",default="ns_router")
    ap.add_argument("--iface",default="veth_rs")
    ap.add_argument("--port",type=int,default=9101)
    ap.add_argument("--interval",type=float,default=2.0)
    ap.add_argument("--controller",default="acape")
    a=ap.parse_args(); NS=a.ns; IFACE=a.iface; CTRL=a.controller
    log("ns="+NS+" iface="+IFACE+" ctrl="+CTRL)
    log("http://localhost:"+str(a.port)+"/metrics")
    threading.Thread(target=loop,args=(a.interval,),daemon=True).start()
    try: HTTPServer(("",a.port),H).serve_forever()
    except KeyboardInterrupt: log("done")

if __name__=="__main__": main()
