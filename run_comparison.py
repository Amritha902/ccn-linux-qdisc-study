#!/usr/bin/env python3
"""
run_comparison.py — Sequential ARED vs ACAPE comparison
Runs Adaptive RED for N minutes, then ACAPE for N minutes.
Both export to Prometheus. Grafana shows both on same timeline.

Usage:
  sudo python3 run_comparison.py               # 10 min each
  sudo python3 run_comparison.py --duration 600  # 10 min each
  sudo python3 run_comparison.py --duration 300  # 5 min each (quick test)
"""

import subprocess, os, sys, time, signal, argparse, json, re
from datetime import datetime
from pathlib import Path

REPO     = Path(__file__).resolve().parent
SCRIPTS  = REPO / "scripts"
EBPF_DIR = REPO / "ebpf"
LOGS     = REPO / "logs"
NS1      = "ns1"
NS2      = "ns2"
IP1      = "10.0.0.1"
IFACE    = "veth1"
PORT     = 5202
RATE     = "10mbit"
FLOWS    = 8

G="\033[92m"; Y="\033[93m"; R="\033[91m"; C="\033[96m"; Z="\033[0m"; B="\033[1m"
def log(m, c=None): print((c or G)+B+"["+datetime.now().strftime("%H:%M:%S")+"]"+Z+" "+m, flush=True)
def warn(m): print(Y+"[WARN] "+Z+m, flush=True)
def err(m):  print(R+"[ERR] "+Z+m, flush=True)
def sep(title): print("\n"+C+B+"━"*52+"\n  "+title+"\n"+"━"*52+Z+"\n", flush=True)

_procs = []
def register(p):
    if p: _procs.append(p)
    return p

def shell(cmd, ns=None, timeout=15):
    if ns: cmd = ["ip","netns","exec",ns]+cmd
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout+r.stderr
    except Exception as e:
        return str(e)

def start(cmd, ns=None, logfile=None):
    if ns: cmd = ["ip","netns","exec",ns]+cmd
    out = open(logfile,"w") if logfile else subprocess.DEVNULL
    p = subprocess.Popen(cmd, stdout=out, stderr=subprocess.STDOUT)
    return register(p)

def kill_controllers():
    for proc in ["acape_v5","adaptive_red","acape_exporter"]:
        subprocess.run(["pkill","-9","-f",proc], capture_output=True)
    time.sleep(2)

def cleanup():
    log("Cleaning up...", Y)
    for p in _procs:
        try: p.terminate(); p.wait(timeout=3)
        except:
            try: p.kill()
            except: pass
    shell(["tc","filter","del","dev",IFACE,"egress"], ns=NS1)
    shell(["tc","qdisc","del","dev",IFACE,"clsact"], ns=NS1)

def signal_handler(sig, frame):
    print()
    log("Stopping...", Y)
    cleanup()
    sys.exit(0)

def reset_fqcodel():
    shell(["tc","qdisc","change","dev",IFACE,"parent","1:1","handle","10:",
           "fq_codel","target","5ms","interval","100ms",
           "limit","1024","quantum","1514"], ns=NS1)
    log("fq_codel reset to defaults (target=5ms)")

