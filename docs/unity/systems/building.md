---
engine: Unity
version: 6+
uses:
  - name: Base building
    text: Grid and free placement, sockets, and a cost paid from the inventory.
  - name: Top-down survival
    text: Barricades and walls built from scavenged materials.
  - name: Life and colony sims
    text: Placing furniture and rooms.
---

# Building and placement

A ghost follows the cursor. It turns green when the footprint is legal, and a confirm swaps it for the real prefab. Grid pieces occupy cells. Free pieces sit on the ray hit. Sockets pull a piece onto a neighbour the way a wall finds a floor in Valheim.

Item costs go through [`IInventory`](inventory/index.md#interface): `Contains` to test, `TryRemove` to pay, `TryAdd` to refund. A single number, such as gold, is a [`FloatVariable`](../architecture/variables.md). One asset is one wallet, which is the limit on that page. The ghost is a transparent tint, not the [outline](../rendering/highlight-outline.md). A selected placed piece can use that outline later. This page does not draw it.

Off, placing, and demolishing are a `BuildPhase` enum. A wheel of pieces, or a pause that must restore this phase, belongs on the [state machine](../architecture/state-machines.md). This script does not push one, and it does not move the character.

## Which mode

| Mode | Where the piece goes | Limit |
| --- | --- | --- |
| Grid | The hit snaps to cells. An odd footprint centres on the cell under the cursor. An even footprint centres on the nearest grid line. | Yaw is a quarter turn. The mesh pivot is the centre of the footprint, on the ground. |
| Free | The hit is the centre. Q, E, and the scroll wheel add a degree step. | Cells are not reserved. A prefab with no collider can overlap another piece. |
| Sockets | The nearest compatible pair inside the radius moves the ghost so the points meet. | A grid piece may leave the cell it started on. Occupancy is whatever cells the footprint then covers. |

## Setup

1. Copy `ItemDefinition`, `ItemStack`, and `IInventory` from the [inventory](inventory/index.md) page before `Buildable`. Costs are fungible stacks. A durability item cannot be `TryRemove`'d, so the ghost stays red. Copy `FloatVariable` as well if a cost is a number rather than an item.
2. Create a `Buildable` asset. Assign the prefab. The prefab pivot is the centre of the footprint, and the ground is local `y = 0`. The mesh and the blocking collider should fit that footprint. A child `SnapPoint` is a socket.
3. Create two transparent materials, one green and one red. On a URP Lit material set **Surface Type** to **Transparent** and the alpha to about `0.45`. A `MaterialPropertyBlock` cannot switch an opaque material to transparent. Assign both on `GhostView`.
4. Add an empty **Grid** object with `PlacementGrid`. Leave its rotation at identity. Its position is the minimum corner of cell `(0, 0)`, not the centre of that cell.
5. On the builder, add `GhostView`, `BuildModeController`, and one `BuildInput`. Copy the Input System file or the legacy file, not both. A new Unity 6 project uses the Input System, so **Active Input Handling** must be **Input System Package (New)** or **Both**. The legacy file needs **Input Manager (Old)** or **Both**.
6. Assign the camera, the player, the grid, and the bag. **Surfaces** is the ground and any piece you may aim at. **Blocks** is the layer that refuses overlap, usually the building layer, and not the ground. An empty block mask skips the physics test. The occupancy map still runs for a grid piece.
7. Press **B** to place the assigned piece, **Q** or **E** or the wheel to rotate, left click to confirm, **X** to demolish, right click or Escape to leave. A hotbar button can call `Begin` instead of **B**. This page does not read the [hotbar](inventory/slots.md).
8. Carving does not need a package. Add `NavMeshObstacle` yourself, or leave **Carve Nav Mesh** on and the controller adds a box. A rebake is `BuildNavRefresh` from the navigation section, and that file needs [AI Navigation 2.x](../ai/enemy.md).

## Data

`Footprint` is cells, not metres. World size is the footprint times the grid's cell size, including a free piece, which borrows that size when no grid is assigned and then uses the controller's own cell size. `Surfaces` of **Nothing** means "use the mask on the controller". `Snap Radius` of `0` turns sockets off.

```csharp
using System;
using System.Collections.Generic;
using UnityEngine;

public enum PlacementKind
{
    Grid,
    Free
}

[Serializable]
public struct BuildItemCost
{
    public ItemDefinition item;
    public int count;
}

/// <summary>
/// Authored piece. The prefab pivot is the footprint centre, on the ground.
/// </summary>
[CreateAssetMenu(fileName = "Buildable", menuName = "Game/Buildable")]
public class Buildable : ScriptableObject
{
    [SerializeField] PlacementKind kind = PlacementKind.Grid;
    [SerializeField] GameObject prefab;
    [SerializeField] GameObject previewPrefab;
    [SerializeField] Vector2Int footprint = Vector2Int.one;
    [SerializeField] float height = 2f;
    [SerializeField] float maxSlope = 35f;
    [SerializeField] bool alignToSurface;
    [SerializeField] bool requiresGround = true;
    [SerializeField] LayerMask surfaces;
    [SerializeField] BuildItemCost[] itemCosts = Array.Empty<BuildItemCost>();
    [SerializeField] FloatVariable currency;
    [SerializeField] float currencyAmount;
    [SerializeField] float snapRadius = 0.75f;
    [SerializeField] bool alignSocketFacing = true;
    [SerializeField] float rotationStep = 15f;
    [SerializeField] bool carveNavMesh = true;

    public PlacementKind Kind => kind;
    public GameObject Prefab => prefab;
    public GameObject Preview => previewPrefab;
    public float Height => Mathf.Max(0.1f, height);
    public float MaxSlope => Mathf.Clamp(maxSlope, 0f, 180f);
    public bool AlignToSurface => alignToSurface;
    public bool RequiresGround => requiresGround;
    public LayerMask Surfaces => surfaces;
    public BuildItemCost[] ItemCosts => itemCosts;
    public FloatVariable Currency => currency;
    public float CurrencyAmount => Mathf.Max(0f, currencyAmount);
    public float SnapRadius => Mathf.Max(0f, snapRadius);
    public bool AlignSocketFacing => alignSocketFacing;
    public float RotationStep => Mathf.Max(1f, rotationStep);
    public bool CarveNavMesh => carveNavMesh;

    public Vector2Int Footprint
    {
        get
        {
            return new Vector2Int(Mathf.Max(1, footprint.x), Mathf.Max(1, footprint.y));
        }
    }

    public BuildItemCost[] SummedCosts()
    {
        if (itemCosts == null || itemCosts.Length == 0)
            return Array.Empty<BuildItemCost>();

        var summed = new List<BuildItemCost>();
        for (int i = 0; i < itemCosts.Length; i++)
        {
            ItemDefinition item = itemCosts[i].item;
            int count = itemCosts[i].count;
            if (item == null || count <= 0)
                continue;

            bool merged = false;
            for (int j = 0; j < summed.Count; j++)
            {
                if (summed[j].item != item)
                    continue;
                BuildItemCost line = summed[j];
                line.count += count;
                summed[j] = line;
                merged = true;
                break;
            }

            if (!merged)
                summed.Add(new BuildItemCost { item = item, count = count });
        }

        return summed.ToArray();
    }

    void OnValidate()
    {
        if (footprint.x < 1)
            footprint.x = 1;
        if (footprint.y < 1)
            footprint.y = 1;
        if (height < 0.1f)
            height = 0.1f;
        if (maxSlope < 0f)
            maxSlope = 0f;
        if (maxSlope > 180f)
            maxSlope = 180f;
        if (rotationStep < 1f)
            rotationStep = 1f;
        if (snapRadius < 0f)
            snapRadius = 0f;
        if (currencyAmount < 0f)
            currencyAmount = 0f;
    }
}
```

## Grid

`WorldToCell` uses `FloorToInt`. A point just west of the origin is cell `-1`. `RoundToInt` would call that cell `0`, and it rounds `-0.5` to the nearest even integer, so the same edge flips between cells. Do not round the index.

The cursor is the centre the player is aiming at. An odd footprint uses the cell under that point as its middle cell. An even footprint has no middle cell, so the centre sits on the nearer grid line. Cell size `1` and a cursor at `x = 1.2` (the fractional part is `0.2`): a `1×1` piece centres at `1.5`, and a `2`-wide piece centres at `1`, covering cells `0` and `1`. At `x = 1.8` the 2-wide piece centres at `2`.

The same rule on negative coordinates still goes through `FloorToInt`. The fractional part is `scaled - FloorToInt(scaled)`, which stays in `[0, 1)` on both sides of the origin. `RoundToInt` is only used later to ask whether a socket left the pivot near a grid corner. That is a tolerance, not the cell index.

Odd quarter turns swap footprint X and Z. The mesh itself is not resized. Yaw is `turns * 90`, and the world box swaps because the pivot rotates. `+90` degrees sends local forward onto world `+X`.

```csharp
using System.Collections.Generic;
using UnityEngine;

/// <summary>
/// Cell (0, 0) has its minimum corner on this transform. Do not rotate the object.
/// </summary>
[DisallowMultipleComponent]
public class PlacementGrid : MonoBehaviour
{
    [SerializeField] float cellSize = 1f;

    readonly Dictionary<Vector2Int, PlacedPiece> _occupied = new Dictionary<Vector2Int, PlacedPiece>();

    public Vector3 Origin => transform.position;
    public float CellSize => Mathf.Max(0.01f, cellSize);

    public Vector2Int WorldToCell(Vector3 world)
    {
        float size = CellSize;
        return new Vector2Int(
            Mathf.FloorToInt((world.x - Origin.x) / size),
            Mathf.FloorToInt((world.z - Origin.z) / size));
    }

    public static int Mod4(int turns)
    {
        int wrapped = turns % 4;
        return wrapped < 0 ? wrapped + 4 : wrapped;
    }

    public static void RotatedFootprint(Vector2Int footprint, int quarterTurns, out int sizeX, out int sizeZ)
    {
        int x = Mathf.Max(1, footprint.x);
        int z = Mathf.Max(1, footprint.y);
        if ((Mod4(quarterTurns) & 1) == 1)
        {
            sizeX = z;
            sizeZ = x;
        }
        else
        {
            sizeX = x;
            sizeZ = z;
        }
    }

    public static float QuarterYaw(int quarterTurns)
    {
        return Mod4(quarterTurns) * 90f;
    }

    public Vector2Int AnchorFor(Vector3 worldCentre, int cellsX, int cellsZ)
    {
        return new Vector2Int(
            AnchorAxis(worldCentre.x, Origin.x, cellsX),
            AnchorAxis(worldCentre.z, Origin.z, cellsZ));
    }

    public Vector3 CentreOf(Vector2Int anchor, int cellsX, int cellsZ, float y)
    {
        float size = CellSize;
        return new Vector3(
            Origin.x + (anchor.x + cellsX * 0.5f) * size,
            y,
            Origin.z + (anchor.y + cellsZ * 0.5f) * size);
    }

    public void CollectCells(Vector3 centre, Quaternion rotation, float localX, float localZ, List<Vector2Int> into)
    {
        into.Clear();
        Vector3 right = rotation * Vector3.right;
        Vector3 forward = rotation * Vector3.forward;
        float extentX = Mathf.Abs(right.x) * localX * 0.5f + Mathf.Abs(forward.x) * localZ * 0.5f;
        float extentZ = Mathf.Abs(right.z) * localX * 0.5f + Mathf.Abs(forward.z) * localZ * 0.5f;
        float inset = Mathf.Min(CellSize * 0.02f, 0.01f);
        Vector3 min = new Vector3(centre.x - extentX + inset, centre.y, centre.z - extentZ + inset);
        Vector3 max = new Vector3(centre.x + extentX - inset, centre.y, centre.z + extentZ - inset);
        Vector2Int a = WorldToCell(min);
        Vector2Int b = WorldToCell(max);
        int x0 = Mathf.Min(a.x, b.x);
        int x1 = Mathf.Max(a.x, b.x);
        int z0 = Mathf.Min(a.y, b.y);
        int z1 = Mathf.Max(a.y, b.y);
        for (int x = x0; x <= x1; x++)
        {
            for (int z = z0; z <= z1; z++)
                into.Add(new Vector2Int(x, z));
        }
    }

    public bool AreFree(List<Vector2Int> cells)
    {
        for (int i = 0; i < cells.Count; i++)
        {
            if (_occupied.ContainsKey(cells[i]))
                return false;
        }

        return true;
    }

    public void Claim(List<Vector2Int> cells, PlacedPiece piece)
    {
        for (int i = 0; i < cells.Count; i++)
            _occupied[cells[i]] = piece;
    }

    public void Release(PlacedPiece piece)
    {
        if (piece == null || piece.Cells == null)
            return;

        for (int i = 0; i < piece.Cells.Count; i++)
        {
            Vector2Int cell = piece.Cells[i];
            if (_occupied.TryGetValue(cell, out PlacedPiece owner) && owner == piece)
                _occupied.Remove(cell);
        }
    }

    int AnchorAxis(float world, float origin, int cells)
    {
        float scaled = (world - origin) / CellSize;
        int cell = Mathf.FloorToInt(scaled);
        if ((cells & 1) == 1)
            return cell - cells / 2;

        float fraction = scaled - cell;
        int towardNextLine = fraction >= 0.5f ? 1 : 0;
        return cell - cells / 2 + towardNextLine;
    }

    void OnEnable()
    {
        if (transform.rotation != Quaternion.identity)
            Debug.LogWarning("Placement grid uses world XZ. Reset its rotation.", this);
    }

    void OnValidate()
    {
        if (cellSize < 0.01f)
            cellSize = 0.01f;
    }
}
```

The inset inside `CollectCells` is a couple of centimetres, and never more than a fiftieth of a cell. A footprint that lands exactly on a grid line would otherwise flicker to the next cell when the float is `n + 0.0000001`. It is not a substitute for `FloorToInt`.

## Free placement

The ray starts at the camera and uses the surface mask. It does not use `Physics.DefaultRaycastLayers`, because that includes the ghost unless every other defence held. The hit point is the centre. Yaw is applied around world up, then the piece is tilted so its up axis matches the ground normal when **Align To Surface** is set. Grid pieces ignore that flag and stay upright. Slope is the angle between the normal and world up.

```csharp
using UnityEngine;

public static class PlacementAim
{
    public static bool TryHit(Camera camera, Vector2 screen, float distance, LayerMask surfaces, out RaycastHit hit)
    {
        hit = default;
        if (camera == null || surfaces.value == 0)
            return false;

        Ray ray = camera.ScreenPointToRay(screen);
        return Physics.Raycast(ray, out hit, distance, surfaces, QueryTriggerInteraction.Ignore);
    }

    public static Quaternion FlatYaw(float yaw)
    {
        return Quaternion.Euler(0f, yaw, 0f);
    }

    public static Quaternion SlopeYaw(float yaw, Vector3 normal)
    {
        if (normal.sqrMagnitude < 0.0001f)
            normal = Vector3.up;
        Quaternion tilt = Quaternion.FromToRotation(Vector3.up, normal.normalized);
        return tilt * Quaternion.AngleAxis(yaw, Vector3.up);
    }
}
```

## Ghost

The preview prefab is used when it is assigned. Otherwise the real prefab is instantiated and stripped. Stripping disables behaviours (scripts and animators), disables colliders, makes a rigidbody kinematic, and moves every child onto **Ignore Raycast**. The placed instance is a different object and is not stripped.

Tinting assigns the shared green or red material. `sharedMaterials` does not clone. `renderer.material` does, and the clone leaks. When either material slot is empty, a property block writes `_BaseColor` (URP) and `_Color` (built-in). The block does not change the shader's surface type, so the material has to be transparent already or the alpha is ignored.

The lift is added after sockets and validity. Tests use the unlifted pivot. Drawing the ghost in the same plane as the ground flickers.

```csharp
using UnityEngine;
using UnityEngine.Rendering;

/// <summary>
/// Preview instance. Colliders and scripts stay off so the aim ray cannot hit it.
/// </summary>
[DisallowMultipleComponent]
public class GhostView : MonoBehaviour
{
    [SerializeField] Material validMaterial;
    [SerializeField] Material invalidMaterial;
    [SerializeField] float lift = 0.02f;

    GameObject _instance;
    Buildable _source;
    MaterialPropertyBlock _block;
    bool _hasTint;
    bool _lastValid;

    public GameObject Instance => _instance;
    public float Lift => lift;

    public GameObject Prepare(Buildable piece)
    {
        if (piece == null || piece.Prefab == null)
        {
            Hide();
            return null;
        }

        if (_instance != null && _source == piece)
            return _instance;

        Hide();
        _source = piece;
        GameObject source = piece.Preview != null ? piece.Preview : piece.Prefab;
        _instance = Instantiate(source);
        _instance.name = "Ghost";
        _instance.hideFlags = HideFlags.DontSave;
        Strip(_instance);
        _hasTint = false;
        return _instance;
    }

    public void Present(Vector3 position, Quaternion rotation, bool valid)
    {
        if (_instance == null)
            return;

        _instance.SetActive(true);
        _instance.transform.SetPositionAndRotation(position + Vector3.up * lift, rotation);
        if (_hasTint && _lastValid == valid)
            return;

        Tint(valid);
        _lastValid = valid;
        _hasTint = true;
    }

    public void Hide()
    {
        if (_instance == null)
            return;

        Destroy(_instance);
        _instance = null;
        _source = null;
        _hasTint = false;
    }

    void Tint(bool valid)
    {
        bool swap = validMaterial != null && invalidMaterial != null;
        Material material = valid ? validMaterial : invalidMaterial;
        Color tint = valid
            ? new Color(0.30f, 0.85f, 0.35f, 0.45f)
            : new Color(0.90f, 0.25f, 0.22f, 0.45f);
        if (_block == null)
            _block = new MaterialPropertyBlock();

        Renderer[] renderers = _instance.GetComponentsInChildren<Renderer>(true);
        for (int i = 0; i < renderers.Length; i++)
        {
            Renderer renderer = renderers[i];
            if (renderer == null)
                continue;

            renderer.shadowCastingMode = ShadowCastingMode.Off;
            renderer.receiveShadows = false;
            if (swap)
            {
                Material[] shared = renderer.sharedMaterials;
                for (int m = 0; m < shared.Length; m++)
                    shared[m] = material;
                renderer.sharedMaterials = shared;
                renderer.SetPropertyBlock(null);
            }
            else
            {
                _block.Clear();
                _block.SetColor("_BaseColor", tint);
                _block.SetColor("_Color", tint);
                renderer.SetPropertyBlock(_block);
            }
        }
    }

    static void Strip(GameObject ghost)
    {
        int layer = LayerMask.NameToLayer("Ignore Raycast");
        if (layer < 0)
            layer = 2;

        Transform[] transforms = ghost.GetComponentsInChildren<Transform>(true);
        for (int i = 0; i < transforms.Length; i++)
            transforms[i].gameObject.layer = layer;

        Collider[] colliders = ghost.GetComponentsInChildren<Collider>(true);
        for (int i = 0; i < colliders.Length; i++)
            colliders[i].enabled = false;

        Behaviour[] behaviours = ghost.GetComponentsInChildren<Behaviour>(true);
        for (int i = 0; i < behaviours.Length; i++)
        {
            if (behaviours[i] != null)
                behaviours[i].enabled = false;
        }

        Rigidbody[] bodies = ghost.GetComponentsInChildren<Rigidbody>(true);
        for (int i = 0; i < bodies.Length; i++)
        {
            bodies[i].isKinematic = true;
            bodies[i].detectCollisions = false;
        }
    }
}
```

## Validity

The overlap box is the footprint, not `Renderer.bounds`. Bounds change with the visual lift and with a child prop. The box is shrunk by **Shrink** on each side, and its bottom sits **Shrink + Skin** above the pivot, so the ground and a flush neighbour are not hits.

`OverlapBoxNonAlloc` collects what the shrunk box touches. `ComputePenetration` then drops a contact thinner than a millimetre. It needs one convex shape, and the probe is a box, so a placed piece may use any collider, including a non-convex `MeshCollider`.

Corner rays start half a metre above the pivot and cast down by `tan(maxSlope) * diagonal + 1`. A miss is a hole. A hit whose height is farther than that drop from the pivot is also a miss, so a socket cannot treat a floor several metres below as support. Corners that differ by more than the drop fail the slope, which lets a legal slope through and rejects a step. **Requires Ground** off skips the corners. A wall that only exists because a socket held it up uses that. The cursor ray's own slope is still tested, in `Follow`, before this method runs.

Range is horizontal distance from the player. `0` is unlimited. A missing player with a positive range is invalid, not unlimited.

```csharp
using System.Collections.Generic;
using UnityEngine;

public struct PlacementReport
{
    public bool AimHit;
    public bool SlopeOk;
    public bool Supported;
    public bool Clear;
    public bool InRange;
    public bool Affordable;
    public bool CellsFree;
    public Vector3 Position;
    public Quaternion Rotation;

    public bool Valid => AimHit && SlopeOk && Supported && Clear && InRange && Affordable && CellsFree;
}

/// <summary>
/// Overlap, ground, slope, range, cost, and cells. The probe collider stays disabled.
/// </summary>
public sealed class PlacementCheck
{
    readonly Collider[] _hits = new Collider[32];
    readonly BoxCollider _probe;
    readonly List<Vector2Int> _cells = new List<Vector2Int>();

    PlacementCheck(BoxCollider probe)
    {
        _probe = probe;
    }

    public List<Vector2Int> Cells => _cells;

    public static PlacementCheck Create(Transform host)
    {
        var probeObject = new GameObject("Placement Probe");
        probeObject.hideFlags = HideFlags.HideAndDontSave;
        probeObject.transform.SetParent(host, false);
        int layer = LayerMask.NameToLayer("Ignore Raycast");
        if (layer < 0)
            layer = 2;
        probeObject.layer = layer;
        BoxCollider box = probeObject.AddComponent<BoxCollider>();
        box.enabled = false;
        return new PlacementCheck(box);
    }

    public void Dispose()
    {
        if (_probe != null)
            Object.Destroy(_probe.gameObject);
    }

    public PlacementReport Evaluate(
        Buildable piece,
        Vector3 position,
        Quaternion rotation,
        bool socketLocked,
        Vector3 playerPosition,
        bool hasPlayer,
        float maxRange,
        LayerMask surfaces,
        LayerMask blocks,
        float shrink,
        float skin,
        PlacementGrid grid,
        float cellSize,
        IInventory bag,
        Transform ghost)
    {
        var report = new PlacementReport
        {
            AimHit = true,
            Position = position,
            Rotation = rotation
        };

        Vector2Int footprint = piece.Footprint;
        float localX = footprint.x * cellSize;
        float localZ = footprint.y * cellSize;
        LayerMask groundMask = piece.Surfaces.value != 0 ? piece.Surfaces : surfaces;

        if (piece.RequiresGround)
        {
            if (!SampleGround(position, rotation, localX, localZ, groundMask, piece.MaxSlope, out float height, out bool slopeOk))
            {
                report.Supported = false;
                report.SlopeOk = false;
                return report;
            }

            report.Supported = true;
            report.SlopeOk = slopeOk;
            if (!socketLocked)
                report.Position.y = height;
        }
        else
        {
            report.Supported = true;
            report.SlopeOk = true;
        }

        report.InRange = IsInRange(hasPlayer, playerPosition, report.Position, maxRange);
        report.Affordable = CanAfford(piece, bag);
        report.Clear = IsClear(report.Position, report.Rotation, localX, localZ, piece.Height, shrink, skin, blocks, ghost);

        if (piece.Kind == PlacementKind.Grid && grid != null)
        {
            grid.CollectCells(report.Position, report.Rotation, localX, localZ, _cells);
            report.CellsFree = _cells.Count > 0 && grid.AreFree(_cells);
        }
        else if (piece.Kind == PlacementKind.Grid)
        {
            report.CellsFree = false;
        }
        else
        {
            _cells.Clear();
            report.CellsFree = true;
        }

        return report;
    }

    public static bool CanAfford(Buildable piece, IInventory bag)
    {
        if (piece == null)
            return false;

        BuildItemCost[] costs = piece.ItemCosts;
        if (costs != null)
        {
            for (int i = 0; i < costs.Length; i++)
            {
                ItemDefinition item = costs[i].item;
                if (item == null || costs[i].count <= 0)
                    continue;
                if (item.MaxDurability > 0f)
                    return false;
                if (Needed(costs, i) == 0)
                    continue;
                if (bag == null || !bag.Contains(item, Needed(costs, i)))
                    return false;
            }
        }

        if (piece.Currency != null && piece.CurrencyAmount > 0f)
            return piece.Currency.Value + 0.0001f >= piece.CurrencyAmount;

        return true;
    }

    public static bool TryPay(Buildable piece, IInventory bag, out BuildItemCost[] paid)
    {
        paid = piece != null ? piece.SummedCosts() : System.Array.Empty<BuildItemCost>();
        if (!CanAfford(piece, bag))
            return false;

        var done = new List<BuildItemCost>();
        for (int i = 0; i < paid.Length; i++)
        {
            if (!bag.TryRemove(paid[i].item, paid[i].count, out _))
            {
                GiveBack(bag, done);
                return false;
            }

            done.Add(paid[i]);
        }

        if (piece.Currency != null && piece.CurrencyAmount > 0f)
        {
            if (piece.Currency.Value + 0.0001f < piece.CurrencyAmount)
            {
                GiveBack(bag, done);
                return false;
            }

            piece.Currency.Value -= piece.CurrencyAmount;
        }

        return true;
    }

    public static bool TryRefund(PlacedPiece placed, IInventory bag)
    {
        if (placed == null)
            return false;

        BuildItemCost[] paid = placed.PaidItems;
        var done = new List<BuildItemCost>();
        if (paid != null)
        {
            for (int i = 0; i < paid.Length; i++)
            {
                if (paid[i].item == null || paid[i].count <= 0)
                    continue;
                if (!TryGive(bag, paid[i].item, paid[i].count))
                {
                    TakeBack(bag, done);
                    return false;
                }

                done.Add(paid[i]);
            }
        }

        if (placed.PaidCurrency != null && placed.PaidAmount > 0f)
            placed.PaidCurrency.Value += placed.PaidAmount;

        return true;
    }

    static int Needed(BuildItemCost[] costs, int index)
    {
        ItemDefinition item = costs[index].item;
        for (int i = 0; i < index; i++)
        {
            if (costs[i].item == item)
                return 0;
        }

        int total = 0;
        for (int i = index; i < costs.Length; i++)
        {
            if (costs[i].item == item)
                total += Mathf.Max(0, costs[i].count);
        }

        return total;
    }

    static bool IsInRange(bool hasPlayer, Vector3 playerPosition, Vector3 point, float maxRange)
    {
        if (maxRange <= 0f)
            return true;
        if (!hasPlayer)
            return false;

        Vector3 flat = point - playerPosition;
        flat.y = 0f;
        return flat.sqrMagnitude <= maxRange * maxRange;
    }

    bool SampleGround(
        Vector3 centre,
        Quaternion rotation,
        float localX,
        float localZ,
        LayerMask surfaces,
        float maxSlope,
        out float height,
        out bool slopeOk)
    {
        height = centre.y;
        slopeOk = true;
        if (surfaces.value == 0)
            return false;

        float diagonal = Mathf.Sqrt(localX * localX + localZ * localZ);
        float drop = Mathf.Tan(maxSlope * Mathf.Deg2Rad) * diagonal + 0.05f;
        float hx = Mathf.Max(0.02f, localX * 0.5f - 0.05f);
        float hz = Mathf.Max(0.02f, localZ * 0.5f - 0.05f);
        float start = centre.y + 0.5f;
        float length = drop + 1f;
        float sum = 0f;
        float minY = float.PositiveInfinity;
        float maxY = float.NegativeInfinity;
        float[] xs = { -hx, hx };
        float[] zs = { -hz, hz };

        for (int ix = 0; ix < 2; ix++)
        {
            for (int iz = 0; iz < 2; iz++)
            {
                Vector3 origin = centre + rotation * new Vector3(xs[ix], 0f, zs[iz]);
                origin.y = start;
                if (!Physics.Raycast(origin, Vector3.down, out RaycastHit hit, length, surfaces, QueryTriggerInteraction.Ignore))
                    return false;
                if (Mathf.Abs(hit.point.y - centre.y) > drop)
                    return false;

                if (Vector3.Angle(hit.normal, Vector3.up) > maxSlope)
                    slopeOk = false;

                sum += hit.point.y;
                if (hit.point.y < minY)
                    minY = hit.point.y;
                if (hit.point.y > maxY)
                    maxY = hit.point.y;
            }
        }

        if (maxY - minY > drop)
            slopeOk = false;

        height = sum * 0.25f;
        return true;
    }

    bool IsClear(
        Vector3 position,
        Quaternion rotation,
        float localX,
        float localZ,
        float height,
        float shrink,
        float skin,
        LayerMask blocks,
        Transform ghost)
    {
        if (blocks.value == 0)
            return true;

        Vector3 half = new Vector3(
            Mathf.Max(0.01f, localX * 0.5f - shrink),
            Mathf.Max(0.01f, height * 0.5f - shrink),
            Mathf.Max(0.01f, localZ * 0.5f - shrink));
        Vector3 centre = position + rotation * new Vector3(0f, height * 0.5f + skin, 0f);
        int count = Physics.OverlapBoxNonAlloc(
            centre,
            half,
            _hits,
            rotation,
            blocks,
            QueryTriggerInteraction.Ignore);

        _probe.center = Vector3.zero;
        _probe.size = half * 2f;
        _probe.transform.SetPositionAndRotation(centre, rotation);

        if (count >= _hits.Length)
            return false;

        for (int i = 0; i < count; i++)
        {
            Collider other = _hits[i];
            if (other == null || other == _probe)
                continue;
            if (ghost != null && other.transform.IsChildOf(ghost))
                continue;

            bool penetrated = Physics.ComputePenetration(
                _probe,
                centre,
                rotation,
                other,
                other.transform.position,
                other.transform.rotation,
                out _,
                out float distance);

            if (!penetrated)
                continue;

            if (distance > 0.001f)
                return false;
        }

        return true;
    }

    static void GiveBack(IInventory bag, List<BuildItemCost> paid)
    {
        for (int i = 0; i < paid.Count; i++)
            TryGive(bag, paid[i].item, paid[i].count);
    }

    static void TakeBack(IInventory bag, List<BuildItemCost> given)
    {
        for (int i = 0; i < given.Count; i++)
        {
            if (bag != null)
                bag.TryRemove(given[i].item, given[i].count, out _);
        }
    }

    static bool TryGive(IInventory bag, ItemDefinition item, int count)
    {
        if (item == null || count <= 0)
            return true;
        if (bag == null)
            return false;

        int before = bag.Count(item);
        bool fitted = bag.TryAdd(new ItemStack(item, count), out _);
        int added = bag.Count(item) - before;
        if (fitted && added == count)
            return true;

        if (added > 0)
            bag.TryRemove(item, added, out _);
        return false;
    }
}
```

`CanAfford` sums duplicate lines, so two wood costs share one stack. `TryAdd` on the [list](inventory/list.md) can keep a partial stack and still return false. The refund counts what actually landed and removes that if the rest did not fit. A `Changed` listener must not spend the same bag during the pay.

## Rotation

Grid yaw is `PlacementGrid.QuarterYaw`. Q, E, and one scroll notch add or remove a quarter turn, and the footprint swap follows the odd turns. Free yaw adds **Rotation Step** degrees, default `15`. A socket that aligns facing, in free mode only, replaces that yaw for the frame so the connector looks at its partner. Grid mode does not take the socket's yaw, or a slightly twisted socket would leave the quarter-turn set.

Scroll up and **E** turn clockwise. The Input System notch is `120` on Windows unless the project set scroll delta to uniform. The legacy `Mouse ScrollWheel` axis is already about `0.1` per notch at the default sensitivity. Both input files turn that into a notch count. The controller clamps a frame to three notches so a flick does not spin the piece a full circle.

## Snap points

A socket is a child transform. `Id` empty never matches. The same id matches, and so does either side of `connectsTo`: a point with id `wall` and `connectsTo` `floor` fits a point whose id is `floor`. That is the wall-to-floor pair. Matching is case-insensitive.

The search runs after the grid or ray pose is on the ghost. Distance is the 3D distance between the points as they stand, so a roof socket does not grab a floor socket outside the radius. The winning pair moves the ghost root until its socket sits on the other socket. Facing is a yaw around world up that makes the ghost socket's forward oppose the placed socket's forward. Scale on the piece must stay `1`. The offset is `rotation * local`, and a scaled root would not match the mesh.

Sockets found at `Start` are the scene's existing points. A confirm adds the new piece's points. The ghost's points are never registered. `FindObjectsByType` is the Unity 6 search. `FindObjectsOfType` is the obsolete one.

```csharp
using System;
using System.Collections.Generic;
using UnityEngine;

/// <summary>
/// One connector. Put it on a child of the piece, at the point that should meet its partner.
/// </summary>
public class SnapPoint : MonoBehaviour
{
    [SerializeField] string id = "wall";
    [SerializeField] string connectsTo;

    public string Id => id;

    public bool Fits(SnapPoint other)
    {
        if (other == null || other == this)
            return false;
        if (string.IsNullOrEmpty(id) || string.IsNullOrEmpty(other.id))
            return false;
        if (Same(id, other.id))
            return true;
        if (!string.IsNullOrEmpty(connectsTo) && Same(connectsTo, other.id))
            return true;
        if (!string.IsNullOrEmpty(other.connectsTo) && Same(other.connectsTo, id))
            return true;
        return false;
    }

    public static bool TrySnap(
        Transform ghost,
        List<SnapPoint> world,
        float radius,
        bool alignYaw,
        ref Vector3 position,
        ref Quaternion rotation)
    {
        if (ghost == null || world == null || radius <= 0f)
            return false;

        SnapPoint[] mine = ghost.GetComponentsInChildren<SnapPoint>(true);
        float best = radius * radius;
        bool found = false;
        Vector3 bestPosition = position;
        Quaternion bestRotation = rotation;

        for (int i = 0; i < mine.Length; i++)
        {
            SnapPoint local = mine[i];
            if (local == null)
                continue;

            Vector3 localOffset = Quaternion.Inverse(ghost.rotation) * (local.transform.position - ghost.position);
            for (int j = 0; j < world.Count; j++)
            {
                SnapPoint other = world[j];
                if (other == null || !local.Fits(other))
                    continue;
                if (other.transform.IsChildOf(ghost))
                    continue;

                float sqr = (local.transform.position - other.transform.position).sqrMagnitude;
                if (sqr >= best)
                    continue;

                Quaternion rot = ghost.rotation;
                if (alignYaw)
                {
                    Vector3 from = Vector3.ProjectOnPlane(local.transform.forward, Vector3.up);
                    Vector3 to = Vector3.ProjectOnPlane(-other.transform.forward, Vector3.up);
                    if (from.sqrMagnitude > 0.0001f && to.sqrMagnitude > 0.0001f)
                        rot = Quaternion.FromToRotation(from, to) * ghost.rotation;
                }

                best = sqr;
                bestRotation = rot;
                bestPosition = other.transform.position - rot * localOffset;
                found = true;
            }
        }

        if (!found)
            return false;

        position = bestPosition;
        rotation = bestRotation;
        return true;
    }

    static bool Same(string a, string b)
    {
        return string.Equals(a, b, StringComparison.OrdinalIgnoreCase);
    }
}
```

A socket lock keeps the Y it just solved. The ground sample may still reject the pose, but it does not pull the wall back down onto the terrain. Without a socket, the corner average becomes the pivot height.

## Build mode

`Begin` enters placing. Left click pays, spawns the prefab (not the preview), claims cells, registers sockets, and stays in placing so the next piece can go down. The new collider and the new cells make the same spot illegal, which is what turns the ghost red on top of the piece you just put down. Right click or Escape destroys the ghost and returns to off. **X** hides the ghost and the next confirm removes the `PlacedPiece` under the cursor, if the refund fits in the bag.

Hand-placed pieces are adopted at `Start` when they already have a `PlacedPiece` and a grid `Buildable`. Their cells are collected from the footprint and the transform. A house with neither is only blocked by its collider.

`NavDirtyCount` increments on place and demolish. Nothing in this file rebuilds the navmesh. The next section listens.

```csharp
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.AI;

public enum BuildPhase
{
    Off,
    Placing,
    Demolishing
}

public struct BuildControls
{
    public Vector2 Pointer;
    public bool HasPointer;
    public bool Confirm;
    public bool Cancel;
    public bool RotateClockwise;
    public bool RotateAnticlockwise;
    public float ScrollNotches;
    public bool StartOrStop;
    public bool ToggleDemolish;
}

/// <summary>
/// Records what was paid so a later edit to the asset does not change the refund.
/// </summary>
public class PlacedPiece : MonoBehaviour
{
    public Buildable Source;
    public List<Vector2Int> Cells;
    public BuildItemCost[] PaidItems;
    public FloatVariable PaidCurrency;
    public float PaidAmount;
}

/// <summary>
/// Off, placing, and demolishing. Copy one BuildInput next to this component.
/// </summary>
[DisallowMultipleComponent]
[RequireComponent(typeof(GhostView))]
[RequireComponent(typeof(BuildInput))]
public class BuildModeController : MonoBehaviour
{
    [SerializeField] Buildable assigned;
    [SerializeField] PlacementGrid grid;
    [SerializeField] Camera viewCamera;
    [SerializeField] Transform player;
    [SerializeField] MonoBehaviour bagSource;
    [SerializeField] Transform parent;
    [SerializeField] LayerMask surfaces;
    [SerializeField] LayerMask blocks;
    [SerializeField] float cellSize = 1f;
    [SerializeField] float maxRange = 8f;
    [SerializeField] float aimDistance = 80f;
    [SerializeField] float shrink = 0.02f;
    [SerializeField] float skin = 0.02f;
    [SerializeField] bool drawFootprint = true;

    GhostView _ghostView;
    BuildInput _input;
    PlacementCheck _check;
    readonly List<SnapPoint> _snaps = new List<SnapPoint>();
    readonly List<Vector2Int> _claimed = new List<Vector2Int>();
    Buildable _piece;
    PlacementReport _report;
    int _quarterTurns;
    float _yaw;
    bool _warnedBag;

    public BuildPhase Phase { get; private set; }
    public int NavDirtyCount { get; private set; }

    void Awake()
    {
        _ghostView = GetComponent<GhostView>();
        _input = GetComponent<BuildInput>();
        _check = PlacementCheck.Create(transform);
        if (viewCamera == null)
            viewCamera = Camera.main;
        if (bagSource != null && bagSource is not IInventory && !_warnedBag)
        {
            _warnedBag = true;
            Debug.LogWarning("Bag source does not implement IInventory.", this);
        }
    }

    void Start()
    {
        SnapPoint[] found = FindObjectsByType<SnapPoint>(FindObjectsInactive.Exclude, FindObjectsSortMode.None);
        for (int i = 0; i < found.Length; i++)
        {
            if (found[i] != null)
                _snaps.Add(found[i]);
        }

        if (surfaces.value == 0)
            Debug.LogWarning("Building has no surface mask. Aim rays will miss.", this);

        AdoptExisting();
    }

    void OnDestroy()
    {
        if (_check != null)
            _check.Dispose();
        if (_ghostView != null)
            _ghostView.Hide();
    }

    void Update()
    {
        if (_input == null)
            return;

        BuildControls controls = _input.Read();
        if (ConsumeMode(controls))
            return;

        if (Phase == BuildPhase.Placing)
        {
            ApplyRotation(controls);
            Follow(controls);
            if (controls.Confirm && _report.Valid)
                Place();
        }
        else if (Phase == BuildPhase.Demolishing && controls.Confirm)
        {
            Demolish(controls);
        }
    }

    public void Begin(Buildable piece)
    {
        if (piece == null || piece.Prefab == null)
        {
            Debug.LogWarning("Buildable needs a prefab.", this);
            return;
        }

        _piece = piece;
        _quarterTurns = 0;
        _yaw = 0f;
        EnterPlacing();
    }

    IInventory Bag => bagSource as IInventory;

    bool ConsumeMode(BuildControls controls)
    {
        if (controls.StartOrStop)
        {
            if (Phase == BuildPhase.Off)
                Begin(assigned);
            else
                ExitMode();
            return true;
        }

        if (controls.Cancel && Phase != BuildPhase.Off)
        {
            ExitMode();
            return true;
        }

        if (!controls.ToggleDemolish)
            return false;

        if (Phase == BuildPhase.Placing)
            EnterDemolishing();
        else if (Phase == BuildPhase.Demolishing)
            EnterPlacing();
        return true;
    }

    void EnterPlacing()
    {
        if (_piece == null)
            return;

        Phase = BuildPhase.Placing;
        _ghostView.Prepare(_piece);
    }

    void EnterDemolishing()
    {
        Phase = BuildPhase.Demolishing;
        _ghostView.Hide();
    }

    void ExitMode()
    {
        Phase = BuildPhase.Off;
        _ghostView.Hide();
        _report = default;
    }

    void ApplyRotation(BuildControls controls)
    {
        int steps = 0;
        if (controls.RotateClockwise)
            steps++;
        if (controls.RotateAnticlockwise)
            steps--;
        if (Mathf.Abs(controls.ScrollNotches) >= 0.5f)
            steps += Mathf.Clamp(Mathf.RoundToInt(controls.ScrollNotches), -3, 3);
        if (steps == 0 || _piece == null)
            return;

        if (_piece.Kind == PlacementKind.Grid)
            _quarterTurns += steps;
        else
            _yaw = Mathf.Repeat(_yaw + steps * _piece.RotationStep, 360f);
    }

    void Follow(BuildControls controls)
    {
        _report = default;
        GameObject ghost = _ghostView.Prepare(_piece);
        if (ghost == null || !controls.HasPointer)
        {
            _ghostView.Hide();
            return;
        }

        LayerMask mask = _piece.Surfaces.value != 0 ? _piece.Surfaces : surfaces;
        if (!PlacementAim.TryHit(viewCamera, controls.Pointer, aimDistance, mask, out RaycastHit hit))
        {
            _ghostView.Hide();
            return;
        }

        if (Vector3.Angle(hit.normal, Vector3.up) > _piece.MaxSlope)
        {
            _report.AimHit = true;
            _report.SlopeOk = false;
            _report.Position = hit.point;
            _ghostView.Present(hit.point, CurrentRotation(hit.normal), false);
            return;
        }

        float size = grid != null ? grid.CellSize : Mathf.Max(0.01f, cellSize);
        Vector2Int footprint = _piece.Footprint;
        float localX = footprint.x * size;
        float localZ = footprint.y * size;
        Quaternion rotation = CurrentRotation(hit.normal);
        Vector3 position = hit.point;

        if (_piece.Kind == PlacementKind.Grid)
        {
            if (grid == null)
            {
                _report.AimHit = true;
                _report.CellsFree = false;
                _ghostView.Present(position, rotation, false);
                return;
            }

            PlacementGrid.RotatedFootprint(footprint, _quarterTurns, out int cellsX, out int cellsZ);
            Vector2Int anchor = grid.AnchorFor(hit.point, cellsX, cellsZ);
            position = grid.CentreOf(anchor, cellsX, cellsZ, hit.point.y);
            rotation = PlacementAim.FlatYaw(PlacementGrid.QuarterYaw(_quarterTurns));
        }

        ghost.transform.SetPositionAndRotation(position, rotation);
        bool alignYaw = _piece.Kind == PlacementKind.Free && _piece.AlignSocketFacing;
        bool locked = SnapPoint.TrySnap(ghost.transform, _snaps, _piece.SnapRadius, alignYaw, ref position, ref rotation);
        if (locked && _piece.Kind == PlacementKind.Grid)
            rotation = PlacementAim.FlatYaw(PlacementGrid.QuarterYaw(_quarterTurns));

        _report = _check.Evaluate(
            _piece,
            position,
            rotation,
            locked,
            player != null ? player.position : Vector3.zero,
            player != null,
            maxRange,
            surfaces,
            blocks,
            shrink,
            skin,
            grid,
            size,
            Bag,
            ghost.transform);

        _ghostView.Present(_report.Position, _report.Rotation, _report.Valid);
        if (drawFootprint)
            DrawFootprint(_report.Position, _report.Rotation, localX, localZ, _report.Valid);
    }

    Quaternion CurrentRotation(Vector3 normal)
    {
        if (_piece.Kind == PlacementKind.Grid)
            return PlacementAim.FlatYaw(PlacementGrid.QuarterYaw(_quarterTurns));
        if (_piece.AlignToSurface)
            return PlacementAim.SlopeYaw(_yaw, normal);
        return PlacementAim.FlatYaw(_yaw);
    }

    void Place()
    {
        float size = grid != null ? grid.CellSize : Mathf.Max(0.01f, cellSize);
        Vector2Int footprint = _piece.Footprint;
        float localX = footprint.x * size;
        float localZ = footprint.y * size;

        if (_piece.Kind == PlacementKind.Grid)
        {
            if (grid == null)
                return;

            grid.CollectCells(_report.Position, _report.Rotation, localX, localZ, _claimed);
            if (_claimed.Count == 0 || !grid.AreFree(_claimed))
                return;
        }

        if (!PlacementCheck.TryPay(_piece, Bag, out BuildItemCost[] paid))
            return;

        GameObject instance = Instantiate(_piece.Prefab, _report.Position, _report.Rotation, parent);
        var placed = instance.AddComponent<PlacedPiece>();
        placed.Source = _piece;
        placed.PaidItems = paid;
        if (_piece.Currency != null && _piece.CurrencyAmount > 0f)
        {
            placed.PaidCurrency = _piece.Currency;
            placed.PaidAmount = _piece.CurrencyAmount;
        }

        if (_piece.Kind == PlacementKind.Grid)
        {
            placed.Cells = new List<Vector2Int>(_claimed);
            grid.Claim(placed.Cells, placed);
        }

        RegisterSnaps(instance);
        AttachObstacle(instance, _piece, localX, localZ);
        NavDirtyCount++;
    }

    void Demolish(BuildControls controls)
    {
        if (viewCamera == null || !controls.HasPointer)
            return;

        int mask = blocks.value != 0 ? blocks.value : Physics.DefaultRaycastLayers;
        Ray ray = viewCamera.ScreenPointToRay(controls.Pointer);
        if (!Physics.Raycast(ray, out RaycastHit hit, aimDistance, mask, QueryTriggerInteraction.Ignore))
            return;

        PlacedPiece placed = hit.collider.GetComponentInParent<PlacedPiece>();
        if (placed == null)
            return;
        if (maxRange > 0f && player == null)
            return;

        if (player != null && maxRange > 0f)
        {
            Vector3 flat = placed.transform.position - player.position;
            flat.y = 0f;
            if (flat.sqrMagnitude > maxRange * maxRange)
                return;
        }

        if (!PlacementCheck.TryRefund(placed, Bag))
            return;

        if (grid != null)
            grid.Release(placed);
        UnregisterSnaps(placed.gameObject);
        NavDirtyCount++;
        Destroy(placed.gameObject);
    }

    void AdoptExisting()
    {
        if (grid == null)
            return;

        PlacedPiece[] pieces = FindObjectsByType<PlacedPiece>(FindObjectsInactive.Exclude, FindObjectsSortMode.None);
        for (int i = 0; i < pieces.Length; i++)
        {
            PlacedPiece placed = pieces[i];
            if (placed == null || placed.Source == null || placed.Source.Kind != PlacementKind.Grid)
                continue;
            if (placed.Cells != null && placed.Cells.Count > 0)
            {
                grid.Claim(placed.Cells, placed);
                continue;
            }

            float size = grid.CellSize;
            Vector2Int footprint = placed.Source.Footprint;
            grid.CollectCells(
                placed.transform.position,
                placed.transform.rotation,
                footprint.x * size,
                footprint.y * size,
                _claimed);
            placed.Cells = new List<Vector2Int>(_claimed);
            grid.Claim(placed.Cells, placed);
        }
    }

    void RegisterSnaps(GameObject instance)
    {
        SnapPoint[] points = instance.GetComponentsInChildren<SnapPoint>(true);
        for (int i = 0; i < points.Length; i++)
        {
            if (points[i] != null && !_snaps.Contains(points[i]))
                _snaps.Add(points[i]);
        }
    }

    void UnregisterSnaps(GameObject instance)
    {
        _snaps.RemoveAll(point => point == null || point.transform.IsChildOf(instance.transform));
    }

    static void AttachObstacle(GameObject instance, Buildable piece, float localX, float localZ)
    {
        if (piece == null || !piece.CarveNavMesh)
            return;

        NavMeshObstacle obstacle = instance.GetComponent<NavMeshObstacle>();
        if (obstacle == null)
        {
            obstacle = instance.AddComponent<NavMeshObstacle>();
            obstacle.shape = NavMeshObstacleShape.Box;
            obstacle.center = new Vector3(0f, piece.Height * 0.5f, 0f);
            obstacle.size = new Vector3(localX, piece.Height, localZ);
        }

        obstacle.carving = true;
        obstacle.carveOnlyStationary = true;
    }

    static void DrawFootprint(Vector3 centre, Quaternion rotation, float localX, float localZ, bool valid)
    {
        Color colour = valid ? Color.green : Color.red;
        Vector3 a = Corner(centre, rotation, -localX, -localZ);
        Vector3 b = Corner(centre, rotation, localX, -localZ);
        Vector3 c = Corner(centre, rotation, localX, localZ);
        Vector3 d = Corner(centre, rotation, -localX, localZ);
        Debug.DrawLine(a, b, colour);
        Debug.DrawLine(b, c, colour);
        Debug.DrawLine(c, d, colour);
        Debug.DrawLine(d, a, colour);
    }

    static Vector3 Corner(Vector3 centre, Quaternion rotation, float x, float z)
    {
        return centre + rotation * new Vector3(x * 0.5f, 0.05f, z * 0.5f);
    }
}
```

The two listings are the same component. Copy one. Device reads are this frame's state and are not multiplied by `Time.deltaTime`. A click on a uGUI button is also a confirm. This sample does not ask the EventSystem.

=== "Input System"

    `Mouse.current.scroll` keeps the platform's own scale unless **Scroll Delta Behavior** is **Uniform Across All Platforms**. One Windows notch is `120`. **Scroll Units Per Notch** is that divisor. Set it to `1` if the project uses the uniform range. With no mouse, a connected gamepad aims at the middle of the screen.

    ```csharp
    using UnityEngine;
    using UnityEngine.InputSystem;

    /// <summary>
    /// Pointer, confirm, rotate, and the build-mode keys.
    /// </summary>
    /// <remarks>
    /// Input System, the default backend in a new Unity 6 project.
    /// Requires the Input System package, and Active Input Handling set to
    /// "Input System Package (New)" or "Both". Reads devices directly so
    /// the sample does not need an actions asset.
    /// </remarks>
    [DisallowMultipleComponent]
    public class BuildInput : MonoBehaviour
    {
        [SerializeField] float scrollUnitsPerNotch = 120f;

        public BuildControls Read()
        {
            var controls = new BuildControls();
            Keyboard keyboard = Keyboard.current;
            Mouse mouse = Mouse.current;
            Gamepad gamepad = Gamepad.current;

            if (mouse != null)
            {
                controls.Pointer = mouse.position.ReadValue();
                controls.HasPointer = true;
                controls.Confirm = mouse.leftButton.wasPressedThisFrame;
                controls.Cancel = mouse.rightButton.wasPressedThisFrame;
                float notch = scrollUnitsPerNotch > 0f ? scrollUnitsPerNotch : 120f;
                controls.ScrollNotches = mouse.scroll.ReadValue().y / notch;
            }
            else if (gamepad != null)
            {
                controls.Pointer = new Vector2(Screen.width, Screen.height) * 0.5f;
                controls.HasPointer = true;
            }

            if (keyboard != null)
            {
                controls.RotateClockwise |= keyboard.eKey.wasPressedThisFrame;
                controls.RotateAnticlockwise |= keyboard.qKey.wasPressedThisFrame;
                controls.StartOrStop = keyboard.bKey.wasPressedThisFrame;
                controls.ToggleDemolish = keyboard.xKey.wasPressedThisFrame;
                controls.Cancel |= keyboard.escapeKey.wasPressedThisFrame;
            }

            if (gamepad != null)
            {
                controls.Confirm |= gamepad.buttonSouth.wasPressedThisFrame;
                controls.Cancel |= gamepad.buttonEast.wasPressedThisFrame;
                controls.RotateClockwise |= gamepad.rightShoulder.wasPressedThisFrame;
                controls.RotateAnticlockwise |= gamepad.leftShoulder.wasPressedThisFrame;
                controls.ToggleDemolish |= gamepad.buttonNorth.wasPressedThisFrame;
            }

            return controls;
        }
    }
    ```

=== "Legacy Input Manager"

    `GetAxis("Mouse ScrollWheel")` is the default wheel axis. At the default sensitivity of `0.1`, one notch is about `0.1`. **Scroll Notch** is that divisor. The axis is already this frame's notch and is not multiplied by `Time.deltaTime`. There is no gamepad on this listing.

    ```csharp
    using UnityEngine;

    /// <summary>
    /// Pointer, confirm, rotate, and the build-mode keys.
    /// </summary>
    /// <remarks>
    /// Legacy Input Manager. Requires Active Input Handling set to
    /// "Input Manager (Old)" or "Both".
    /// </remarks>
    [DisallowMultipleComponent]
    public class BuildInput : MonoBehaviour
    {
        [SerializeField] float scrollNotch = 0.1f;

        public BuildControls Read()
        {
            var controls = new BuildControls
            {
                Pointer = Input.mousePosition,
                HasPointer = true,
                Confirm = Input.GetMouseButtonDown(0),
                Cancel = Input.GetMouseButtonDown(1) || Input.GetKeyDown(KeyCode.Escape),
                RotateClockwise = Input.GetKeyDown(KeyCode.E),
                RotateAnticlockwise = Input.GetKeyDown(KeyCode.Q),
                StartOrStop = Input.GetKeyDown(KeyCode.B),
                ToggleDemolish = Input.GetKeyDown(KeyCode.X)
            };

            float notch = scrollNotch > 0f ? scrollNotch : 0.1f;
            controls.ScrollNotches = Input.GetAxis("Mouse ScrollWheel") / notch;
            return controls;
        }
    }
    ```

## Navigation mesh

A placed collider does not change the navmesh by itself. Two options, and they should not both run:

- **Carve.** `AttachObstacle` adds a `NavMeshObstacle` when the prefab does not have one, sized to the footprint in local space, with carving on. `carveOnlyStationary` waits until the object is still, which a freshly spawned piece is. This is the `UnityEngine.AI` type. It does not need the AI Navigation package. An obstacle you authored on the prefab keeps its own size. The controller only turns carving on.
- **Rebake.** `BuildNavRefresh` calls `NavMeshSurface.UpdateNavMesh` once per place or demolish, after the controller's `NavDirtyCount` changes. That type lives in `Unity.AI.Navigation`, the same [AI Navigation 2.x](../ai/enemy.md) package as the enemy page. Bake the surface in the editor first. `navMeshData` is null until you do. A rebuild that is still running is left alone. The next change waits for it.

`UpdateNavMesh` rebuilds the surface from the geometry. It does not know about carve holes, so a rebake can fill a hole the obstacle just cut until the obstacle carves again. Pick carving for a wall, and a rebake for a floor that should become walkable. `BuildNavMesh` every confirm stalls the frame. The enemy page has the same warning. This page does not create off-mesh links.

```csharp
using Unity.AI.Navigation;
using UnityEngine;
using UnityEngine.AI;

/// <summary>
/// One rebake after a place or a demolish. Requires AI Navigation 2.x.
/// Leave this off the builder when the piece only carves.
/// </summary>
[DisallowMultipleComponent]
public class BuildNavRefresh : MonoBehaviour
{
    [SerializeField] NavMeshSurface surface;
    [SerializeField] BuildModeController builder;

    AsyncOperation _running;
    int _seen;

    void Update()
    {
        if (builder == null || surface == null)
            return;
        if (builder.NavDirtyCount == _seen)
            return;
        if (_running != null && !_running.isDone)
            return;
        if (surface.navMeshData == null)
        {
            _seen = builder.NavDirtyCount;
            Debug.LogWarning("Bake the NavMeshSurface before placing.", surface);
            return;
        }

        _seen = builder.NavDirtyCount;
        _running = surface.UpdateNavMesh(surface.navMeshData);
    }
}
```

## Parameters

| Field | Default | Effect |
| --- | --- | --- |
| Footprint | `1, 1` | Cells. World size is this times the cell size. |
| Height | `2` | Overlap box and a generated nav obstacle. |
| Max Slope | `35` | Degrees from world up. |
| Rotation Step | `15` | Degrees per notch in free mode. Grid mode uses 90. |
| Snap Radius | `0.75` | Metres. `0` disables sockets. |
| Cell Size | `1` | Metres, on the grid. The controller's value is the fallback for a free piece with no grid. |
| Max Range | `8` | Horizontal metres from the player. `0` is unlimited. |
| Shrink | `0.02` | Metres taken off each side of the overlap box. |
| Skin | `0.02` | Metres the overlap box is lifted, before the shrink, so the bottom clears the ground. |
| Ghost lift | `0.02` | Visual only. Validity uses the unlifted pivot. |

## Pitfalls

!!! warning "Common pitfalls"

    `RoundToInt` is the wrong cell index. Just west of the origin, `FloorToInt` returns `-1` and `RoundToInt` returns `0`. `RoundToInt` also sends `-0.5` to the nearest even integer, so the same edge changes cell. The fractional part for an even footprint is `scaled - FloorToInt(scaled)`, which stays in `[0, 1)` on both sides of zero. A tolerance that asks "is this nearly a whole number" may use `Round`. The index itself may not.

    The pivot is the centre of the footprint, on the ground. A mesh authored with the pivot on the minimum corner will sit half a footprint away from the cells it occupies. The overlap box will not match the picture. Scale stays `1`. A scaled root breaks the socket offset, which is `rotation * local`.

    The ghost raycasts against itself if a collider is still enabled, or if the aim mask includes **Ignore Raycast**, or if the ghost was left on the building layer. `Strip` does all three defences. Do not run `Strip` on the placed prefab. That copy needs its collider, or free placement will stack and demolish will not find it.

    `renderer.material` clones a material and leaks it. Assign `sharedMaterials`, or a property block. The block cannot turn an opaque URP Lit material transparent. The green and red materials are transparent before Play Mode. Two ghosts that share those materials are supposed to. Do not `new Material` per ghost.

    The lift that stops z-fighting is not part of the pose. Sockets and the overlap box use the unlifted pivot. A preview material with no lift, drawn in the ground plane, flickers. A polygon offset on the preview shader is the other fix. The lift is the one in this page.

    An overlap box that reaches below the pivot hits the ground and the ghost is never green. Keep the ground layer out of **Blocks**. The shrink is what lets two flush footprints share a face. The buffer holds 32 hits. A full buffer is treated as blocked.

    `BuildNavMesh` on every confirm stalls the frame. Carving and `UpdateNavMesh` together fight: the rebake fills the hole the obstacle cut. The enemy page is the bake setup. A negative scale on the surface's parent breaks that bake.

    A `FloatVariable` wallet is one value per asset. Two players who share the asset share the gold. Item costs have to be fungible. `TryRemove` refuses a durability definition, and the ghost stays red. A `Changed` listener that spends the bag during pay will fight the refund.

    The grid object uses world XZ. A rotated grid does not follow its local axes. Cell `(0, 0)` starts at the object's position, which is the minimum corner, not the cell centre.
