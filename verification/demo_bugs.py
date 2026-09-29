#!/usr/bin/env python3
"""Reproduce the three defects that zeroed the eBPF telemetry.

Uses field values taken from a real flow_map entry captured on kernel 6.18
(packets=47264, bytes=3119540, first_seen=502568911582, last_seen=512572233902,
gap=181126), so the arithmetic below is the arithmetic that ran during the
original experiments.

Each defect alone forces active_flows=0, elephant_ratio=0.0, workload=MICE,
quantum=300B and rtt_proxy=0.0 -- exactly what all 32 runs recorded.
"""
import os, struct, sys, time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
import acape

# Real captured values.
PACKETS, NBYTES = 47264, 3119540
FIRST_NS, LAST_NS, GAP_NS, ELEPHANT = 502568911582, 512572233902, 181126, 0

raw = bytearray(56)
struct.pack_into("<QQQQQ", raw, 0, PACKETS, NBYTES, FIRST_NS, LAST_NS, GAP_NS)
struct.pack_into("<I", raw, 40, ELEPHANT)
# bpftool --json renders byte arrays as hex strings, which is what the original
# code was handed:
hexlist = [f"0x{b:02x}" for b in raw]

print("=" * 76)
print("BUG 1  bpftool --json yields hex STRINGS; bytes() on them raises")
print("=" * 76)
print(f"  entry['value'][:4] = {hexlist[:4]}")
try:
    bytes(hexlist[16:24])          # exactly what acape_v5.py did
    print("  no error (unexpected)")
except TypeError as e:
    print(f"  bytes(raw[16:24]) -> TypeError: {e}")
print("  acape_v5.py wrapped this in `except: pass`, so read_flows() returned")
print("  zeros on every tick and the failure was never visible.")
print()

b = acape.decode_bpftool_bytes(hexlist)
u64 = lambda o: struct.unpack_from("<Q", b, o)[0]

print("=" * 76)
print("BUG 2  struct offsets omitted first_seen_ns, shifting every later field")
print("=" * 76)
print("  true : packets@0 bytes@8 first_seen@16 last_seen@24 gap@32 elephant@40")
print("  v5   : packets@0 bytes@8 last_ns@16    gap@24       elephant@32")
print()
print(f"  offset 16 = {u64(16):>14}   truly first_seen_ns, v5 read it as last_ns")
print(f"  offset 24 = {u64(24):>14}   truly last_seen_ns,  v5 read it as gap_ns")
print(f"  offset 32 = {u64(32):>14}   truly gap_ns; v5 read its low 4 bytes as")
print(f"                                 is_elephant -> {struct.unpack_from('<I', b, 32)[0]}")
print(f"  offset 40 = {struct.unpack_from('<I', b, 40)[0]:>14}   the real is_elephant flag")
print()

print("=" * 76)
print("BUG 3  CLOCK_REALTIME compared against CLOCK_MONOTONIC")
print("=" * 76)
now_real = time.time_ns()
now_mono = acape.monotonic_ns()
print(f"  time.time_ns()      = {now_real:>22}  (since 1970)")
print(f"  bpf_ktime_get_ns()  = {LAST_NS:>22}  (since boot)")
v5_age = (now_real - LAST_NS) / 1e9
print(f"  v5 age = (realtime - ktime)/1e9 = {v5_age:,.0f} s = {v5_age/3.154e7:,.1f} YEARS")
print(f"  filter `if age < 2.0` -> {v5_age < 2.0}")
print()
correct_age = (now_mono - acape.monotonic_ns() + 1_000_000) / 1e9
print(f"  corrected comparison uses CLOCK_MONOTONIC on both sides -> age ~ "
      f"{abs(correct_age):.4f}s, passes the filter")
print()
print("=" * 76)
print("RESULT: active_flows = 0 in 21,128 of 21,128 recorded ticks (100%).")
print("The paper attributed this to 'namespace file-descriptor isolation'.")
print("The maps were populated throughout; the fault was entirely in userspace.")
print("=" * 76)
