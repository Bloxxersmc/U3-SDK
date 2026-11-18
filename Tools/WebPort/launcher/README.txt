Unturned web port - local launcher
==================================

Double-click "Start Unturned.bat".

It serves this folder at http://localhost:8765 (this PC only), starts the shared online server
if it isn't already running, and opens your browser. Press "Play offline" for singleplayer or
"Play online" to join the shared server. Keep the launcher window open while playing; closing it
stops the server it started.

Your name is picked for you (Survivor-NNNN) and can be changed on the start page.

FOR YOUR OWN PC ONLY. The gamedata folder holds Smartly Dressed Games' and third parties' game
content, converted from your own Unturned install. Don't upload it, share it, or host it on a
public site: the U3 SDK license doesn't allow redistributing it. The launcher only listens on
localhost and never uploads anything.

Needs Python 3 (https://www.python.org/downloads/). The online server also needs the U3-SDK
folder (with Builds/WebServer) and your Unturned Steam install; their paths are in launcher.json.
