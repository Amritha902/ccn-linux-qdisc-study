#!/usr/bin/env python3
"""
orchestrator.py -- ACAPE Master Orchestrator
One command runs everything.

sudo python3 orchestrator.py --mode comparison --duration 600
sudo python3 orchestrator.py --mode full       --duration 600
sudo python3 orchestrator.py --mode acape      --duration 900
sudo python3 orchestrator.py --mode fairness
sudo python3 orchestrator.py --simple          # flat topology
"""

import subprocess, os, sys, time, signal, argparse, json, re
from datetime import datetime
from pathlib import Path

REPO     = Path(__file__).resolve().parent
SCRIPTS  = REPO / "scripts"
EBPF_DIR = REPO / "ebpf"
LOGS     = REPO / "logs"
PLOTS    = REPO / "plots"

NS_CLIENT="ns2"; NS_SERVER="ns1"; NS_ROUTER="ns_router"
IP_S="10.0.0.1";  IP_C="10.0.0.2";  IF_S="veth1"
IP_CR="192.168.1.2"; IP_RC="192.168.1.1"
IP_RS="192.168.2.1"; IP_SR="192.168.2.2"; IF_R="veth_rs"
PORT=5202; FLOWS=8; RATE="10mbit"

G="\033[92m";Y="\033[93m";R="\033[91m";C="\033[96m";P="\033[95m";Z="\033[0m";B="\033[1m"
def log(m,c=None): print((c or G)+B+"["+datetime.now().strftime("%H:%M:%S")+"]"+Z+" "+m,flush=True)
def warn(m): print(Y+"[WARN] "+Z+m,flush=True)
def err(m):  print(R+"[ERR]  "+Z+m,flush=True)
def sep(t):  print("\n"+P+B+"="*56+"\n  "+t+"\n"+"="*56+Z,flush=True)

_procs=[]
def reg(p):
    if p: _procs.append(p)
    return p

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
    log("Stopping all processes...",Y)
    for p in _procs:
        try: p.terminate(); p.wait(timeout=3)
        except:
            try: p.kill()
            except: pass
    for ifc,ns in [(IF_S,NS_SERVER),(IF_R,NS_ROUTER)]:
        sh(["tc","filter","del","dev",ifc,"egress"],ns=ns)
        sh(["tc","qdisc","del","dev",ifc,"clsact"],ns=ns)
    log("Cleanup done",Y)

def stop_signal(sig,frame):
    print(); log("Ctrl+C",Y); cleanup(); run_plots(); sys.exit(0)

def kill_all():
    for p in ["iperf3","acape_v5","adaptive_red","acape_exporter"]: kill_by(p)
    time.sleep(1.5)

# ── Simple topology ───────────────────────────────────────────
def setup_simple():
    sep("Simple topology  ns2 -- veth1 -- ns1")
    kill_all()
    sh(["ip","netns","del",NS_SERVER]); sh(["ip","netns","del",NS_CLIENT])
    sh(["ip","link","del",IF_S]); time.sleep(1)
    for cmd in [
        ["ip","netns","add",NS_SERVER],["ip","netns","add",NS_CLIENT],
        ["ip","link","add",IF_S,"type","veth","peer","name","veth2"],
        ["ip","link","set",IF_S,"netns",NS_SERVER],
        ["ip","link","set","veth2","netns",NS_CLIENT],
    ]: sh(cmd)
    sh(["ip","addr","add",IP_S+"/24","dev",IF_S],ns=NS_SERVER)
    sh(["ip","addr","add",IP_C+"/24","dev","veth2"],ns=NS_CLIENT)
    for ifc,ns in [(IF_S,NS_SERVER),("veth2",NS_CLIENT),("lo",NS_SERVER),("lo",NS_CLIENT)]:
        sh(["ip","link","set",ifc,"up"],ns=ns)
    sh(["tc","qdisc","add","dev",IF_S,"root","handle","1:",
        "tbf","rate",RATE,"burst","32kbit","latency","400ms"],ns=NS_SERVER)
    sh(["tc","qdisc","add","dev",IF_S,"parent","1:1","handle","10:",
        "fq_codel","target","5ms","interval","100ms","limit","1024","quantum","1514"],ns=NS_SERVER)
    ping=sh(["ping","-c","3","-W","1",IP_S],ns=NS_CLIENT)
    if "0% packet loss" in ping or "3 received" in ping:
        log("Simple topology ready"); return IF_S,NS_SERVER,IP_S
    err("Ping failed"); sys.exit(1)

