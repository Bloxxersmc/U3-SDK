////////////////////////////////////////////////////////////////////////////////////////
// This file is part of the U3 SDK: https://github.com/smartlydressedgames/u3-sdk/    //
// Please refer to the included LICENSE.txt for copyright notice and license details. //
////////////////////////////////////////////////////////////////////////////////////////
#if UNITY_WEBGL && !UNITY_EDITOR
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace SDG.Unturned
{
	/// <summary>
	/// The game's asset bundles are the desktop (Direct3D) builds retargeted for the browser by
	/// Tools/WebPort/bundles/convert_for_web.py, so the shader programs inside them can't run here.
	/// Every shader the SDK has source for is compiled into the web build (see WebBuild.cs), so
	/// materials loaded from bundles are pointed at the same-named shader from the build instead.
	/// </summary>
	public class WebShaderFixer : MonoBehaviour
	{
		private const float SCAN_INTERVAL_SECONDS = 1.0f;

		private static WebShaderFixer instance;

		private readonly Dictionary<string, Shader> replacements = new Dictionary<string, Shader>();
		private readonly HashSet<int> handledMaterials = new HashSet<int>();
		private readonly HashSet<string> loggedMissing = new HashSet<string>();
		private Shader fallback;
		private float nextScanTime;

		[RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.BeforeSceneLoad)]
		private static void Create()
		{
			if (instance != null)
				return;

			GameObject go = new GameObject("WebShaderFixer");
			DontDestroyOnLoad(go);
			instance = go.AddComponent<WebShaderFixer>();
		}

		/// <summary>
		/// Fix materials right away, e.g. after a level or a large batch of assets finished loading.
		/// </summary>
		public static void RequestScan()
		{
			if (instance != null)
			{
				instance.nextScanTime = 0.0f;
			}
		}

		private void Awake()
		{
			fallback = Shader.Find("Standard");
			SceneManager.sceneLoaded += (scene, mode) => RequestScan();
		}

		private void LateUpdate()
		{
			if (Time.realtimeSinceStartup < nextScanTime)
				return;
			nextScanTime = Time.realtimeSinceStartup + SCAN_INTERVAL_SECONDS;
			Scan();
		}

		private void Scan()
		{
			int fixedCount = 0;
			foreach (Material material in Resources.FindObjectsOfTypeAll<Material>())
			{
				if (material == null || !handledMaterials.Add(material.GetInstanceID()))
					continue;

				Shader current = material.shader;
				if (current != null && current.isSupported)
					continue;

				string name = current != null ? current.name : string.Empty;
				Shader replacement = FindReplacement(name);
				if (replacement == null || replacement == current)
					continue;

				int renderQueue = material.renderQueue;
				material.shader = replacement;
				material.renderQueue = renderQueue;
				++fixedCount;
			}

			if (fixedCount > 0)
			{
				UnturnedLog.info($"WebShaderFixer: re-pointed {fixedCount} material(s) at web shaders");
			}
		}

		private Shader FindReplacement(string name)
		{
			if (replacements.TryGetValue(name, out Shader cached))
				return cached;

			Shader found = string.IsNullOrEmpty(name) ? null : Shader.Find(name);
			if (found == null || !found.isSupported)
			{
				if (loggedMissing.Add(name))
				{
					UnturnedLog.warn($"WebShaderFixer: no web build of shader \"{name}\", using Standard");
				}
				found = fallback;
			}

			replacements[name] = found;
			return found;
		}
	}
}
#endif // UNITY_WEBGL && !UNITY_EDITOR
