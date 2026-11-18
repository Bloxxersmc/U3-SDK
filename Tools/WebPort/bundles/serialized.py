"""
Minimal reader for Unity SerializedFile (format 22, with type trees): object table plus a
type-tree driven value reader. Used to inspect what a bundle actually stores.

    python Tools/WebPort/bundles/serialized.py <bundle> [ClassName] [limit]
"""
import struct, sys

# Unity's built-in "common strings" table (type-tree names with the high offset bit set).
COMMON = ("AABB\0AnimationClip\0AnimationCurve\0AnimationState\0Array\0Base\0BitField\0bitset\0bool\0char\0"
          "ColorRGBA\0Component\0data\0deque\0double\0dynamic_array\0FastPropertyName\0first\0float\0Font\0"
          "GameObject\0Generic Mono\0GradientNEW\0GUID\0GUIStyle\0int\0list\0long long\0map\0Matrix4x4f\0MdFour\0"
          "MonoBehaviour\0MonoScript\0m_ByteSize\0m_Curve\0m_EditorClassIdentifier\0m_EditorHideFlags\0m_Enabled\0"
          "m_ExtensionPtr\0m_GameObject\0m_Index\0m_IsArray\0m_IsStatic\0m_MetaFlag\0m_Name\0m_ObjectHideFlags\0"
          "m_PrefabInternal\0m_PrefabParentObject\0m_Script\0m_StaticEditorFlags\0m_Type\0m_Version\0Object\0pair\0"
          "PPtr<Component>\0PPtr<GameObject>\0PPtr<Material>\0PPtr<MonoBehaviour>\0PPtr<MonoScript>\0PPtr<Object>\0"
          "PPtr<Prefab>\0PPtr<Sprite>\0PPtr<TextAsset>\0PPtr<Texture>\0PPtr<Texture2D>\0PPtr<Transform>\0Prefab\0"
          "Quaternionf\0Rectf\0RectInt\0RectOffset\0second\0set\0short\0size\0SInt16\0SInt32\0SInt64\0SInt8\0"
          "staticvector\0string\0TextAsset\0TextMesh\0Texture\0Texture2D\0Transform\0TypelessData\0UInt16\0UInt32\0"
          "UInt64\0UInt8\0unsigned int\0unsigned long long\0unsigned short\0vector\0Vector2f\0Vector3f\0Vector4f\0"
          "m_ScriptingClassIdentifier\0Gradient\0Type*\0int2_storage\0int3_storage\0BoundsInt\0"
          "m_CorrespondingSourceObject\0m_PrefabInstance\0m_PrefabAsset\0FileSize\0Hash128\0RenderingLayerMask\0")


def cstr(buf, off):
    e = buf.index(b"\0", off)
    return buf[off:e].decode("utf-8", "replace"), e + 1


def common_string(off):
    b = COMMON.encode()
    return b[off:b.index(b"\0", off)].decode() if off < len(b) else f"<common {off}>"


class Node:
    __slots__ = ("type", "name", "size", "flags", "level", "children")


