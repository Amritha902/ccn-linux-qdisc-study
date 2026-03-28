// ACAPE eBPF TC Monitor — zero includes, BCC built-ins only
// Amritha S, VIT Chennai 2026
// Ubuntu 24 / kernel 6.x — all structs defined inline

#define ETH_P_IP   0x0800
#define IPPROTO_TCP 6
#define IPPROTO_UDP 17
#define TC_ACT_OK   0
#define ELEPHANT_BYTES 10000000ULL

// Minimal ethernet header
struct eth_hdr {
    unsigned char h_dest[6];
    unsigned char h_source[6];
    unsigned short h_proto;
} __attribute__((packed));

// Minimal IP header
struct ip_hdr {
    unsigned char  ihl_version;
    unsigned char  tos;
    unsigned short tot_len;
    unsigned short id;
    unsigned short frag_off;
    unsigned char  ttl;
    unsigned char  protocol;
    unsigned short check;
    unsigned int   saddr;
    unsigned int   daddr;
} __attribute__((packed));

// Just the ports from TCP/UDP
struct port_hdr {
    unsigned short source;
    unsigned short dest;
} __attribute__((packed));

struct flow_key_t {
    u32 src_ip;
    u32 dst_ip;
    u16 src_port;
    u16 dst_port;
    u8  proto;
};

struct flow_stats_t {
    u64 packets;
    u64 bytes;
    u64 last_seen_ns;
    u64 interpacket_gap_ns;
    u32 is_elephant;
};

struct global_t {
    u64 total_packets;
    u64 total_bytes;
};

BPF_HASH(flow_map, struct flow_key_t, struct flow_stats_t, 65536);
BPF_ARRAY(global_map, struct global_t, 1);
BPF_ARRAY(pkt_hist, u64, 4);

int tc_egress_monitor(struct __sk_buff *skb) {
    void *data     = (void *)(long)skb->data;
    void *data_end = (void *)(long)skb->data_end;

    struct eth_hdr *eth = data;
    if ((void *)(eth + 1) > data_end) return TC_ACT_OK;
    if (bpf_ntohs(eth->h_proto) != ETH_P_IP) return TC_ACT_OK;

    struct ip_hdr *ip = (void *)(eth + 1);
    if ((void *)(ip + 1) > data_end) return TC_ACT_OK;

    struct flow_key_t key = {};
    key.src_ip = ip->saddr;
    key.dst_ip = ip->daddr;
    key.proto  = ip->protocol;

    if (ip->protocol == IPPROTO_TCP || ip->protocol == IPPROTO_UDP) {
        struct port_hdr *ports = (void *)(ip + 1);
        if ((void *)(ports + 1) > data_end) return TC_ACT_OK;
        key.src_port = bpf_ntohs(ports->source);
        key.dst_port = bpf_ntohs(ports->dest);
    }

    u64 now = bpf_ktime_get_ns();
    u32 len = skb->len;

    struct flow_stats_t *fs = flow_map.lookup(&key);
    if (!fs) {
        struct flow_stats_t nfs = {};
        nfs.packets = 1;
        nfs.bytes   = len;
        nfs.last_seen_ns = now;
        flow_map.insert(&key, &nfs);
    } else {
        u64 gap = now - fs->last_seen_ns;
        fs->interpacket_gap_ns = fs->interpacket_gap_ns == 0 ? gap :
                                 (fs->interpacket_gap_ns * 7 + gap) >> 3;
        fs->packets++;
        fs->bytes += len;
        fs->last_seen_ns = now;
        if (fs->bytes > ELEPHANT_BYTES) fs->is_elephant = 1;
    }

    u32 zero = 0;
    struct global_t *gs = global_map.lookup(&zero);
    if (gs) { gs->total_packets++; gs->total_bytes += len; }

    u32 b = (len < 128) ? 0 : (len < 512) ? 1 : (len < 1500) ? 2 : 3;
    u64 *cnt = pkt_hist.lookup(&b);
    if (cnt) (*cnt)++;

    return TC_ACT_OK;
}
