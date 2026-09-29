#!/usr/bin/env python3
"""Regression tests for the four defects found in scripts/acape_v5.py.

Each test fails against the v5 behaviour and passes against src/acape.py.
Run: python3 -m pytest tests/test_acape.py -v   (or: python3 tests/test_acape.py)
"""
import os, struct, sys, time, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
import acape  # noqa: E402


# Real `tc -s qdisc show dev veth_rs` output: TBF root + fq_codel child.
# The child is what the controller is supposed to measure.
TC_OUTPUT = """qdisc tbf 1: root refcnt 5 rate 10Mbit burst 4Kb lat 400ms
 Sent 41296198 bytes 625652 pkt (dropped 7, overlimits 1787970 requeues 0)
 backlog 0b 0p requeues 0
qdisc fq_codel 10: parent 1:1 limit 1024p flows 1024 quantum 1514 target 5ms interval 100ms memory_limit 32Mb ecn drop_batch 64
 Sent 41296198 bytes 625652 pkt (dropped 4211, overlimits 0 requeues 0)
 backlog 337622b 223p requeues 0
  maxpacket 1514 drop_overlimit 0 new_flow_count 12 ecn_mark 0
  new_flows_len 0 old_flows_len 1
"""


class TestF1ReadTcSelectsCorrectQdisc(unittest.TestCase):
    """v5's re.search() over the whole blob always matched the TBF root."""

    def test_stanzas_split(self):
        s = acape.split_qdisc_stanzas(TC_OUTPUT)
        self.assertEqual(len(s), 2)
        self.assertTrue(s[0].startswith("qdisc tbf"))
        self.assertTrue(s[1].startswith("qdisc fq_codel"))

    def test_child_stats_not_root(self):
        child = acape.parse_stanza(acape.split_qdisc_stanzas(TC_OUTPUT)[1])
        self.assertEqual(child["kind"], "fq_codel")
        self.assertEqual(child["drops"], 4211)      # v5 would read 7 (TBF's)
        self.assertEqual(child["backlog_p"], 223)   # v5 would read 0 (TBF's)
        self.assertEqual(child["backlog_b"], 337622)

    def test_root_is_kept_separately(self):
        root = acape.parse_stanza(acape.split_qdisc_stanzas(TC_OUTPUT)[0])
        self.assertEqual(root["kind"], "tbf")
        self.assertEqual(root["drops"], 7)
        self.assertEqual(root["overlimits"], 1787970)

    def test_v5_regex_would_pick_root(self):
        import re
        self.assertEqual(int(re.search(r"dropped (\d+)", TC_OUTPUT).group(1)), 7)
        self.assertEqual(int(re.search(r"backlog \d+b (\d+)p", TC_OUTPUT).group(1)), 0)


def make_flow_value(packets, nbytes, first_ns, last_ns, gap_ns, is_elephant):
    b = bytearray(56)
    struct.pack_into("<QQQQQ", b, 0, packets, nbytes, first_ns, last_ns, gap_ns)
    struct.pack_into("<I", b, 40, is_elephant)
    return [f"0x{x:02x}" for x in b]          # bpftool --json emits hex STRINGS


class TestF2ReadFlows(unittest.TestCase):
    def test_a_hex_string_decode(self):
        """v5: bytes(raw[16:24]) -> TypeError, swallowed by bare except."""
        raw = make_flow_value(10, 20, 1, 2, 3, 0)
        with self.assertRaises(TypeError):
            bytes(raw[16:24])                  # exactly what v5 did
        self.assertEqual(len(acape.decode_bpftool_bytes(raw)), 56)

    def test_b_struct_offsets(self):
        raw = make_flow_value(packets=47264, nbytes=3119540,
                              first_ns=502568911582, last_ns=512572233902,
                              gap_ns=181126, is_elephant=1)
        fv = acape.parse_flow_value(raw)
        self.assertEqual(fv["packets"], 47264)
        self.assertEqual(fv["bytes"], 3119540)
        self.assertEqual(fv["first_seen_ns"], 502568911582)
        self.assertEqual(fv["last_seen_ns"], 512572233902)
        self.assertEqual(fv["gap_ns"], 181126)
        self.assertEqual(fv["is_elephant"], 1)

    def test_b_v5_offsets_were_wrong(self):
        """v5 read is_elephant from offset 32 = low half of gap_ns."""
        raw = make_flow_value(1, 1, 111, 222, 0xDEADBEEF, 0)
        b = acape.decode_bpftool_bytes(raw)
        v5_is_elephant = struct.unpack_from("<I", b, 32)[0]
        self.assertEqual(v5_is_elephant, 0xDEADBEEF)   # garbage, not a flag
        self.assertEqual(acape.parse_flow_value(raw)["is_elephant"], 0)

    def test_c_clock_domain(self):
        """v5 compared CLOCK_REALTIME with bpf_ktime_get_ns (CLOCK_MONOTONIC)."""
        ktime = acape.monotonic_ns()
        v5_age = (time.time_ns() - ktime) / 1e9
        self.assertGreater(v5_age, 1e9, "v5 age should be ~50+ years")
        correct_age = (acape.monotonic_ns() - ktime) / 1e9
        self.assertLess(correct_age, 2.0, "correct age must pass the <2s filter")


