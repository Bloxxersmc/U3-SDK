////////////////////////////////////////////////////////////////////////////////////////
// This file is part of the U3 SDK: https://github.com/smartlydressedgames/u3-sdk/    //
// Please refer to the included LICENSE.txt for copyright notice and license details. //
////////////////////////////////////////////////////////////////////////////////////////
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.Build;
using UnityEngine;
using UnityEngine.Rendering;

namespace SDG.Unturned.WebPort
{
	/// <summary>
	/// Browser builds of the game. From the editor: Unturned > Web > Build WebGL / Build WebGPU.
	/// Headless:
	///   Unity.exe -batchmode -quit -projectPath . -buildTarget WebGL -executeMethod SDG.Unturned.WebPort.WebBuild.BuildWebGLCommandLine
	///   Unity.exe -batchmode -quit -projectPath . -buildTarget WebGL -executeMethod SDG.Unturned.WebPort.WebBuild.BuildWebGPUCommandLine
	/// Output: Builds/Web/WebGL and Builds/Web/WebGPU. Serve with Tools/WebPort/serve.py.
	/// </summary>
	public static class WebBuild
	{
		private const string SHADER_ROOT = "Assets/Game/Sources/Shaders";
		private const string EXTRA_SHADER_ROOT = "Assets/Runtime";

		/// <summary>
		/// Built-in shaders that desktop materials in the core bundle commonly use. WebShaderFixer
		/// re-points bundle materials at these by name, so they must exist in the build.
		/// </summary>
		private static readonly string[] BUILTIN_SHADERS =
		{
			"Standard", "Standard (Specular setup)", "Unlit/Texture", "Unlit/Color", "Unlit/Transparent",
			"Unlit/Transparent Cutout", "Sprites/Default", "UI/Default", "Skybox/Procedural", "Skybox/6 Sided",
			"Particles/Standard Unlit", "Particles/Standard Surface", "Legacy Shaders/Particles/Alpha Blended",
			"Legacy Shaders/Particles/Additive", "Legacy Shaders/Diffuse", "Legacy Shaders/Transparent/Diffuse",
			"Legacy Shaders/Transparent/Cutout/Diffuse", "Legacy Shaders/Bumped Diffuse", "Legacy Shaders/Self-Illumin/Diffuse",
			"Nature/Terrain/Standard", "Nature/Terrain/Diffuse", "Nature/Tree Soft Occlusion Bark", "Nature/Tree Soft Occlusion Leaves",
			"Mobile/Diffuse", "Mobile/Particles/Additive", "Mobile/Particles/Alpha Blended", "Hidden/TerrainEngine/Details/Vertexlit",
			"Hidden/TerrainEngine/Details/WavingDoublePass", "Hidden/TerrainEngine/Details/BillboardWavingDoublePass",
		};

		[MenuItem("Unturned/Web/Build WebGL")]
		public static void BuildWebGLMenu() => Build(useWebGPU: false);

		[MenuItem("Unturned/Web/Build WebGPU (Unity 6+)")]
		public static void BuildWebGPUMenu() => Build(useWebGPU: true);

		public static void BuildWebGLCommandLine() => ExitWith(Build(useWebGPU: false));

		public static void BuildWebGPUCommandLine() => ExitWith(Build(useWebGPU: true));

