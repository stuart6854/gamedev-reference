---
engine: Unity
version: 6+
uses:
  - name: Strategy and tactics
    text: Box, click, and double-click selection of units.
  - name: Life and colony sims
    text: Selecting several colonists to give one order.
---

# Drag selection

RTS-style unit selection: click a unit to select it, drag a rectangle to select many, Shift to add, Ctrl to remove, and double-click to select every visible unit of the same type. The rectangle is drawn with a UI image. It pairs with the [top-down strategy camera](../cameras/rts.md), which pans with the middle mouse button and leaves the left free.

What a selection then does, such as moving in formation, is a separate page. Highlighting selected units can use a marker object, or the [highlight and outline](../rendering/highlight-outline.md) effects.

## Which test

A dragged rectangle is a screen-space shape. Deciding which units are "in" it has several answers:

| Method | Test | Good for | Weak at |
| --- | --- | --- | --- |
| **Screen point** | Project the unit's position to the screen. Inside the rectangle? | Most RTS games. Cheap and predictable. | A tall unit whose feet are just outside is missed, even if most of it is inside. |
| **World frustum** | Build planes through the rectangle's edges. Do the unit's bounds touch the volume? | Units of different sizes and heights. Selects anything visibly overlapped. | Picks up units hidden behind terrain or buildings, since nothing tests occlusion. |
| **Ground quad** | Project the corners onto the ground plane. Is the unit's position inside the quad? | Flat maps seen from high up. | Units on hills, and a tilted camera, make the quad and the screen disagree. |
| **Lasso** | Point-in-polygon on the screen points traced by the drag. | Irregular groups. | Needs a path drawn, not a rectangle. |

The script implements screen point and world frustum, chosen in the inspector. Lasso is at the end.

## Setup

1. Put `SelectableUnit` on each unit's root, with a collider on a layer in **Click Mask**. Set **Type Id**, for example `Archer`, and optionally a **Selection Marker** child such as a ring decal, inactive by default.
2. Create a canvas in **Screen Space - Overlay**, and under it a UI **Image** for the rectangle: a translucent fill, or a sliced outline sprite. Set its anchors and pivot to bottom-left (0, 0). Uncheck **Raycast Target**.
3. Add an **EventSystem** if the scene has none, so clicks on other UI do not select through it.
4. Put `SelectionManager` on any object. Assign the camera, the rectangle, and the canvas.
5. Copy one `SelectionInput` listing, Input System or legacy, not both.
6. Other scripts read `SelectionManager.Selected` and subscribe to `SelectionChanged`.

## What each step is doing

A press records the pointer position. Until the pointer has moved **Drag Threshold** pixels, the press is a click. That stops a shaky click from becoming a tiny drag that selects nothing.

On release, a click raycasts for one unit. A drag tests every registered unit against the rectangle. Units register themselves in a static list when enabled, so the test never searches the scene.

The result is applied by mode:

| Held | Mode | Effect |
| --- | --- | --- |
| Nothing | Replace | The selection becomes exactly the units found. A click on empty ground clears it. |
| Shift | Add | Found units are added. |
| Ctrl | Remove | Found units are removed. |

A second click on the same unit within **Double Click Time** selects every enabled unit with the same type id that is on screen, using the same mode.

### The frustum planes

Each edge of the rectangle, together with the camera, defines a plane. With rays from `ScreenPointToRay` through two adjacent corners, the plane through the first ray's origin, a point along it, and the second ray's origin works for both perspective and orthographic cameras. Each plane is then flipped if needed so a point along the rectangle's centre ray is on its positive side, which is the inside for `GeometryUtility.TestPlanesAABB`. A fifth plane at the camera, facing forward, rejects units behind it.

## Scripts

### Input