# ── Router topology ───────────────────────────────────────────
def setup_router():
    sep("Router topology  ns2 -- ns_router -- ns1")
    kill_all()
    for ns in [NS_SERVER,NS_CLIENT,NS_ROUTER]: sh(["ip","netns","del",ns])
    for ifc in [IF_S,"veth_cr","veth_rs"]: sh(["ip","link","del",ifc])
    time.sleep(1.5)
    for ns in [NS_SERVER,NS_CLIENT,NS_ROUTER]: sh(["ip","netns","add",ns])
    sh(["ip","link","add","veth_cr","type","veth","peer","name","veth_rc"])
    sh(["ip","link","set","veth_cr","netns",NS_CLIENT])
    sh(["ip","link","set","veth_rc","netns",NS_ROUTER])
    sh(["ip","link","add","veth_rs","type","veth","peer","name","veth_sr"])
    sh(["ip","link","set","veth_rs","netns",NS_ROUTER])
    sh(["ip","link","set","veth_sr","netns",NS_SERVER])
    sh(["ip","addr","add",IP_CR+"/24","dev","veth_cr"],ns=NS_CLIENT)
    sh(["ip","addr","add",IP_RC+"/24","dev","veth_rc"],ns=NS_ROUTER)
    sh(["ip","addr","add",IP_RS+"/24","dev","veth_rs"],ns=NS_ROUTER)
    sh(["ip","addr","add",IP_SR+"/24","dev","veth_sr"],ns=NS_SERVER)
    for ifc,ns in [("veth_cr",NS_CLIENT),("veth_rc",NS_ROUTER),
                   ("veth_rs",NS_ROUTER),("veth_sr",NS_SERVER),
                   ("lo",NS_CLIENT),("lo",NS_ROUTER),("lo",NS_SERVER)]:
        sh(["ip","link","set",ifc,"up"],ns=ns)
    sh(["sysctl","-w","net.ipv4.ip_forward=1"],ns=NS_ROUTER)
    sh(["ip","route","add","192.168.2.0/24","via",IP_RC],ns=NS_CLIENT)
    sh(["ip","route","add","192.168.1.0/24","via",IP_RS],ns=NS_SERVER)
    sh(["tc","qdisc","add","dev","veth_rs","root","handle","1:",
        "tbf","rate",RATE,"burst","32kbit","latency","400ms"],ns=NS_ROUTER)
    sh(["tc","qdisc","add","dev","veth_rs","parent","1:1","handle","10:",
        "fq_codel","target","5ms","interval","100ms","limit","1024","quantum","1514"],ns=NS_ROUTER)
    ping=sh(["ping","-c","3","-W","1",IP_SR],ns=NS_CLIENT)
    if "0% packet loss" in ping or "3 received" in ping:
        log("Router topology ready  ns2("+IP_CR+") -> ns_router -> ns1("+IP_SR+")")
        return IF_R,NS_ROUTER,IP_SR
    err("Ping failed"); sys.exit(1)

