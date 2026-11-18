"""
Generates Assets/Plugins/WebGL/SteamOfflineStubs.c: a C implementation of every native
function Steamworks.NET imports, so browser builds link and run with no Steam client.

Every function is a no-op that returns zero, except a short list of overrides that make
the game believe it is signed in offline as a local player. Run after updating Steamworks.NET:

    python Tools/WebPort/gen_steam_stubs.py
"""
import os, re, sys, glob

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SW = os.path.join(ROOT, "Assets", "com.rlabrecque.steamworks.net", "Runtime")
OUT = os.path.join(ROOT, "Assets", "Plugins", "WebGL", "SteamOfflineStubs.c")

PRIM = {
    "bool": "i32", "byte": "i32", "sbyte": "i32", "short": "i32", "ushort": "i32",
    "int": "i32", "uint": "i32", "char": "i32", "IntPtr": "i32", "UIntPtr": "i32",
    "long": "i64", "ulong": "i64", "float": "f32", "double": "f64", "void": "void",
}
CTYPE = {"i32": "int32_t", "i64": "int64_t", "f32": "float", "f64": "double", "void": "void"}

def read_all(paths):
    return "\n".join(open(p, encoding="utf-8-sig").read() for p in paths)

src_types = read_all(glob.glob(os.path.join(SW, "**", "*.cs"), recursive=True))

enums = {}
for m in re.finditer(r"\benum\s+(\w+)\s*(?::\s*(\w+))?\s*\{", src_types):
    enums[m.group(1)] = m.group(2) or "int"

structs = {}
for m in re.finditer(r"\bstruct\s+(\w+)\s*(?::[^{]*)?\{", src_types):
    name, start, depth, i = m.group(1), m.end(), 1, m.end()
    while depth and i < len(src_types):
        depth += {"{": 1, "}": -1}.get(src_types[i], 0)
        i += 1
    body = src_types[start:i - 1]
    # Drop nested method/property bodies so only top-level field declarations remain.
    flat, d = [], 0
    for ch in body:
        if ch == "{": d += 1; continue
        if ch == "}": d -= 1; continue
        if d == 0: flat.append(ch)
    fields = []
    for stmt in "".join(flat).split(";"):
        stmt = re.sub(r"\[[^\]]*\]", "", stmt).strip()
        if not stmt or re.search(r"\b(static|const)\b|\(|=>|\boperator\b", stmt):
            continue
        fm = re.match(r"(?:(?:public|private|internal)\s+)?(?:fixed\s+)?([\w\.]+(?:\[\])?)\s+(\w+)\s*(\[\d+\])?$", stmt)
        if fm:
            fields.append((fm.group(1), bool(fm.group(3))))
    structs.setdefault(name, fields)

def classify(t, seen=()):
    t = t.split(".")[-1]
    if t.endswith("[]") or t.endswith("*"):
        return "i32"
    if t in PRIM:
        return PRIM[t]
    if t in enums:
        return PRIM[enums[t]]
    if t in structs and t not in seen:
        f = structs[t]
        if len(f) == 1 and not f[0][1]:
            return classify(f[0][0], seen + (t,))
        return "sret"
    return "i32"  # handles, delegates, classes, marshalled strings are all pointers

SIZES = {"bool": 1, "byte": 1, "sbyte": 1, "short": 2, "ushort": 2, "char": 2, "int": 4, "uint": 4,
         "float": 4, "IntPtr": 4, "long": 8, "ulong": 8, "double": 8}

def min_size(t, seen=()):
    """Lower bound on a struct's size (sum of fields, no padding), so zeroing it never overruns."""
    t = t.split(".")[-1]
    if t in SIZES:
        return SIZES[t]
    if t in enums:
        return SIZES[enums[t]]
    if t in structs and t not in seen:
        return sum(0 if arr else min_size(ft, seen + (t,)) for ft, arr in structs[t])
    return 4

nm = open(os.path.join(SW, "autogen", "NativeMethods.cs"), encoding="utf-8-sig").read()
decl = re.compile(
    r'\[DllImport\(\w+,\s*EntryPoint\s*=\s*"(\w+)"[^\]]*\]\s*'
    r'(?:\[return:[^\]]*\]\s*)?'
    r'public static extern ([\w\.\[\]]+) (\w+)\(([^)]*)\);', re.S)

