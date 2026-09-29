#!/usr/bin/env bash
# Boot a local QEMU VM whose kernel actually contains the AQM qdiscs.
#
# WHY THIS EXISTS
# ---------------
# The session container runs a Firecracker kernel with CONFIG_NET_SCH_FQ_CODEL,
# CODEL, RED, PIE, CAKE and NETEM all unset and no loadable-module support, so
# fq_codel cannot be instantiated there at all:
#
#     $ tc qdisc add dev veth1 parent 1:1 fq_codel
#     Error: Specified qdisc kind is unknown.
#
# This boots a 6.12.48 kernel built with every AQM compiled in, and mounts the
# container's filesystem over 9p so the guest reuses the toolchain already
# installed here (iperf3, clang, bpftool, python3).
#
# NETWORKING: none. The VM is given no network device (-nic none). All traffic
# in these experiments is generated inside the guest between network
# namespaces, so the VM needs no connectivity, and nothing is listening on or
# forwarded from the host. The only host interfaces are the serial console and
# the 9p filesystem share.
set -euo pipefail

KDIR="${KDIR:-/root/linux-6.12.48}"
KERNEL="$KDIR/arch/x86/boot/bzImage"
MEM="${MEM:-4096}"
CPUS="${CPUS:-2}"
SHARE="${SHARE:-/}"
INIT="${INIT:-/sbin/init}"

[ -f "$KERNEL" ] || { echo "kernel not built: $KERNEL" >&2; exit 1; }

exec qemu-system-x86_64 \
    -kernel "$KERNEL" \
    -m "$MEM" -smp "$CPUS" \
    -nographic -no-reboot \
    -nic none \
    -fsdev local,id=r,path="$SHARE",security_model=none,multidevs=remap \
    -device virtio-9p-pci,fsdev=r,mount_tag=hostroot \
    -append "root=hostroot rootfstype=9p rootflags=trans=virtio,version=9p2000.L,cache=loose rw \
             console=ttyS0 init=$INIT panic=1 loglevel=4 random.trust_cpu=on" \
    "$@"
