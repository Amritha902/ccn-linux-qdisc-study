# Pilot run (superseded)

23 runs collected with the first-generation instrumentation, retained as a
cross-check on the definitive suite in `results/`.

**Do not cite these numbers.** They were collected before three measurement
improvements and differ in methodology:

- Latency came from a single 5 Hz `ping` probe (~300 samples). The definitive
  suite uses a 20 Hz probe (~1200 samples) *and* in-band bulk-flow RTT from
  iperf3's TCP_INFO, because the two differ substantially — the probe is
  privileged by `fq_codel`'s new-flow heuristic.
- There is no sham-controller condition, so any latency difference between
  static and adaptive `fq_codel` confounds the controller's CPU cost with its
  control decisions.
- Field names differ (`rtt_*` rather than `sparse_rtt_*`/`bulk_rtt_*`), so the
  analysis scripts leave several columns blank for this data.

The AQM comparison here (pfifo vs the flow-queueing disciplines) agrees with
the definitive suite, which is why it is kept.
