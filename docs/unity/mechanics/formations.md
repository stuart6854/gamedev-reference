---
engine: Unity
version: 6+
package: AI Navigation 2.x
---

# Formation movement

A move order for a selected group that keeps its shape: line, box, wedge, or circle, facing the way the player chose. Each unit gets a slot, and the slots are assigned so units do not cross each other's paths more than they have to. Units are `NavMeshAgent`s. The selection comes from `SelectionManager` on the [drag selection](selection.md) page.

Two ways to get there:

| Mode | How | Good for | Weak at |
| --- | --- | --- | --- |
| **Independent** | Each unit paths straight to its slot at the destination. | Most orders. Cheap, and the group reforms at the end. | The group breaks shape on the way, and splits around obstacles. Fast units arrive first. |
| **March** | A virtual anchor walks the group's path at the slowest unit's pace. Each unit follows its slot around the anchor. | Armies that should look like a formation the whole way. | Slots swing wide on corners, and a narrow gap squeezes the shape. More `SetDestination` calls. |

## Setup

1. Bake a NavMesh with a `NavMeshSurface` (AI Navigation package). Put a `NavMeshAgent` on each unit, next to its `SelectableUnit`.
2. Put `FormationCommander` on any object. Assign the camera, the `SelectionManager`, and a **Ground Mask** containing the terrain.
3. Copy one `OrderInput` listing, Input System or legacy, not both.
4. Right-click the ground to move there, facing away from the group. Right-drag to set the facing: press at the destination and drag the way the front should face.
5. Pick **Shape**, **Spacing**, and **March** in the inspector. Spacing should be at least twice the agent radius, or avoidance pushes units off their slots.

## Slots

A shape is a list of offsets in the formation's local space: \(+z\) forward, \(+x\) right, all shifted so their centroid is at the origin. The order's destination is that centroid. A slot's world position is

\[
\mathbf{p}_{\text{slot}} = \mathbf{p}_{\text{dest}} + R_{\text{facing}}\,\mathbf{o}
\]

with \(R_{\text{facing}}\) the rotation that turns \(+z\) to the facing direction.

| Shape | Layout |
| --- | --- |
| Line | One row, centred. |
| Box | \(\lceil\sqrt{n}\,\rceil\) columns. A short last row is centred. |
| Wedge | One unit at the front, then rows of 2, 3, 4, and so on. |
| Circle | Evenly spaced on a circle whose circumference is \(n \times\) spacing. |

Each slot is snapped to the NavMesh with `NavMesh.SamplePosition`. A slot inside a building moves to the nearest walkable point. Two slots can snap to the same point, and avoidance separates the units.

## Assigning units to slots

Slots are taken in order, front row first, and each takes the nearest unit not yet assigned. That is \(O(n^2)\), and good enough for a few dozen units: front units come from the front of the group, and few paths cross.

The optimal assignment, the one that minimises total distance, is the Hungarian algorithm at \(O(n^3)\). It is worth it for very large groups, or where crossing paths look wrong.

## Facing

A plain right-click faces from the group's centroid towards the destination, so the group advances the way it is moving. A right-drag faces along the drag, from the press point to the release point, and puts the formation's centre at the press point. A drag shorter than **Min Drag** counts as a click.

When a unit reaches its slot, the agent stops turning, so the commander turns it to the formation's facing.

## March mode

The anchor starts at the group's centroid and walks the corners of `NavMesh.CalculatePath` towards the destination. Its speed is the slowest unit's speed times **March Speed Factor**, below 1, so units that fall behind can catch up. If any unit is more than **Catch Up Distance** from its slot, the anchor waits.

The formation's rotation follows the path segment the anchor is on, and turns to the order's facing at the end. Slots are re-sent to agents every **Repath Interval** seconds rather than every frame, because each `SetDestination` starts a path query.

## Scripts

### Input

=== "Input System"

    ```csharp
    using UnityEngine;
    using UnityEngine.InputSystem;

    /// <summary>
    /// Move-order input for the Input System: the right mouse button.
    /// </summary>
    public static class OrderInput
    {
        public static Vector2 PointerPosition =>
            Mouse.current != null ? Mouse.current.position.ReadValue() : Vector2.zero;

        public static bool PressedThisFrame =>
            Mouse.current != null && Mouse.current.rightButton.wasPressedThisFrame;

        public static bool ReleasedThisFrame =>
            Mouse.current != null && Mouse.current.rightButton.wasReleasedThisFrame;
    }
    ```

