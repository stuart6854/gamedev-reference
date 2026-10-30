---
engine: Unity
version: 6+
package: URP 17.x
uses:
  - name: Top-down survival
    text: Only what the character can see is lit; rooms behind walls go dark, and zombies there are hidden.
  - name: Strategy and tactics
    text: Unexplored map is black, explored map is grey, and enemy units show only inside vision.
  - name: Roguelikes
    text: Grid field of view, with remembered tiles drawn dimmed.
  - name: Stealth
    text: The player sees the guards' view cones and knows what is out of sight.
---

# Fog of war and vision

Showing the player only what their character can see, and dimming what they have seen before. Inside buildings it pairs with [roof and wall cutaways](cutaways.md). A grid over the map stores three states per cell:

| State | Shown as | Units in it |
| --- | --- | --- |
| **Visible** | Normal. | Shown. |
| **Explored** | Darkened and desaturated: the layout as last seen. | Hidden. |
| **Unknown** | Near black. | Hidden. |

The visible set is computed on the CPU, a few times a second, with **shadowcasting** on a grid of blocked cells. The result goes into a small texture, and a full-screen pass darkens the scene by looking up each pixel's world position in it. Nothing in the world needs a special material.

## Which cells are visible

The map is a grid of cells, about half a metre each, marked blocked where a wall stands at eye height. This is the same baking as the flow field on the steering page: a `Physics.CheckBox` per cell, once at load, and again for a cell when a door opens.

**Recursive shadowcasting** finds every cell visible from one cell, within a radius. It sweeps each of the eight octants around the viewer row by row, outwards. A blocked cell casts a shadow: the range of slopes behind it is skipped for every further row. The cost is proportional to the number of visible cells, not to the area of the radius, and walls themselves are marked visible, so the player sees the wall faces that bound the room.

A view cone narrows this: a cell counts only if it is within half the **Field Of View** of the facing direction, or within **Close Radius**, so the player always sees around their feet. Project Zomboid shows exactly this: a cone ahead, and a small circle all round.

### Smoothing

Cells flip between states as the player moves, which would look like a hard-edged grid. Two things hide it:

- Each cell's shown value moves towards its target by **Fade Speed** per second, rather than jumping.
- The texture uses bilinear filtering, so edges between cells are soft gradients rather than steps.

## Drawing it

The values go into an `R8` texture, one texel per cell: 255 visible, 128 explored, 0 unknown, with the fades in between. The texture and the grid's world placement are set as shader globals.

A **Full Screen Pass Renderer Feature** runs a Shader Graph after the scene is drawn. For each pixel it reads the scene depth, rebuilds the world position, finds the cell, and blends the colour:

```hlsl
// FogOfWar.hlsl. Globals set by VisionGrid.
TEXTURE2D(_FogTex);
SAMPLER(sampler_FogTex);
float4 _FogParams;   // xy: world X and Z of the grid's corner, zw: 1 / grid size in metres

void FogSample_float(float2 ScreenUV, float RawDepth, out float Visibility)
{
    float3 world = ComputeWorldSpacePosition(ScreenUV, RawDepth, UNITY_MATRIX_I_VP);
    float2 uv = (world.xz - _FogParams.xy) * _FogParams.zw;
    Visibility = SAMPLE_TEXTURE2D_LOD(_FogTex, sampler_FogTex, uv, 0).r;
    if (any(uv < 0) || any(uv > 1))
        Visibility = 0;
}

void FogApply_float(float3 Color, float Visibility, out float3 Out)
{
    float grey = dot(Color, float3(0.299, 0.587, 0.114));
    float3 explored = lerp(grey.xxx, Color, 0.3) * 0.45;
    float3 unknown = Color * 0.04;

    // 0..0.5 blends unknown to explored, 0.5..1 blends explored to fully visible.
    Out = Visibility < 0.5
        ? lerp(unknown, explored, Visibility * 2)
        : lerp(explored, Color, (Visibility - 0.5) * 2);
}
```

The world position comes from the depth of the surface under the pixel, so a wall's side and the floor in front of it each find their own cell. That is what makes it work with a tilted or perspective camera, where a flat overlay plane would not line up.

## Hiding units

Units outside vision must not be drawn at all, or the player sees them through the fog. A `FogHidden` component on each unit asks the grid whether its cell is visible, and turns its renderers off when it is not. The player's own units, and anything that should stay on the map once seen, such as buildings, do not get it.

## Setup

1. In the URP Asset, tick **Depth Texture**.
2. Create the Shader Graph: on the URP renderer asset, **Add Renderer Feature → Full Screen Pass Renderer Feature**. Under **Pass Material**, choose **New → ShaderGraph Fullscreen**. Open the graph it makes.
3. In the graph, add two **Custom Function** nodes using the HLSL file above:
    - `FogSample`: **UV** from a **Screen Position** node (Default), **RawDepth** from a **Scene Depth** node in **Raw** mode. Output `Visibility`.
    - `FogApply`: **Color** from the **URP Sample Buffer** node set to **Blit Source**, and the `Visibility`. Output `Out` into **Base Color**.
