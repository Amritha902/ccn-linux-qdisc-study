#!/bin/bash
# Guest-side entry point. Runs as init inside the QEMU VM, executes whatever
# command RUNCMD names, then powers off. Results are written into the 9p share,
# which is the host's filesystem, so they persist after the VM exits.
exec > /dev/ttyS0 2>&1

mount -t proc  proc  /proc        2>/dev/null
mount -t sysfs sys   /sys         2>/dev/null
mount -t devtmpfs dev /dev        2>/dev/null
mount -t devpts devpts /dev/pts   2>/dev/null
mount -t tmpfs tmpfs /tmp         2>/dev/null
mount -t tmpfs tmpfs /run         2>/dev/null
mount -t bpf   bpf   /sys/fs/bpf  2>/dev/null
mount -t debugfs debugfs /sys/kernel/debug 2>/dev/null

ip link set lo up
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export HOME=/root
export PYTHONUNBUFFERED=1
ulimit -n 65536
sysctl -qw net.ipv4.tcp_congestion_control=cubic 2>/dev/null

echo "=====GUEST_UP===== kernel $(uname -r)"

RUNCMD_FILE=/home/user/ccn-linux-qdisc-study/.runcmd
if [ -f "$RUNCMD_FILE" ]; then
    bash "$RUNCMD_FILE"
    echo "=====GUEST_RC=$?====="
else
    echo "no .runcmd supplied in project dir"
fi

echo "=====GUEST_DONE====="
sync
poweroff -f
