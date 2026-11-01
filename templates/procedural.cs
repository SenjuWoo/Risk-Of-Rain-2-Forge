// Procedural mesh template: builds geometry at runtime, so a mod that needs custom shapes does not need
// Unity, Blender, an AssetBundle or any paid tool. The mesh below is a noise-displaced icosphere (a rock,
// a crystal, a blob); the same routine with different parameters covers most placeholder and even shipped
// assets. Compilation is not a runtime test - spawn it and look at it before trusting it.
using BepInEx;
using BepInEx.Configuration;
using System.Collections.Generic;
using UnityEngine;

namespace @__NAME__;

[BepInPlugin(PluginGuid, PluginName, PluginVersion)]
public sealed class Plugin : BaseUnityPlugin
{
    public const string PluginGuid = "__GUID__";
    public const string PluginName = "__NAME__";
    public const string PluginVersion = "1.0.0";

    private ConfigEntry<bool> debugLog;
    private ConfigEntry<float> radius;
    private ConfigEntry<int> subdivisions;
    private ConfigEntry<float> roughness;

    private void Awake()
    {
        debugLog = Config.Bind("Diagnostics", "DebugLogging", false, "Log plugin startup for troubleshooting.");
        radius = Config.Bind("Mesh", "Radius", 0.85f, "Metres. 0.85 is a boulder held in one hand.");
        subdivisions = Config.Bind("Mesh", "Subdivisions", 1, new ConfigDescription("0 = 20 faces, 1 = 80, 2 = 320. Each step costs 4x the vertices.", new AcceptableValueRange<int>(0, 3)));
        roughness = Config.Bind("Mesh", "Roughness", 0.22f, new ConfigDescription("How far vertices wander off the sphere. 0 is a smooth ball.", new AcceptableValueRange<float>(0f, 0.6f)));

        Mesh probe = ProceduralMesh.IcoSphere(radius.Value, subdivisions.Value, roughness.Value);
        if (debugLog.Value)
            Logger.LogInfo($"{PluginName} {PluginVersion} loaded; generated a {probe.vertexCount}-vertex mesh.");
    }
}

/// <summary>
/// Runtime geometry. Everything here is pure Unity API, so it works in any BepInEx plugin and needs no
/// editor, no AssetBundle and no licence.
/// </summary>
public static class ProceduralMesh
{
    /// <summary>An icosphere with each vertex pushed in or out by deterministic noise.</summary>
    public static Mesh IcoSphere(float radius, int subdivisions, float roughness)
    {
        float t = (1f + Mathf.Sqrt(5f)) * 0.5f;
        List<Vector3> verts = new List<Vector3>
        {
            new Vector3(-1, t, 0), new Vector3(1, t, 0), new Vector3(-1, -t, 0), new Vector3(1, -t, 0),
            new Vector3(0, -1, t), new Vector3(0, 1, t), new Vector3(0, -1, -t), new Vector3(0, 1, -t),
            new Vector3(t, 0, -1), new Vector3(t, 0, 1), new Vector3(-t, 0, -1), new Vector3(-t, 0, 1)
        };
        for (int i = 0; i < verts.Count; i++) verts[i] = verts[i].normalized;

        List<int> faces = new List<int>
        {
            0,11,5, 0,5,1, 0,1,7, 0,7,10, 0,10,11, 1,5,9, 5,11,4, 11,10,2, 10,7,6, 7,1,8,
            3,9,4, 3,4,2, 3,2,6, 3,6,8, 3,8,9, 4,9,5, 2,4,11, 6,2,10, 8,6,7, 9,8,1
        };

        for (int pass = 0; pass < subdivisions; pass++)
        {
            Dictionary<long, int> midpoints = new Dictionary<long, int>();
            List<int> next = new List<int>(faces.Count * 4);
            for (int i = 0; i < faces.Count; i += 3)
            {
                int a = faces[i], b = faces[i + 1], c = faces[i + 2];
                int ab = Midpoint(verts, midpoints, a, b);
                int bc = Midpoint(verts, midpoints, b, c);
                int ca = Midpoint(verts, midpoints, c, a);
                next.AddRange(new[] { a, ab, ca, b, bc, ab, c, ca, bc, ab, bc, ca });
            }
            faces = next;
        }

        // Flat-shaded: one vertex per corner, so the facets read as rock rather than a smooth ball.
        Vector3[] positions = new Vector3[faces.Count];
        Vector3[] normals = new Vector3[faces.Count];
        int[] triangles = new int[faces.Count];
        for (int i = 0; i < faces.Count; i++)
        {
            Vector3 p = verts[faces[i]];
            float lump = 1f + (Mathf.PerlinNoise(p.x * 2.3f + 11f, p.z * 2.3f + 7f) - 0.5f) * 2f * roughness;
            positions[i] = p * radius * lump;
            triangles[i] = i;
        }
        for (int i = 0; i < positions.Length; i += 3)
        {
            Vector3 n = Vector3.Cross(positions[i + 1] - positions[i], positions[i + 2] - positions[i]).normalized;
            normals[i] = normals[i + 1] = normals[i + 2] = n;
        }

        Mesh mesh = new Mesh { name = "ProceduralIcoSphere" };
        if (positions.Length > 65000) mesh.indexFormat = UnityEngine.Rendering.IndexFormat.UInt32;
        mesh.vertices = positions;
        mesh.normals = normals;
        mesh.triangles = triangles;
        mesh.RecalculateBounds();
        return mesh;
    }

    private static int Midpoint(List<Vector3> verts, Dictionary<long, int> cache, int a, int b)
    {
        long key = a < b ? ((long)a << 32) | (uint)b : ((long)b << 32) | (uint)a;
        if (cache.TryGetValue(key, out int known)) return known;
        verts.Add(((verts[a] + verts[b]) * 0.5f).normalized);
        cache[key] = verts.Count - 1;
        return verts.Count - 1;
    }
}
