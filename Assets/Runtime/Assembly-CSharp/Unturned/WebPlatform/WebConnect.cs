////////////////////////////////////////////////////////////////////////////////////////
// This file is part of the U3 SDK: https://github.com/smartlydressedgames/u3-sdk/    //
// Please refer to the included LICENSE.txt for copyright notice and license details. //
////////////////////////////////////////////////////////////////////////////////////////
#if UNITY_WEBGL && !UNITY_EDITOR
using System.Runtime.InteropServices;
using SDG.NetTransport.WebSocket;
using Unturned.SystemEx;

namespace SDG.Unturned
{
	/// <summary>
	/// Direct connect for web players: "host:port" of a server running ServerTransport_WebSocket
	/// (the port is the server's connection port, i.e. its configured port + 1).
	/// </summary>
	public static class WebConnect
	{
		[DllImport("__Internal")] private static extern string WebSock_GetRequestedServer();

		public const ushort DefaultConnectionPort = 27016;

		public static string GetRequestedServer()
		{
			return WebSock_GetRequestedServer();
		}

		public static void Connect(string hostAndPort, string password)
		{
			string host = hostAndPort.Trim();
			ushort port = DefaultConnectionPort;
			string withoutScheme = host.Replace("wss://", "").Replace("ws://", "");
			int colon = withoutScheme.LastIndexOf(':');
			if (colon > 0 && ushort.TryParse(withoutScheme.Substring(colon + 1).TrimEnd('/'), out ushort parsed))
			{
				port = parsed;
				withoutScheme = withoutScheme.Substring(0, colon);
			}

			// Plain IPv4 addresses go into the normal connect parameters; host names only into the socket URL.
			if (!IPv4Address.TryParse(withoutScheme, out uint ip))
			{
				ip = new IPv4Address("127.0.0.1").value;
			}
			ClientTransport_WebSocket.ServerUrlOverride = host.StartsWith("ws") ? host : withoutScheme + ":" + port;

			UnturnedLog.info($"Web connect: {ClientTransport_WebSocket.ServerUrlOverride}");
			ServerConnectParameters parameters = new ServerConnectParameters(new IPv4Address(ip), (ushort) (port - 1), port, password ?? string.Empty);
			Provider.connect(parameters, null, null);
		}
	}
}
#endif // UNITY_WEBGL && !UNITY_EDITOR