=== "Input System"

    ```csharp
    using UnityEngine;
    using UnityEngine.InputSystem;

    /// <summary>
    /// Selection input for the Input System: left mouse, Shift to add, Ctrl to remove.
    /// </summary>
    public static class SelectionInput
    {
        public static Vector2 PointerPosition =>
            Mouse.current != null ? Mouse.current.position.ReadValue() : Vector2.zero;

        public static bool PressedThisFrame =>
            Mouse.current != null && Mouse.current.leftButton.wasPressedThisFrame;

        public static bool ReleasedThisFrame =>
            Mouse.current != null && Mouse.current.leftButton.wasReleasedThisFrame;

        public static bool Additive =>
            Keyboard.current != null && Keyboard.current.shiftKey.isPressed;

        public static bool Subtractive =>
            Keyboard.current != null && Keyboard.current.ctrlKey.isPressed;
    }
    ```

=== "Legacy Input Manager"

    ```csharp
    using UnityEngine;

    /// <summary>
    /// Selection input for the legacy Input Manager: left mouse, Shift to add, Ctrl to remove.
    /// </summary>
    public static class SelectionInput
    {
        public static Vector2 PointerPosition => Input.mousePosition;
        public static bool PressedThisFrame => Input.GetMouseButtonDown(0);
        public static bool ReleasedThisFrame => Input.GetMouseButtonUp(0);

        public static bool Additive =>
            Input.GetKey(KeyCode.LeftShift) || Input.GetKey(KeyCode.RightShift);

        public static bool Subtractive =>
            Input.GetKey(KeyCode.LeftControl) || Input.GetKey(KeyCode.RightControl);
    }
    ```

### Selectable unit

```csharp
using System;
using System.Collections.Generic;
using UnityEngine;

/// <summary>
/// A unit the selection manager can pick. Registers itself while enabled.
/// </summary>
[DisallowMultipleComponent]
public class SelectableUnit : MonoBehaviour
{
    static readonly List<SelectableUnit> _all = new List<SelectableUnit>();
    public static IReadOnlyList<SelectableUnit> All => _all;

    [Tooltip("Units with the same type are selected together by a double-click.")]
    [SerializeField] string typeId = "Unit";

    [Tooltip("Shown while selected. Optional.")]
    [SerializeField] GameObject selectionMarker;

    public string TypeId => typeId;
    public bool IsSelected { get; private set; }
    public event Action<bool> SelectionChanged;

    Collider _collider;
    Renderer _renderer;

    // With domain reload off, the list would keep units from the last Play session.
    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
    static void ResetStatics()
    {
        _all.Clear();
    }

    void Awake()
    {
        _collider = GetComponentInChildren<Collider>();
        _renderer = GetComponentInChildren<Renderer>();
    }

    void OnEnable()
    {
        _all.Add(this);
        if (selectionMarker != null)
            selectionMarker.SetActive(IsSelected);
    }

    void OnDisable()
    {
        _all.Remove(this);
        SetSelected(false);
    }

    /// <summary>World bounds for the frustum test: the collider, else the renderer, else a point.</summary>
    public Bounds WorldBounds
    {
        get
        {
            if (_collider != null)
                return _collider.bounds;
            if (_renderer != null)
                return _renderer.bounds;
            return new Bounds(transform.position, Vector3.zero);
        }
    }

    /// <summary>Called by the selection manager.</summary>
    public void SetSelected(bool selected)
    {
        if (IsSelected == selected)
            return;

        IsSelected = selected;
        if (selectionMarker != null)
            selectionMarker.SetActive(selected);
        SelectionChanged?.Invoke(selected);
    }
}
```

### Selection manager

