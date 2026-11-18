"""Minimal UnityFS (asset bundle) reader: header, block/directory info, serialized-file metadata."""
import struct

def lz4_block_decompress(src, usize):
    dst, i, n = bytearray(), 0, len(src)
    while i < n:
        tok = src[i]; i += 1
        lit = tok >> 4
        if lit == 15:
            while True:
                b = src[i]; i += 1; lit += b
                if b != 255: break
        dst += src[i:i + lit]; i += lit
        if i >= n: break
        off = src[i] | (src[i + 1] << 8); i += 2
        ml = tok & 15
        if ml == 15:
            while True:
                b = src[i]; i += 1; ml += b
                if b != 255: break
        ml += 4
        start = len(dst) - off
        for k in range(ml):
            dst.append(dst[start + k])
    assert len(dst) == usize, (len(dst), usize)
    return bytes(dst)

def decompress(data, usize, comp):
    if comp == 0: return data
    if comp in (2, 3): return lz4_block_decompress(data, usize)
    if comp == 1:
        import lzma
        props, dsize = data[:5], usize
        return lzma.LZMADecompressor(lzma.FORMAT_RAW, filters=[{"id": lzma.FILTER_LZMA1, "dict_size": struct.unpack("<I", props[1:5])[0],
            "lc": props[0] % 9, "lp": (props[0] // 9) % 5, "pb": props[0] // 45}]).decompress(data[5:])[:dsize]
    raise ValueError(comp)

class Bundle:
    def __init__(self, path):
        self.f = open(path, "rb")
        d = self.f.read(4096)
        self.signature = d[:d.index(b"\0")].decode()
        o = d.index(b"\0") + 1
        if self.signature == "UnityRaw":
            self._init_raw(d, o)
            return
        self.format = struct.unpack(">I", d[o:o + 4])[0]; o += 4
        a = d.index(b"\0", o); self.player = d[o:a].decode(); o = a + 1
        b = d.index(b"\0", o); self.engine = d[o:b].decode(); o = b + 1
        self.size, csz, usz, self.flags = struct.unpack(">qIII", d[o:o + 20]); o += 20
        if self.format >= 7: o = (o + 15) & ~15
        if self.flags & 0x80:
            self.f.seek(self.size - csz); raw = self.f.read(csz)
            data_start = o
        else:
            self.f.seek(o); raw = self.f.read(csz); data_start = o + csz
            if self.flags & 0x200: data_start = (data_start + 15) & ~15
        info = decompress(raw, usz, self.flags & 0x3F)
        p = 16
        nb = struct.unpack(">I", info[p:p + 4])[0]; p += 4
        self.blocks = []
        for _ in range(nb):
            u, c, fl = struct.unpack(">IIH", info[p:p + 10]); p += 10
            self.blocks.append((u, c, fl))
        nn = struct.unpack(">I", info[p:p + 4])[0]; p += 4
        self.nodes = []
        for _ in range(nn):
            off, sz, fl = struct.unpack(">qqI", info[p:p + 20]); p += 20
            e = info.index(b"\0", p); name = info[p:e].decode(); p = e + 1
            self.nodes.append((name, off, sz, fl))
        self.data_start = data_start

    def _init_raw(self, d, o):
        """Legacy uncompressed bundle (Unity 5.x 'UnityRaw')."""
        self.format = struct.unpack(">I", d[o:o + 4])[0]; o += 4
        a = d.index(b"\0", o); self.player = d[o:a].decode(); o = a + 1
        b = d.index(b"\0", o); self.engine = d[o:b].decode(); o = b + 1
        _min_streamed, header_size = struct.unpack(">II", d[o:o + 8])
        self.f.seek(header_size)
        hdr = self.f.read(65536)
        n = struct.unpack(">I", hdr[:4])[0]; p = 4
        self.nodes = []
        for _ in range(n):
            e = hdr.index(b"\0", p); name = hdr[p:e].decode(); p = e + 1
            off, sz = struct.unpack(">II", hdr[p:p + 8]); p += 8
            flag = 0 if name.endswith((".resS", ".resource")) else 4
            self.nodes.append((name, off, sz, flag))
        self.data_start = header_size
        total = max(off + sz for _, off, sz, _ in self.nodes)
        self.blocks = [(total, total, 0)]
        self.flags = 0
        self.size = header_size + total

    def read_stream(self, offset, length):
        """Read `length` bytes of the uncompressed data stream starting at `offset`."""
        out, upos, cpos = bytearray(), 0, self.data_start
        for u, c, fl in self.blocks:
            if upos + u > offset and upos < offset + length:
                self.f.seek(cpos)
                blk = decompress(self.f.read(c), u, fl & 0x3F)
                lo = max(0, offset - upos); hi = min(u, offset + length - upos)
                out += blk[lo:hi]
            upos += u; cpos += c
            if upos >= offset + length: break
        return bytes(out)

def serialized_header(buf):
    """Parse a SerializedFile (version >= 22) header + start of metadata."""
    msize, fsize, ver, doff = struct.unpack(">IIII", buf[:16])
    if ver >= 22:
        msize, fsize, doff = struct.unpack(">IQQ", buf[20:40]); p = 48
    else:
        p = 20
    big = buf[16] != 0
    e = "<" if not big else ">"
    s = buf.index(b"\0", p); unity = buf[p:s].decode(); p = s + 1
    platform = struct.unpack(e + "i", buf[p:p + 4])[0]; p += 4
    typetree = buf[p] != 0
    return {"version": ver, "unity": unity, "platform": platform, "typetree": typetree, "platform_offset": p - 4, "big": big}