# ── eBPF ──────────────────────────────────────────────────────
def setup_ebpf(iface,ns_ctrl):
    sep("Building + attaching eBPF")
    os.chdir(EBPF_DIR)
    subprocess.run(["make","clean"],capture_output=True)
    subprocess.run(["make"],capture_output=True)
    os.chdir(REPO)
    if not (EBPF_DIR/"tc_monitor.o").exists():
        warn("eBPF compile failed"); return
    sh(["tc","qdisc","add","dev",iface,"clsact"],ns=ns_ctrl)
    sh(["tc","filter","del","dev",iface,"egress"],ns=ns_ctrl)
    sh(["tc","filter","add","dev",iface,"egress",
        "bpf","direct-action","obj",str(EBPF_DIR/"tc_monitor.o"),"sec","tc_egress"],ns=ns_ctrl)
    out=sh(["tc","filter","show","dev",iface,"egress"],ns=ns_ctrl)
    pid=next((w for w in out.split() if w.isdigit()),"?")
    log("eBPF attached -- prog_id="+pid+" JIT compiled")

# ── Monitoring ────────────────────────────────────────────────
def start_monitoring(iface,ns_ctrl):
    sep("Prometheus + Grafana + Exporter v2")
    sh(["systemctl","start","prometheus"])
    sh(["systemctl","start","grafana-server"])
    time.sleep(2)
    # Use v2 exporter if available, fall back to original
    exp_v2 = SCRIPTS/"acape_exporter_v2.py"
    exp_v1 = SCRIPTS/"acape_exporter.py"
    exp    = exp_v2 if exp_v2.exists() else exp_v1
    log("Starting exporter: "+exp.name)
    launch([sys.executable,str(exp),"--ns",ns_ctrl,"--iface",iface],
           logfile=str(LOGS/("exporter.log")))
    time.sleep(2)
    log("Dashboard: http://localhost:3000/d/acape2026/acape-live-monitor")

# ── fq_codel reset ────────────────────────────────────────────
def reset_fq(iface,ns_ctrl):
    sh(["tc","qdisc","change","dev",iface,"parent","1:1","handle","10:",
        "fq_codel","target","5ms","interval","100ms","limit","1024","quantum","1514"],ns=ns_ctrl)
    log("fq_codel reset: target=5ms limit=1024 quantum=1514")

# ── Status ────────────────────────────────────────────────────
def show_status(iface,ns_ctrl,label,el,rem):
    out=sh(["tc","-s","qdisc","show","dev",iface],ns=ns_ctrl)
    bl =(re.search(r"backlog \d+b (\d+)p",out) or type("",(),{"group":lambda s,i:"?"})()).group(1)
    tm =re.search(r"target (\d+)(us|ms)",out)
    if tm:
        v,u=int(tm.group(1)),tm.group(2)
        tgt=str(round(v/1000.0,1))+"ms" if u=="us" else str(v)+"ms"
    else: tgt="?"
    print("\r  ["+label+"] t="+str(el)+"s rem="+str(rem)+"s  bl="+str(bl)+"p  tgt="+tgt+"   ",end="",flush=True)

