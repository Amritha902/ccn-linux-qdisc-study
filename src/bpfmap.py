#!/usr/bin/env python3
"""Read BPF maps through the bpf(2) syscall directly, without bpftool.

Two reasons this replaces the `bpftool map dump --json` path:

1. Cost. Spawning bpftool once per 500 ms control tick cost ~2.5 s per call in
   the VM (large binary loaded over a 9p root under emulation), stretching the
   control interval from 0.5 s to 3.17 s and reducing a 20 s run to 7 samples.
   Reading the map in-process brings the tick back to ~0.5 s.

2. Correctness. bpftool's JSON renders byte arrays as hex STRINGS
   (['0xa0','0xb8', ...]). The original controller called bytes(raw[16:24]) on
   that list, which raises TypeError; a bare `except: pass` swallowed it and
   returned zeros for every tick of every run. Reading raw bytes from the
   kernel removes that entire class of bug.

Falls back to bpftool if the syscall path is unavailable.
"""
import ctypes, ctypes.util, errno, os, struct

__NR_bpf = 321  # x86_64

BPF_MAP_LOOKUP_ELEM   = 1
BPF_MAP_GET_NEXT_KEY  = 4
BPF_MAP_GET_NEXT_ID   = 12
BPF_MAP_GET_FD_BY_ID  = 14
BPF_OBJ_GET_INFO_BY_FD = 15

_libc = ctypes.CDLL(ctypes.util.find_library("c") or "libc.so.6", use_errno=True)


def _bpf(cmd, attr):
    buf = ctypes.create_string_buffer(attr, max(len(attr), 128))
    r = _libc.syscall(ctypes.c_long(__NR_bpf), ctypes.c_int(cmd),
                      ctypes.byref(buf), ctypes.c_uint(len(buf)))
    if r < 0:
        raise OSError(ctypes.get_errno(), os.strerror(ctypes.get_errno()))
    return r, buf


class MapInfo(ctypes.Structure):
    """struct bpf_map_info — prefix through `name` is all we need."""
    _fields_ = [("type", ctypes.c_uint32), ("id", ctypes.c_uint32),
                ("key_size", ctypes.c_uint32), ("value_size", ctypes.c_uint32),
                ("max_entries", ctypes.c_uint32), ("map_flags", ctypes.c_uint32),
                ("name", ctypes.c_char * 16)]


def map_fd_by_id(map_id):
    _, _ = None, None
    fd, _ = _bpf(BPF_MAP_GET_FD_BY_ID, struct.pack("=III", map_id, 0, 0))
    return fd


def map_info(fd):
    info = MapInfo()
    attr = struct.pack("=IIQ", fd, ctypes.sizeof(info),
                       ctypes.addressof(info))
    _bpf(BPF_OBJ_GET_INFO_BY_FD, attr)
    return info


def list_map_ids():
    ids, cur = [], 0
    while True:
        try:
            _, buf = _bpf(BPF_MAP_GET_NEXT_ID, struct.pack("=III", cur, 0, 0))
        except OSError as e:
            if e.errno == errno.ENOENT:
                return ids
            raise
        cur = struct.unpack_from("=I", buf, 4)[0]
        ids.append(cur)


def find_map_by_name(prefix):
    """Return (map_id, fd, info) for the first map whose name starts with prefix."""
    for mid in list_map_ids():
        try:
            fd = map_fd_by_id(mid)
        except OSError:
            continue
        try:
            info = map_info(fd)
        except OSError:
            os.close(fd)
            continue
        if info.name.decode(errors="replace").startswith(prefix):
            return mid, fd, info
        os.close(fd)
    return None, None, None


def iter_map(fd, key_size, value_size, limit=100000):
    """Yield (key_bytes, value_bytes) for every entry in the map."""
    key = ctypes.create_string_buffer(key_size)
    nxt = ctypes.create_string_buffer(key_size)
    val = ctypes.create_string_buffer(value_size)
    have_key = False
    n = 0
    while n < limit:
        attr = struct.pack("=IIQQQ", fd, 0,
                           ctypes.addressof(key) if have_key else 0,
                           ctypes.addressof(nxt), 0)
        try:
            _bpf(BPF_MAP_GET_NEXT_KEY, attr)
        except OSError as e:
            if e.errno == errno.ENOENT:
                return
            raise
        ctypes.memmove(key, nxt, key_size)
        have_key = True
        lattr = struct.pack("=IIQQQ", fd, 0, ctypes.addressof(key),
                            ctypes.addressof(val), 0)
        try:
            _bpf(BPF_MAP_LOOKUP_ELEM, lattr)
        except OSError:
            continue        # entry evicted between iteration and lookup (LRU)
        yield bytes(key), bytes(val)
        n += 1


def available():
    try:
        list_map_ids()
        return True
    except OSError:
        return False


if __name__ == "__main__":
    print("bpf syscall available:", available())
    mid, fd, info = find_map_by_name("flow_ma")
    if mid is None:
        print("flow_map not found")
    else:
        print(f"flow_map id={mid} key={info.key_size}B value={info.value_size}B "
              f"max_entries={info.max_entries}")
        print("entries:", sum(1 for _ in iter_map(fd, info.key_size, info.value_size)))
