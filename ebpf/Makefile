CLANG   ?= clang
ARCH    := $(shell uname -m)
KVER    := $(shell uname -r)
INC     := /usr/include/$(ARCH)-linux-gnu

# -g is REQUIRED for BTF on modern kernels (Ubuntu 22+/24+)
BPF_CFLAGS := -O2 -g -target bpf -Wall \
              -Wno-unused-value -Wno-pointer-sign \
              -Wno-compare-distinct-pointer-types \
              -I$(INC)

all: tc_monitor.o

tc_monitor.o: tc_monitor.c
	$(CLANG) $(BPF_CFLAGS) -c $< -o $@
	@echo "✅ Built: $@"

deps:
	sudo apt install -y clang llvm libbpf-dev \
	    linux-headers-$(KVER) python3-bpfcc bpfcc-tools iproute2

attach:
	sudo ip netns exec ns1 tc qdisc add dev veth1 clsact 2>/dev/null || true
	sudo ip netns exec ns1 tc filter add dev veth1 egress \
	    bpf direct-action obj tc_monitor.o sec tc_egress
	@echo "✅ Attached. Verifying:"
	@sudo ip netns exec ns1 tc filter show dev veth1 egress

detach:
	sudo ip netns exec ns1 tc filter del dev veth1 egress 2>/dev/null || true
	sudo ip netns exec ns1 tc qdisc del dev veth1 clsact 2>/dev/null || true
	@echo "Detached."

clean:
	rm -f tc_monitor.o

.PHONY: all deps attach detach clean
