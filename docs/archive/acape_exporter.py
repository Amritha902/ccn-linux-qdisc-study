#!/usr/bin/env python3
"""
ACAPE Prometheus Exporter
Amritha S — VIT Chennai 2026

Reads ACAPE BPF maps via bpftool + tc stats via iproute2
Exposes them as Prometheus metrics on port 9101

Pipeline:
  eBPF TC hook → BPF maps → THIS SCRIPT → Prometheus → Grafana

Run: sudo python3 acape_exporter.py --ns ns1 --iface veth1
     (keep running alongside acape_v5.py)

Install dependency:
  pip3 install prometheus-client --break-system-packages
"""

import subprocess, json, re, time, struct, os, sys, argparse
from datetime import datetime

try:
    from prometheus_client import start_http_server, Gauge, Counter, Info
    from prometheus_client.core import CollectorRegistry, GaugeMetricFamily
    from prometheus_client import REGISTRY, make_wsgi_app
except ImportError:
    print("Installing prometheus-client...")
    os.system("pip3 install prometheus-client --break-system-packages -q")
    from prometheus_client import start_http_server, Gauge, Counter, Info

# ── Prometheus metrics ────────────────────────────────────────
PORT = 9101

# tc-derived (always available)
g_drop_rate    = Gauge('acape_drop_rate_per_sec',   'Instantaneous drop rate drops/sec')
g_backlog_pkts = Gauge('acape_backlog_packets',      'Queue backlog in packets')
g_throughput   = Gauge('acape_throughput_mbps',      'Throughput in Mbps')
g_drops_total  = Gauge('acape_drops_total',          'Cumulative drops')

# fq_codel parameters (what ACAPE is tuning)
g_target_ms    = Gauge('acape_fqcodel_target_ms',    'fq_codel target delay ms')
g_interval_ms  = Gauge('acape_fqcodel_interval_ms',  'fq_codel interval ms')
g_limit_pkts   = Gauge('acape_fqcodel_limit_packets','fq_codel queue limit packets')
g_quantum_b    = Gauge('acape_fqcodel_quantum_bytes','fq_codel quantum bytes')

# eBPF-derived (when BPF maps readable)
g_active_flows  = Gauge('acape_ebpf_active_flows',   'Active flows from eBPF map')
g_elephant_flows= Gauge('acape_ebpf_elephant_flows', 'Elephant flows (bytes>10MB)')
g_mice_flows    = Gauge('acape_ebpf_mice_flows',     'Mice flows (bytes<10MB)')
g_elephant_ratio= Gauge('acape_ebpf_elephant_ratio', 'Elephant flow ratio 0-1')
g_rtt_proxy_ms  = Gauge('acape_ebpf_rtt_proxy_ms',  'RTT proxy from inter-packet gap ms')
g_total_pkts    = Gauge('acape_ebpf_total_packets',  'Total packets seen by eBPF')
g_total_bytes   = Gauge('acape_ebpf_total_bytes',    'Total bytes seen by eBPF')

# Packet size histogram
g_pkt_small  = Gauge('acape_pkt_size_small',  'Packets <128 bytes')
g_pkt_medium = Gauge('acape_pkt_size_medium', 'Packets 128-512 bytes')
g_pkt_large  = Gauge('acape_pkt_size_large',  'Packets 512-1500 bytes')
g_pkt_jumbo  = Gauge('acape_pkt_size_jumbo',  'Packets >1500 bytes')

# ACAPE state
g_prog_id      = Gauge('acape_ebpf_prog_id',         'BPF program ID (0=not attached)')
g_ebpf_active  = Gauge('acape_ebpf_active',          '1 if eBPF attached, 0 otherwise')

# ── Shell helpers ─────────────────────────────────────────────
def run(cmd):
    try: return subprocess.check_output(cmd, stderr=subprocess.DEVNULL,
                                         text=True, timeout=3)
    except: return ""

def rns(ns, cmd):
    try: return subprocess.check_output(["ip","netns","exec",ns]+cmd,
                                         stderr=subprocess.DEVNULL,
                                         text=True, timeout=3)
    except: return ""

