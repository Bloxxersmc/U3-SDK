// Browser WebSocket for the web client's game transport (ClientTransport_WebSocket.cs).
// One connection at a time. Incoming binary messages are queued and drained by C# each frame.
mergeInto(LibraryManager.library, {

  WebSock_Open: function (urlPtr) {
    var url = UTF8ToString(urlPtr);
    var state = { socket: null, queue: [], status: 0, error: "" }; // status: 0 connecting, 1 open, 2 closed/failed
    window.unturnedSock = state;
    try {
      var ws = new WebSocket(url);
      ws.binaryType = "arraybuffer";
      ws.onopen = function () { state.status = 1; console.log("[Unturned web] connected to " + url); };
      ws.onmessage = function (e) { if (e.data instanceof ArrayBuffer) state.queue.push(new Uint8Array(e.data)); };
      ws.onerror = function () { state.error = "Could not connect to " + url + " (is the server running and reachable?)"; };
      ws.onclose = function (e) {
        if (state.status !== 2) {
          state.status = 2;
          if (!state.error) state.error = "Connection to " + url + " closed (code " + e.code + (e.reason ? ", " + e.reason : "") + ")";
        }
      };
      state.socket = ws;
    } catch (e) {
      state.status = 2;
      state.error = "Invalid server address " + url + ": " + e;
    }
  },

  // 0 connecting, 1 open, 2 closed or failed.
  WebSock_State: function () {
    var s = window.unturnedSock;
    return s ? s.status : 2;
  },

  WebSock_Error: function () {
    var s = window.unturnedSock, msg = (s && s.error) || "";
    var size = lengthBytesUTF8(msg) + 1, buf = _malloc(size);
    stringToUTF8(msg, buf, size);
    return buf;
  },

  // Copies the next queued message into buffer. Returns its size, 0 if none, or -size if the buffer is too small.
  WebSock_Receive: function (buffer, capacity) {
    var s = window.unturnedSock;
    if (!s || !s.queue.length) return 0;
    var msg = s.queue[0];
    if (msg.length > capacity) return -msg.length;
    s.queue.shift();
    HEAPU8.set(msg, buffer);
    return msg.length;
  },

  WebSock_Send: function (buffer, size) {
    var s = window.unturnedSock;
    if (!s || s.status !== 1) return 0;
    try {
      s.socket.send(HEAPU8.slice(buffer, buffer + size));
      return 1;
    } catch (e) {
      return 0;
    }
  },

  WebSock_BufferedAmount: function () {
    var s = window.unturnedSock;
    return s && s.socket ? s.socket.bufferedAmount : 0;
  },

  WebSock_Close: function () {
    var s = window.unturnedSock;
    if (s) {
      s.status = 2;
      try { if (s.socket) s.socket.close(1000, "client disconnect"); } catch (e) {}
      window.unturnedSock = null;
    }
  },

  // Address the page asked to connect to (?connect=host:port or the start page field), or "".
  WebSock_GetRequestedServer: function () {
    var v = (typeof window !== "undefined" && window.unturnedConnectTo) || "";
    var size = lengthBytesUTF8(v) + 1, buf = _malloc(size);
    stringToUTF8(v, buf, size);
    return buf;
  },
});
