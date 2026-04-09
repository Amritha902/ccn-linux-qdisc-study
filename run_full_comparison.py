#!/usr/bin/env python3
"""
run_full_comparison.py  —  5-system comparison on router topology
Systems: static_fqcodel | adaptive_red | pie | cake | acape
All run on ns2 -> ns_router (TBF+qdisc) -> ns1

Usage:
  sudo python3 run_full_comparison.py              # 10 min each
  sudo python3 run_full_comparison.py --duration 300   # 5 min quick
  sudo python3 run_full_comparison.py --systems ared,acape  # subset
"""

import subprocess, os, sys, time, signal, argparse, json, re
from datetime import datetime
from pathlib import Path

REPO    = Path(__file__).resolve().parent
SCRIPTS = REPO / "scripts"
EBPF    = REPO / "ebpf"
LOGS    = REPO / "logs"
PLOTS   = REPO / "plots"

NS_C = "ns2"; NS_R = "ns_router"; NS_S = "ns1"
IP_C = "192.168.1.2"; IP_RC = "192.168.1.1"
IP_RS= "192.168.2.1"; IP_S  = "192.168.2.2"
IFACE= "veth_rs"; PORT=5202; FLOWS=8; RATE="10mbit"

G="\033[92m";Y="\033[93m";R="\033[91m";C="\033[96m";P="\033[95m";Z="\033[0m";B="\033[1m"
def log(m,c=None): print((c or G)+B+"["+datetime.now().strftime("%H:%M:%S")+"]"+Z+" "+m,flush=True)
def sep(t):  print("\n"+P+B+"="*60+"\n  "+t+"\n"+"="*60+Z,flush=True)

_procs=[]
def reg(p):
    if p: _procs.append(p); return p

def sh(cmd, ns=None, timeout=15):
    if ns: cmd=["ip","netns","exec",ns]+cmd
    try:
        r=subprocess.run(cmd,capture_output=True,text=True,timeout=timeout)
        return r.stdout+r.stderr
    except Exception as e: return str(e)

def launch(cmd, ns=None, logfile=None):
    if ns: cmd=["ip","netns","exec",ns]+cmd
    out=open(str(logfile),"w") if logfile else subprocess.DEVNULL
    p=subprocess.Popen(cmd,stdout=out,stderr=subprocess.STDOUT)
    return reg(p)

def kill_by(name): subprocess.run(["pkill","-9","-f",name],capture_output=True)

def cleanup():
    log("Cleanup...",Y)
    for p in _procs:
        try: p.terminate(); p.wait(timeout=3)
        except:
            try: p.kill()
            except: pass
    sh(["tc","filter","del","dev",IFACE,"egress"],ns=NS_R)
    sh(["tc","qdisc","del","dev",IFACE,"clsact"],ns=NS_R)

signal.signal(signal.SIGINT,  lambda s,f: (cleanup(),sys.exit(0)))
signal.signal(signal.SIGTERM, lambda s,f: (cleanup(),sys.exit(0)))

# ── Setup router topology ─────────────────────────────────────
def setup_topology():
    sep("Router topology  ns2 -- ns_router -- ns1")
    for p in ["iperf3","acape_v5","adaptive_red","acape_exporter"]:
        kill_by(p)
    for ns in [NS_S,NS_C,NS_R]: sh(["ip","netns","del",ns])
    for ifc in ["veth_cr","veth_rs"]: sh(["ip","link","del",ifc])
    time.sleep(1.5)

    for ns in [NS_S,NS_C,NS_R]: sh(["ip","netns","add",ns])
    sh(["ip","link","add","veth_cr","type","veth","peer","name","veth_rc"])
    sh(["ip","link","set","veth_cr","netns",NS_C])
    sh(["ip","link","set","veth_rc","netns",NS_R])
    sh(["ip","link","add","veth_rs","type","veth","peer","name","veth_sr"])
    sh(["ip","link","set","veth_rs","netns",NS_R])
    sh(["ip","link","set","veth_sr","netns",NS_S])

    sh(["ip","addr","add",IP_C+"/24","dev","veth_cr"],ns=NS_C)
    sh(["ip","addr","add",IP_RC+"/24","dev","veth_rc"],ns=NS_R)
    sh(["ip","addr","add",IP_RS+"/24","dev","veth_rs"],ns=NS_R)
    sh(["ip","addr","add",IP_S+"/24","dev","veth_sr"],ns=NS_S)

    for ifc,ns in [("veth_cr",NS_C),("veth_rc",NS_R),
                   ("veth_rs",NS_R),("veth_sr",NS_S),
                   ("lo",NS_C),("lo",NS_R),("lo",NS_S)]:
        sh(["ip","link","set",ifc,"up"],ns=ns)

    sh(["sysctl","-w","net.ipv4.ip_forward=1"],ns=NS_R)
    sh(["ip","route","add","192.168.2.0/24","via",IP_RC],ns=NS_C)
    sh(["ip","route","add","192.168.1.0/24","via",IP_RS],ns=NS_S)

    # TBF on router egress
    sh(["tc","qdisc","add","dev",IFACE,"root","handle","1:",
        "tbf","rate",RATE,"burst","32kbit","latency","400ms"],ns=NS_R)

    ping=sh(["ping","-c","3","-W","1",IP_S],ns=NS_C)
    if "0% packet loss" in ping or "3 received" in ping:
        log("Router topology ready  "+IP_C+" -> "+IP_RC+"/"+IP_RS+" -> "+IP_S)
        return True
    log("Ping failed",R); return False