=== "Legacy Input Manager"

    ```csharp
    using UnityEngine;

    /// <summary>
    /// Move-order input for the legacy Input Manager: the right mouse button.
    /// </summary>
    public static class OrderInput
    {
        public static Vector2 PointerPosition => Input.mousePosition;
        public static bool PressedThisFrame => Input.GetMouseButtonDown(1);
        public static bool ReleasedThisFrame => Input.GetMouseButtonUp(1);
    }
    ```

### Formation shapes

```csharp
using System.Collections.Generic;
using UnityEngine;

public enum FormationShape
{
    Line,
    Box,
    Wedge,
    Circle
}

/// <summary>
/// Slot offsets in formation space: +z forward, +x right, centred on their own centroid.
/// </summary>
public static class Formation
{
    public static void Slots(FormationShape shape, int count, float spacing, List<Vector3> result)
    {
        result.Clear();
        if (count <= 0)
            return;

        switch (shape)
        {
            case FormationShape.Line:
                for (int i = 0; i < count; i++)
                    result.Add(new Vector3((i - (count - 1) * 0.5f) * spacing, 0f, 0f));
                break;

            case FormationShape.Box:
            {
                int columns = Mathf.CeilToInt(Mathf.Sqrt(count));
                for (int i = 0; i < count; i++)
                {
                    int row = i / columns;
                    int inRow = Mathf.Min(columns, count - row * columns);
                    int column = i % columns;
                    result.Add(new Vector3((column - (inRow - 1) * 0.5f) * spacing, 0f, -row * spacing));
                }
                break;
            }

            case FormationShape.Wedge:
            {
                int placed = 0;
                for (int row = 0; placed < count; row++)
                {
                    int inRow = Mathf.Min(row + 1, count - placed);
                    for (int k = 0; k < inRow; k++, placed++)
                        result.Add(new Vector3((k - (inRow - 1) * 0.5f) * spacing, 0f, -row * spacing));
                }
                break;
            }

            case FormationShape.Circle:
            {
                if (count == 1)
                {
                    result.Add(Vector3.zero);
                    break;
                }

                float radius = Mathf.Max(spacing, count * spacing / (2f * Mathf.PI));
                for (int i = 0; i < count; i++)
                {
                    float angle = i * 2f * Mathf.PI / count;
                    result.Add(new Vector3(Mathf.Sin(angle) * radius, 0f, Mathf.Cos(angle) * radius));
                }
                break;
            }
        }

        Vector3 centroid = Vector3.zero;
        for (int i = 0; i < result.Count; i++)
            centroid += result[i];
        centroid /= result.Count;
        for (int i = 0; i < result.Count; i++)
            result[i] -= centroid;
    }
}
```

### Formation commander

