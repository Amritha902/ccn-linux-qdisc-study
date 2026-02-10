# Linux Queue Discipline Analysis (Live Ubuntu Environment)

This project studies Linux traffic scheduling and queue behavior using
native kernel tools (`tc`, `ip`, `iperf3`) in a live Ubuntu environment.

## Environment
- Ubuntu: Live session (Try Ubuntu)
- Kernel: Linux (verified via uname)
- Qdisc: pfifo_fast (baseline)

## Motivation
To observe queue-level behavior (drops, backlog, scheduling)
instead of only end-to-end throughput metrics.

## Status
Phase 1: Baseline verification and environment validation completed.
