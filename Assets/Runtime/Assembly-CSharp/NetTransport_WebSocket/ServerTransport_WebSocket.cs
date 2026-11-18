////////////////////////////////////////////////////////////////////////////////////////
// This file is part of the U3 SDK: https://github.com/smartlydressedgames/u3-sdk/    //
// Please refer to the included LICENSE.txt for copyright notice and license details. //
////////////////////////////////////////////////////////////////////////////////////////
#if !UNITY_WEBGL || UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.Net;
using System.Net.Sockets;
using System.Security.Cryptography;
using System.Text;

namespace SDG.NetTransport.WebSocket
{
	/// <summary>
	/// Server transport that browser clients (ClientTransport_WebSocket) can reach: a plain TCP listener on the
	/// connection port that speaks WebSocket (RFC 6455). Each game message is one binary WebSocket message.
	/// Run a dedicated server with: -NetTransport WebSocket -OfflineOnly
	/// </summary>
	public class ServerTransport_WebSocket : IServerTransport
	{
		internal const int MaxMessageSize = 1024 * 1024;
		private const int MaxHandshakeSize = 16 * 1024;

		private struct PendingMessage
		{
			public TransportConnection_WebSocket connection;
			public byte[] buffer;
		}

		private Socket listenSocket;
		private readonly List<TransportConnection_WebSocket> connections = new List<TransportConnection_WebSocket>();
		private readonly Queue<PendingMessage> messages = new Queue<PendingMessage>();
		private readonly byte[] receiveBuffer = new byte[64 * 1024];
		private ServerTransportConnectionFailureCallback failureCallback;

		public void Initialize(ServerTransportConnectionFailureCallback connectionFailureCallback)
		{
			failureCallback = connectionFailureCallback;
			int port = Unturned.Provider.GetServerConnectionPort();
			if (!IPAddress.TryParse(Unturned.Provider.bindAddress, out IPAddress address))
			{
				address = IPAddress.Any;
			}
			IPEndPoint localEndPoint = new IPEndPoint(address, port);
			listenSocket = new Socket(AddressFamily.InterNetwork, SocketType.Stream, ProtocolType.Tcp);
			listenSocket.Blocking = false;
			listenSocket.Bind(localEndPoint);
			listenSocket.Listen(16);
			Unturned.UnturnedLog.info($"WebSocket server transport listening on ws://{localEndPoint}");
			SDG.Framework.Utilities.TimeUtility.updated += OnUpdate;
		}

		public void TearDown()
		{
			SDG.Framework.Utilities.TimeUtility.updated -= OnUpdate;
			foreach (TransportConnection_WebSocket connection in connections)
			{
				try { connection.socket.Close(); } catch { }
			}
			connections.Clear();
			listenSocket?.Close();
			listenSocket = null;
		}

		public bool Receive(byte[] buffer, out long size, out ITransportConnection transportConnection)
		{
			if (listenSocket != null && messages.Count > 0)
			{
				PendingMessage message = messages.Dequeue();
				if (message.buffer.Length <= buffer.Length)
				{
					Buffer.BlockCopy(message.buffer, 0, buffer, 0, message.buffer.Length);
					size = message.buffer.Length;
					transportConnection = message.connection;
					return true;
				}
				Close(message.connection, "message larger than receive buffer", true);
			}
			size = 0;
			transportConnection = null;
			return false;
		}

		internal void Close(TransportConnection_WebSocket connection, string reason, bool isError)
		{
			if (connection.wasClosed)
				return;
			connection.wasClosed = true;
			try
			{
				if (connection.isOpen)
				{
					connection.QueueFrame(0x8, Array.Empty<byte>(), 0);
					connection.Flush();
				}
				connection.socket.Close();
			}
			catch { }
			connections.Remove(connection);
			if (reason != null)
			{
				failureCallback?.Invoke(connection, reason, isError);
			}
		}

		private void OnUpdate()
		{
			if (listenSocket == null)
				return;

			while (Unturned.Provider.hasRoomForNewConnection && listenSocket.Poll(0, SelectMode.SelectRead))
			{
				try
				{
					Socket clientSocket = listenSocket.Accept();
					clientSocket.Blocking = false;
					clientSocket.NoDelay = true;
					connections.Add(new TransportConnection_WebSocket(this, clientSocket));
				}
				catch (SocketException)
				{
					break;
				}
			}

			for (int i = connections.Count - 1; i >= 0; --i)
			{
				TransportConnection_WebSocket connection = connections[i];
				try
				{
					ReadAvailable(connection);
					if (!connection.wasClosed)
						connection.Flush();
				}
				catch (Exception e)
				{
					Close(connection, "WebSocket error: " + e.Message, true);
				}
			}
		}

