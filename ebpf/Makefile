CLANG  ?= clang
ARCH   := $(shell uname -m)
KVER   := $(shell uname -r)
INC    := /usr/include/$(ARCH)-linux-gnu

# -g is REQUIRED: embeds BTF so bpftool can dump maps with field names
CFLAGS := -O2 -g -target bpf -Wall \
           -Wno-unused-value -Wno-pointer-sign \
           -Wno-compare-distinct-pointer-types \
           -I$(INC)

all: tc_monitor.o

tc_monitor.o: tc_monitor.c
	$(CLANG) $(CFLAGS) -c $< -o $@
	@echo "✅ Built: $@"

clean:
	rm -f tc_monitor.o

deps:
	sudo apt install -y clang llvm libbpf-dev \
	    linux-tools-$(KVER) bpftool \
	    linux-headers-$(KVER) iproute2 iperf3

.PHONY: all clean deps