# ── Run one phase ─────────────────────────────────────────────
def run_phase(label,duration,iface,ns_ctrl,server_ip,ctrl_cmd,ctrl_log):
    sep("PHASE: "+label+"  ("+str(duration)+"s / "+str(duration//60)+"m)")
    srv=launch(["iperf3","-s","-p",str(PORT)],ns=NS_SERVER,
               logfile=str(LOGS/("iperf_srv_"+label+".log")))
    time.sleep(2)
    ts=datetime.now().strftime("%H%M%S")
    traf=launch(["iperf3","-c",server_ip,"-p",str(PORT),
                 "-P",str(FLOWS),"-t",str(duration),"-i","10",
                 "--logfile",str(LOGS/("iperf_"+label+"_"+ts+".log"))],ns=NS_CLIENT)
    time.sleep(5)
    ctrl=launch(ctrl_cmd,logfile=ctrl_log)
    time.sleep(2)
    t0=time.time()
    while time.time()-t0<duration:
        el=int(time.time()-t0); rem=duration-el
        show_status(iface,ns_ctrl,label,el,rem)
        if traf.poll() is not None: print(); log("Traffic done"); break
        time.sleep(5)
    print()
    for p in [ctrl,traf,srv]:
        p.terminate()
        try: p.wait(timeout=5)
        except: p.kill()
    _procs[:]=[p for p in _procs if p.poll() is None]
    time.sleep(3); log(label+" complete")

# ── Fairness ──────────────────────────────────────────────────
def run_fairness(iface,ns_ctrl,server_ip,label="ACAPE"):
    sep("Jain Fairness Index -- "+label)
    reset_fq(iface,ns_ctrl)
    srv=launch(["iperf3","-s","-p",str(PORT)],ns=NS_SERVER,
               logfile=str(LOGS/("fair_srv.log")))
    time.sleep(2)
    ts=datetime.now().strftime("%H%M%S")
    outj=str(LOGS/("fairness_"+label+"_"+ts+".json"))
    log("Measuring 30s...")
    sh(["iperf3","-c",server_ip,"-p",str(PORT),
        "-P",str(FLOWS),"-t","30","-J","--logfile",outj],ns=NS_CLIENT,timeout=45)
    srv.terminate()
    try: srv.wait(timeout=3)
    except: pass
    try:
        d=json.load(open(outj))
        rates=[s["sender"]["bits_per_second"]/1e6 for s in d["end"]["streams"]]
        n=len(rates); jain=sum(rates)**2/(n*sum(r**2 for r in rates)); tot=sum(rates)
        print()
        log("Fairness -- "+label)
        for i,r in enumerate(rates): print("  Flow "+str(i+1)+": "+str(round(r,3))+" Mbps")
        log("Jain index  : "+str(round(jain,4))+" (1.0=perfect)")
        log("Total tput  : "+str(round(tot,2))+" Mbps")
        summary={"label":label,"jain":round(jain,4),"total_mbps":round(tot,2),
                 "n_flows":n,"per_flow":[round(r,3) for r in rates],
                 "ts":datetime.now().isoformat()}
        json.dump(summary,open(str(LOGS/("fair_summary_"+label+".json")),"w"),indent=2)
        log("Saved: logs/fair_summary_"+label+".json")
        return round(jain,4)
    except Exception as e:
        warn("Fairness parse failed: "+str(e)); return None

# ── Plots ─────────────────────────────────────────────────────
def run_plots():
    PLOTS.mkdir(exist_ok=True)
    sep("Generating plots")
    for sc in ["plot_acape.py","plot_comparison.py"]:
        sf=SCRIPTS/sc
        if not sf.exists(): warn(sc+" not found"); continue
        try:
            subprocess.run([sys.executable,str(sf),
                            "--logdir",str(LOGS.resolve()),
                            "--plotdir",str(PLOTS.resolve())],
                           timeout=90,capture_output=True)
            log(sc+" done")
        except Exception as e: warn(sc+" failed: "+str(e))
    log("Plots: "+str(len(list(PLOTS.glob("*.png"))))+" files")

# ── Phase helpers ─────────────────────────────────────────────
def do_ared(iface,ns_ctrl,server_ip,duration):
    reset_fq(iface,ns_ctrl)
    sc=SCRIPTS/"adaptive_red.py"
    if not sc.exists(): warn("adaptive_red.py not in scripts/"); return
    run_phase("AdaptiveRED",duration,iface,ns_ctrl,server_ip,
              [sys.executable,str(sc),
               "--ns",ns_ctrl,"--iface",iface,
               "--logdir",str(LOGS),"--duration",str(duration+30)],
              str(LOGS/("ared_phase.log")))

def do_acape(iface,ns_ctrl,server_ip,duration):
    reset_fq(iface,ns_ctrl)
    sc=SCRIPTS/"acape_v5.py"
    if not sc.exists(): warn("acape_v5.py not in scripts/"); return
    run_phase("ACAPE",duration,iface,ns_ctrl,server_ip,
              [sys.executable,str(sc),
               "--ns",ns_ctrl,"--iface",iface,"--logdir",str(LOGS)],
              str(LOGS/("acape_phase.log")))

# ── Main ──────────────────────────────────────────────────────
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--mode",default="comparison",
                    choices=["comparison","acape","ared","fairness","full"])
    ap.add_argument("--duration",type=int,default=600)
    ap.add_argument("--simple",action="store_true")
    ap.add_argument("--no-grafana",action="store_true")
    ap.add_argument("--no-ebpf",action="store_true")
    args=ap.parse_args()

    if os.geteuid()!=0: sys.exit("sudo python3 orchestrator.py")
    signal.signal(signal.SIGINT,stop_signal)
    signal.signal(signal.SIGTERM,stop_signal)
    LOGS.mkdir(exist_ok=True); PLOTS.mkdir(exist_ok=True)

    print()
    print("="*56)
    print("  ACAPE Master Orchestrator -- VIT Chennai 2026")
    print("="*56)
    print("  Mode      : "+args.mode)
    print("  Duration  : "+str(args.duration)+"s per phase ("+str(args.duration//60)+"m)")
    print("  Topology  : "+("simple 2-node" if args.simple else "router 3-node"))
    print("  TCP       : CUBIC (Linux default)")
    print("  Flows     : "+str(FLOWS)+" parallel")
    print("  Bottleneck: "+RATE)
    print("="*56); print()

    if args.simple: iface,ns_ctrl,server_ip=setup_simple()
    else:           iface,ns_ctrl,server_ip=setup_router()

    if not args.no_ebpf: setup_ebpf(iface,ns_ctrl)
    if not args.no_grafana: start_monitoring(iface,ns_ctrl)

    if args.mode=="comparison":
        do_ared(iface,ns_ctrl,server_ip,args.duration)
        kill_by("adaptive_red")
        sep("RESET -- 15s boundary in Grafana")
        reset_fq(iface,ns_ctrl); time.sleep(15)
        do_acape(iface,ns_ctrl,server_ip,args.duration)

    elif args.mode=="full":
        do_ared(iface,ns_ctrl,server_ip,args.duration)
        kill_by("adaptive_red")
        sep("RESET"); reset_fq(iface,ns_ctrl); time.sleep(15)
        do_acape(iface,ns_ctrl,server_ip,args.duration)
        kill_by("acape_v5")
        sep("RESET -- fairness tests"); reset_fq(iface,ns_ctrl); time.sleep(15)
        do_ared(iface,ns_ctrl,server_ip,args.duration//2)
        kill_by("adaptive_red")
        run_fairness(iface,ns_ctrl,server_ip,label="ARED_fairness")
        reset_fq(iface,ns_ctrl); time.sleep(15)
        do_acape(iface,ns_ctrl,server_ip,args.duration//2)
        kill_by("acape_v5")
        run_fairness(iface,ns_ctrl,server_ip,label="ACAPE_fairness")

    elif args.mode=="acape":
        do_acape(iface,ns_ctrl,server_ip,args.duration)

    elif args.mode=="ared":
        do_ared(iface,ns_ctrl,server_ip,args.duration)

    elif args.mode=="fairness":
        do_acape(iface,ns_ctrl,server_ip,min(args.duration,120))
        kill_by("acape_v5")
        run_fairness(iface,ns_ctrl,server_ip,label="ACAPE_fairness")

    sep("ALL DONE")
    cleanup(); run_plots()
    print()
    log("Logs  : "+str(LOGS))
    log("Plots : "+str(PLOTS))
    print()
    log("Grafana screenshots:")
    print("  1. Full timeline -- ARED vs ACAPE boundary")
    print("  2. target -- ARED flat vs ACAPE staircase 5ms->1ms")
    print("  3. backlog -- slower ARED vs faster ACAPE")
    print("  4. Gradient signals C1  5. eBPF flows C3  6. Topology panel")
    print()
    ts=datetime.now().strftime("%Y%m%d_%H%M")
    print("  git add -A && git commit -m 'ACAPE_"+ts+"' && git push")

if __name__=="__main__": main()
