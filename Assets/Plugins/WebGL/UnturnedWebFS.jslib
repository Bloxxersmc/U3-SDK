// Bridges the web page (WebGLTemplates/Unturned) and the game's virtual file system.
// The page reads the player's prepared game folder (Tools/WebPort/bundles/convert_for_web.py) plus
// their saves (IndexedDB) into window.unturnedWebFiles before the player starts; nothing is uploaded.
mergeInto(LibraryManager.library, {

  WebFS_MountGameFiles: function () {
    var root = "/unturned";
    var files = (typeof window !== "undefined" && window.unturnedWebFiles) || [];
    var persistent = ["Worlds", "Cloud"];

    function mkdirTree(path) {
      var parts = path.split("/").filter(function (p) { return p.length > 0; });
      var cur = "";
      for (var i = 0; i < parts.length; ++i) {
        cur += "/" + parts[i];
        try { FS.mkdir(cur); } catch (e) { /* exists */ }
      }
    }

    mkdirTree(root);
    persistent.forEach(function (d) { mkdirTree(root + "/" + d); });

    var written = 0, bytes = 0, saves = 0;
    for (var i = 0; i < files.length; ++i) {
      var f = files[i];
      var rel = f.path.replace(/\\/g, "/").replace(/^\/+/, "");
      var top = rel.split("/")[0];
      // Saves come only from IndexedDB, never from the install folder.
      if (persistent.indexOf(top) >= 0 && !f.save) continue;
      var full = root + "/" + rel;
      mkdirTree(full.substring(0, full.lastIndexOf("/")));
      FS.writeFile(full, f.data, { canOwn: true });
      written++; bytes += f.data.length;
      if (f.save) saves++;
      f.data = null;
    }
    if (typeof window !== "undefined") window.unturnedWebFiles = null;
    console.log("[Unturned web] mounted " + written + " files (" + Math.round(bytes / 1048576) + " MB, " + saves + " from saves) at " + root);

    // Persist saves: copy files changed since the last pass to IndexedDB via the page.
    var lastSave = Date.now();
    function collect(dir, out, since) {
      var names;
      try { names = FS.readdir(dir); } catch (e) { return; }
      for (var k = 0; k < names.length; ++k) {
        var n = names[k];
        if (n === "." || n === "..") continue;
        var p = dir + "/" + n, st;
        try { st = FS.stat(p); } catch (e) { continue; }
        if (FS.isDir(st.mode)) collect(p, out, since);
        else if (st.mtime.getTime() >= since) out.push({ path: p.substring(root.length + 1), data: FS.readFile(p) });
      }
    }
    function save() {
      if (typeof window === "undefined" || !window.unturnedStoreSaves) return;
      var since = lastSave, now = Date.now(), changed = [];
      persistent.forEach(function (d) { collect(root + "/" + d, changed, since); });
      lastSave = now;
      if (changed.length) window.unturnedStoreSaves(changed);
    }
    if (typeof window !== "undefined") {
      window.unturnedSaveNow = save;
      if (!window.unturnedSaveTimer) {
        window.unturnedSaveTimer = setInterval(save, 15000);
        window.addEventListener("beforeunload", save);
        window.addEventListener("visibilitychange", function () { if (document.visibilityState === "hidden") save(); });
      }
    }
    return written;
  },

  WebFS_SaveNow: function () {
    if (typeof window !== "undefined" && window.unturnedSaveNow) window.unturnedSaveNow();
  },

  // Random per-browser account number (1 .. 2^31-1) chosen by the page and kept in localStorage,
  // so every web player gets their own SteamID on servers.
  WebFS_GetAccountId: function () {
    var id = (typeof window !== "undefined" && window.unturnedAccountId) | 0;
    return id > 0 ? id : 1;
  },

  WebFS_GetPlayerName: function () {
    var name = (typeof window !== "undefined" && window.unturnedPlayerName) || "Player";
    var size = lengthBytesUTF8(name) + 1;
    var buffer = _malloc(size);
    stringToUTF8(name, buffer, size);
    return buffer;
  },
});