```csharp
using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.EventSystems;

/// <summary>
/// Click, drag-rectangle, and double-click selection of SelectableUnits.
/// </summary>
public class SelectionManager : MonoBehaviour
{
    public enum BoxMethod
    {
        ScreenPoint,
        Frustum
    }

    [SerializeField] Camera cam;

    [Tooltip("UI Image on a Screen Space - Overlay canvas. Anchors and pivot at (0, 0).")]
    [SerializeField] RectTransform selectionBox;
    [SerializeField] Canvas canvas;

    [SerializeField] LayerMask clickMask = ~0;
    [SerializeField] BoxMethod method = BoxMethod.ScreenPoint;

    [Tooltip("Pixels the pointer must move before a press becomes a drag.")]
    [SerializeField] float dragThreshold = 8f;
    [SerializeField] float doubleClickTime = 0.3f;

    public event Action SelectionChanged;

    public IReadOnlyList<SelectableUnit> Selected
    {
        get
        {
            Prune();
            return _selected;
        }
    }

    static readonly Predicate<SelectableUnit> IsGone = unit => unit == null || !unit.isActiveAndEnabled;

    readonly List<SelectableUnit> _selected = new List<SelectableUnit>();
    readonly List<SelectableUnit> _found = new List<SelectableUnit>();
    readonly Plane[] _planes = new Plane[5];

    Vector2 _pressPosition;
    bool _pressing;
    bool _dragging;
    float _lastClickTime = -1f;
    SelectableUnit _lastClicked;

    void Awake()
    {
        if (cam == null)
            cam = Camera.main;
        if (selectionBox != null)
            selectionBox.gameObject.SetActive(false);
    }

    void OnDisable()
    {
        _pressing = false;
        _dragging = false;
        if (selectionBox != null)
            selectionBox.gameObject.SetActive(false);
    }

    void Update()
    {
        if (cam == null)
            return;

        Vector2 pointer = SelectionInput.PointerPosition;

        if (SelectionInput.PressedThisFrame)
        {
            // A click on a button or panel is not a selection.
            if (EventSystem.current != null && EventSystem.current.IsPointerOverGameObject())
                return;

            _pressing = true;
            _dragging = false;
            _pressPosition = pointer;
        }

        if (!_pressing)
            return;

        if (!_dragging && (pointer - _pressPosition).sqrMagnitude >= dragThreshold * dragThreshold)
        {
            _dragging = true;
            if (selectionBox != null)
                selectionBox.gameObject.SetActive(true);
        }

        if (_dragging)
            DrawBox(_pressPosition, pointer);

        if (SelectionInput.ReleasedThisFrame)
        {
            _pressing = false;
            if (_dragging)
            {
                _dragging = false;
                if (selectionBox != null)
                    selectionBox.gameObject.SetActive(false);
                BoxSelect(_pressPosition, pointer);
            }
            else
            {
                Click(pointer);
            }
        }
    }

    void Click(Vector2 pointer)
    {
        SelectableUnit hit = null;
        if (Physics.Raycast(cam.ScreenPointToRay(pointer), out RaycastHit info, Mathf.Infinity, clickMask))
            hit = info.collider.GetComponentInParent<SelectableUnit>();

        bool doubleClick = hit != null && hit == _lastClicked &&
                           Time.unscaledTime - _lastClickTime <= doubleClickTime;
        _lastClicked = hit;
        _lastClickTime = Time.unscaledTime;

        _found.Clear();
        if (doubleClick)
        {
            IReadOnlyList<SelectableUnit> all = SelectableUnit.All;
            for (int i = 0; i < all.Count; i++)
            {
                if (all[i].TypeId == hit.TypeId && OnScreen(all[i].transform.position))
                    _found.Add(all[i]);
            }
        }
        else if (hit != null)
        {
            _found.Add(hit);
        }

        Apply(_found);
    }

    void BoxSelect(Vector2 a, Vector2 b)
    {
        Rect rect = Rect.MinMaxRect(
            Mathf.Min(a.x, b.x), Mathf.Min(a.y, b.y), Mathf.Max(a.x, b.x), Mathf.Max(a.y, b.y));

        if (method == BoxMethod.Frustum)
            BuildPlanes(rect);

        _found.Clear();
        IReadOnlyList<SelectableUnit> all = SelectableUnit.All;
        for (int i = 0; i < all.Count; i++)
        {
            SelectableUnit unit = all[i];
            bool inside = method == BoxMethod.Frustum
                ? GeometryUtility.TestPlanesAABB(_planes, unit.WorldBounds)
                : InRect(rect, unit.transform.position);
            if (inside)
                _found.Add(unit);
        }

        Apply(_found);
    }

    void Apply(List<SelectableUnit> found)
    {
        Prune();
        bool add = SelectionInput.Additive;
        bool remove = SelectionInput.Subtractive;

        if (!add && !remove)
        {
            for (int i = 0; i < _selected.Count; i++)
                _selected[i].SetSelected(false);
            _selected.Clear();
        }

        for (int i = 0; i < found.Count; i++)
        {
            SelectableUnit unit = found[i];
            if (remove)
            {
                if (_selected.Remove(unit))
                    unit.SetSelected(false);
            }
            else if (!unit.IsSelected)
            {
                _selected.Add(unit);
                unit.SetSelected(true);
            }
        }

        SelectionChanged?.Invoke();
    }

    bool InRect(Rect rect, Vector3 world)
    {
        Vector3 screen = cam.WorldToScreenPoint(world);
        return screen.z > 0f && rect.Contains(screen);
    }

    bool OnScreen(Vector3 world)
    {
        Vector3 screen = cam.WorldToScreenPoint(world);
        return screen.z > 0f && screen.x >= 0f && screen.y >= 0f &&
               screen.x <= Screen.width && screen.y <= Screen.height;
    }

    void BuildPlanes(Rect rect)
    {
        Ray r0 = cam.ScreenPointToRay(new Vector2(rect.xMin, rect.yMin));
        Ray r1 = cam.ScreenPointToRay(new Vector2(rect.xMax, rect.yMin));
        Ray r2 = cam.ScreenPointToRay(new Vector2(rect.xMax, rect.yMax));
        Ray r3 = cam.ScreenPointToRay(new Vector2(rect.xMin, rect.yMax));
        Vector3 inside = cam.ScreenPointToRay(rect.center).GetPoint(cam.nearClipPlane + 1f);

        _planes[0] = EdgePlane(r0, r1, inside);
        _planes[1] = EdgePlane(r1, r2, inside);
        _planes[2] = EdgePlane(r2, r3, inside);
        _planes[3] = EdgePlane(r3, r0, inside);
        _planes[4] = new Plane(cam.transform.forward, cam.transform.position);
    }

    static Plane EdgePlane(Ray a, Ray b, Vector3 inside)
    {
        // Through a's origin, a point along a, and b's origin: valid for perspective and orthographic.
        Plane plane = new Plane(a.origin, a.GetPoint(1f), b.origin);
        if (!plane.GetSide(inside))
            plane.Flip();
        return plane;
    }

    void DrawBox(Vector2 a, Vector2 b)
    {
        if (selectionBox == null)
            return;

        float scale = canvas != null ? canvas.scaleFactor : 1f;
        Vector2 min = Vector2.Min(a, b);
        Vector2 max = Vector2.Max(a, b);
        selectionBox.anchoredPosition = min / scale;
        selectionBox.sizeDelta = (max - min) / scale;
    }

    void Prune()
    {
        _selected.RemoveAll(IsGone);
    }
}
```

