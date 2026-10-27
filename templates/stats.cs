// Movement speed example using the verified R2API.RecalculateStats 1.7.0 API.
// Keep the default at 1.0; multiplayer behavior requires host/client testing.
using BepInEx;
using BepInEx.Configuration;
using R2API;
using RoR2;

namespace @__NAME__;

[BepInPlugin(PluginGuid, PluginName, PluginVersion)]
[BepInDependency("com.bepis.r2api.recalculatestats", BepInDependency.DependencyFlags.HardDependency)]
public sealed class Plugin : BaseUnityPlugin
{
    public const string PluginGuid = "__GUID__";
    public const string PluginName = "__NAME__";
    public const string PluginVersion = "1.0.0";
    private ConfigEntry<float> speedMultiplier;
    private ConfigEntry<bool> debugLog;

    private void Awake()
    {
        speedMultiplier = Config.Bind("Gameplay", "MoveSpeedMultiplier", 1f,
            new ConfigDescription("Player movement speed multiplier.", new AcceptableValueRange<float>(0.1f, 10f)));
        debugLog = Config.Bind("Diagnostics", "DebugLogging", false, "Log plugin startup for troubleshooting.");
        RecalculateStatsAPI.GetStatCoefficients += ApplyStats;
        if (debugLog.Value)
            Logger.LogInfo($"{PluginName} {PluginVersion} loaded.");
    }

    private void ApplyStats(CharacterBody body, RecalculateStatsAPI.StatHookEventArgs args)
    {
        if (body.isPlayerControlled)
            args.moveSpeedTotalMult *= speedMultiplier.Value;
    }

    private void OnDestroy()
    {
        RecalculateStatsAPI.GetStatCoefficients -= ApplyStats;
    }
}
