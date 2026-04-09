#!/usr/bin/env python3
"""
quick_test.py — 2-minute sanity check
Verifies the entire pipeline works before a long run.

Usage: sudo python3 quick_test.py
"""
import subprocess, sys, os, time
from pathlib import Path

REPO = Path(__file__).resolve().parent
GREEN="\033[92m"; RED="\033[91m"; YELLOW="\033[93m"; RESET="\033[0m"; BOLD="\033[1m"

def check(name, ok, detail=""):
    mark = f"{GREEN}PASS{RESET}" if ok else f"{RED}FAIL{RESET}"
    print(f"  [{mark}] {name}" + (f" — {detail}" if detail else ""))
    return ok

def shell(cmd, ns=None, timeout=10):
    if ns: cmd = ["ip","netns","exec",ns] + cmd
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout + r.stderr, r.returncode == 0
    except Exception as e:
        return str(e), False

if os.geteuid() != 0:
    sys.exit("Run as root: sudo python3 quick_test.py")

print(f"\n{BOLD}ACAPE Quick Test — 2 min pipeline check{RESET}\n")

results = []

# 1. Namespace exists
out,ok = shell(["ip","netns","list"])
ns_ok = "ns1" in out and "ns2" in out
results.append(check("Namespaces ns1+ns2 exist", ns_ok, "run run_acape.py first" if not ns_ok else ""))

# 2. Connectivity
out,ok = shell(["ping","-c","2","-W","1","10.0.0.1"], ns="ns2")
ping_ok = "0% packet loss" in out or "2 received" in out
results.append(check("Ping ns2→ns1 (0% loss)", ping_ok))

# 3. TBF + fq_codel
out,ok = shell(["tc","qdisc","show","dev","veth1"], ns="ns1")
tc_ok = "tbf" in out and "fq_codel" in out
results.append(check("TBF + fq_codel attached", tc_ok))

# 4. eBPF compiled
ebpf_ok = (REPO/"ebpf"/"tc_monitor.o").exists()
results.append(check("eBPF object compiled", ebpf_ok, "cd ebpf && make" if not ebpf_ok else ""))

# 5. eBPF attached
out,ok = shell(["tc","filter","show","dev","veth1","egress"], ns="ns1")
jit_ok = "jited" in out or "id" in out
results.append(check("eBPF filter attached (jited)", jit_ok))

# 6. Quick iperf test
print(f"\n  Testing iperf throughput (5s)...")
srv = subprocess.Popen(["ip","netns","exec","ns1","iperf3","-s","-p","5202","--one-off"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1)
out,ok = shell(["iperf3","-c","10.0.0.1","-p","5202","-t","5","-P","4","-J"], ns="ns2", timeout=20)
srv.terminate()
try:
    import json
    d = json.loads(out)
    mbps = d["end"]["sum_received"]["bits_per_second"]/1e6
    iperf_ok = 8 <= mbps <= 12
    results.append(check(f"iperf throughput ~10 Mbps", iperf_ok, f"got {mbps:.1f} Mbps"))
except:
    results.append(check("iperf throughput", False, "parse failed"))

# 7. Prometheus
try:
    import urllib.request
    urllib.request.urlopen("http://localhost:9090/-/ready", timeout=2)
    results.append(check("Prometheus running (:9090)", True))
except:
    results.append(check("Prometheus running (:9090)", False, "sudo systemctl start prometheus"))

# 8. Grafana
try:
    import urllib.request
    urllib.request.urlopen("http://localhost:3000", timeout=2)
    results.append(check("Grafana running (:3000)", True))
except:
    results.append(check("Grafana running (:3000)", False, "sudo systemctl start grafana-server"))

# 9. Exporter
try:
    import urllib.request
    out = urllib.request.urlopen("http://localhost:9101/metrics", timeout=2).read().decode()
    exp_ok = "acape_" in out
    results.append(check("ACAPE exporter (:9101/metrics)", exp_ok))
except:
    results.append(check("ACAPE exporter (:9101/metrics)", False, "start acape_exporter.py"))

# Summary
passed = sum(results)
total  = len(results)
print(f"\n{'='*44}")
print(f"  {passed}/{total} checks passed")
if passed == total:
    print(f"  {GREEN}{BOLD}ALL GOOD — run sudo python3 run_acape.py{RESET}")
else:
    print(f"  {YELLOW}Fix failures above, then run run_acape.py{RESET}")
print(f"{'='*44}\n")
