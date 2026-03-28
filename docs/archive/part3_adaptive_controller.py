#!/usr/bin/env python3

import subprocess
import re
import time
import csv
import os
import argparse
from datetime import datetime

# ---------------- DEFAULTS ----------------
DEFAULT_TARGET = 5
DEFAULT_INTERVAL = 100
DEFAULT_LIMIT = 10240

THRESHOLDS = {
    "drop_light": 5,
    "drop_moderate": 20,
    "drop_heavy": 50,
    "backlog_light": 50,
    "backlog_moderate": 200,
    "backlog_heavy": 500,
}

PARAM_TABLE = {
    "NORMAL":   {"target": 7, "interval": 120, "limit": DEFAULT_LIMIT},
    "LIGHT":    {"target": 5, "interval": 100, "limit": DEFAULT_LIMIT},
    "MODERATE": {"target": 4, "interval": 85,  "limit": int(DEFAULT_LIMIT * 0.9)},
    "HEAVY":    {"target": 3, "interval": 65,  "limit": int(DEFAULT_LIMIT * 0.7)},
}

LOG_FILE = "logs/adaptive_controller.csv"


# ---------------- RUN COMMAND ----------------
def run_cmd(cmd, netns=None):
    if netns:
        cmd = ["ip", "netns", "exec", netns] + cmd
    return subprocess.run(cmd, capture_output=True, text=True)


# ---------------- GET STATS ----------------
def get_stats(interface, netns):
    result = run_cmd(["tc", "-s", "qdisc", "show", "dev", interface], netns)

    stats = {
        "drops": 0,
        "backlog": 0,
        "timestamp": time.time()
    }

    for line in result.stdout.splitlines():
        m = re.search(r"dropped (\d+)", line)
        if m:
            stats["drops"] = int(m.group(1))

        m = re.search(r"backlog \S+ (\d+)p", line)
        if m:
            stats["backlog"] = int(m.group(1))

    return stats


# ---------------- DETECT PARENT ----------------
def detect_parent(interface, netns):
    result = run_cmd(["tc", "qdisc", "show", "dev", interface], netns)

    for line in result.stdout.splitlines():
        if "fq_codel" in line:
            m = re.search(r"parent (\S+)", line)
            if m:
                return ["parent", m.group(1)]

    return ["root"]


# ---------------- APPLY ----------------
def apply_params(interface, params, netns):
    parent = detect_parent(interface, netns)

    cmd = [
        "tc", "qdisc", "change", "dev", interface
    ] + parent + [
        "fq_codel",
        "target", f"{params['target']}ms",
        "interval", f"{params['interval']}ms",
        "limit", str(params["limit"])
    ]

    result = run_cmd(cmd, netns)

    if result.returncode != 0:
        print(f"[WARN] tc failed: {result.stderr.strip()}")
        return False

    return True


# ---------------- CLASSIFY ----------------
def classify(cur, prev):
    dt = cur["timestamp"] - prev["timestamp"]
    if dt <= 0:
        return "NORMAL", 0

    drop_rate = (cur["drops"] - prev["drops"]) / dt
    backlog = cur["backlog"]

    T = THRESHOLDS

    if drop_rate >= T["drop_heavy"] or backlog >= T["backlog_heavy"]:
        return "HEAVY", drop_rate
    elif drop_rate >= T["drop_moderate"] or backlog >= T["backlog_moderate"]:
        return "MODERATE", drop_rate
    elif drop_rate >= T["drop_light"] or backlog >= T["backlog_light"]:
        return "LIGHT", drop_rate
    else:
        return "NORMAL", drop_rate


# ---------------- LOG ----------------
def init_log():
    os.makedirs("logs", exist_ok=True)
    with open(LOG_FILE, "w") as f:
        writer = csv.writer(f)
        writer.writerow(["time", "state", "drop_rate", "backlog", "target", "interval", "limit"])


def log(state, drop_rate, backlog, params):
    with open(LOG_FILE, "a") as f:
        writer = csv.writer(f)
        writer.writerow([
            datetime.now().strftime("%H:%M:%S"),
            state,
            round(drop_rate, 2),
            backlog,
            params["target"],
            params["interval"],
            params["limit"]
        ])


# ---------------- MAIN LOOP ----------------
def run(interface, netns):

    print("\n=== Adaptive Controller Started ===\n")

    prev = None
    current_params = PARAM_TABLE["NORMAL"]

    init_log()

    while True:
        cur = get_stats(interface, netns)

        if prev:
            state, drop_rate = classify(cur, prev)
            new_params = PARAM_TABLE[state]

            changed = False

            if new_params != current_params:
                if apply_params(interface, new_params, netns):
                    current_params = new_params
                    changed = True

            print(f"{state:>8} | drop/s={drop_rate:>6.1f} | backlog={cur['backlog']:>4} | "
                  f"target={current_params['target']}ms | "
                  f"{'*** YES' if changed else ''}")

            log(state, drop_rate, cur["backlog"], current_params)

        prev = cur
        time.sleep(1)


# ---------------- ENTRY ----------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--interface", required=True)
    parser.add_argument("--netns", default=None)

    args = parser.parse_args()

    run(args.interface, args.netns)
