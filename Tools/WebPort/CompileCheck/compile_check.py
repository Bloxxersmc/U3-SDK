"""
Compile the game's runtime C# against an Unturned install's Unity DLLs with player defines,
without the Unity editor. Default is the WebGL player; pass --desktop to check the desktop build.

    python Tools/WebPort/CompileCheck/compile_check.py [--managed <Unturned_Data/Managed>] [--desktop]
"""
import argparse, glob, os, subprocess, sys, tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
ap = argparse.ArgumentParser()
ap.add_argument("--managed", default=r"C:\Program Files (x86)\Steam\steamapps\common\Unturned\Unturned_Data\Managed")
ap.add_argument("--desktop", action="store_true")
args = ap.parse_args()

csc = sorted(glob.glob(r"C:\Program Files\dotnet\sdk\*\Roslyn\bincore\csc.dll"))[-1]
versions = ["UNITY_5_3", "UNITY_5_4", "UNITY_5_5", "UNITY_5_6"] + [f"UNITY_{y}_{m}" for y in range(2017, 2023) for m in range(1, 5) if not (y >= 2022 and m > 3) and not (y >= 2020 and m > 3)]
defines = [v + "_OR_NEWER" for v in versions] + ["UNITY_2022_3_62", "UNITY_2022_3", "UNITY_2022", "NET_4_6", "NET_UNITY_4_8",
           "GAME", "UNITY_POST_PROCESSING_STACK_V2", "STEAMWORKS_NET", "ENABLE_IL2CPP"]
defines += ["UNITY_STANDALONE", "UNITY_STANDALONE_WIN", "UNITY_64", "WITH_GRANTPACKAGE_PROMO"] if args.desktop else ["UNITY_WEBGL"]

skip = {"Assembly-CSharp.dll", "UnityEx.dll", "com.rlabrecque.steamworks.net.dll", "BattlEye.dll"}
base_refs = [p for p in glob.glob(os.path.join(args.managed, "*.dll")) if os.path.basename(p) not in skip]
tmp = os.path.join(tempfile.gettempdir(), "u3-webcheck")
os.makedirs(tmp, exist_ok=True)

# Same assembly split as the Unity project's asmdefs, so the shipped DLLs' references resolve.
steps = [
    ("com.rlabrecque.steamworks.net", ["Assets/com.rlabrecque.steamworks.net/Runtime"]),
    ("UnityEx", ["Assets/Runtime/UnityEx"]),
    ("Assembly-CSharp", ["Assets/Runtime/Assembly-CSharp"]),
]
built, total = [], 0
for name, dirs in steps:
    srcs = []
    for d in dirs:
        srcs += glob.glob(os.path.join(ROOT, d, "**", "*.cs"), recursive=True)
    out = os.path.join(tmp, name + ".dll")
    rsp = ["-nologo", "-noconfig", "-nostdlib+", "-target:library", "-unsafe+", "-langversion:9.0",
           "-nowarn:0612,0618,0162,0168,0219,0414,0649,0067,0169,1998,0108,0114,0429,0436,8632",
           f"-out:{out}", "-define:" + ";".join(defines)] + [f'-r:"{r}"' for r in base_refs + built] + [f'"{s}"' for s in srcs]
    rspf = os.path.join(tmp, name + ".rsp")
    open(rspf, "w", encoding="utf-8").write("\n".join(rsp))
    r = subprocess.run(["dotnet", "exec", csc, "@" + rspf], capture_output=True, text=True)
    lines = [l.replace(ROOT + os.sep, "") for l in r.stdout.splitlines() if ": error " in l]
    if lines:
        print("\n".join(sorted(set(lines))[:150]))
    print(f"[{'DESKTOP' if args.desktop else 'WEBGL'}] {name}: {len(lines)} errors")
    total += len(lines)
    if lines:
        break
    built.append(out)
sys.exit(1 if total else 0)
