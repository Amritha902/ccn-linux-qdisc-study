#!/usr/bin/env python3
"""Demonstrate the throughput overshoot and why goodput must come from
sum_received, using real measured runs from results/.

With a large unmanaged buffer the sender pushes into the queue faster than the
link drains. iperf3's sum_sent counts what entered the socket, so it reports
more than the link can physically carry. sum_received counts what actually
crossed the bottleneck.

Reporting sum_sent as "throughput" produces figures above the link rate, which
is the signature of the mistake.
"""
import glob, json, os, sys

RES = sys.argv[1] if len(sys.argv) > 1 else "results"

rows = []
for f in sorted(glob.glob(os.path.join(RES, "*", "summary.json"))):
    d = json.load(open(f))
    if d.get("workload") != "steady":
        continue
    st = (d.get("stages") or [{}])[0]
    rows.append((d["label"], d.get("rate_mbit", 10),
                 st.get("sent_mbps"), d.get("throughput_mbps"),
                 d.get("backlog_mean_pkts"), d.get("rtt_p95_ms")))

print("=" * 88)
print("THROUGHPUT OVERSHOOT: iperf3 sum_sent vs sum_received on a 10 Mbit link")
print("=" * 88)
print(f"{'run':26s} {'link':>6s} {'sum_sent':>10s} {'sum_recv':>10s} "
      f"{'overshoot':>10s} {'backlog':>9s} {'p95 RTT':>9s}")
print("-" * 88)
for label, rate, sent, recv, bl, rtt in rows:
    if sent is None or recv is None:
        continue
    over = sent - rate
    flag = "  <== IMPOSSIBLE" if sent > rate * 1.02 else ""
    print(f"{label:26s} {rate:6.0f} {sent:10.2f} {recv:10.2f} "
          f"{over:+10.2f} {bl if bl else 0:9.1f} {rtt if rtt else 0:9.1f}{flag}")

print()
print("=" * 88)
print("WHY")
print("=" * 88)
print("  A 10 Mbit link cannot deliver more than 10 Mbps. Any 'throughput'")
print("  figure above the link rate is measuring what the SENDER queued, not")
print("  what the receiver got.")
print()
print("  pfifo holds ~1000 packets, so the sender fills the buffer and iperf3")
print("  counts those bytes as sent. The excess shows up as queueing delay,")
print("  not as delivered data -- note the backlog and p95 RTT columns.")
print()
print("  Flow-queueing AQMs keep the queue short, so sender and receiver")
print("  figures nearly agree and no overshoot appears.")
print()
print("  This is why src/run_experiment.py takes goodput from sum_received.")
print("=" * 88)