def setup_namespace():
    log("Setting up namespace — "+RATE)
    for proc in ["iperf3","acape_v5","adaptive_red","acape_exporter"]:
        subprocess.run(["pkill","-9","-f",proc], capture_output=True)
    time.sleep(1)
    shell(["ip","netns","del",NS1]); shell(["ip","netns","del",NS2])
    shell(["ip","link","del",IFACE]); time.sleep(1)

    for cmd in [
        ["ip","netns","add",NS1], ["ip","netns","add",NS2],
        ["ip","link","add",IFACE,"type","veth","peer","name","veth2"],
        ["ip","link","set",IFACE,"netns",NS1],
        ["ip","link","set","veth2","netns",NS2],
    ]: shell(cmd)

    shell(["ip","addr","add",IP1+"/24","dev",IFACE], ns=NS1)
    shell(["ip","addr","add","10.0.0.2/24","dev","veth2"], ns=NS2)
    for ifc,ns in [(IFACE,NS1),("veth2",NS2),("lo",NS1),("lo",NS2)]:
        shell(["ip","link","set",ifc,"up"], ns=ns)

    shell(["tc","qdisc","add","dev",IFACE,"root","handle","1:",
           "tbf","rate",RATE,"burst","32kbit","latency","400ms"], ns=NS1)
    shell(["tc","qdisc","add","dev",IFACE,"parent","1:1","handle","10:",
           "fq_codel","target","5ms","interval","100ms",
           "limit","1024","quantum","1514"], ns=NS1)

    ping = shell(["ping","-c","3","-W","1",IP1], ns=NS2)
    ok = "0% packet loss" in ping or "3 received" in ping
    if ok: log("Namespace ready")
    else:  err("Ping failed!"); sys.exit(1)

def setup_ebpf():
    log("Building + attaching eBPF...")
    os.chdir(EBPF_DIR)
    subprocess.run(["make","clean"], capture_output=True)
    subprocess.run(["make"], capture_output=True)
    os.chdir(REPO)
    if not (EBPF_DIR/"tc_monitor.o").exists():
        warn("eBPF compile failed — tc-only mode"); return
    shell(["tc","qdisc","add","dev",IFACE,"clsact"], ns=NS1)
    shell(["tc","filter","del","dev",IFACE,"egress"], ns=NS1)
    shell(["tc","filter","add","dev",IFACE,"egress",
           "bpf","direct-action",
           "obj",str(EBPF_DIR/"tc_monitor.o"),
           "sec","tc_egress"], ns=NS1)
    out = shell(["tc","filter","show","dev",IFACE,"egress"], ns=NS1)
    pid = next((w for w in out.split() if w.isdigit()),"?")
    log("eBPF attached — prog_id="+pid)

def start_monitoring():
    log("Starting Prometheus + Grafana + exporter...")
    shell(["systemctl","start","prometheus"])
    shell(["systemctl","start","grafana-server"])
    time.sleep(2)
    start([sys.executable, str(SCRIPTS/"acape_exporter.py"),
           "--ns",NS1,"--iface",IFACE],
          logfile=str(LOGS/"exporter.log"))
    time.sleep(2)
    log("Grafana: http://localhost:3000/d/acape2026/acape-live-monitor")

def wait_with_status(duration, label):
    start_t = time.time()
    while time.time()-start_t < duration:
        elapsed   = int(time.time()-start_t)
        remaining = duration-elapsed
        # Read latest tc stats for live display
        out = shell(["tc","-s","qdisc","show","dev",IFACE], ns=NS1)
        bl_m = re.search(r"backlog \d+b (\d+)p", out)
        bl = bl_m.group(1) if bl_m else "?"
        dr_m = re.search(r"dropped (\d+)", out)
        print("\r  ["+label+"] t="+str(elapsed)+"s  remaining="+str(remaining)+"s  backlog="+bl+"p  ",
              end="", flush=True)
        time.sleep(5)
    print()

