"""
Prepare a local copy of your own Unturned install for the browser build.

  * Asset bundles (.masterbundle, .unity3d) are retargeted from StandaloneWindows64 to WebGL and
    recompressed as chunked LZ4, so the WebGL player accepts them and can stream them from its
    virtual file system instead of unpacking everything into memory.
  * Every other file the game reads (.dat, .asset, localization, map data, ...) is copied as is.
  * Windows binaries (.exe, .dll, Unturned_Data, BattlEye, ...) are skipped.

The output stays on your machine. It contains SDG's and third parties' game content, which may
not be redistributed, so never commit it or upload it to a public host.

    pip install lz4
    python Tools/WebPort/bundles/convert_for_web.py --src "C:/.../steamapps/common/Unturned" --out "C:/.../UnturnedWebData" [--maps PEI]
"""
import argparse, lzma, os, shutil, struct, sys, tempfile, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from unityfs import Bundle, decompress, serialized_header  # noqa: E402

try:
    import lz4.block
except ImportError:
    sys.exit("This tool needs the lz4 package:  python -m pip install --user lz4")

WEBGL = 20
CHUNK = 128 * 1024
# Per-chunk storage flags: low 6 bits = compression (0 none, 3 LZ4HC); 0x40 = "streamed".
BLOCK_FLAGS_RAW = 0x0
BLOCK_FLAGS_LZ4 = 0x3
SKIP_DIRS = {"Unturned_Data", "MonoBleedingEdge", "BattlEye", "Logs", "Servers", "Sandbox", "Extras", "Modules"}
SKIP_EXT = {".exe", ".dll", ".pdb", ".bat", ".lnk", ".vdf"}
BUNDLE_EXT = {".masterbundle", ".unity3d"}


def write_cstr(f, s):
    f.write(s.encode() + b"\0")


# Textures whose streamed pixel data is at most this size get it moved inline. The WebGL player
# loaded small streamed textures with no pixels ("The image data of Texture ... has an unexpected
# size (expected N, got 0)") while large ones were fine; inline data takes the path that works.
INLINE_TEXTURE_BYTES = 256 * 1024


def inline_small_textures(raw, nodes, threshold):
    """
    raw: file with the bundle's uncompressed data stream. Returns (new_raw or None, new_nodes, count).
    Only format 22+ serialized files with type trees are rewritten; anything else is left as is.
    """
    from serialized import SerializedFile
    sf_nodes = [n for n in nodes if n[3] & 4]
    if len(sf_nodes) != 1:
        return None, nodes, 0
    name, off, size, flags = sf_nodes[0]
    raw.seek(off)
    buf = raw.read(size)
    try:
        sf = SerializedFile(buf)
    except Exception:
        return None, nodes, 0
    by_name = {n[0]: n for n in nodes}
    res_name = name + ".resS"
    if res_name not in by_name:
        return None, nodes, 0
    res_off = by_name[res_name][1]

    new_blobs, count = [], 0
    for obj in sf.objects:
        pid, start, osize, tid = obj
        blob = buf[sf.data_offset + start:sf.data_offset + start + osize]
        cls, root = sf.types[tid]
        if root is not None and root.type == "Texture2D":
            spans = sf.field_spans(obj)
            _, v = sf.read_object(obj)
            sd = v.get("m_StreamData") or {}
            img = v.get("image data")
            if ("image data" in spans and "m_StreamData" in spans and isinstance(img, tuple) and img[1] == 0
                    and 0 < sd.get("size", 0) <= threshold and sd.get("path", "").endswith(res_name)):
                raw.seek(res_off + sd["offset"])
                pixels = raw.read(sd["size"])
                i0, i1 = spans["image data"]
                s0, s1 = spans["m_StreamData"]
                e = sf.e
                img_bytes = struct.pack(e + "i", len(pixels)) + pixels
                img_bytes += b"\0" * ((4 - len(img_bytes) % 4) % 4)
                # StreamingInfo: offset (UInt64), size (UInt32), path (string, empty).
                sd_bytes = struct.pack(e + "QIi", 0, 0, 0)
                blob = blob[:i0] + img_bytes + blob[i1:s0] + sd_bytes + blob[s1:]
                count += 1
        new_blobs.append(blob)
    if not count:
        return None, nodes, 0

    new_sf = sf.rebuild(new_blobs)
    delta = len(new_sf) - size
    out = tempfile.TemporaryFile()
    raw.seek(0)
    shutil.copyfileobj(_LimitedReader(raw, off), out)
    out.write(new_sf)
    raw.seek(off + size)
    shutil.copyfileobj(raw, out, 16 * 1024 * 1024)
    new_nodes = []
    for n in nodes:
        nname, noff, nsize, nflags = n
        if nname == name:
            new_nodes.append((nname, noff, len(new_sf), nflags))
        elif noff > off:
            new_nodes.append((nname, noff + delta, nsize, nflags))
        else:
            new_nodes.append(n)
    return out, new_nodes, count


