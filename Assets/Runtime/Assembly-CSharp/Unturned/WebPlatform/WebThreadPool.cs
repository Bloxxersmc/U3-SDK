////////////////////////////////////////////////////////////////////////////////////////
// This file is part of the U3 SDK: https://github.com/smartlydressedgames/u3-sdk/    //
// Please refer to the included LICENSE.txt for copyright notice and license details. //
////////////////////////////////////////////////////////////////////////////////////////
using System.Threading;

namespace SDG.Unturned
{
	/// <summary>
	/// Browser builds (WebGL/WebGPU) run on a single thread, so work that the desktop game
	/// hands to the thread pool runs inline on the calling thread instead.
	/// </summary>
	public static class WebThreadPool
	{
		public static bool QueueUserWorkItem(WaitCallback callback, object state)
		{
#if UNITY_WEBGL && !UNITY_EDITOR
			callback(state);
			return true;
#else
			return ThreadPool.QueueUserWorkItem(callback, state);
#endif
		}
	}
}