def run_phase(label, duration, controller_cmd, logfile):
    log("Starting traffic ("+str(FLOWS)+" flows, "+str(duration)+"s)...")
    ts = datetime.now().strftime("%H%M%S")
    traffic_p = start(
        ["iperf3","-c",IP1,"-p",str(PORT),
         "-P",str(FLOWS),"-t",str(duration),
         "-i","10","--logfile",str(LOGS/("iperf_"+label+"_"+ts+".log"))],
        ns=NS2
    )
    time.sleep(5)

    log("Starting "+label+" controller...")
    ctrl_p = start(controller_cmd, logfile=logfile)
    time.sleep(2)

    wait_with_status(duration, label)

    # Stop controller and traffic
    ctrl_p.terminate()
    try: ctrl_p.wait(timeout=5)
    except: ctrl_p.kill()
    traffic_p.terminate()
    try: traffic_p.wait(timeout=5)
    except: traffic_p.kill()

    time.sleep(3)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration",   type=int, default=600, help="Duration per controller in seconds")
    parser.add_argument("--no-grafana", action="store_true")
    args = parser.parse_args()

    if os.geteuid()!=0: sys.exit("sudo python3 run_comparison.py")

    signal.signal(signal.SIGINT,  signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    LOGS.mkdir(exist_ok=True)

    print()
    print("="*52)
    print("  ARED vs ACAPE Comparison — VIT Chennai 2026")
    print("="*52)
    print("  Each controller runs for: "+str(args.duration)+"s ("+str(args.duration//60)+"m)")
    print("  Total time: "+str(args.duration*2)+"s ("+str((args.duration*2)//60)+"m)")
    print("  Bottleneck: "+RATE+", "+str(FLOWS)+" TCP flows")
    print("="*52)
    print()

    # Setup (once)
    log("Setting up testbed...")
    setup_namespace()
    setup_ebpf()

    # Start iperf server (persistent)
    log("Starting iperf server in ns1...")
    start(["iperf3","-s","-p",str(PORT)], ns=NS1,
          logfile=str(LOGS/"iperf_server_comparison.log"))
    time.sleep(2)

    if not args.no_grafana:
        start_monitoring()

    # ── PHASE 1: Adaptive RED ─────────────────────────────────
    sep("PHASE 1 — Adaptive RED (Floyd 2001)")
    log("fq_codel starting at default 5ms target")
    log("ARED will adapt max_p → mapped to target")
    log("Watch Grafana: target stays mostly flat, slow stabilisation")

    run_phase(
        label="ARED",
        duration=args.duration,
        controller_cmd=[sys.executable, str(SCRIPTS/"adaptive_red.py"),
                        "--ns",NS1,"--iface",IFACE,
                        "--logdir",str(LOGS),
                        "--duration",str(args.duration+30)],
        logfile=str(LOGS/"ared_controller.log")
    )

    # ── Reset between phases ──────────────────────────────────
    sep("RESET — resetting fq_codel to defaults")
    kill_controllers()
    reset_fqcodel()
    log("Pausing 15s before ACAPE phase...")
    log("In Grafana: you will see a clear boundary between the two phases")
    time.sleep(15)

    # ── PHASE 2: ACAPE ────────────────────────────────────────
    sep("PHASE 2 — ACAPE (our system)")
    log("fq_codel back at default 5ms target")
    log("ACAPE will drive target down to 1ms using gradient + prediction")
    log("Watch Grafana: target staircase, faster backlog drop, [PREDICTIVE] tags")

    run_phase(
        label="ACAPE",
        duration=args.duration,
        controller_cmd=[sys.executable, str(SCRIPTS/"acape_v5.py"),
                        "--ns",NS1,"--iface",IFACE,
                        "--logdir",str(LOGS)],
        logfile=str(LOGS/"acape_comparison.log")
    )

    # ── Done ─────────────────────────────────────────────────
    sep("COMPARISON COMPLETE")
    cleanup()

    log("Generating comparison plots...")
    try:
        subprocess.run(
            [sys.executable, str(SCRIPTS/"plot_comparison.py"),
             "--logdir",str(LOGS),"--plotdir",str(REPO/"plots")],
            timeout=90
        )
        log("Plots saved to plots/")
    except Exception as e:
        warn("Plot failed: "+str(e))
        log("Manual plot: python3 scripts/plot_comparison.py --logdir "+str(LOGS))

    print()
    log("Key things to screenshot in Grafana:")
    print("  1. The gap/boundary between ARED and ACAPE phases")
    print("  2. fq_codel target: flat in ARED phase, staircase in ACAPE phase")
    print("  3. Backlog: slower drop in ARED, faster in ACAPE (<5s)")
    print("  4. Drop rate: compare both phases")
    print()
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    print("  cd "+str(REPO)+" && git add -A && git commit -m 'Comparison_"+ts+"' && git push")

if __name__=="__main__":
    main()