def bpftool(*args):
    out = run(["bpftool"]+list(args))
    if not out: out = run(["/usr/sbin/bpftool"]+list(args))
    return out

# ── Readers ───────────────────────────────────────────────────
_prev_tc = {"ts": 0, "drops": 0, "bytes": 0}

def read_tc_metrics(ns, iface):
    global _prev_tc
    out = rns(ns, ["tc","-s","qdisc","show","dev",iface])
    if not out: return

    now = time.time()
    m = re.search(r"Sent (\d+) bytes", out)
    cur_bytes = int(m.group(1)) if m else 0
    m = re.search(r"dropped (\d+)", out)
    cur_drops = int(m.group(1)) if m else 0
    m = re.search(r"backlog \d+b (\d+)p", out)
    backlog = int(m.group(1)) if m else 0

    dt = max(now - _prev_tc["ts"], 1e-6)
    if _prev_tc["ts"] > 0:
        drop_rate  = max(0, cur_drops - _prev_tc["drops"]) / dt
        throughput = max(0, cur_bytes - _prev_tc["bytes"]) * 8 / (dt * 1e6)
        g_drop_rate.set(round(drop_rate, 2))
        g_throughput.set(round(throughput, 3))

    g_backlog_pkts.set(backlog)
    g_drops_total.set(cur_drops)
    _prev_tc = {"ts": now, "drops": cur_drops, "bytes": cur_bytes}

def read_fqcodel_params(ns, iface):
    out = rns(ns, ["tc","qdisc","show","dev",iface])
    if not out or "fq_codel" not in out: return
    for metric, pat in [
        (g_target_ms,   r"target (\d+)ms"),
        (g_interval_ms, r"interval (\d+)ms"),
        (g_limit_pkts,  r"limit (\d+)p?"),
        (g_quantum_b,   r"quantum (\d+)"),
    ]:
        m = re.search(pat, out)
        if m: metric.set(float(m.group(1)))

def get_prog_id(ns, iface):
    out = rns(ns, ["tc","filter","show","dev",iface,"egress"])
    if not out or "bpf" not in out: return None
    m = re.search(r'\bid (\d+)\b', out)
    return int(m.group(1)) if m else None

def get_map_ids(prog_id):
    if prog_id is None: return {}
    out = bpftool("prog","show","id",str(prog_id),"--json")
    if not out: return {}
    try:
        d = json.loads(out)
        maps = {}
        for mid in d.get("map_ids", []):
            mout = bpftool("map","show","id",str(mid),"--json")
            try:
                md = json.loads(mout)
                maps[md.get("name","")] = mid
            except: pass
        return maps
    except: return {}

def parse_flow_val(raw):
    if isinstance(raw, dict):
        return {
            "packets":  int(raw.get("packets",  raw.get("pkts", 0))),
            "bytes":    int(raw.get("bytes",    0)),
            "last_ns":  int(raw.get("last_ns",  raw.get("last_seen_ns", 0))),
            "gap_ns":   int(raw.get("gap_ns",   raw.get("interpacket_gap_ns", 0))),
            "elephant": int(raw.get("elephant", raw.get("is_elephant", 0))),
        }
    elif isinstance(raw, list) and len(raw) >= 36:
        try:
            b = bytes(int(x,16) if isinstance(x,str) else x for x in raw)
            p,by,ln,gn,el = struct.unpack_from('<QQQQi', b)
            return {"packets":p,"bytes":by,"last_ns":ln,"gap_ns":gn,"elephant":el}
        except: return None
    return None

