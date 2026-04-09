#!/usr/bin/env python3
"""
setup.py — One-time namespace + eBPF setup
Run this once after every reboot before run_acape.py

Usage: sudo python3 setup.py
       sudo python3 setup.py --scenario S2   (5Mbit bottleneck)
"""
import subprocess, sys, os, time, argparse
from pathlib import Path

REPO = Path(__file__).resolve().parent

G="\033[92m"; Y="\033[93m"; R="\033[91m"; C="\033[96m"; X="\033[0m"; B="\033[1m"
def log(m): print(f"{G}{B}[setup]{X} {m}",flush=True)
def err(m): print(f"{R}[ERR]{X} {m}",flush=True)

SCENARIOS = {
    "S1":{"rate":"10mbit","burst":"32kbit"},
    "S2":{"rate":"5mbit", "burst":"16kbit"},
    "S3":{"rate":"20mbit","burst":"64kbit"},
    "S4":{"rate":"10mbit","burst":"32kbit"},
}

def sh(cmd, ns=None):
    if ns: cmd = ["ip","netns","exec",ns]+cmd
    return subprocess.run(cmd, capture_output=True, text=True)

def main():
    if os.geteuid()!=0: sys.exit("sudo python3 setup.py")

    p = argparse.ArgumentParser()
    p.add_argument("--scenario", default="S1", choices=list(SCENARIOS.keys()))
    args = p.parse_args()
    s = SCENARIOS[args.scenario]

    print(f"\n{B}ACAPE Setup — {args.scenario} ({s['rate']}){X}\n")

    # Kill existing
    log("Killing existing processes...")
    for proc in ["iperf3","acape_v5","acape_exporter"]:
        subprocess.run(["pkill","-9","-f",proc], capture_output=True)
    time.sleep(1)

    # Clean
    log("Removing old namespaces...")
    sh(["ip","netns","del","ns1"]); sh(["ip","netns","del","ns2"])
    sh(["ip","link","del","veth1"])
    time.sleep(1.5)

    # Create
    log("Creating namespaces + veth pair...")
    for cmd in [
        ["ip","netns","add","ns1"], ["ip","netns","add","ns2"],
        ["ip","link","add","veth1","type","veth","peer","name","veth2"],
        ["ip","link","set","veth1","netns","ns1"],
        ["ip","link","set","veth2","netns","ns2"],
    ]: sh(cmd)

    # IPs
    sh(["ip","addr","add","10.0.0.1/24","dev","veth1"],ns="ns1")
    sh(["ip","addr","add","10.0.0.2/24","dev","veth2"],ns="ns2")
    for ifc,ns in [("veth1","ns1"),("veth2","ns2"),("lo","ns1"),("lo","ns2")]:
        sh(["ip","link","set",ifc,"up"],ns=ns)

    # Bottleneck
    log(f"Applying TBF {s['rate']} + fq_codel...")
    sh(["tc","qdisc","add","dev","veth1","root","handle","1:",
        "tbf","rate",s["rate"],"burst",s["burst"],"latency","400ms"],ns="ns1")
    sh(["tc","qdisc","add","dev","veth1","parent","1:1","handle","10:",
        "fq_codel","target","5ms","interval","100ms","limit","1024","quantum","1514"],ns="ns1")

    # Ping check
    log("Verifying connectivity...")
    r = sh(["ping","-c","3","-W","1","10.0.0.1"],ns="ns2")
    if "0% packet loss" in r.stdout or "3 received" in r.stdout:
        log(f"{G}Ping OK — 0% loss{X}")
    else:
        err("Ping failed!"); sys.exit(1)

    # Build eBPF
    log("Building eBPF program...")
    ebpf = REPO/"ebpf"
    r1 = subprocess.run(["make","clean"],cwd=ebpf,capture_output=True,text=True)
    r2 = subprocess.run(["make"],cwd=ebpf,capture_output=True,text=True)
    if not (ebpf/"tc_monitor.o").exists():
        err("eBPF compile failed:"); print(r2.stderr[:400]); sys.exit(1)
    log("eBPF compiled: tc_monitor.o")

    # Attach
    log("Attaching eBPF to veth1 (ns1)...")
    sh(["tc","qdisc","add","dev","veth1","clsact"],ns="ns1")
    sh(["tc","filter","del","dev","veth1","egress"],ns="ns1")
    r = sh(["tc","filter","add","dev","veth1","egress",
            "bpf","direct-action","obj",str(ebpf/"tc_monitor.o"),"sec","tc_egress"],ns="ns1")

    out = sh(["tc","filter","show","dev","veth1","egress"],ns="ns1").stdout
    if "jited" in out or ("id" in out and "direct-action" in out):
        prog_id = next((w for w in out.split() if w.isdigit()),"?")
        log(f"{G}eBPF attached — prog_id={prog_id}, JIT compiled ✓{X}")
    else:
        err("eBPF attach may have failed — check output:")
        print(out[:300])

    # Monitoring
    log("Starting Prometheus + Grafana...")
    subprocess.run(["systemctl","start","prometheus","grafana-server"],capture_output=True)
    time.sleep(2)

    print(f"\n{'='*52}")
    print(f"  {G}{B}Setup complete!{X}")
    print(f"  Scenario : {args.scenario} — {s['rate']} bottleneck")
    print(f"  Now run  : sudo python3 run_acape.py --scenario {args.scenario}")
    print(f"  Or test  : sudo python3 quick_test.py")
    print(f"{'='*52}\n")

if __name__=="__main__":
    main()
