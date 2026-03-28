// SPDX-License-Identifier: GPL-2.0
/*
 * ACAPE: Adaptive Condition-Aware Packet Engine
 * eBPF TC Telemetry Collector
 * Amritha S — VIT Chennai 2026
 *
 * Attaches to TC egress on veth1 inside ns1.
 * Collects per-flow stats, estimates inter-packet gap (proxy for RTT),
 * classifies elephant vs mice flows, and exports via BPF maps.
 *
 * Build:  clang -O2 -g -target bpf -c tc_monitor.c -o tc_monitor.o \
 *                -I/usr/include/x86_64-linux-gnu
 * Attach: tc qdisc add dev veth1 clsact
 *         tc filter add dev veth1 egress bpf direct-action \
 *                obj tc_monitor.o sec tc_egress
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

#define ELEPHANT_BYTES   10000000ULL   /* 10 MB threshold */
#define MAX_FLOWS        65536
#define NS_PER_MS        1000000ULL

/* ── Flow 5-tuple key ─────────────────────────────────────── */
struct flow_key {
    __u32 src_ip;
    __u32 dst_ip;
    __u16 src_port;
    __u16 dst_port;
    __u8  proto;
    __u8  _pad[3];
};

/* ── Per-flow statistics ──────────────────────────────────── */
struct flow_stats {
    __u64 packets;
    __u64 bytes;
    __u64 first_seen_ns;
    __u64 last_seen_ns;
    __u64 interpacket_gap_ns;   /* EWMA of inter-packet gap (RTT proxy) */
    __u32 is_elephant;          /* 1 = elephant flow (>10 MB) */
    __u32 flow_rate_kbps;       /* approx rate in kbps */
    __u8  _pad[4];
};

/* ── Global per-CPU counters (lock-free hot path) ────────── */
struct global_stats {
    __u64 total_packets;
    __u64 total_bytes;
    __u64 elephant_count;   /* flows classified as elephant */
    __u64 mice_count;       /* flows classified as mice */
    __u64 timestamp_ns;
};

/* ── BPF Maps ─────────────────────────────────────────────── */
struct {
    __uint(type,        BPF_MAP_TYPE_LRU_HASH);
    __type(key,         struct flow_key);
    __type(value,       struct flow_stats);
    __uint(max_entries, MAX_FLOWS);
} flow_map SEC(".maps");

struct {
    __uint(type,        BPF_MAP_TYPE_PERCPU_ARRAY);
    __type(key,         __u32);
    __type(value,       struct global_stats);
    __uint(max_entries, 1);
} global_map SEC(".maps");

/* Packet size histogram: 0=<128B, 1=128-512B, 2=512-1500B, 3=>1500B */
struct {
    __uint(type,        BPF_MAP_TYPE_ARRAY);
    __type(key,         __u32);
    __type(value,       __u64);
    __uint(max_entries, 4);
} pkt_size_hist SEC(".maps");

/* ── Helper: parse 5-tuple ────────────────────────────────── */
static __always_inline int
parse_key(struct __sk_buff *skb, struct flow_key *key)
{
    void *data     = (void *)(long)skb->data;
    void *data_end = (void *)(long)skb->data_end;

    struct ethhdr *eth = data;
    if ((void *)(eth + 1) > data_end) return -1;
    if (eth->h_proto != bpf_htons(ETH_P_IP)) return -1;

    struct iphdr *ip = (void *)(eth + 1);
    if ((void *)(ip + 1) > data_end) return -1;

    key->src_ip  = ip->saddr;
    key->dst_ip  = ip->daddr;
    key->proto   = ip->protocol;
    key->src_port = key->dst_port = 0;

    if (ip->protocol == IPPROTO_TCP) {
        struct tcphdr *tcp = (void *)(ip + 1);
        if ((void *)(tcp + 1) > data_end) return -1;
        key->src_port = bpf_ntohs(tcp->source);
        key->dst_port = bpf_ntohs(tcp->dest);
    } else if (ip->protocol == IPPROTO_UDP) {
        struct udphdr *udp = (void *)(ip + 1);
        if ((void *)(udp + 1) > data_end) return -1;
        key->src_port = bpf_ntohs(udp->source);
        key->dst_port = bpf_ntohs(udp->dest);
    }
    return 0;
}

/* ── TC egress program ────────────────────────────────────── */
SEC("tc_egress")
int tc_egress_monitor(struct __sk_buff *skb)
{
    struct flow_key key = {};
    if (parse_key(skb, &key) < 0)
        return TC_ACT_OK;

    __u64 now = bpf_ktime_get_ns();
    __u32 len = skb->len;

    /* ── Per-flow update ───────────────────────────────────── */
    struct flow_stats *fs = bpf_map_lookup_elem(&flow_map, &key);
    if (!fs) {
        struct flow_stats nfs = {
            .packets           = 1,
            .bytes             = len,
            .first_seen_ns     = now,
            .last_seen_ns      = now,
            .interpacket_gap_ns = 0,
            .is_elephant       = 0,
            .flow_rate_kbps    = 0,
        };
        bpf_map_update_elem(&flow_map, &key, &nfs, BPF_ANY);
    } else {
        __u64 gap = now - fs->last_seen_ns;
        /* EWMA of inter-packet gap: α=0.125 (like TCP RTT estimation) */
        if (fs->interpacket_gap_ns == 0)
            fs->interpacket_gap_ns = gap;
        else
            fs->interpacket_gap_ns = (fs->interpacket_gap_ns * 7 + gap) / 8;

        __sync_fetch_and_add(&fs->packets, 1);
        __sync_fetch_and_add(&fs->bytes, len);
        fs->last_seen_ns = now;

        /* Elephant detection */
        if (fs->bytes > ELEPHANT_BYTES)
            fs->is_elephant = 1;

        /* Approximate rate (bytes/ns → kbps) */
        __u64 age_ns = now - fs->first_seen_ns;
        if (age_ns > NS_PER_MS) {
            __u64 rate = (fs->bytes * 8000) / (age_ns / 1000);
            fs->flow_rate_kbps = (__u32)(rate & 0xFFFFFFFF);
        }
    }

    /* ── Global per-CPU update ─────────────────────────────── */
    __u32 zero = 0;
    struct global_stats *gs = bpf_map_lookup_elem(&global_map, &zero);
    if (gs) {
        gs->total_packets++;
        gs->total_bytes += len;
        gs->timestamp_ns = now;
    }

    /* ── Packet size histogram ─────────────────────────────── */
    __u32 bucket = (len < 128) ? 0 : (len < 512) ? 1 : (len < 1500) ? 2 : 3;
    __u64 *cnt = bpf_map_lookup_elem(&pkt_size_hist, &bucket);
    if (cnt) (*cnt)++;

    return TC_ACT_OK;
}

char _license[] SEC("license") = "GPL";
