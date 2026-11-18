////////////////////////////////////////////////////////////////////////////////////////
// This file is part of the U3 SDK: https://github.com/smartlydressedgames/u3-sdk/    //
// Please refer to the included LICENSE.txt for copyright notice and license details. //
////////////////////////////////////////////////////////////////////////////////////////
using UnityEngine;

namespace SDG.Unturned
{
	/// <summary>
	/// Lets the same code build on Unity 2022.3 (desktop game) and Unity 6 (web builds, which need
	/// Unity 6 for WebGPU).
	/// </summary>
	public static class UnityVersionCompat
	{
		/// <summary>
		/// Per-object integer id for dictionary keys and sorting. Unity 6 made GetInstanceID() an error
		/// (replaced by EntityId); Object.GetHashCode() returns the same per-object id.
		/// </summary>
		public static int GetStableId(this Object obj)
		{
#if UNITY_6000_0_OR_NEWER
			return obj.GetHashCode();
#else
			return obj.GetInstanceID();
#endif
		}

		/// <summary>
		/// LightType.Area was renamed to LightType.Rectangle in Unity 6.
		/// </summary>
#if UNITY_6000_0_OR_NEWER
		public const LightType AreaLight = LightType.Rectangle;
#else
		public const LightType AreaLight = LightType.Area;
#endif
	}
}