def read_ebpf_metrics(map_ids):
    now_ns = time.time_ns()

    # flow_map
    flow_mid = next((v for k,v in map_ids.items() if "flow" in k), None)
    if flow_mid:
        out = bpftool("map","dump","id",str(flow_mid),"--json")
        if out and out.strip() not in ("[]",""):
            try:
                entries = json.loads(out)
                active = eleph = mice = 0
                total_gap = 0
                for e in entries:
                    raw = e.get("formatted",{}).get("value") or e.get("value")
                    parsed = parse_flow_val(raw)
                    if not parsed: continue
                    age = (now_ns - parsed["last_ns"])/1e9
                    if age < 2.0 and parsed["packets"] > 0:
                        active += 1
                        total_gap += parsed["gap_ns"]
                        if parsed["elephant"]: eleph += 1
                        else: mice += 1
                ratio = eleph/max(active,1)
                rtt = (total_gap/max(active,1))/1e6
                g_active_flows.set(active)
                g_elephant_flows.set(eleph)
                g_mice_flows.set(mice)
                g_elephant_ratio.set(round(ratio,3))
                g_rtt_proxy_ms.set(round(rtt,3))
            except: pass

    # global_map
    glob_mid = next((v for k,v in map_ids.items() if "global" in k), None)
    if glob_mid:
        out = bpftool("map","dump","id",str(glob_mid),"--json")
        if out:
            try:
                entries = json.loads(out)
                if entries:
                    raw = entries[0].get("value", {})
                    if isinstance(raw, dict):
                        g_total_pkts.set(int(raw.get("packets", raw.get("total_packets",0))))
                        g_total_bytes.set(int(raw.get("bytes",  raw.get("total_bytes",0))))
            except: pass

    # size_hist
    hist_mid = next((v for k,v in map_ids.items()
                     if "hist" in k or "size" in k), None)
    if hist_mid:
        out = bpftool("map","dump","id",str(hist_mid),"--json")
        if out:
            try:
                entries = json.loads(out)
                hist = [0,0,0,0]
                for e in entries:
                    k = e.get("key"); v = e.get("value")
                    try:
                        idx = int(k) if not isinstance(k,list) else int(k[0])
                        val = int(v) if not isinstance(v,list) else int(v[0])
                        if 0<=idx<4: hist[idx]=val
                    except: pass
                g_pkt_small.set(hist[0])
                g_pkt_medium.set(hist[1])
                g_pkt_large.set(hist[2])
                g_pkt_jumbo.set(hist[3])
            except: pass

# ── Collection loop ───────────────────────────────────────────
def collect(ns, iface, interval=2):
    print(f"[ACAPE Exporter] Starting on port {PORT}")
    print(f"[ACAPE Exporter] namespace={ns}  iface={iface}")
    print(f"[ACAPE Exporter] Prometheus → http://localhost:{PORT}/metrics")
    print(f"[ACAPE Exporter] Add to Grafana: http://localhost:{PORT}")
    print(f"[ACAPE Exporter] Collecting every {interval}s...\n")

    start_http_server(PORT)

    while True:
        try:
            # tc metrics
            read_tc_metrics(ns, iface)
            read_fqcodel_params(ns, iface)

            # eBPF metrics
            prog_id = get_prog_id(ns, iface)
            g_prog_id.set(prog_id or 0)
            g_ebpf_active.set(1 if prog_id else 0)

            if prog_id:
                map_ids = get_map_ids(prog_id)
                read_ebpf_metrics(map_ids)

            ts = datetime.now().strftime("%H:%M:%S")
            print(f"[{ts}] scraped — prog_id={prog_id}  "
                  f"drop_rate={g_drop_rate._value.get():.0f}/s  "
                  f"backlog={g_backlog_pkts._value.get():.0f}p  "
                  f"flows={g_active_flows._value.get():.0f}  "
                  f"target={g_target_ms._value.get():.1f}ms",
                  flush=True)

        except Exception as e:
            print(f"[ERR] {e}")

        time.sleep(interval)

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="ACAPE Prometheus Exporter")
    p.add_argument("--ns",       default="ns1")
    p.add_argument("--iface",    default="veth1")
    p.add_argument("--interval", type=int, default=2)
    args = p.parse_args()
    if os.geteuid() != 0:
        sys.exit("Run as root: sudo python3 acape_exporter.py")
    collect(args.ns, args.iface, args.interval)