```csharp
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.AI;

/// <summary>
/// Right-click move orders for the selected units, in formation.
/// </summary>
public class FormationCommander : MonoBehaviour
{
    [SerializeField] Camera cam;
    [SerializeField] SelectionManager selection;
    [SerializeField] LayerMask groundMask = ~0;

    [Header("Formation")]
    [SerializeField] FormationShape shape = FormationShape.Box;
    [Min(0.1f)] [SerializeField] float spacing = 1.5f;
    [Tooltip("Pixels of right-drag before it sets the facing.")]
    [SerializeField] float minDrag = 12f;
    [SerializeField] float maxSlotSnap = 2f;
    [SerializeField] float arriveTurnSpeed = 360f;

    [Header("March")]
    [SerializeField] bool march;
    [Range(0.1f, 1f)] [SerializeField] float marchSpeedFactor = 0.85f;
    [SerializeField] float catchUpDistance = 4f;
    [SerializeField] float repathInterval = 0.25f;

    class Order
    {
        public readonly List<NavMeshAgent> Agents = new List<NavMeshAgent>();
        public readonly List<Vector3> Offsets = new List<Vector3>();
        public readonly List<Vector3> Corners = new List<Vector3>();
        public Vector3 Destination;
        public Quaternion Facing;
        public bool March;
        public int Corner;
        public Vector3 Anchor;
        public Quaternion AnchorRotation;
        public float Speed;
        public float NextRepath;

        public void RemoveAt(int i)
        {
            Agents.RemoveAt(i);
            Offsets.RemoveAt(i);
        }
    }

    readonly List<Order> _orders = new List<Order>();
    readonly Dictionary<NavMeshAgent, Order> _orderOf = new Dictionary<NavMeshAgent, Order>();
    readonly List<NavMeshAgent> _agents = new List<NavMeshAgent>();
    readonly List<Vector3> _slots = new List<Vector3>();
    readonly List<bool> _taken = new List<bool>();
    NavMeshPath _path;

    Vector2 _pressScreen;
    Vector3 _pressWorld;
    bool _pressValid;

    void Awake()
    {
        if (cam == null)
            cam = Camera.main;
        _path = new NavMeshPath();
    }

    void Update()
    {
        ReadInput();

        for (int i = _orders.Count - 1; i >= 0; i--)
        {
            if (Tick(_orders[i]))
            {
                foreach (NavMeshAgent agent in _orders[i].Agents)
                    _orderOf.Remove(agent);
                _orders.RemoveAt(i);
            }
        }
    }

    void ReadInput()
    {
        if (OrderInput.PressedThisFrame)
        {
            _pressScreen = OrderInput.PointerPosition;
            _pressValid = GroundPoint(_pressScreen, out _pressWorld);
        }

        if (!OrderInput.ReleasedThisFrame || !_pressValid)
            return;

        _pressValid = false;
        if (selection == null)
            return;

        _agents.Clear();
        IReadOnlyList<SelectableUnit> selected = selection.Selected;
        for (int i = 0; i < selected.Count; i++)
        {
            if (selected[i].TryGetComponent(out NavMeshAgent agent) && agent.isOnNavMesh)
                _agents.Add(agent);
        }
        if (_agents.Count == 0)
            return;

        Vector3 facing;
        Vector2 release = OrderInput.PointerPosition;
        if ((release - _pressScreen).sqrMagnitude >= minDrag * minDrag && GroundPoint(release, out Vector3 releaseWorld))
            facing = releaseWorld - _pressWorld;
        else
            facing = _pressWorld - Centroid(_agents);

        Issue(_agents, _pressWorld, facing);
    }

    /// <summary>Moves the agents into formation at destination, with the front along facing.</summary>
    public void Issue(List<NavMeshAgent> agents, Vector3 destination, Vector3 facing)
    {
        facing.y = 0f;
        Quaternion rotation = facing.sqrMagnitude > 1e-4f ? Quaternion.LookRotation(facing) : Quaternion.identity;

        Order order = new Order { Destination = destination, Facing = rotation, March = march };

        // Take the agents out of any earlier order.
        foreach (NavMeshAgent agent in agents)
        {
            if (_orderOf.TryGetValue(agent, out Order previous))
            {
                int index = previous.Agents.IndexOf(agent);
                if (index >= 0)
                    previous.RemoveAt(index);
            }
            _orderOf[agent] = order;
        }

        // Front row first, each slot takes the nearest free agent.
        Formation.Slots(shape, agents.Count, spacing, _slots);
        _taken.Clear();
        for (int i = 0; i < agents.Count; i++)
            _taken.Add(false);

        float slowest = float.MaxValue;
        for (int s = 0; s < _slots.Count; s++)
        {
            Vector3 slotWorld = destination + rotation * _slots[s];
            int best = -1;
            float bestDistance = float.MaxValue;
            for (int a = 0; a < agents.Count; a++)
            {
                if (_taken[a])
                    continue;
                float distance = (agents[a].transform.position - slotWorld).sqrMagnitude;
                if (distance < bestDistance)
                {
                    bestDistance = distance;
                    best = a;
                }
            }

            _taken[best] = true;
            order.Agents.Add(agents[best]);
            order.Offsets.Add(_slots[s]);
            slowest = Mathf.Min(slowest, agents[best].speed);
        }

        if (order.March && NavMesh.CalculatePath(Snap(Centroid(agents), destination), Snap(destination, destination), NavMesh.AllAreas, _path)
            && _path.status != NavMeshPathStatus.PathInvalid && _path.corners.Length > 0)
        {
            order.Corners.AddRange(_path.corners);
            order.Anchor = order.Corners[0];
            order.Corner = 1;
            order.AnchorRotation = rotation;
            order.Speed = slowest * marchSpeedFactor;
            order.NextRepath = 0f;
        }
        else
        {
            order.March = false;
            for (int i = 0; i < order.Agents.Count; i++)
                order.Agents[i].SetDestination(Snap(destination + rotation * order.Offsets[i], destination));
        }

        _orders.Add(order);
    }

    /// <summary>Advances one order. True when every unit has arrived and turned.</summary>
    bool Tick(Order order)
    {
        for (int i = order.Agents.Count - 1; i >= 0; i--)
        {
            if (order.Agents[i] == null || !order.Agents[i].isActiveAndEnabled)
                order.RemoveAt(i);
        }
        if (order.Agents.Count == 0)
            return true;

        bool marching = order.March && order.Corner < order.Corners.Count;
        if (order.March)
            Advance(order);

        bool done = !marching;
        for (int i = 0; i < order.Agents.Count; i++)
        {
            NavMeshAgent agent = order.Agents[i];
            bool arrived = !agent.pathPending && agent.remainingDistance <= agent.stoppingDistance + 0.05f;
            if (marching || !arrived)
            {
                done = false;
                continue;
            }

            Transform body = agent.transform;
            body.rotation = Quaternion.RotateTowards(body.rotation, order.Facing, arriveTurnSpeed * Time.deltaTime);
            if (Quaternion.Angle(body.rotation, order.Facing) > 1f)
                done = false;
        }

        return done;
    }

    void Advance(Order order)
    {
        if (order.Corner < order.Corners.Count && !AnyStraggler(order))
        {
            float step = order.Speed * Time.deltaTime;
            while (step > 0f && order.Corner < order.Corners.Count)
            {
                Vector3 to = order.Corners[order.Corner] - order.Anchor;
                float length = to.magnitude;
                if (length <= step)
                {
                    order.Anchor = order.Corners[order.Corner];
                    order.Corner++;
                    step -= length;
                }
                else
                {
                    order.Anchor += to / length * step;
                    step = 0f;
                }
            }
        }

        if (order.Corner < order.Corners.Count)
        {
            Vector3 heading = order.Corners[order.Corner] - order.Anchor;
            heading.y = 0f;
            if (heading.sqrMagnitude > 1e-4f)
                order.AnchorRotation = Quaternion.LookRotation(heading);
        }
        else
        {
            order.AnchorRotation = order.Facing;
        }

        // After the anchor arrives, the final slots are sent once.
        bool atEnd = order.Corner >= order.Corners.Count;
        if (atEnd ? order.NextRepath < 0f : Time.time < order.NextRepath)
            return;

        for (int i = 0; i < order.Agents.Count; i++)
        {
            Vector3 slot = order.Anchor + order.AnchorRotation * order.Offsets[i];
            order.Agents[i].SetDestination(Snap(slot, order.Anchor));
        }

        order.NextRepath = atEnd ? -1f : Time.time + repathInterval;
    }

    bool AnyStraggler(Order order)
    {
        float limit = catchUpDistance * catchUpDistance;
        for (int i = 0; i < order.Agents.Count; i++)
        {
            Vector3 slot = order.Anchor + order.AnchorRotation * order.Offsets[i];
            if ((order.Agents[i].transform.position - slot).sqrMagnitude > limit)
                return true;
        }
        return false;
    }

    Vector3 Snap(Vector3 position, Vector3 fallback)
    {
        if (NavMesh.SamplePosition(position, out NavMeshHit hit, maxSlotSnap, NavMesh.AllAreas))
            return hit.position;
        if (NavMesh.SamplePosition(fallback, out hit, maxSlotSnap, NavMesh.AllAreas))
            return hit.position;
        return fallback;
    }

    bool GroundPoint(Vector2 screen, out Vector3 point)
    {
        if (cam != null && Physics.Raycast(cam.ScreenPointToRay(screen), out RaycastHit hit, Mathf.Infinity, groundMask))
        {
            point = hit.point;
            return true;
        }

        point = default;
        return false;
    }

    static Vector3 Centroid(List<NavMeshAgent> agents)
    {
        Vector3 sum = Vector3.zero;
        for (int i = 0; i < agents.Count; i++)
            sum += agents[i].transform.position;
        return sum / agents.Count;
    }
}
```

!!! warning "Common pitfalls"

    Spacing below twice the agent radius makes neighbours' avoidance fight over the slots, and the group jitters at the destination. Raise the spacing or lower the radius.

    `remainingDistance` is not ready on the frame of `SetDestination`. Without the `pathPending` check, every unit looks arrived on the first frame, and turns to face before it has moved.

    A slot inside an obstacle with **Max Slot Snap** too small fails to sample, and the unit is sent to the destination's centre instead. Raise it, or accept the bunching.

    In march mode, a unit that cannot reach its slot, such as one stuck behind a wall, holds the whole group because the anchor waits for stragglers. Lower **Catch Up Distance** waits less; set it very high to never wait.

    The greedy assignment can still cross two paths when the group approaches from an odd angle. For large armies, use the Hungarian algorithm.
