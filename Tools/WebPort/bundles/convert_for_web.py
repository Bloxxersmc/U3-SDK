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
SKIP_DIRS = {"Unturned_Data", "MonoBleedingEdge", "BattlEye", "Logs", "Servers", "Sandbox", "Extras", "Modules"}
SKIP_EXT = {".exe", ".dll", ".pdb", ".bat", ".lnk", ".vdf"}
BUNDLE_EXT = {".masterbundle", ".unity3d"}


def write_cstr(f, s):
    f.write(s.encode() + b"\0")


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
                    packed.write(chunk); blocks.append((len(chunk), len(chunk), 0x40))
                else:
                    packed.write(c); blocks.append((len(chunk), len(c), 0x43))

            info = bytearray(16)
            info += struct.pack(">I", len(blocks))
            for u, c, fl in blocks:
                info += struct.pack(">IIH", u, c, fl)
            info += struct.pack(">I", len(b.nodes))
            for name, off, size, flags in b.nodes:
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
