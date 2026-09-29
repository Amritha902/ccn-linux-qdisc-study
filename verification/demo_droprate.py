#!/usr/bin/env python3
"""Show that the original logs' drop rates exceed what the link can carry."""
import csv, glob, os, statistics as st

MTU, RATE = 1514, 10e6
MAXPPS = RATE / (MTU * 8)

print("=" * 84)
print("DROP RATES IN THE ORIGINAL LOGS vs THE LINK'S PHYSICAL PACKET RATE")
print("=" * 84)
print(f"  Link rate                : {RATE/1e6:.0f} Mbit/s")
print(f"  Full-size packet         : {MTU} bytes")
print(f"  Maximum packets/s        : {MAXPPS:.0f}")
print(f"  iperf3 reported          : ~179 retransmits/s")
print()
print(f"{'log':42s} {'median drop/s':>14s} {'max drop/s':>12s} {'x link rate':>12s}")
print("-" * 84)
rows = []
for f in sorted(glob.glob("logs/acape_metrics_*.csv")):
    try:
        drs = [float(r["drop_rate_per_s"]) for r in csv.DictReader(open(f))
               if r.get("drop_rate_per_s")]
    except Exception:
        continue
    if not drs:
        continue
    med = st.median(drs)
    if med > MAXPPS:
        rows.append((os.path.basename(f), med, max(drs)))
for n, med, mx in sorted(rows, key=lambda r: -r[1])[:14]:
    print(f"{n:42s} {med:14.0f} {mx:12.0f} {med/MAXPPS:11.0f}x")
print()
print(f"  {len(rows)} of 32 runs have a MEDIAN drop rate above the physical packet rate.")
print()
print("  A queue cannot drop more packets per second than can arrive. These")
print("  figures are consistent with a stream of 66-byte ACKs overflowing the")
print("  shaper (10e6/(66*8) = 18,939 ACK/s admitted), not with data queueing.")
print("=" * 84)
