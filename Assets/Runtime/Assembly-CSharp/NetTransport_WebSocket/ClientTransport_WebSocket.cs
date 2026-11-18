////////////////////////////////////////////////////////////////////////////////////////
// This file is part of the U3 SDK: https://github.com/smartlydressedgames/u3-sdk/    //
// Please refer to the included LICENSE.txt for copyright notice and license details. //
////////////////////////////////////////////////////////////////////////////////////////
#if UNITY_WEBGL && !UNITY_EDITOR
using System.Runtime.InteropServices;
using Unturned.SystemEx;

namespace SDG.NetTransport.WebSocket
{
	/// <summary>
	/// Browser client transport: one WebSocket (Plugins/WebGL/UnturnedWebSocket.jslib) to a server running
	/// ServerTransport_WebSocket. Each game message is one binary WebSocket message.
	/// </summary>
	public class ClientTransport_WebSocket : IClientTransport
	{
		[DllImport("__Internal")] private static extern void WebSock_Open(string url);
		[DllImport("__Internal")] private static extern int WebSock_State();
		[DllImport("__Internal")] private static extern string WebSock_Error();
		[DllImport("__Internal")] private static extern int WebSock_Receive(byte[] buffer, int capacity);
		[DllImport("__Internal")] private static extern int WebSock_Send(byte[] buffer, int size);
		[DllImport("__Internal")] private static extern void WebSock_Close();

		/// <summary>
		/// Optional "host:port" or "ws://host:port" that overrides the connect parameters' IPv4 address,
		/// so web players can connect by host name. Set by the web Connect flow.
		/// </summary>
		public static string ServerUrlOverride;

		private ClientTransportReady readyCallback;
		private ClientTransportFailure failureCallback;
		private bool isOpen;
		private bool isTornDown;
		private uint remoteAddress;
		private ushort remotePort;

		public void Initialize(ClientTransportReady callback, ClientTransportFailure failureCallback)
		{
			readyCallback = callback;
			this.failureCallback = failureCallback;
			var parameters = SDG.Unturned.Provider.CurrentServerConnectParameters;
			remoteAddress = parameters.address.value;
			remotePort = parameters.connectionPort;
			string url = BuildUrl(ServerUrlOverride, parameters.address, remotePort);
			SDG.Unturned.UnturnedLog.info($"WebSocket transport connecting to {url}");
			WebSock_Open(url);
			SDG.Framework.Utilities.TimeUtility.updated += OnUpdate;
		}

		internal static string BuildUrl(string overrideAddress, IPv4Address address, ushort port)
		{
			if (!string.IsNullOrEmpty(overrideAddress))
			{
				string a = overrideAddress.Trim();
				if (a.StartsWith("ws://") || a.StartsWith("wss://"))
					return a;
				// Pages served over https may only open wss:// sockets.
				string scheme = UnityEngine.Application.absoluteURL.StartsWith("https:") ? "wss://" : "ws://";
				return scheme + a;
			}
			return $"ws://{address}:{port}";
		}

		private void OnUpdate()
		{
			if (isTornDown)
				return;
			int state = WebSock_State();
			if (!isOpen && state == 1)
			{
				isOpen = true;
				readyCallback?.Invoke();
			}
			else if (state == 2)
			{
				SDG.Framework.Utilities.TimeUtility.updated -= OnUpdate;
				string error = WebSock_Error();
				failureCallback?.Invoke(string.IsNullOrEmpty(error) ? "Connection closed" : error);
			}
		}

		public void TearDown()
		{
			isTornDown = true;
			SDG.Framework.Utilities.TimeUtility.updated -= OnUpdate;
			WebSock_Close();
		}

		public bool Receive(byte[] buffer, out long size)
		{
			size = 0;
			if (isTornDown || !isOpen)
				return false;
			int n = WebSock_Receive(buffer, buffer.Length);
			if (n < 0)
			{
				SDG.Unturned.UnturnedLog.error($"WebSocket message of {-n} bytes is larger than the {buffer.Length} byte receive buffer; dropping connection");
				WebSock_Close();
				return false;
			}
			size = n;
			return n > 0;
		}

		public void Send(byte[] buffer, long size, ENetReliability reliability)
		{
			// WebSockets are reliable and ordered, so unreliable messages are simply sent reliably.
			if (isTornDown || !isOpen)
				return;
			WebSock_Send(buffer, (int) size);
		}

		public bool TryGetIPv4Address(out IPv4Address address)
		{
			address = new IPv4Address(remoteAddress);
			return true;
		}

		public bool TryGetConnectionPort(out ushort connectionPort)
		{
			connectionPort = remotePort;
			return true;
		}

		public bool TryGetQueryPort(out ushort queryPort)
		{
			queryPort = SDG.Unturned.MathfEx.ClampToUShort(remotePort - 1);
			return true;
		}

		public bool TryGetPing(out int pingMs)
		{
			pingMs = 0;
			return false;
		}
	}
}
#endif // UNITY_WEBGL && !UNITY_EDITOR