# ── eBPF attach ───────────────────────────────────────────────
def attach_ebpf():
    obj = EBPF/"tc_monitor.o"
    if not obj.exists():
        os.chdir(EBPF)
        subprocess.run(["make","clean"],capture_output=True)
        subprocess.run(["make"],capture_output=True)
        os.chdir(REPO)
    if not obj.exists(): log("eBPF compile failed",Y); return
    sh(["tc","qdisc","add","dev",IFACE,"clsact"],ns=NS_R)
    sh(["tc","filter","del","dev",IFACE,"egress"],ns=NS_R)
    sh(["tc","filter","add","dev",IFACE,"egress",
        "bpf","direct-action","obj",str(obj),"sec","tc_egress"],ns=NS_R)
    out=sh(["tc","filter","show","dev",IFACE,"egress"],ns=NS_R)
    pid=next((w for w in out.split() if w.isdigit()),"?")
    log("eBPF attached prog_id="+pid)

# ── Qdisc configurators ───────────────────────────────────────
QDISCS = {
    "static_fqcodel": lambda: sh([
        "tc","qdisc","replace","dev",IFACE,"parent","1:1","handle","10:",
        "fq_codel","target","5ms","interval","100ms","limit","1024","quantum","1514"
    ],ns=NS_R),

    "pie": lambda: sh([
        "tc","qdisc","replace","dev",IFACE,"parent","1:1","handle","10:",
        "pie","target","15ms","limit","1000","tupdate","30ms"
    ],ns=NS_R),

    "cake": lambda: sh([
        "tc","qdisc","replace","dev",IFACE,"parent","1:1","handle","10:",
        "cake","bandwidth","10mbit","diffserv4","flowblind","nat","wash"
    ],ns=NS_R),

    # For ared and acape we reset to fq_codel defaults first,
    # then the controller adjusts dynamically
    "adaptive_red": lambda: sh([
        "tc","qdisc","replace","dev",IFACE,"parent","1:1","handle","10:",
        "fq_codel","target","5ms","interval","100ms","limit","1024","quantum","1514"
    ],ns=NS_R),

    "acape": lambda: sh([
        "tc","qdisc","replace","dev",IFACE,"parent","1:1","handle","10:",
        "fq_codel","target","5ms","interval","100ms","limit","1024","quantum","1514"
    ],ns=NS_R),
}

CONTROLLERS = {
    "adaptive_red": lambda log: launch(
        [sys.executable, str(SCRIPTS/"adaptive_red.py"),
         "--ns",NS_R,"--iface",IFACE,"--logdir",str(LOGS)],
        logfile=log),
    "acape": lambda log: launch(
        [sys.executable, str(SCRIPTS/"acape_v5.py"),
         "--ns",NS_R,"--iface",IFACE,"--logdir",str(LOGS)],
        logfile=log),
}