4. On the renderer feature, set **Injection Point** to **Before Rendering Post Processing**, **Requirements** to **Depth**, and tick **Fetch Color Buffer**.
5. Put `VisionGrid` on an empty object at the bottom-left corner of the map, with **Size** and **Cell Size** covering it, and **Blockers** set to the wall layers. Assign the **Viewer**, usually the player.
6. Put `FogHidden` on enemies and other units that should only show inside vision.

## Scripts

### Vision grid

```csharp
using UnityEngine;

/// <summary>
/// A grid of blocked cells, the viewer's visible set by recursive shadowcasting,
/// remembered cells, and a texture the fog shader reads.
/// </summary>
public class VisionGrid : MonoBehaviour
{
    [Tooltip("Cells along X and Z. The transform is the bottom-left corner.")]
    [SerializeField] Vector2Int size = new Vector2Int(256, 256);
    [Min(0.1f)] [SerializeField] float cellSize = 0.5f;
    [SerializeField] LayerMask blockers;
    [Tooltip("Height of the sight line above the ground, for baking blocked cells.")]
    [SerializeField] float eyeHeight = 1.5f;

    [Header("Viewer")]
    [SerializeField] Transform viewer;
    [SerializeField] float viewRadius = 25f;
    [Range(1f, 360f)] [SerializeField] float fieldOfView = 120f;
    [SerializeField] float closeRadius = 3f;
    [SerializeField] float updateInterval = 0.1f;
    [SerializeField] float fadeSpeed = 6f;

    static readonly int FogTexId = Shader.PropertyToID("_FogTex");
    static readonly int FogParamsId = Shader.PropertyToID("_FogParams");

    // Octant transforms for shadowcasting.
    static readonly int[] XX = { 1, 0, 0, -1, -1, 0, 0, 1 };
    static readonly int[] XY = { 0, 1, -1, 0, 0, -1, 1, 0 };
    static readonly int[] YX = { 0, 1, 1, 0, 0, -1, -1, 0 };
    static readonly int[] YY = { 1, 0, 0, 1, -1, 0, 0, -1 };

    bool[] _blocked;
    bool[] _visible;
    bool[] _explored;
    float[] _shown;
    byte[] _pixels;
    Texture2D _texture;
    float _nextUpdate;
    float _lastUpdate;
    int _originX, _originZ;
    Vector3 _facing;

    void Awake()
    {
        int count = size.x * size.y;
        _blocked = new bool[count];
        _visible = new bool[count];
        _explored = new bool[count];
        _shown = new float[count];
        _pixels = new byte[count];

        _texture = new Texture2D(size.x, size.y, TextureFormat.R8, false, true)
        {
            filterMode = FilterMode.Bilinear,
            wrapMode = TextureWrapMode.Clamp
        };

        BakeBlockers();
        Shader.SetGlobalTexture(FogTexId, _texture);
        Vector3 corner = transform.position;
        Shader.SetGlobalVector(FogParamsId,
            new Vector4(corner.x, corner.z, 1f / (size.x * cellSize), 1f / (size.y * cellSize)));
    }

    void OnDestroy()
    {
        if (_texture != null)
            Destroy(_texture);
    }

    /// <summary>Re-reads walls. Call for one cell's area when a door opens, or for all after loading.</summary>
    public void BakeBlockers()
    {
        Vector3 halfExtents = new Vector3(cellSize * 0.4f, 0.1f, cellSize * 0.4f);
        for (int z = 0; z < size.y; z++)
        {
            for (int x = 0; x < size.x; x++)
            {
                Vector3 centre = CellCentre(x, z) + Vector3.up * eyeHeight;
                _blocked[z * size.x + x] = Physics.CheckBox(centre, halfExtents, Quaternion.identity, blockers,
                    QueryTriggerInteraction.Ignore);
            }
        }
    }

    public bool IsVisible(Vector3 position)
    {
        return TryCell(position, out int x, out int z) && _visible[z * size.x + x];
    }

    public bool IsExplored(Vector3 position)
    {
        return TryCell(position, out int x, out int z) && _explored[z * size.x + x];
    }

    void Update()
    {
        if (viewer != null && Time.time >= _nextUpdate)
        {
            _nextUpdate = Time.time + updateInterval;
            ComputeVisible();
        }

        float dt = Time.time - _lastUpdate;
        if (dt >= 1f / 30f) // the fade needs no more than 30 uploads a second
        {
            _lastUpdate = Time.time;
            UploadFaded(dt);
        }
    }

    void ComputeVisible()
    {
        System.Array.Clear(_visible, 0, _visible.Length);
        if (!TryCell(viewer.position, out _originX, out _originZ))
            return;

        _facing = viewer.forward;
        _facing.y = 0f;
        _facing.Normalize();

        int radius = Mathf.CeilToInt(viewRadius / cellSize);
        Mark(_originX, _originZ);
        for (int octant = 0; octant < 8; octant++)
            CastLight(1, 1f, 0f, radius, XX[octant], XY[octant], YX[octant], YY[octant]);
    }

    // Recursive shadowcasting over one octant.
    void CastLight(int row, float start, float end, int radius, int xx, int xy, int yx, int yy)
    {
        if (start < end)
            return;

        float newStart = 0f;
        for (int j = row; j <= radius; j++)
        {
            int dx = -j - 1;
            int dy = -j;
            bool blocked = false;

            while (dx <= 0)
            {
                dx++;
                int x = _originX + dx * xx + dy * xy;
                int z = _originZ + dx * yx + dy * yy;
                float leftSlope = (dx - 0.5f) / (dy + 0.5f);
                float rightSlope = (dx + 0.5f) / (dy - 0.5f);

                if (start < rightSlope)
                    continue;
                if (end > leftSlope)
                    break;

                if (dx * dx + dy * dy <= radius * radius)
                    Mark(x, z);

                if (blocked)
                {
                    if (Blocked(x, z))
                    {
                        newStart = rightSlope;
                        continue;
                    }
                    blocked = false;
                    start = newStart;
                }
                else if (Blocked(x, z) && j < radius)
                {
                    blocked = true;
                    CastLight(j + 1, start, leftSlope, radius, xx, xy, yx, yy);
                    newStart = rightSlope;
                }
            }

            if (blocked)
                break;
        }
    }

    void Mark(int x, int z)
    {
        if (x < 0 || z < 0 || x >= size.x || z >= size.y)
            return;

        // The view cone: inside the field of view, or close enough to see all round.
        float ox = x - _originX;
        float oz = z - _originZ;
        float distance = Mathf.Sqrt(ox * ox + oz * oz) * cellSize;
        if (distance > closeRadius && fieldOfView < 360f)
        {
            Vector3 to = new Vector3(ox, 0f, oz);
            if (Vector3.Angle(_facing, to) > fieldOfView * 0.5f)
                return;
        }

        int cell = z * size.x + x;
        _visible[cell] = true;
        _explored[cell] = true;
    }

    bool Blocked(int x, int z)
    {
        return x < 0 || z < 0 || x >= size.x || z >= size.y || _blocked[z * size.x + x];
    }

    void UploadFaded(float dt)
    {
        float step = fadeSpeed * dt;
        for (int i = 0; i < _shown.Length; i++)
        {
            float target = _visible[i] ? 1f : _explored[i] ? 0.5f : 0f;
            _shown[i] = Mathf.MoveTowards(_shown[i], target, step);
            _pixels[i] = (byte)(_shown[i] * 255f);
        }
        _texture.SetPixelData(_pixels, 0);
        _texture.Apply(false);
    }

    bool TryCell(Vector3 position, out int x, out int z)
    {
        Vector3 local = position - transform.position;
        x = Mathf.FloorToInt(local.x / cellSize);
        z = Mathf.FloorToInt(local.z / cellSize);
        return x >= 0 && z >= 0 && x < size.x && z < size.y;
    }

    Vector3 CellCentre(int x, int z) =>
        transform.position + new Vector3((x + 0.5f) * cellSize, 0f, (z + 0.5f) * cellSize);
}
```

