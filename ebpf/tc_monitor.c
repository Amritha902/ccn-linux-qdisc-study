// SPDX-License-Identifier: GPL-2.0
/*
 * ACAPE: eBPF TC Monitor
 * Amritha S — VIT Chennai 2026
 *
 * Uses proper linux/ headers — compiles with clang -g -target bpf
 * The -g flag embeds BTF so bpftool can read map entries with field names.
 *
 * Build:
 *   clang -O2 -g -target bpf \
 *         -I/usr/include/$(uname -m)-linux-gnu \
 *         -c tc_monitor.c -o tc_monitor.o
 *
 * Attach (inside ns1):
 *   tc qdisc add dev veth1 clsact
 *   tc filter add dev veth1 egress bpf direct-action \
 *          obj tc_monitor.o sec tc_egress
 *
 * Read maps (from HOST — BPF maps are kernel-global):
 *   bpftool prog show id <N> --json        # get map IDs
 *   bpftool map dump id <M> --json         # dump entries with BTF names
 */

#include <linux/bpf.h>
#include <linux/pkt_cls.h>
#include <linux/if_ether.h>
#include <linux/ip.h>
#include <linux/tcp.h>
#include <linux/udp.h>
#include <linux/in.h>
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_endian.h>

#define ELEPHANT_BYTES 10000000ULL

/* ── Flow key: 5-tuple ──────────────────────────────────────── */
struct flow_key {
    __u32 src_ip;
    __u32 dst_ip;
    __u16 src_port;
    __u16 dst_port;
    __u8  proto;
    __u8  _pad[3];
};

/* ── Per-flow stats ─────────────────────────────────────────── */
struct flow_val {
    __u64 packets;
    __u64 bytes;
    __u64 last_ns;
    __u64 gap_ns;       /* EWMA inter-packet gap (RTT proxy) */
    __u32 elephant;     /* 1 = bytes > 10 MB */
    __u32 _pad;
};

/* ── Global counter ─────────────────────────────────────────── */
struct global_val {
    __u64 packets;
    __u64 bytes;
};

/* ── BPF Maps ───────────────────────────────────────────────── */
struct {
    __uint(type,        BPF_MAP_TYPE_LRU_HASH);
    __type(key,         struct flow_key);
    __type(value,       struct flow_val);
    __uint(max_entries, 65536);
} flow_map SEC(".maps");

struct {
    __uint(type,        BPF_MAP_TYPE_PERCPU_ARRAY);
    __type(key,         __u32);
    __type(value,       struct global_val);
    __uint(max_entries, 1);
} global_map SEC(".maps");

struct {
    __uint(type,        BPF_MAP_TYPE_ARRAY);
    __type(key,         __u32);
    __type(value,       __u64);
    __uint(max_entries, 4);  /* <128B / 128-512B / 512-1500B / >1500B */
} size_hist SEC(".maps");

/* ── TC egress hook ─────────────────────────────────────────── */
SEC("tc_egress")
int tc_egress_monitor(struct __sk_buff *skb)
{
    void *data     = (void *)(long)skb->data;
    void *data_end = (void *)(long)skb->data_end;

    struct ethhdr *eth = data;
    if ((void *)(eth + 1) > data_end) return TC_ACT_OK;
    if (eth->h_proto != bpf_htons(ETH_P_IP)) return TC_ACT_OK;

    struct iphdr *ip = (void *)(eth + 1);
    if ((void *)(ip + 1) > data_end) return TC_ACT_OK;

    struct flow_key key = {};
    key.src_ip = ip->saddr;
    key.dst_ip = ip->daddr;
    key.proto  = ip->protocol;

    if (ip->protocol == IPPROTO_TCP) {
        struct tcphdr *tcp = (void *)(ip + 1);
        if ((void *)(tcp + 1) > data_end) return TC_ACT_OK;
        key.src_port = bpf_ntohs(tcp->source);
        key.dst_port = bpf_ntohs(tcp->dest);
    } else if (ip->protocol == IPPROTO_UDP) {
        struct udphdr *udp = (void *)(ip + 1);
        if ((void *)(udp + 1) > data_end) return TC_ACT_OK;
        key.src_port = bpf_ntohs(udp->source);
        key.dst_port = bpf_ntohs(udp->dest);
    }

    __u64 now = bpf_ktime_get_ns();
    __u32 len = skb->len;

    struct flow_val *fv = bpf_map_lookup_elem(&flow_map, &key);
    if (!fv) {
        struct flow_val nv = {};
        nv.packets  = 1;
        nv.bytes    = len;
        nv.last_ns  = now;
        bpf_map_update_elem(&flow_map, &key, &nv, BPF_ANY);
    } else {
        __u64 gap = now - fv->last_ns;
        fv->gap_ns = fv->gap_ns ? (fv->gap_ns * 7 + gap) >> 3 : gap;
        __sync_fetch_and_add(&fv->packets, 1);
        __sync_fetch_and_add(&fv->bytes, len);
        fv->last_ns = now;
        if (fv->bytes > ELEPHANT_BYTES) fv->elephant = 1;
    }

    __u32 zero = 0;
    struct global_val *gv = bpf_map_lookup_elem(&global_map, &zero);
    if (gv) {
        __sync_fetch_and_add(&gv->packets, 1);
        __sync_fetch_and_add(&gv->bytes, len);
    }

    __u32 bucket = (len < 128) ? 0 : (len < 512) ? 1 : (len < 1500) ? 2 : 3;
    __u64 *cnt = bpf_map_lookup_elem(&size_hist, &bucket);
    if (cnt) __sync_fetch_and_add(cnt, 1);

    return TC_ACT_OK;
}

char LICENSE[] SEC("license") = "GPL";