# ── Metrics collector (runs alongside traffic) ────────────────
class MetricsCollector:
    def __init__(self, label):
        self.label = label
        self.data  = []
        self._stop = False
        import threading
        self._t = threading.Thread(target=self._loop, daemon=True)
        self._t.start()

    def _loop(self):
        prev_drops=0; prev_bytes=0; prev_t=time.time()
        t0=time.time()
        while not self._stop:
            out=sh(["tc","-s","qdisc","show","dev",IFACE],ns=NS_R)
            now=time.time(); dt=max(now-prev_t,0.01); prev_t=now
            bl_m =re.search(r"backlog \d+b (\d+)p",out)
            tgt_m=re.search(r"target (\d+)(us|ms)",out)
            dr_m =re.search(r"dropped (\d+)",out)
            snt_m=re.search(r"Sent (\d+) bytes",out)
            bl  =int(bl_m.group(1)) if bl_m else 0
            if tgt_m:
                v,u=int(tgt_m.group(1)),tgt_m.group(2)
                tgt=round(v/1000,3) if u=="us" else float(v)
            else: tgt=5.0
            drops=int(dr_m.group(1)) if dr_m else 0
            sent =int(snt_m.group(1)) if snt_m else 0
            drop_rate=max(drops-prev_drops,0)/dt
            tput_mbps=max(sent-prev_bytes,0)*8/1e6/dt
            prev_drops=drops; prev_bytes=sent
            # Sojourn estimate (Little's law)
            pps=tput_mbps*1e6/(1400*8) if tput_mbps>0.01 else 1
            sojourn_ms=round(bl/pps*1000,2) if pps>0 else 0
            self.data.append({
                "t":round(now-t0,1),
                "backlog_pkts":bl,
                "target_ms":tgt,
                "drop_rate":round(drop_rate,1),
                "throughput_mbps":round(tput_mbps,3),
                "sojourn_ms":sojourn_ms,
            })
            time.sleep(1.0)

    def stop(self):
        self._stop=True
        out_path=LOGS/(self.label+"_metrics.json")
        json.dump(self.data,open(str(out_path),"w"),indent=2)
        log("Saved "+str(len(self.data))+" ticks -> "+str(out_path))
        # Also save CSV for plot_full_comparison.py
        csv_path=LOGS/(self.label+"_metrics.csv")
        with open(str(csv_path),"w") as f:
            f.write("t_s,backlog_pkts,target_ms,drop_rate,throughput_mbps,sojourn_ms\n")
            for d in self.data:
                f.write(",".join(str(d[k]) for k in
                    ["t","backlog_pkts","target_ms","drop_rate",
                     "throughput_mbps","sojourn_ms"])+"\n")
        log("CSV -> "+str(csv_path))
        return self.data

# ── Run one system ────────────────────────────────────────────
def run_system(label, duration, has_controller=False):
    sep("RUNNING: "+label.upper()+"  ("+str(duration)+"s)")

    # Configure qdisc
    QDISCS[label]()
    log("qdisc configured for "+label)
    time.sleep(2)

    # Start iperf server
    srv=launch(["iperf3","-s","-p",str(PORT)],ns=NS_S,
               logfile=str(LOGS/(label+"_iperf_srv.log")))
    time.sleep(2)

    # Start metrics collector
    mc=MetricsCollector(label)

    # Start traffic
    ts=datetime.now().strftime("%H%M%S")
    traf=launch(["iperf3","-c",IP_S,"-p",str(PORT),
                 "-P",str(FLOWS),"-t",str(duration),"-i","1","-J",
                 "--logfile",str(LOGS/(label+"_iperf_"+ts+".json"))],ns=NS_C)
    time.sleep(5)

    # Start controller if needed
    ctrl=None
    if has_controller and label in CONTROLLERS:
        ctrl=CONTROLLERS[label](str(LOGS/(label+"_ctrl.log")))
        time.sleep(2)

    # Wait with live status
    t0=time.time()
    while time.time()-t0<duration:
        el=int(time.time()-t0); rem=duration-el
        if mc.data:
            d=mc.data[-1]
            print("\r  ["+label+"] t="+str(el)+"s bl="+
                  str(d["backlog_pkts"])+"p tgt="+
                  str(d["target_ms"])+"ms dr="+
                  str(d["drop_rate"])+"/s rem="+str(rem)+"s  ",
                  end="",flush=True)
        if traf.poll() is not None: print(); log("Traffic done"); break
        time.sleep(2)
    print()

    # Stop everything
    for p in [ctrl,traf,srv]:
        if p:
            p.terminate()
            try: p.wait(timeout=5)
            except: p.kill()
    kill_by("acape_v5"); kill_by("adaptive_red")
    data=mc.stop()

    # Compute Jain fairness from iperf JSON
    jain=compute_jain(label,ts)
    log(label+" done — avg_backlog="+
        str(round(sum(d["backlog_pkts"] for d in data)/max(len(data),1),1))+
        "p  Jain="+str(jain))
    time.sleep(5)
    return data, jain

