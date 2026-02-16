import subprocess
import time
import re

INTERFACE = "wlp4s0"
TARGET_NORMAL = "5ms"
TARGET_CONGESTED = "3ms"

previous_drops = 0

def get_drops():
    output = subprocess.check_output(
        f"tc -s qdisc show dev {INTERFACE}",
        shell=True
    ).decode()

    match = re.search(r'dropped (\d+)', output)
    if match:
        return int(match.group(1))
    return 0

def change_target(value):
    subprocess.call(
        f"sudo tc qdisc change dev {INTERFACE} root fq_codel target {value}",
        shell=True
    )

print("Starting ACAPE Adaptive Controller...")

while True:
    current_drops = get_drops()
    drop_delta = current_drops - previous_drops

    print(f"Drops this interval: {drop_delta}")

    if drop_delta > 20:
        print("Congestion detected → tightening delay target")
        change_target(TARGET_CONGESTED)
    else:
        print("Stable → normal delay target")
        change_target(TARGET_NORMAL)

    previous_drops = current_drops
    time.sleep(1)