## Lasso

Record the pointer while dragging, adding a point whenever it has moved a few pixels from the last one. On release, test each unit's screen position against the polygon with the even–odd rule: cast a ray to the right and count the edges it crosses.

```csharp
static bool InPolygon(List<Vector2> polygon, Vector2 p)
{
    bool inside = false;
    for (int i = 0, j = polygon.Count - 1; i < polygon.Count; j = i++)
    {
        Vector2 a = polygon[i];
        Vector2 b = polygon[j];
        if ((a.y > p.y) != (b.y > p.y) &&
            p.x < (b.x - a.x) * (p.y - a.y) / (b.y - a.y) + a.x)
            inside = !inside;
    }
    return inside;
}
```

The closing edge, from the last point back to the first, is included by starting `j` at the end. Draw the path with a `LineRenderer` in screen space, or a UI line.

!!! warning "Common pitfalls"

    Without an EventSystem in the scene, `EventSystem.current` is null and the UI check is skipped, so clicking a HUD button also clears the selection.

    With anchors or pivot not at (0, 0), the rectangle draws offset. With a canvas scaler, positions must be divided by `canvas.scaleFactor`, as `DrawBox` does.

    `WorldToScreenPoint` of a point behind the camera still returns x and y. Without the `z > 0` check, units behind the camera can land inside the rectangle.

    The frustum method uses collider bounds, which are axis-aligned in world space. A long unit rotated 45° has a bounding box much bigger than itself, and is selected from further away.

    A unit without a collider cannot be clicked, only boxed. Put its collider on a layer in **Click Mask**.