OVERRIDES = {
    "SteamAPI_Init": "return 1;",
    "SteamAPI_IsSteamRunning": "return 1;",
    "SteamAPI_RestartAppIfNecessary": "return 0;",
    "SteamAPI_GetHSteamPipe": "return 1;",
    "SteamAPI_GetHSteamUser": "return 1;",
    "SteamGameServer_GetHSteamPipe": "return 1;",
    "SteamGameServer_GetHSteamUser": "return 1;",
    "SteamAPI_ManualDispatch_GetNextCallback": "return 0;",
    "ISteamUser_GetSteamID": "return WEB_STEAM_ID;",
    "ISteamUser_BLoggedOn": "return 1;",
    "ISteamFriends_GetPersonaName": "return (int32_t)(intptr_t)web_player_name;",
    "ISteamFriends_GetFriendPersonaName": "return (int32_t)(intptr_t)web_player_name;",
    "ISteamApps_BIsSubscribed": "return 1;",
    "ISteamApps_GetCurrentGameLanguage": "return (int32_t)(intptr_t)\"english\";",
    "ISteamApps_GetAvailableGameLanguages": "return (int32_t)(intptr_t)\"english\";",
    "ISteamUtils_GetSteamUILanguage": "return (int32_t)(intptr_t)\"english\";",
    "ISteamUtils_GetAppID": "return 304930;",
    "ISteamUtils_GetServerRealTime": "return (int32_t)time(NULL);",
    "ISteamUtils_IsOverlayEnabled": "return 0;",
}

seen, out, stats = set(), [], {"sret": 0, "total": 0}
for entry, ret, csname, params in decl.findall(nm):
    if entry in seen:
        continue
    seen.add(entry)
    stats["total"] += 1
    args = []
    for i, p in enumerate(filter(None, (x.strip() for x in params.split(",")))):
        p = re.sub(r"\[[^\]]*\]\s*", "", p)
        toks = p.split()
        if toks[0] in ("ref", "out", "in"):
            k = "i32"
        else:
            k = classify(toks[0])
            if k == "sret":
                k = "i32"  # multi-field struct passed by value -> passed indirectly
        args.append(f"{CTYPE[k]} a{i}")
    rk = classify(ret)
    key = entry.replace("SteamAPI_ISteam", "ISteam")
    body = OVERRIDES.get(key) or OVERRIDES.get(entry)
    if rk == "sret":
        stats["sret"] += 1
        args.insert(0, "void* sret")
        size = str(min_size(ret.split(".")[-1]))
        out.append(f"EXPORT void {entry}({', '.join(args)}) {{ memset(sret, 0, {size}); }}")
        continue
    if rk == "void":
        out.append(f"EXPORT void {entry}({', '.join(args) or 'void'}) {{ {body or ''} }}")
        continue
    if body is None:
        if ret.split(".")[-1] == "IntPtr":
            body = "return (int32_t)(intptr_t)web_zero_block;"  # non-null: interfaces "exist", strings read as ""
        else:
            body = "return 0;"
    out.append(f"EXPORT {CTYPE[rk]} {entry}({', '.join(args) or 'void'}) {{ {body} }}")

header = r'''// GENERATED by Tools/WebPort/gen_steam_stubs.py - do not edit by hand.
// Offline stand-in for steam_api used by browser (WebGL/WebGPU) builds.
#include <stdint.h>
#include <string.h>
#include <time.h>
#define EXPORT __attribute__((used, visibility("default")))
#define WEB_STEAM_ID ((int64_t)76561197960265729LL)
static char web_zero_block[65536] __attribute__((aligned(16)));
static char web_player_name[64] = "Player";
EXPORT void WebSteam_SetPlayerName(const char* name) { if (name) { strncpy(web_player_name, name, 63); web_player_name[63] = 0; } }

'''
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", encoding="utf-8", newline="\n") as f:
    f.write(header + "\n".join(out) + "\n")
print(f"wrote {OUT}: {stats['total']} functions, {stats['sret']} struct returns")
missing = [k for k in OVERRIDES if not any(e == k or e.replace('SteamAPI_ISteam', 'ISteam') == k for e in seen)]
if missing:
    print("overrides with no matching import:", missing)