class _LimitedReader:
    def __init__(self, f, n):
        self.f, self.left = f, n

    def read(self, size=-1):
        if self.left <= 0:
            return b""
        size = self.left if size < 0 else min(size, self.left)
        data = self.f.read(size)
        self.left -= len(data)
        return data


def convert_bundle(src, dst, platform=WEBGL):
    b = Bundle(src)
    if b.signature == "UnityRaw":
        # Uncompressed legacy bundle: copy, then patch each serialized file's platform in place.
        shutil.copyfile(src, dst)
        patched = 0
        with open(dst, "r+b") as f:
            for name, off, size, flags in b.nodes:
                if not (flags & 4):
                    continue
                f.seek(b.data_start + off)
                hdr = serialized_header(f.read(4096))
                if hdr["platform"] != platform:
                    f.seek(b.data_start + off + hdr["platform_offset"])
                    f.write(struct.pack(">i" if hdr["big"] else "<i", platform))
                    patched += 1
        return b.blocks[0][0], patched, 1
    total = sum(u for u, _, _ in b.blocks)
    with tempfile.TemporaryFile() as raw:
        # 1. Unpack the whole data stream to a temp file, block by block.
        b.f.seek(b.data_start)
        for u, c, fl in b.blocks:
            comp = fl & 0x3F
            data = b.f.read(c)
            if comp == 1:
                props = data[:5]
                dec = lzma.LZMADecompressor(lzma.FORMAT_RAW, filters=[{
                    "id": lzma.FILTER_LZMA1, "dict_size": struct.unpack("<I", props[1:5])[0],
                    "lc": props[0] % 9, "lp": (props[0] // 9) % 5, "pb": props[0] // 45}])
                left, pos, step = u, 5, 8 * 1024 * 1024
                while left > 0:
                    out = dec.decompress(data[pos:pos + step] if pos < len(data) else b"", max_length=min(left, 64 * 1024 * 1024))
                    pos += step
                    if out:
                        raw.write(out); left -= len(out)
                    elif pos >= len(data) and dec.eof:
                        break
                if left:
                    raise IOError(f"{src}: LZMA block ended {left} bytes short")
            else:
                raw.write(decompress(data, u, comp))

        # 2. Retarget every serialized file in the archive.
        patched = 0
        for name, off, size, flags in b.nodes:
            if not (flags & 4):
                continue
            raw.seek(off)
            hdr = serialized_header(raw.read(4096))
            if hdr["platform"] != platform:
                raw.seek(off + hdr["platform_offset"])
                raw.write(struct.pack("<i", platform))
                patched += 1

        # 2b. Small textures: move their pixels from the .resS stream into the object itself.
        nodes = list(b.nodes)
        inlined = 0
        if INLINE_TEXTURE_BYTES > 0:
            new_raw, nodes, inlined = inline_small_textures(raw, nodes, INLINE_TEXTURE_BYTES)
            if new_raw is not None:
                raw.close()
                raw = new_raw
                print(f"  {os.path.basename(src)}: moved {inlined} small texture(s) inline")

        # 3. Recompress as 128 KiB LZ4 chunks (what Unity's ChunkBasedCompression produces).
        blocks = []
        with tempfile.TemporaryFile() as packed:
            raw.seek(0)
            while True:
                chunk = raw.read(CHUNK)
                if not chunk:
                    break
                c = lz4.block.compress(chunk, mode="high_compression", compression=9, store_size=False)
                if len(c) >= len(chunk):
                    packed.write(chunk); blocks.append((len(chunk), len(chunk), BLOCK_FLAGS_RAW))
                else:
                    packed.write(c); blocks.append((len(chunk), len(c), BLOCK_FLAGS_LZ4))

            info = bytearray(16)
            info += struct.pack(">I", len(blocks))
            for u, c, fl in blocks:
                info += struct.pack(">IIH", u, c, fl)
            info += struct.pack(">I", len(nodes))
            for name, off, size, flags in nodes:
                info += struct.pack(">qqI", off, size, flags) + name.encode() + b"\0"
            cinfo = lz4.block.compress(bytes(info), mode="high_compression", compression=9, store_size=False)

            flags = 0x40 | 0x200 | 0x3  # info combined with directory, padded, LZ4HC
            with open(dst, "wb") as f:
                f.write(b"UnityFS\0"); f.write(struct.pack(">I", b.format))
                write_cstr(f, b.player); write_cstr(f, b.engine)
                size_pos = f.tell()
                f.write(struct.pack(">qIII", 0, len(cinfo), len(info), flags))
                if b.format >= 7:
                    f.write(b"\0" * ((16 - f.tell() % 16) % 16))
                f.write(cinfo)
                f.write(b"\0" * ((16 - f.tell() % 16) % 16))
                packed.seek(0)
                shutil.copyfileobj(packed, f, 16 * 1024 * 1024)
                end = f.tell()
                f.seek(size_pos); f.write(struct.pack(">q", end))
    return total, patched, len(blocks)


def verify_bundle(path, platform=WEBGL):
    b = Bundle(path)
    for name, off, size, flags in b.nodes:
        if flags & 4:
            hdr = serialized_header(b.read_stream(off, 4096))
            if hdr["platform"] != platform:
                return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=r"C:\Program Files (x86)\Steam\steamapps\common\Unturned")
    ap.add_argument("--out", default=os.path.join(os.path.expanduser("~"), "Downloads", "UnturnedWebData"))
    ap.add_argument("--maps", nargs="*", default=["PEI"], help="map folders to include (default: PEI). 'all' for every map")
    ap.add_argument("--force", action="store_true", help="reconvert bundles that already exist in --out")
    a = ap.parse_args()
    src, out = os.path.abspath(a.src), os.path.abspath(a.out)
    if out.startswith(src):
        sys.exit("--out must not be inside the Unturned install")

    copied = converted = 0
    t0 = time.time()
    for dirpath, dirnames, filenames in os.walk(src):
        rel = os.path.relpath(dirpath, src)
        parts = [] if rel == "." else rel.split(os.sep)
        if parts and parts[0] in SKIP_DIRS:
            dirnames[:] = []; continue
        if len(parts) >= 1 and parts[0] == "Maps" and len(parts) >= 2 and a.maps != ["all"] and parts[1] not in a.maps:
            dirnames[:] = []; continue
        if parts and parts[0] == "Bundles" and len(parts) >= 2 and parts[1] == "Workshop":
            dirnames[:] = []; continue
        os.makedirs(os.path.join(out, rel), exist_ok=True)
        for fn in filenames:
            ext = os.path.splitext(fn)[1].lower()
            if ext in SKIP_EXT:
                continue
            s, d = os.path.join(dirpath, fn), os.path.join(out, rel, fn)
            if ext in BUNDLE_EXT:
                if os.path.exists(d) and not a.force and os.path.getmtime(d) >= os.path.getmtime(s):
                    continue
                t = time.time()
                total, patched, nblocks = convert_bundle(s, d)
                ok = verify_bundle(d)
                converted += 1
                print(f"bundle {os.path.join(rel, fn)}: {total / 1e6:.0f} MB unpacked, {patched} file(s) retargeted, "
                      f"{os.path.getsize(s) / 1e6:.0f} -> {os.path.getsize(d) / 1e6:.0f} MB, {time.time() - t:.0f}s, verify={'ok' if ok else 'FAILED'}")
                if not ok:
                    sys.exit(f"verification failed for {d}")
            else:
                if not os.path.exists(d) or os.path.getsize(d) != os.path.getsize(s):
                    shutil.copy2(s, d); copied += 1
    print(f"done in {time.time() - t0:.0f}s: {converted} bundles converted, {copied} files copied -> {out}")


if __name__ == "__main__":
    main()
