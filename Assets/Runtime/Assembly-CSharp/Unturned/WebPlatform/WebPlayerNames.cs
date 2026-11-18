////////////////////////////////////////////////////////////////////////////////////////
// This file is part of the U3 SDK: https://github.com/smartlydressedgames/u3-sdk/    //
// Please refer to the included LICENSE.txt for copyright notice and license details. //
////////////////////////////////////////////////////////////////////////////////////////
using System;
using System.Text;
using Steamworks;

namespace SDG.Unturned
{
	/// <summary>
	/// Name rules for offline (web) servers, where players pick their own names instead of using a Steam profile.
	/// </summary>
	public static class WebPlayerNames
	{
		public const int MaxLength = 24;

		public static string Clean(string name)
		{
			StringBuilder sb = new StringBuilder();
			foreach (char c in name ?? string.Empty)
			{
				if (char.IsControl(c) || c == '<' || c == '>')
					continue;
				sb.Append(char.IsWhiteSpace(c) ? ' ' : c);
			}
			string cleaned = sb.ToString().Trim();
			while (cleaned.Contains("  "))
				cleaned = cleaned.Replace("  ", " ");
			if (cleaned.Length > MaxLength)
				cleaned = cleaned.Substring(0, MaxLength).TrimEnd();
			// The server rejects names shorter than 2 characters and names that are only a number.
			if (cleaned.Length < 2 || long.TryParse(cleaned, out _))
				cleaned = "Survivor-" + cleaned;
			return cleaned;
		}

		/// <summary>
		/// Cleaned name, with " (2)", " (3)" ... appended if another connected or pending player already uses it.
		/// </summary>
		public static string MakeUnique(string requested, CSteamID steamID)
		{
			string baseName = Clean(requested);
			string candidate = baseName;
			for (int n = 2; IsTaken(candidate, steamID); ++n)
			{
				string suffix = $" ({n})";
				string head = baseName.Length + suffix.Length > 32 ? baseName.Substring(0, 32 - suffix.Length) : baseName; // server limit is 32
				candidate = head + suffix;
			}
			return candidate;
		}

		private static bool IsTaken(string name, CSteamID steamID)
		{
			foreach (SteamPlayer client in Provider.clients)
			{
				if (client.playerID.steamID != steamID && string.Equals(client.playerID.playerName, name, StringComparison.OrdinalIgnoreCase))
					return true;
			}
			foreach (SteamPending pending in Provider.pending)
			{
				if (pending.playerID != null && pending.playerID.steamID != steamID && string.Equals(pending.playerID.playerName, name, StringComparison.OrdinalIgnoreCase))
					return true;
			}
			return false;
		}
	}
}