class SerializedFile:
    def __init__(self, buf):
        self.buf = buf
        ver = struct.unpack(">I", buf[8:12])[0]
        assert ver >= 22, f"format {ver} not supported"
        self.big = buf[16] != 0
        msize, fsize, self.data_offset = struct.unpack(">IQQ", buf[20:40])
        e = ">" if self.big else "<"
        self.e = e
        p = 48
        self.unity, p = cstr(buf, p)
        self.platform = struct.unpack(e + "i", buf[p:p + 4])[0]; p += 4
        has_tree = buf[p] != 0; p += 1
        ntypes = struct.unpack(e + "i", buf[p:p + 4])[0]; p += 4
        self.types = []
        for _ in range(ntypes):
            cls = struct.unpack(e + "i", buf[p:p + 4])[0]; p += 4
            p += 1  # stripped
            p += 2  # script type index
            if cls == 114:
                p += 16
            p += 16  # old type hash
            root = None
            if has_tree:
                nn, sl = struct.unpack(e + "ii", buf[p:p + 8]); p += 8
                raw = []
                for _ in range(nn):
                    ver_, level, tflags, to, no, size, idx, meta, _ref = struct.unpack(e + "HBBIIiiIQ", buf[p:p + 32]); p += 32
                    raw.append((level, to, no, size, meta, tflags))
                strings = buf[p:p + sl]; p += sl
                def s(o):
                    if o & 0x80000000:
                        return common_string(o & 0x7FFFFFFF)
                    return strings[o:strings.index(b"\0", o)].decode()
                stack = []
                for level, to, no, size, meta, tflags in raw:
                    n = Node(); n.type, n.name, n.size, n.flags, n.level, n.children = s(to), s(no), size, meta, level, []
                    while stack and stack[-1].level >= level:
                        stack.pop()
                    if stack:
                        stack[-1].children.append(n)
                    else:
                        root = n
                    stack.append(n)
                ndeps = struct.unpack(e + "i", buf[p:p + 4])[0]; p += 4 + 4 * ndeps
            self.types.append((cls, root))
        self._objects_at = p
        nobj = struct.unpack(e + "i", buf[p:p + 4])[0]; p += 4
        self.objects = []
        for _ in range(nobj):
            p = (p + 3) & ~3
            pid, start, size, tid = struct.unpack(e + "qqIi", buf[p:p + 24]); p += 24
            self.objects.append((pid, start, size, tid))

    PRIM = {"bool": "?", "char": "c", "SInt8": "b", "UInt8": "B", "SInt16": "h", "short": "h", "UInt16": "H",
            "unsigned short": "H", "SInt32": "i", "int": "i", "UInt32": "I", "unsigned int": "I", "Type*": "I",
            "SInt64": "q", "long long": "q", "UInt64": "Q", "unsigned long long": "Q", "FileSize": "Q",
            "float": "f", "double": "d"}

    def read(self, node, pos):
        e = self.e
        def align(n, pos):
            return (pos + 3) & ~3 if n.flags & 0x4000 else pos
        if node.type in self.PRIM:
            fmt = e + self.PRIM[node.type]
            sz = struct.calcsize(fmt)
            v = struct.unpack(fmt, self.buf[pos:pos + sz])[0]
            return v, align(node, pos + sz)
        if node.type == "string":
            n = struct.unpack(e + "i", self.buf[pos:pos + 4])[0]
            v = self.buf[pos + 4:pos + 4 + n].decode("utf-8", "replace")
            return v, (pos + 4 + n + 3) & ~3
        if node.type == "TypelessData":
            n = struct.unpack(e + "i", self.buf[pos:pos + 4])[0]
            return ("<bytes>", n), align(node, pos + 4 + n)
        if node.children and node.children[0].type == "Array":
            arr = node.children[0]
            n = struct.unpack(e + "i", self.buf[pos:pos + 4])[0]; pos += 4
            elem = arr.children[1]
            if elem.type in ("UInt8", "char", "SInt8"):
                v = ("<bytes>", n); pos += n
            else:
                v = []
                for _ in range(n):
                    x, pos = self.read(elem, pos); v.append(x)
            pos = align(arr, pos)
            return v, align(node, pos)
        out = {}
        for c in node.children:
            out[c.name], pos = self.read(c, pos)
        return out, align(node, pos)

    def read_object(self, obj):
        pid, start, size, tid = obj
        cls, root = self.types[tid]
        v, _ = self.read(root, self.data_offset + start)
        return cls, v

    def field_spans(self, obj):
        """Top-level fields of an object as {name: (start, end)} offsets relative to the object start."""
        pid, start, size, tid = obj
        cls, root = self.types[tid]
        base = self.data_offset + start
        pos, spans = base, {}
        for c in root.children:
            s = pos
            _, pos = self.read(c, pos)
            spans[c.name] = (s - base, pos - base)
        return spans

    def metadata_object_table_offset(self):
        """Byte offset (in the file) of the object count that precedes the object table."""
        return self._objects_at

    def rebuild(self, new_objects):
        """
        Serialize this file again with replaced object bytes.
        new_objects: list parallel to self.objects of bytes (the full object data).
        Returns the new file bytes. Metadata layout is unchanged except for object offsets/sizes.
        """
        e = self.e
        meta_start = 48
        # Rewrite the object table in place within a copy of the metadata.
        meta = bytearray(self.buf[:self.data_offset])
        p = self._objects_at + 4
        data = bytearray()
        for (pid, start, size, tid), blob in zip(self.objects, new_objects):
            p = (p + 3) & ~3
            data += b"\0" * ((8 - len(data) % 8) % 8)  # Unity aligns object data to 8 bytes
            struct.pack_into(e + "qqIi", meta, p, pid, len(data), len(blob), tid)
            p += 24
            data += blob
        out = bytes(meta) + bytes(data)
        hdr = bytearray(out[:48])
        struct.pack_into(">Q", hdr, 24, len(out))  # file size (format 22 header)
        return bytes(hdr) + out[48:]


if __name__ == "__main__":
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from unityfs import Bundle
    b = Bundle(sys.argv[1])
    want = sys.argv[2] if len(sys.argv) > 2 else "Texture2D"
    limit = int(sys.argv[3]) if len(sys.argv) > 3 else 20
    for name, off, size, flags in b.nodes:
        if not flags & 4:
            continue
        sf = SerializedFile(b.read_stream(off, size))
        print(f"{name}: unity {sf.unity}, platform {sf.platform}, {len(sf.objects)} objects")
        shown = 0
        for obj in sf.objects:
            cls, root = sf.types[obj[3]]
            if root is None or root.type != want:
                continue
            _, v = sf.read_object(obj)
            sd = v.get("m_StreamData", {})
            print(v.get("m_Name"), "fmt", v.get("m_TextureFormat"), f"{v.get('m_Width')}x{v.get('m_Height')}",
                  "mips", v.get("m_MipCount"), "inline", v.get("image data"), "stream", sd.get("size"), sd.get("path"))
            shown += 1
            if shown >= limit:
                break