		private void ReadAvailable(TransportConnection_WebSocket connection)
		{
			while (!connection.wasClosed && connection.socket.Available > 0)
			{
				int n = connection.socket.Receive(receiveBuffer, 0, receiveBuffer.Length, SocketFlags.None, out SocketError error);
				if (error == SocketError.WouldBlock)
					return;
				if (error != SocketError.Success || n == 0)
				{
					Close(connection, "client disconnected", false);
					return;
				}
				connection.incoming.AddRange(new ArraySegment<byte>(receiveBuffer, 0, n));
				if (!connection.isOpen)
				{
					if (!TryHandshake(connection))
						return;
				}
				ParseFrames(connection);
			}
			// A closed TCP stream reports readable with nothing available.
			if (!connection.wasClosed && connection.socket.Poll(0, SelectMode.SelectRead) && connection.socket.Available == 0)
			{
				Close(connection, "client disconnected", false);
			}
		}

		private bool TryHandshake(TransportConnection_WebSocket connection)
		{
			List<byte> data = connection.incoming;
			int end = IndexOfHeaderEnd(data);
			if (end < 0)
			{
				if (data.Count > MaxHandshakeSize)
					Close(connection, "handshake too large", true);
				return false;
			}
			string request = Encoding.ASCII.GetString(data.GetRange(0, end).ToArray());
			data.RemoveRange(0, end + 4);

			string key = null;
			foreach (string line in request.Split(new[] { "\r\n" }, StringSplitOptions.None))
			{
				int colon = line.IndexOf(':');
				if (colon > 0 && line.Substring(0, colon).Trim().Equals("Sec-WebSocket-Key", StringComparison.OrdinalIgnoreCase))
					key = line.Substring(colon + 1).Trim();
			}
			if (key == null)
			{
				byte[] bad = Encoding.ASCII.GetBytes("HTTP/1.1 400 Bad Request\r\nContent-Length: 46\r\n\r\nThis port is an Unturned WebSocket game port.\n");
				connection.socket.Send(bad);
				Close(connection, null, false);
				return false;
			}
			string accept;
			using (SHA1 sha1 = SHA1.Create())
			{
				accept = Convert.ToBase64String(sha1.ComputeHash(Encoding.ASCII.GetBytes(key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11")));
			}
			string response = "HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: " + accept + "\r\n\r\n";
			connection.outgoing.AddRange(Encoding.ASCII.GetBytes(response));
			connection.isOpen = true;
			Unturned.UnturnedLog.info($"WebSocket client connected from {connection.GetAddressString(true)}");
			return true;
		}

		private static int IndexOfHeaderEnd(List<byte> data)
		{
			for (int i = 0; i + 3 < data.Count; ++i)
			{
				if (data[i] == '\r' && data[i + 1] == '\n' && data[i + 2] == '\r' && data[i + 3] == '\n')
					return i;
			}
			return -1;
		}

		private void ParseFrames(TransportConnection_WebSocket connection)
		{
			List<byte> data = connection.incoming;
			while (!connection.wasClosed && data.Count >= 2)
			{
				bool fin = (data[0] & 0x80) != 0;
				int opcode = data[0] & 0x0F;
				bool masked = (data[1] & 0x80) != 0;
				long length = data[1] & 0x7F;
				int header = 2;
				if (length == 126)
				{
					if (data.Count < 4) return;
					length = (data[2] << 8) | data[3];
					header = 4;
				}
				else if (length == 127)
				{
					if (data.Count < 10) return;
					length = 0;
					for (int k = 0; k < 8; ++k) length = (length << 8) | data[2 + k];
					header = 10;
				}
				if (!masked)
				{
					Close(connection, "unmasked client frame", true);
					return;
				}
				if (length > MaxMessageSize)
				{
					Close(connection, "message too large", true);
					return;
				}
				if (data.Count < header + 4 + length)
					return;

				byte[] mask = { data[header], data[header + 1], data[header + 2], data[header + 3] };
				byte[] payload = new byte[length];
				int start = header + 4;
				for (int k = 0; k < length; ++k)
					payload[k] = (byte) (data[start + k] ^ mask[k & 3]);
				data.RemoveRange(0, start + (int) length);

				switch (opcode)
				{
					case 0x0: // continuation
					case 0x2: // binary
						if (connection.fragment == null)
							connection.fragment = new List<byte>();
						connection.fragment.AddRange(payload);
						if (connection.fragment.Count > MaxMessageSize)
						{
							Close(connection, "message too large", true);
							return;
						}
						if (fin)
						{
							messages.Enqueue(new PendingMessage { connection = connection, buffer = connection.fragment.ToArray() });
							connection.fragment = null;
						}
						break;
					case 0x8: // close
						Close(connection, "client disconnected", false);
						return;
					case 0x9: // ping
						connection.QueueFrame(0xA, payload, payload.Length);
						break;
					default: // text, pong: ignored
						break;
				}
			}
		}
	}

	internal class TransportConnection_WebSocket : ITransportConnection
	{
		internal readonly ServerTransport_WebSocket server;
		internal readonly Socket socket;
		internal readonly List<byte> incoming = new List<byte>();
		internal readonly List<byte> outgoing = new List<byte>();
		internal List<byte> fragment;
		internal bool isOpen;
		internal bool wasClosed;
		private readonly IPEndPoint remote;

		public TransportConnection_WebSocket(ServerTransport_WebSocket server, Socket socket)
		{
			this.server = server;
			this.socket = socket;
			remote = socket.RemoteEndPoint as IPEndPoint;
		}

		internal void QueueFrame(int opcode, byte[] payload, int size)
		{
			outgoing.Add((byte) (0x80 | opcode));
			if (size < 126)
			{
				outgoing.Add((byte) size);
			}
			else if (size <= 0xFFFF)
			{
				outgoing.Add(126);
				outgoing.Add((byte) (size >> 8));
				outgoing.Add((byte) size);
			}
			else
			{
				outgoing.Add(127);
				for (int k = 7; k >= 0; --k)
					outgoing.Add((byte) ((long) size >> (8 * k)));
			}
			outgoing.AddRange(new ArraySegment<byte>(payload, 0, size));
		}

		internal void Flush()
		{
			if (outgoing.Count == 0)
				return;
			byte[] pending = outgoing.ToArray();
			int sent = socket.Send(pending, 0, pending.Length, SocketFlags.None, out SocketError error);
			if (error == SocketError.WouldBlock)
				return;
			if (error != SocketError.Success)
				throw new SocketException((int) error);
			outgoing.RemoveRange(0, sent);
		}

		public void Send(byte[] buffer, long size, ENetReliability reliability)
		{
			if (wasClosed || !isOpen)
				return;
			QueueFrame(0x2, buffer, (int) size);
			try
			{
				Flush();
			}
			catch (Exception e)
			{
				server.Close(this, "WebSocket send failed: " + e.Message, true);
			}
		}

		public void CloseConnection()
		{
			server.Close(this, null, false);
		}

		public bool TryGetIPv4Address(out uint address)
		{
			byte[] b = remote?.Address.MapToIPv4().GetAddressBytes();
			if (b != null && b.Length == 4)
			{
				address = ((uint) b[0] << 24) | ((uint) b[1] << 16) | ((uint) b[2] << 8) | b[3];
				return true;
			}
			address = 0;
			return false;
		}

		public bool TryGetPort(out ushort port)
		{
			port = remote != null ? (ushort) remote.Port : (ushort) 0;
			return remote != null;
		}

		public bool TryGetSteamId(out ulong steamId)
		{
			steamId = 0;
			return false;
		}

		public IPAddress GetAddress() => remote?.Address;

		public string GetAddressString(bool withPort)
		{
			if (remote == null)
				return null;
			return withPort ? remote.ToString() : remote.Address.ToString();
		}

		public bool Equals(ITransportConnection other) => ReferenceEquals(this, other);

		public override bool Equals(object obj) => ReferenceEquals(this, obj);

		public override int GetHashCode() => System.Runtime.CompilerServices.RuntimeHelpers.GetHashCode(this);

		public override string ToString() => "WebSocket " + GetAddressString(true);
	}
}
#endif // !UNITY_WEBGL || UNITY_EDITOR