class TestF3TargetResolution(unittest.TestCase):
    def test_sub_ms_expressed_in_us(self):
        """v5: int(round(0.6)) -> '1ms'; 0.4 -> '0ms' (invalid)."""
        self.assertEqual(acape.fmt_time(0.6), "600us")
        self.assertEqual(acape.fmt_time(0.4), "400us")
        self.assertEqual(acape.fmt_time(4.05), "4050us")

    def test_v5_rounding_destroyed_the_staircase(self):
        seq = [5.0, 4.5, 4.05, 3.65, 3.28, 2.95, 2.66, 2.39,
               2.15, 1.94, 1.74, 1.57, 1.41, 1.27, 1.14, 1.03]
        v5 = [int(round(x)) for x in seq]
        self.assertEqual(v5, [5, 4, 4, 4, 3, 3, 3, 2, 2, 2, 2, 2, 1, 1, 1, 1])
        self.assertEqual(len(set(v5)), 5)          # 16 steps collapse to 5 values
        v6 = [acape.fmt_time(x) for x in seq]
        self.assertEqual(len(set(v6)), 16)         # all 16 preserved

    def test_roundtrip_parse(self):
        for ms in (0.2, 0.75, 1.0, 4.05, 5.0, 20.0):
            self.assertAlmostEqual(
                acape.parse_time_to_ms(acape.fmt_time(ms)), ms, places=3)


class TestF4PredictionAffectsAction(unittest.TestCase):
    def test_v5_heavy_worsening_was_mislabelled_stable(self):
        """v5's `idx<3` guard made a worsening HEAVY report STABLE."""
        idx = acape.REGIMES.index("HEAVY")
        c = 1.0                                   # strongly worsening
        v5_traj = "WORSENING" if (c > 0.5 and idx < 3) else (
            "RECOVERING" if (c < -0.5 and idx > 0) else "STABLE")
        self.assertEqual(v5_traj, "STABLE")        # the bug
        _, traj = acape.predict("HEAVY", 100.0, 100.0)
        self.assertEqual(traj, "WORSENING")        # fixed

    def test_prediction_changes_the_action(self):
        params = {"target": 5.0, "interval": 100.0, "limit": 1024, "quantum": 1514}
        # HEAVY but recovering -> predicted MODERATE -> gentler additive decrease
        rec, reason_r, pred_r = acape.aimd("HEAVY", "RECOVERING", "MODERATE",
                                           params, "MICE")
        # HEAVY and steady -> reactive multiplicative decrease
        sta, reason_s, pred_s = acape.aimd("HEAVY", "STABLE", "HEAVY",
                                            params, "MICE")
        self.assertTrue(pred_r)
        self.assertFalse(pred_s)
        self.assertIn("[PREDICTIVE]", reason_r)
        self.assertIn("[REACTIVE]", reason_s)
        self.assertNotEqual(rec["target"], sta["target"])   # v5: these were equal

    def test_v5_eff_always_equalled_regime(self):
        for traj, pred in (("STABLE", "HEAVY"), ("RECOVERING", "MODERATE")):
            v5_eff = pred if traj == "WORSENING" else "HEAVY"
            self.assertEqual(v5_eff, "HEAVY")      # never the prediction

    def test_bounds_respected(self):
        p = {"target": 0.2, "interval": 20.0, "limit": 64, "quantum": 300}
        out, _, _ = acape.aimd("HEAVY", "STABLE", "HEAVY", p, "MICE")
        self.assertGreaterEqual(out["target"], acape.T_MIN)
        self.assertGreaterEqual(out["limit"], acape.L_MIN)


class TestGradient(unittest.TestCase):
    def test_linear_slope_recovered(self):
        h = [{"ts": i * 0.5, "backlog": 100 + 20 * (i * 0.5)} for i in range(10)]
        self.assertAlmostEqual(acape.gradient(h, "backlog"), 20.0, places=6)

    def test_flat_series_zero(self):
        h = [{"ts": i * 0.5, "backlog": 300.0} for i in range(10)]
        self.assertAlmostEqual(acape.gradient(h, "backlog"), 0.0, places=9)


if __name__ == "__main__":
    unittest.main(verbosity=2)
