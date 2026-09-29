#!/usr/bin/env python3
"""Print the live contents of the eBPF flow_map.

Used as evidence that the eBPF telemetry pipeline works end to end. In the
original study this read returned zero flows in all 21,128 recorded samples,
because of three defects in the userspace decode path (see
verification/demo_bugs.py).
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpfmap
from acape import parse_flow_value, monotonic_ns


def main():
    if not bpfmap.available():
        print("bpf(2) syscall unavailable")
        return 1
    mid, fd, info = bpfmap.find_map_by_name("flow_ma")
    if mid is None:
        print("flow_map not found — is the eBPF program attached?")
        return 1
    print(f"flow_map id={mid}  key={info.key_size}B  value={info.value_size}B  "
          f"max_entries={info.max_entries}")

    values = [v for _, v in bpfmap.iter_map(fd, info.key_size, info.value_size)]
    fvs = [parse_flow_value(v) for v in values]
    now = monotonic_ns()
    active = [f for f in fvs if f["packets"] > 0
              and (now - f["last_seen_ns"]) / 1e9 < 2.0]

    print(f"map entries           = {len(fvs)}")
    print(f"active flows (age<2s) = {len(active)}")
    print(f"total packets seen    = {sum(f['packets'] for f in fvs)}")
    print(f"total bytes seen      = {sum(f['bytes'] for f in fvs)}")
    print(f"elephant flows        = {sum(1 for f in active if f['is_elephant'])}")
    print()
    for f in active[:10]:
        age_ms = (now - f["last_seen_ns"]) / 1e6
        print(f"  pkts={f['packets']:7d}  bytes={f['bytes']:10d}  "
              f"gap_ns={f['gap_ns']:9d}  age={age_ms:7.1f}ms  "
              f"elephant={f['is_elephant']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