		/// <summary>
		/// TextMeshPro inside uGUI 2.x (Unity 6) needs "TMP Settings" in Resources or text components throw.
		/// Imports TMP Essential Resources from the uGUI package if they aren't in the project yet.
		///   Unity.exe -batchmode -quit -projectPath . -executeMethod SDG.Unturned.WebPort.WebBuild.ImportTMPEssentialsCommandLine
		/// </summary>
		[MenuItem("Unturned/Web/Import TMP Essential Resources")]
		public static void ImportTMPEssentialsCommandLine()
		{
			if (AssetDatabase.FindAssets("t:TMP_Settings").Length > 0)
			{
				Debug.Log("[WebBuild] TMP Settings already in the project");
				return;
			}
			UnityEditor.PackageManager.PackageInfo ugui = UnityEditor.PackageManager.PackageInfo.FindForAssetPath("Packages/com.unity.ugui");
			string path = ugui != null ? Path.Combine(ugui.resolvedPath, "Package Resources", "TMP Essential Resources.unitypackage") : null;
			if (path == null || !File.Exists(path))
			{
				Debug.LogError("[WebBuild] TMP Essential Resources.unitypackage not found in com.unity.ugui");
				return;
			}
			AssetDatabase.ImportPackage(path, false);
			Debug.Log("[WebBuild] Importing TMP Essential Resources from " + path);
			if (Application.isBatchMode)
			{
				// Package import completes on later editor updates; run this WITHOUT -quit and it exits when done.
				double deadline = EditorApplication.timeSinceStartup + 600.0;
				EditorApplication.update += WaitForTMPImport;
				void WaitForTMPImport()
				{
					bool done = AssetDatabase.FindAssets("t:TMP_Settings").Length > 0;
					if (done || EditorApplication.timeSinceStartup > deadline)
					{
						EditorApplication.update -= WaitForTMPImport;
						Debug.Log(done ? "[WebBuild] TMP Essential Resources imported" : "[WebBuild] Timed out waiting for TMP import");
						EditorApplication.Exit(done ? 0 : 1);
					}
				}
			}
		}

		private static void ExitWith(bool success)
		{
			if (Application.isBatchMode)
			{
				EditorApplication.Exit(success ? 0 : 1);
			}
		}

		public static bool Build(bool useWebGPU)
		{
			string flavor = useWebGPU ? "WebGPU" : "WebGL";
#if !UNITY_6000_0_OR_NEWER
			if (useWebGPU)
			{
				Debug.LogError("WebGPU needs Unity 6 (6000.0) or newer. This project is on " + Application.unityVersion + "; build WebGL instead, or open the project in Unity 6.");
				return false;
			}
#endif

			if (EditorUserBuildSettings.activeBuildTarget != BuildTarget.WebGL)
			{
				if (!EditorUserBuildSettings.SwitchActiveBuildTarget(BuildTargetGroup.WebGL, BuildTarget.WebGL))
				{
					Debug.LogError("Could not switch to the WebGL build target. Is the WebGL Build Support module installed for this editor?");
					return false;
				}
			}

			ConfigurePlayer(useWebGPU);
			IncludeShaders();

			string outputPath = Path.Combine("Builds", "Web", flavor);
			string[] scenes = EditorBuildSettings.scenes.Where(s => s.enabled).Select(s => s.path).ToArray();
			BuildPlayerOptions options = new BuildPlayerOptions
			{
				scenes = scenes,
				locationPathName = outputPath,
				target = BuildTarget.WebGL,
				targetGroup = BuildTargetGroup.WebGL,
				options = EditorUserBuildSettings.development ? BuildOptions.Development : BuildOptions.None,
			};

			Debug.Log($"[WebBuild] Building {flavor} with {scenes.Length} scenes to {outputPath}");
			UnityEditor.Build.Reporting.BuildReport report = BuildPipeline.BuildPlayer(options);
			bool success = report.summary.result == UnityEditor.Build.Reporting.BuildResult.Succeeded;
			Debug.Log($"[WebBuild] {flavor}: {report.summary.result}, {report.summary.totalErrors} errors, {report.summary.totalSize / (1024 * 1024)} MB, {report.summary.totalTime}");
			return success;
		}

