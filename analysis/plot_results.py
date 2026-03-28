import re
import matplotlib.pyplot as plt

# ---------- CONTROLLER ----------
time_c, drop, backlog = [], [], []

with open("logs/final_run/controller.log") as f:
    t = 0
    for line in f:
        if "drop/s" in line:
            t += 1
            d = float(re.search(r"drop/s=\s*([0-9.]+)", line).group(1))
            b = int(re.search(r"backlog=\s*([0-9]+)", line).group(1))
            time_c.append(t)
            drop.append(d)
            backlog.append(b)

# ---------- TC ----------
time_tc, drops_tc = [], []

with open("logs/final_run/tc.log") as f:
    t = 0
    for line in f:
        if "dropped" in line:
            t += 1
            d = int(re.search(r"dropped (\d+)", line).group(1))
            time_tc.append(t)
            drops_tc.append(d)

# ---------- IPERF ----------
time_i, throughput = [], []

with open("logs/final_run/iperf.log") as f:
    t = 0
    for line in f:
        if "Mbits/sec" in line and "receiver" in line:
            t += 1
            val = float(re.search(r"([0-9.]+) Mbits/sec", line).group(1))
            time_i.append(t)
            throughput.append(val)

# ---------- PLOTS ----------

plt.figure()
plt.plot(time_i, throughput)
plt.title("Throughput vs Time")
plt.xlabel("Time")
plt.ylabel("Mbps")
plt.savefig("results/throughput.png")

plt.figure()
plt.plot(time_c, drop)
plt.title("Drop Rate vs Time")
plt.xlabel("Time")
plt.ylabel("drop/s")
plt.savefig("results/drop_rate.png")

plt.figure()
plt.plot(time_c, backlog)
plt.title("Backlog vs Time")
plt.xlabel("Time")
plt.ylabel("packets")
plt.savefig("results/backlog.png")

plt.figure()
plt.plot(time_tc, drops_tc)
plt.title("TC Drops vs Time")
plt.xlabel("Time")
plt.ylabel("drops")
plt.savefig("results/tc_drops.png")

print("DONE: graphs saved in /results/")

