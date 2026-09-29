#!/usr/bin/env python3
"""Produce the numbered evidence set for the methodology.

Each figure is a verbatim capture of a command that was actually executed, with
a step number and a caption stating what it demonstrates. Steps that need the
AQM-capable kernel are executed inside the VM via src/invm.sh; the rest run on
the host. Nothing is re-typed or mocked.

    python3 src/make_evidence.py --outdir figures/steps
"""
import argparse, json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from capture import run_and_capture, capture_step, side_by_side  # noqa: E402

INDEX = []


def host(step, title, explain, cmd, outdir):
    p, rc, out = run_and_capture(step, title, explain, cmd, outdir)
    INDEX.append({"step": step, "title": title, "explain": explain,
                  "image": os.path.basename(p), "where": "host", "command": cmd})
    return out


def invm(cmd, timeout=1200):
    r = subprocess.run(["bash", os.path.join(HERE, "invm.sh"), cmd],
                       capture_output=True, text=True,
                       env=dict(os.environ, TIMEOUT=str(timeout)), cwd=ROOT)
    out = r.stdout
    # strip the guest banner lines
    keep = [ln for ln in out.split("\n")
            if not ln.startswith("=====GUEST")]
    return "\n".join(keep).strip("\n")


def vm(step, title, explain, cmd, outdir, max_lines=44, timeout=1200):
    out = invm(cmd, timeout)
    lines = out.split("\n")
    if len(lines) > max_lines:
        out = "\n".join(lines[:max_lines - 1] +
                        [f"... [{len(lines)-max_lines+1} more lines omitted]"])
    p = capture_step(step, title, explain, cmd, out, outdir)
    print(f"  STEP {step}  {title}  -> {os.path.basename(p)}  [in VM]")
    INDEX.append({"step": step, "title": title, "explain": explain,
                  "image": os.path.basename(p), "where": "vm", "command": cmd})
    return out


