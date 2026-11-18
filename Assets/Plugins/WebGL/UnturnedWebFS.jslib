// Bridges the web page (WebGLTemplates/Unturned) and the game's virtual file system.
// The page reads the player's prepared game folder (Tools/WebPort/bundles/convert_for_web.py) into
// window.unturnedWebFiles before the player starts; nothing is uploaded anywhere.
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

    // Saves live in IndexedDB so they survive reloads. Populating is async; the game only reads
    // saves after the menu has loaded, long after this finishes.
    persistent.forEach(function (dir) {
      var path = root + "/" + dir;
      mkdirTree(path);
      try { FS.mount(IDBFS, {}, path); } catch (e) { console.warn("[Unturned web] IDBFS mount failed for " + path, e); }
    });
    try {
      FS.syncfs(true, function (err) {
        if (err) console.warn("[Unturned web] loading saves failed", err);
        else console.log("[Unturned web] saves loaded");
      });
    } catch (e) { console.warn("[Unturned web] syncfs failed", e); }

    var written = 0, bytes = 0;
    for (var i = 0; i < files.length; ++i) {
      var f = files[i];
      var rel = f.path.replace(/\\/g, "/").replace(/^\/+/, "");
      var top = rel.split("/")[0];
      if (persistent.indexOf(top) >= 0) continue; // never overwrite the player's saves
      var full = root + "/" + rel;
      mkdirTree(full.substring(0, full.lastIndexOf("/")));
      FS.writeFile(full, f.data, { canOwn: true });
      written++; bytes += f.data.length;
      f.data = null;
    }
    if (typeof window !== "undefined") window.unturnedWebFiles = null;
    console.log("[Unturned web] mounted " + written + " files (" + Math.round(bytes / 1048576) + " MB) at " + root);

    if (typeof window !== "undefined" && !window.unturnedSaveTimer) {
      var save = function () { try { FS.syncfs(false, function () {}); } catch (e) {} };
      window.unturnedSaveTimer = setInterval(save, 15000);
      window.addEventListener("beforeunload", save);
      window.addEventListener("visibilitychange", function () { if (document.visibilityState === "hidden") save(); });
    }
    return written;
  },

  WebFS_SaveNow: function () {
    try { FS.syncfs(false, function (err) { if (err) console.warn("[Unturned web] save failed", err); }); } catch (e) {}
  },

  WebFS_GetPlayerName: function () {
    var name = (typeof window !== "undefined" && window.unturnedPlayerName) || "Player";
    var size = lengthBytesUTF8(name) + 1;
    var buffer = _malloc(size);
    stringToUTF8(name, buffer, size);
    return buffer;
  },
});
