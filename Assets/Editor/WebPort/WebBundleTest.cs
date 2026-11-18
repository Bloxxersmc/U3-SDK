////////////////////////////////////////////////////////////////////////////////////////
// This file is part of the U3 SDK: https://github.com/smartlydressedgames/u3-sdk/    //
// Please refer to the included LICENSE.txt for copyright notice and license details. //
////////////////////////////////////////////////////////////////////////////////////////
using System;
using UnityEditor;
using UnityEngine;

namespace SDG.Unturned.WebPort
{
	/// <summary>
	/// Checks that a bundle made by Tools/WebPort/bundles/convert_for_web.py decompresses and loads.
	///   Unity.exe -batchmode -quit -projectPath . -executeMethod SDG.Unturned.WebPort.WebBundleTest.Run -bundle "C:/.../core.masterbundle"
	/// </summary>
	public static class WebBundleTest
	{
		public static void Run()
		{
			string[] args = Environment.GetCommandLineArgs();
			string path = null;
			for (int i = 0; i < args.Length - 1; ++i)
			{
				if (args[i] == "-bundle")
					path = args[i + 1];
			}

			bool ok = false;
			AssetBundle bundle = null;
			try
			{
				bundle = AssetBundle.LoadFromFile(path);
				if (bundle == null)
				{
					Debug.LogError($"[WebBundleTest] LoadFromFile failed: {path}");
				}
				else
				{
					string[] names = bundle.GetAllAssetNames();
					int loaded = 0, failed = 0;
					// Spread loads across the whole bundle so most compressed chunks get decompressed.
					int step = Math.Max(1, names.Length / 400);
					for (int i = 0; i < names.Length; i += step)
					{
						UnityEngine.Object obj = bundle.LoadAsset(names[i]);
						if (obj != null) ++loaded; else ++failed;
					}
					Debug.Log($"[WebBundleTest] {path}: {names.Length} assets, loaded {loaded}, failed {failed}");
					ok = failed == 0 && loaded > 0;
				}
			}
			catch (Exception e)
			{
				Debug.LogException(e);
			}
			finally
			{
				if (bundle != null)
					bundle.Unload(true);
			}
			Debug.Log(ok ? "[WebBundleTest] RESULT OK" : "[WebBundleTest] RESULT FAILED");
			if (Application.isBatchMode)
				EditorApplication.Exit(ok ? 0 : 1);
		}
	}
}