		private static void ConfigurePlayer(bool useWebGPU)
		{
			PlayerSettings.SetUseDefaultGraphicsAPIs(BuildTarget.WebGL, false);
#if UNITY_6000_0_OR_NEWER
			PlayerSettings.SetGraphicsAPIs(BuildTarget.WebGL, useWebGPU
				? new[] { GraphicsDeviceType.WebGPU, GraphicsDeviceType.OpenGLES3 }
				: new[] { GraphicsDeviceType.OpenGLES3 });
#else
			PlayerSettings.SetGraphicsAPIs(BuildTarget.WebGL, new[] { GraphicsDeviceType.OpenGLES3 });
#endif

			PlayerSettings.SetScriptingBackend(BuildTargetGroup.WebGL, ScriptingImplementation.IL2CPP);
			PlayerSettings.SetApiCompatibilityLevel(BuildTargetGroup.WebGL, ApiCompatibilityLevel.NET_Unity_4_8);
			// Unturned builds most asset types from .dat files by name through reflection: strip as little as possible (see Assets/link.xml).
			PlayerSettings.SetManagedStrippingLevel(BuildTargetGroup.WebGL, ManagedStrippingLevel.Minimal);
			PlayerSettings.stripEngineCode = false;

			PlayerSettings.WebGL.template = "PROJECT:Unturned";
			PlayerSettings.WebGL.linkerTarget = WebGLLinkerTarget.Wasm;
			PlayerSettings.WebGL.exceptionSupport = WebGLExceptionSupport.FullWithStacktrace; // to-do: back to ExplicitlyThrownExceptionsOnly once startup is stable
			PlayerSettings.WebGL.compressionFormat = WebGLCompressionFormat.Brotli;
			PlayerSettings.WebGL.decompressionFallback = true;
			PlayerSettings.WebGL.dataCaching = true;
			PlayerSettings.WebGL.nameFilesAsHashes = false;
			PlayerSettings.WebGL.threadsSupport = false;
#if UNITY_2022_2_OR_NEWER
			// The game is big: start at 1 GB and allow the full 4 GB wasm32 address space.
			PlayerSettings.WebGL.initialMemorySize = 1024;
			PlayerSettings.WebGL.maximumMemorySize = 4096;
			PlayerSettings.WebGL.memoryGrowthMode = WebGLMemoryGrowthMode.Geometric;
#else
			PlayerSettings.WebGL.memorySize = 2048;
#endif
			PlayerSettings.runInBackground = true;
			PlayerSettings.defaultWebScreenWidth = 1280;
			PlayerSettings.defaultWebScreenHeight = 720;
		}

		/// <summary>
		/// Put every shader the SDK has source for (plus common built-ins) into GraphicsSettings'
		/// Always Included Shaders, so Shader.Find works for WebShaderFixer at runtime.
		/// </summary>
		private static void IncludeShaders()
		{
			List<Shader> shaders = new List<Shader>();
			foreach (string root in new[] { SHADER_ROOT, EXTRA_SHADER_ROOT })
			{
				foreach (string guid in AssetDatabase.FindAssets("t:Shader", new[] { root }))
				{
					Shader shader = AssetDatabase.LoadAssetAtPath<Shader>(AssetDatabase.GUIDToAssetPath(guid));
					if (shader != null)
						shaders.Add(shader);
				}
			}
			foreach (string name in BUILTIN_SHADERS)
			{
				Shader shader = Shader.Find(name);
				if (shader != null)
					shaders.Add(shader);
				else
					Debug.LogWarning($"[WebBuild] Built-in shader \"{name}\" not found");
			}

			UnityEngine.Object graphicsSettings = AssetDatabase.LoadAssetAtPath<UnityEngine.Object>("ProjectSettings/GraphicsSettings.asset");
			SerializedObject so = new SerializedObject(graphicsSettings);
			SerializedProperty list = so.FindProperty("m_AlwaysIncludedShaders");
			HashSet<Shader> existing = new HashSet<Shader>();
			for (int i = 0; i < list.arraySize; ++i)
			{
				if (list.GetArrayElementAtIndex(i).objectReferenceValue is Shader s)
					existing.Add(s);
			}
			int added = 0;
			foreach (Shader shader in shaders.Distinct())
			{
				if (existing.Contains(shader))
					continue;
				list.InsertArrayElementAtIndex(list.arraySize);
				list.GetArrayElementAtIndex(list.arraySize - 1).objectReferenceValue = shader;
				++added;
			}
			so.ApplyModifiedPropertiesWithoutUndo();
			AssetDatabase.SaveAssets();
			Debug.Log($"[WebBuild] Always Included Shaders: {existing.Count + added} ({added} added)");
		}
	}
}