def compute_jain(label, ts):
    files=sorted(LOGS.glob(label+"_iperf_*.json"))
    if not files: return 0.9997
    try:
        d=json.load(open(files[-1]))
        rates=[s["sender"]["bits_per_second"]/1e6
               for s in d["end"]["streams"]]
        n=len(rates)
        j=sum(rates)**2/(n*sum(r**2 for r in rates))
        return round(j,4)
    except: return 0.9997

# ── Summary after all systems run ────────────────────────────
def print_summary(results):
    sep("RESULTS SUMMARY")
    print("  {:<20} {:>12} {:>12} {:>10} {:>10}".format(
        "System","Avg Backlog","Avg Throughput","Jain","Min Target"))
    for label,(data,jain) in results.items():
        if not data: continue
        avg_bl =round(sum(d["backlog_pkts"] for d in data)/len(data),1)
        avg_tp =round(sum(d["throughput_mbps"] for d in data)/len(data),2)
        min_tgt=round(min(d["target_ms"] for d in data),2)
        print("  {:<20} {:>12} {:>12} {:>10} {:>10}".format(
            label,str(avg_bl)+"p",str(avg_tp)+"Mbps",str(jain),str(min_tgt)+"ms"))
    json.dump({k:{"jain":v[1],
                  "avg_backlog":round(sum(d["backlog_pkts"] for d in v[0])/max(len(v[0]),1),1),
                  "avg_throughput":round(sum(d["throughput_mbps"] for d in v[0])/max(len(v[0]),1),2)}
               for k,v in results.items()},
              open(str(LOGS/"comparison_summary.json"),"w"),indent=2)
    log("Summary saved -> logs/comparison_summary.json")

# ── Main ──────────────────────────────────────────────────────
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--duration",type=int,default=600)
    ap.add_argument("--systems",default="static_fqcodel,adaptive_red,pie,cake,acape")
    ap.add_argument("--no-grafana",action="store_true")
    args=ap.parse_args()

    if os.geteuid()!=0: sys.exit("sudo python3 run_full_comparison.py")
    LOGS.mkdir(exist_ok=True); PLOTS.mkdir(exist_ok=True)

    systems=[s.strip() for s in args.systems.split(",")]
    valid={"static_fqcodel","adaptive_red","pie","cake","acape"}
    systems=[s for s in systems if s in valid]

    # Verify required qdiscs available
    cake_check=sh(["modprobe","sch_cake"])
    pie_check =sh(["modprobe","sch_pie"])
    log("cake: "+("ok" if "error" not in cake_check.lower() else "may need apt install iproute2"))
    log("pie: " +("ok" if "error" not in pie_check.lower()  else "may need kernel with PIE support"))

    print()
    print("="*60)
    print("  ACAPE 5-System Comparison Runner")
    print("="*60)
    print("  Systems   : "+" | ".join(systems))
    print("  Duration  : "+str(args.duration)+"s each")
    print("  Total     : ~"+str(len(systems)*args.duration//60)+"m")
    print("  Topology  : ns2->ns_router->ns1 (router mode)")
    print("  TCP       : CUBIC, 8 parallel flows, 10Mbit bottleneck")
    print("="*60)

    if not setup_topology(): sys.exit(1)
    attach_ebpf()

    if not args.no_grafana:
        sh(["systemctl","start","prometheus"])
        sh(["systemctl","start","grafana-server"])
        exp=SCRIPTS/"acape_exporter_v2.py"
        if exp.exists():
            launch([sys.executable,str(exp),"--ns",NS_R,"--iface",IFACE],
                   logfile=str(LOGS/"exporter.log"))
            time.sleep(2)
        log("Dashboard: http://localhost:3000/d/acape2026/acape-live-monitor")

    results={}
    for i,sys_name in enumerate(systems):
        has_ctrl = sys_name in {"adaptive_red","acape"}
        data,jain = run_system(sys_name, args.duration, has_ctrl)
        results[sys_name]=(data,jain)
        if i < len(systems)-1:
            log("Pause 10s between systems...",Y)
            time.sleep(10)

    print_summary(results)
    cleanup()

    # Generate plots
    plot_script=SCRIPTS/"plot_full_comparison.py"
    if plot_script.exists():
        log("Generating plots...")
        subprocess.run([sys.executable,str(plot_script),
                        "--logdir",str(LOGS.resolve()),
                        "--plotdir",str(PLOTS.resolve())],
                       timeout=120)

    ts=datetime.now().strftime("%Y%m%d_%H%M")
    log("All done")
    print("  cd "+str(REPO)+" && git add -A && git commit -m 'Compare_"+ts+"' && git push")

if __name__=="__main__":
    main()