The shadowcasting is the well-known RogueBasin formulation: each octant is the same sweep with the axes swapped and flipped by the four multipliers.

### Fog hidden

```csharp
using UnityEngine;

/// <summary>
/// Hides this object's renderers while its position is outside the viewer's vision.
/// </summary>
public class FogHidden : MonoBehaviour
{
    [SerializeField] VisionGrid grid;

    Renderer[] _renderers;
    bool _shown = true;

    void Awake()
    {
        _renderers = GetComponentsInChildren<Renderer>();
        if (grid == null)
            grid = FindAnyObjectByType<VisionGrid>();
    }

    void LateUpdate()
    {
        bool visible = grid == null || grid.IsVisible(transform.position);
        if (visible == _shown)
            return;

        _shown = visible;
        foreach (Renderer r in _renderers)
            r.enabled = visible;
    }
}
```

`FindAnyObjectByType` is a fallback for a unit placed without a reference. Spawners should assign the grid.

## Sizes and cost

| Map | Cell | Grid | Texture |
| --- | --- | --- | --- |
| 128 m square | 0.5 m | 256 × 256 | 64 KB |
| 512 m square | 1 m | 512 × 512 | 256 KB |
| 1 km square | 1 m | 1024 × 1024 | 1 MB |

The shadowcasting cost follows the visible area, so it does not grow with the map. The fade and upload loop over every cell, which at a million cells is noticeable. For large maps, fade and upload only a window around the viewer, or tile the map into several grids.

!!! warning "Common pitfalls"

    Without **Depth Texture** in the URP Asset, the scene depth reads as empty, every pixel lands outside the grid, and the screen goes black.

    Blocked cells baked at floor height see furniture as walls; baked above head height see over walls. Bake at eye height.

    Cells larger than the thinnest wall let sight leak through it at an angle. Keep cells no larger than the walls are thick, or thicken the colliders on the blocker layer.

    Units hidden only by the fog shader still draw, and their outlines, shadows, and health bars give them away. Turn their renderers off with `FogHidden`.

    The fog also darkens the UI if the UI is drawn by the same camera in world space. Put HUD canvases in screen space overlay, which is drawn after the pass.