def sbs(step, title, explain, left, right, outdir):
    p = side_by_side(step, title, explain, left, right, outdir)
    INDEX.append({"step": step, "title": title, "explain": explain,
                  "image": os.path.basename(p), "where": "comparison",
                  "command": f"{left['command']}  ||  {right['command']}"})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default=os.path.join(ROOT, "figures", "steps"))
    ap.add_argument("--skip-vm", action="store_true")
    a = ap.parse_args()
    od = a.outdir
    os.makedirs(od, exist_ok=True)

    # ── Part A: why a VM was needed ──────────────────────────────────────
    host("01", "Session kernel cannot run the AQMs under study",
         "The cloud container runs a Firecracker kernel with every AQM compiled out and no "
         "loadable-module support, so fq_codel cannot be instantiated here at all. This is "
         "why the experiments run inside a purpose-built VM rather than directly.",
         "uname -r; echo; zcat /proc/config.gz | grep -E "
         "'NET_SCH_(FQ_CODEL|CODEL|RED|PIE|CAKE|NETEM|TBF|HTB)='; echo; "
         "echo 'CONFIG_MODULES:'; zcat /proc/config.gz | grep -c '^CONFIG_MODULES=' "
         "|| echo '0 (no module support)'", od)

    host("02", "Kernel built with every AQM compiled in",
         "A 6.12.48 kernel was configured and built with fq_codel, CoDel, CAKE, PIE, FQ-PIE, "
         "RED, netem, TBF and HTB all built in (=y), plus BTF for eBPF. This kernel is what "
         "the experiments run on.",
         "grep -E '^CONFIG_NET_SCH_(FQ_CODEL|CODEL|CAKE|PIE|FQ_PIE|RED|NETEM|TBF|HTB)=|"
         "^CONFIG_DEBUG_INFO_BTF=|^CONFIG_NET_CLS_BPF=|^CONFIG_VETH=|^CONFIG_NET_NS=' "
         "/root/linux-6.12.48/.config | sort; echo; ls -lh /root/linux-6.12.48/arch/x86/boot/bzImage", od)

    if not a.skip_vm:
        vm("03", "AQM availability confirmed inside the VM",
           "Each queue discipline is instantiated on a real veth device in the guest. "
           "Availability is demonstrated, not assumed.",
           "uname -r; ip link add vt type veth peer name vt2 >/dev/null 2>&1; "
           "ip link set vt up; "
           "for q in fq_codel codel cake pie fq_pie netem sfq htb pfifo; do "
           "if tc qdisc replace dev vt root $q 2>/dev/null; then echo \"  $q: AVAILABLE\"; "
           "else echo \"  $q: missing\"; fi; done; "
           "tc qdisc replace dev vt root red limit 100000 avpkt 1000 bandwidth 10mbit "
           "min 30000 max 90000 burst 55 2>/dev/null && echo '  red: AVAILABLE'; "
           "tc qdisc replace dev vt root tbf rate 10mbit burst 32kbit latency 400ms "
           "2>/dev/null && echo '  tbf: AVAILABLE'; ip link del vt", od)

        # ── Part B: the topology correction ─────────────────────────────
        vm("04", "Corrected three-node router topology",
           "The bottleneck now sits on the router's egress toward the server, so it is on the "
           "data path. TBF is the shaper and the AQM under study is its child.",
           "bash src/testbed.sh setup", od)

        old = invm(
            "ip netns del n1 2>/dev/null; ip netns del n2 2>/dev/null; "
            "ip netns add n1; ip netns add n2; "
            "ip link add veth1 type veth peer name veth2; "
            "ip link set veth1 netns n1; ip link set veth2 netns n2; "
            "ip netns exec n1 ip addr add 10.0.0.1/24 dev veth1; "
            "ip netns exec n2 ip addr add 10.0.0.2/24 dev veth2; "
            "ip netns exec n1 ip link set veth1 up; ip netns exec n2 ip link set veth2 up; "
            "ip netns exec n1 tc qdisc add dev veth1 root handle 1: tbf rate 10mbit "
            "burst 32kbit latency 400ms; "
            "ip netns exec n1 tc qdisc add dev veth1 parent 1:1 handle 10: fq_codel "
            "target 5ms interval 100ms limit 1024; "
            "ip netns exec n1 iperf3 -s -p 5301 -D; sleep 2; "
            "ip netns exec n2 iperf3 -c 10.0.0.1 -p 5301 -P 8 -t 10 2>&1 | tail -3; "
            "echo; echo 'qdisc counters on the shaped interface:'; "
            "ip netns exec n1 tc -s qdisc show dev veth1 | head -3; "
            "ip netns exec n1 tc -s qdisc show dev veth1 | awk '/Sent/{print \"  bytes/pkt =\", $2/$4}' | head -1")
        new = invm(
            "bash src/testbed.sh setup >/dev/null 2>&1; "
            "ip netns exec ns_server iperf3 -s -p 5302 -D; sleep 2; "
            "ip netns exec ns_client iperf3 -c 192.168.2.2 -p 5302 -P 8 -t 10 2>&1 | tail -3; "
            "echo; echo 'qdisc counters on the bottleneck:'; "
            "ip netns exec ns_router tc -s qdisc show dev veth_rs | sed -n '4,6p'; "
            "ip netns exec ns_router tc -s qdisc show dev veth_rs | awk '/Sent/{print \"  bytes/pkt =\", $2/$4}' | tail -1")

        sbs("05", "The original two-node testbed shaped ACKs, not data",
            "README Parts 2-4 put the bottleneck on veth1 inside ns1 but ran iperf3 FROM ns2, so "
            "data flowed ns2 -> ns1 while the egress qdisc on veth1 shaped only ns1 -> ns2: the "
            "acknowledgement path. Left panel: data passes unshaped at multi-Gbit and the queue "
            "carries 66-byte ACKs. Right panel: the corrected topology shapes the data path, and "
            "the queue carries full-size packets. Every backlog and drop figure in the original "
            "Parts 2-4 was a measurement of ACK queueing.",
            {"label": "BEFORE - 2-node (ns1/veth1), ACK path",
             "command": "iperf3 -c 10.0.0.1 through TBF on veth1 egress",
             "output": old, "verdict": "bad"},
            {"label": "AFTER - 3-node router, data path",
             "command": "iperf3 -c 192.168.2.2 through TBF on router egress",
             "output": new, "verdict": "good"}, od)

        # ── Part C: eBPF pipeline ───────────────────────────────────────
        vm("06", "eBPF telemetry program compiles, attaches and JITs",
           "tc_monitor.c is compiled with BTF, attached at the clsact egress hook on the router, "
           "and verified JIT-compiled. Its maps are then located through the bpf(2) syscall.",
           "clang -O2 -g -target bpf -I/usr/include/x86_64-linux-gnu "
           "-c ebpf/tc_monitor.c -o ebpf/tc_monitor.o && echo 'compiled OK'; "
           "bash src/testbed.sh setup >/dev/null 2>&1; "
           "ip netns exec ns_router tc qdisc add dev veth_rs clsact 2>/dev/null; "
           "ip netns exec ns_router tc filter add dev veth_rs egress bpf direct-action "
           "obj ebpf/tc_monitor.o sec tc_egress && echo 'attached OK'; echo; "
           "ip netns exec ns_router tc filter show dev veth_rs egress; echo; "
           "cd src && python3 bpfmap.py", od)

        vm("07", "eBPF flow telemetry is live under traffic",
           "With traffic running, the flow_map is read through bpf(2) and reports real per-flow "
           "state. In all 21,128 samples of the original study this read returned zero.",
           "bash src/testbed.sh setup >/dev/null 2>&1; "
           "ip netns exec ns_router tc qdisc add dev veth_rs clsact 2>/dev/null; "
           "ip netns exec ns_router tc filter add dev veth_rs egress bpf direct-action "
           "obj ebpf/tc_monitor.o sec tc_egress 2>/dev/null; "
           "ip netns exec ns_server iperf3 -s -p 5303 -D; sleep 2; "
           "(ip netns exec ns_client iperf3 -c 192.168.2.2 -p 5303 -P 6 -t 14 >/dev/null 2>&1 &); "
           "sleep 7; python3 src/dump_flows.py", od)

    # ── Part D: the userspace bugs, proven ──────────────────────────────
    host("08", "Regression tests pin all four defects",
         "Seventeen tests, each of which fails against the original implementation's behaviour "
         "and passes against the corrected one. They cover the qdisc-selection bug, the three "
         "eBPF decode bugs, the integer-millisecond rounding, and the inert prediction.",
         "cd %s && python3 tests/test_acape.py 2>&1 | tail -26" % ROOT, od)

    host("09", "Why the eBPF telemetry read zero in every historical run",
         "Three independent defects in read_flows(), each fatal on its own. The immediate cause "
         "was a TypeError swallowed by a bare except; behind it sat wrong struct offsets and a "
         "comparison of CLOCK_REALTIME against CLOCK_MONOTONIC giving ages of decades.",
         "cd %s && python3 verification/demo_bugs.py" % ROOT, od)

    with open(os.path.join(od, "index.json"), "w") as fh:
        json.dump(INDEX, fh, indent=2)
    print(f"\n{len(INDEX)} evidence figures -> {od}")


if __name__ == "__main__":
    main()
