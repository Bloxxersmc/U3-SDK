"""
Assemble a self-contained site folder: the web build plus your converted game data.

    python Tools/WebPort/package_site.py [--build Builds/Web/WebGL] [--data ~/Downloads/UnturnedWebData] [--out ~/Downloads/UnturnedWeb]

The page finds gamedata/manifest.json next to itself and loads the game without the folder picker, so any
static web server can serve the folder (e.g. `python -m http.server 8765` inside it, or serve.py).
The game data is SDG's and third parties' content: keep the folder for your own use; publishing it
is redistribution, which the U3 SDK license and FAQ don't allow.
"""
import argparse, json, os, shutil

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOME = os.path.expanduser("~")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", default=os.path.join(ROOT, "Builds", "Web", "WebGL"))
    ap.add_argument("--data", default=os.path.join(HOME, "Downloads", "UnturnedWebData"))
    ap.add_argument("--out", default=os.path.join(HOME, "Downloads", "UnturnedWeb"))
    a = ap.parse_args()
    build, data, out = (os.path.abspath(p) for p in (a.build, a.data, a.out))
    if not os.path.exists(os.path.join(build, "index.html")):
        raise SystemExit(f"No web build at {build}")
    if not os.path.exists(os.path.join(data, "Bundles", "core.masterbundle")):
        raise SystemExit(f"No converted game data at {data} (run Tools/WebPort/bundles/convert_for_web.py)")

    os.makedirs(out, exist_ok=True)
    # Web build (small): replace it each time.
    for name in os.listdir(build):
        src, dst = os.path.join(build, name), os.path.join(out, name)
        if os.path.isdir(src):
            shutil.rmtree(dst, ignore_errors=True)
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)

    # Game data (large): copy only files that changed.
    gd = os.path.join(out, "gamedata")
    files, copied = [], 0
    for dp, _, fns in os.walk(data):
        for fn in fns:
            src = os.path.join(dp, fn)
            rel = os.path.relpath(src, data)
            dst = os.path.join(gd, rel)
            size = os.path.getsize(src)
            if not os.path.exists(dst) or os.path.getsize(dst) != size or os.path.getmtime(dst) < os.path.getmtime(src):
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)
                copied += 1
            files.append({"path": rel.replace(os.sep, "/"), "size": size})
    with open(os.path.join(gd, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump({"files": files}, f)
    total = sum(f["size"] for f in files)
    print(f"Site ready at {out}: {len(files)} game files ({total / 1048576:.0f} MB, {copied} copied this run)")
    print(f"Try it:  cd \"{out}\"  then  python -m http.server 8765  and open http://localhost:8765/")


if __name__ == "__main__":
    main()
