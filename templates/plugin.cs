// Minimal Mono/BepInEx 5 plugin. Diagnostic logging is opt-in via its config.
// Inspect installed game APIs before adding behavior; compilation is not a runtime test.
using BepInEx;
using BepInEx.Configuration;

namespace @__NAME__;

[BepInPlugin(PluginGuid, PluginName, PluginVersion)]
public sealed class Plugin : BaseUnityPlugin
{
    public const string PluginGuid = "__GUID__";
    public const string PluginName = "__NAME__";
    public const string PluginVersion = "1.0.0";
    private ConfigEntry<bool> debugLog;

    private void Awake()
    {
        debugLog = Config.Bind("Diagnostics", "DebugLogging", false, "Log plugin startup for troubleshooting.");
        if (debugLog.Value)
            Logger.LogInfo($"{PluginName} {PluginVersion} loaded.");
    }
}
