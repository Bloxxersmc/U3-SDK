"""
Run a dedicated server that browser players can join (WebSocket transport, no Steam login needed).

    1. Build it once in Unity: Unturned > Web > Build Web Server (Windows), or headless:
       Unity.exe -batchmode -nographics -quit -projectPath . -buildTarget Win64 ^
           -executeMethod SDG.Unturned.WebPort.WebBuild.BuildWebServerCommandLine
    2. python Tools/WebPort/server/run_web_server.py [--map PEI] [--port 27015] [--name WebPort]

The server needs the game's content, which isn't part of the SDK. This links the folders from your own
Unturned install into Builds/WebServer (directory junctions: nothing is copied, uploaded, or changed in
the install). Server saves go to Builds/WebServer/Servers/<name>/.

Web players connect to <this PC's address>:<port + 1> (default 27016). Open that TCP port in the
firewall to let other PCs join.
"""
import argparse, os, shutil, subprocess, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
SERVER_DIR = os.path.join(ROOT, "Builds", "WebServer")
LINK_DIRS = ["Bundles", "Maps", "Localization", "Content", "Extras", "Sandbox", "LoadingScreens", "CuratedMapIcons"]
COPY_FILES = ["Status.json", "EconInfo.bin", "StreamerNames.json"]


def link_dir(src, dst):
    if os.path.lexists(dst):
        return
    # Directory junctions need no admin rights (unlike symlinks).
    subprocess.check_call(["cmd", "/c", "mklink", "/J", dst, src], stdout=subprocess.DEVNULL)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--install", default=r"C:\Program Files (x86)\Steam\steamapps\common\Unturned", help="your Unturned install")
    ap.add_argument("--name", default="WebPort", help="server id (folder under Servers/)")
    ap.add_argument("--map", default="PEI")
    ap.add_argument("--port", type=int, default=27015, help="server port; web players connect to port + 1")
    ap.add_argument("--maxplayers", type=int, default=8)
    a = ap.parse_args()

    exe = os.path.join(SERVER_DIR, "Unturned.exe")
    if not os.path.exists(exe):
        sys.exit(f"No server build at {exe}. Build it first (see this script's docstring).")
    if not os.path.isdir(os.path.join(a.install, "Bundles")):
        sys.exit(f"{a.install} doesn't look like an Unturned install (no Bundles folder). Pass --install.")

    for d in LINK_DIRS:
        src = os.path.join(a.install, d)
        if os.path.isdir(src):
            link_dir(src, os.path.join(SERVER_DIR, d))
    for f in COPY_FILES:
        src, dst = os.path.join(a.install, f), os.path.join(SERVER_DIR, f)
        if os.path.exists(src) and not os.path.exists(dst):
            shutil.copy2(src, dst)

    server_cfg = os.path.join(SERVER_DIR, "Servers", a.name, "Server")
    os.makedirs(server_cfg, exist_ok=True)
    with open(os.path.join(server_cfg, "Commands.dat"), "w", encoding="utf-8") as f:
        f.write(f"Name {a.name}\nMap {a.map}\nPort {a.port}\nMaxPlayers {a.maxplayers}\nPerspective Both\nMode Normal\n")

    args = [exe, "-batchmode", "-nographics", "-OfflineOnly", "-NetTransport", "WebSocket", f"+LanServer/{a.name}",
            "-logFile", os.path.join(SERVER_DIR, "Servers", a.name, "Server.log")]
    print(f"Starting {a.name} on {a.map}; web players connect to <this PC>:{a.port + 1}")
    print("Log:", os.path.join(SERVER_DIR, "Servers", a.name, "Server.log"))
    sys.exit(subprocess.call(args, cwd=SERVER_DIR))


if __name__ == "__main__":
    main()
