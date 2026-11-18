////////////////////////////////////////////////////////////////////////////////////////
// This file is part of the U3 SDK: https://github.com/smartlydressedgames/u3-sdk/    //
// Please refer to the included LICENSE.txt for copyright notice and license details. //
////////////////////////////////////////////////////////////////////////////////////////
#if UNITY_WEBGL && !UNITY_EDITOR
using System.Runtime.InteropServices;
using UnityEngine;

namespace SDG.Unturned
{
	/// <summary>
	/// Puts the player's game files into the browser's virtual file system at /unturned
	/// (see Plugins/WebGL/UnturnedWebFS.jslib) before anything reads game paths.
	/// </summary>
	public static class WebFileSystem
	{
		[DllImport("__Internal")]
		private static extern int WebFS_MountGameFiles();

		[DllImport("__Internal")]
		private static extern void WebFS_SaveNow();

		[DllImport("__Internal")]
		private static extern string WebFS_GetPlayerName();

		[DllImport("__Internal")]
		private static extern void WebSteam_SetPlayerName(string name);

		public static int MountedFileCount { get; private set; }

		[RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
		private static void MountBeforeGameStarts()
		{
			DisableJsonDynamicCode();
			MountedFileCount = WebFS_MountGameFiles();
			WebSteam_SetPlayerName(WebFS_GetPlayerName());
			Debug.Log($"[WebFileSystem] {MountedFileCount} game files mounted at /unturned");
		}

		/// <summary>
		/// Json.NET builds object constructors with Reflection.Emit unless told not to, and IL2CPP
		/// (browser builds) can't run generated code. Make it use plain reflection instead.
		/// </summary>
		private static void DisableJsonDynamicCode()
		{
			System.Type reflector = typeof(Newtonsoft.Json.JsonConvert).Assembly.GetType("Newtonsoft.Json.Serialization.JsonTypeReflector");
			System.Reflection.FieldInfo field = reflector?.GetField("_dynamicCodeGeneration", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Static);
			if (field != null)
			{
				field.SetValue(null, (bool?) false);
			}
			else
			{
				Debug.LogWarning("[WebFileSystem] Could not turn off Json.NET dynamic code generation; JSON files may fail to load");
			}
		}

		/// <summary>
		/// Flush saves to IndexedDB now (they are also flushed every 15 seconds and when the tab closes).
		/// </summary>
		public static void SaveNow()
		{
			WebFS_SaveNow();
		}
	}
}
#endif // UNITY_WEBGL && !UNITY_EDITOR
