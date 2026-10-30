---
engine: Unity
version: 6+
uses:
  - name: Strategy and tactics
    text: Edge pan, drag pan, rotation, and zoom to the cursor.
  - name: Base building
    text: A top-down view for placing and managing structures.
  - name: Life and colony sims
    text: A camera for watching and managing a settlement.
---

# Top-down strategy camera

The camera of an RTS or a city builder. It looks down at a point on the ground and can be panned with the keys, the screen edges, or by dragging the ground with the middle mouse button. The scroll wheel zooms towards the cursor, Q and E rotate around the point, and the point stays inside the map.

Like the [first-person camera](first-person.md), it is one script on an unparented camera. It stores a **focus** point on the ground, a yaw, and a distance, and builds the camera pose from them every frame. Nothing is parented, so there is no rig hierarchy to keep in step. The left mouse button is left free for selection, which is the [drag selection](../mechanics/selection.md) page.

## Setup

1. Add `StrategyCamera` to the **Camera**. Leave the camera at the top level of the scene.
2. Set **Bounds Min** and **Bounds Max** to the playable rectangle on the XZ plane. The focus point cannot leave it.
3. Set **Ground Mask** to the terrain layer if the ground is not flat. The focus point then rides the terrain height. Leave it at **Nothing** for a flat map at **Ground Height**.
4. Copy one `StrategyCameraInput` listing, Input System or legacy, not both.
5. Press Play. WASD or the arrow keys pan, Shift pans faster, the middle mouse button drags the ground, the wheel zooms, and Q and E rotate.

## What each step is doing

The camera's pose comes from four numbers:

\[
R = \text{Euler}(\theta_{\text{pitch}}, \psi_{\text{yaw}}, 0), \qquad
p_{\text{camera}} = p_{\text{focus}} - R\,\hat{z}\, d
\]

\(\hat{z}\) is local forward and \(d\) is the distance. Pitch is not a free input. It follows the zoom: it is **Near Pitch** at **Min Distance** and **Far Pitch** at **Max Distance**, so the view tilts towards the horizon as it closes in. That is how most strategy games read: a map from far away, and the sides of units up close.

Every input moves a **target**: target focus, target yaw, target distance. The actual values chase their targets with the [exponential blend](../../maths/interpolation.md#frame-rate-independent-damping) at **Sharpness**. The camera uses `Time.unscaledDeltaTime` throughout, so it still moves while the game is paused with `Time.timeScale = 0`, which strategy games usually allow.

**Key and edge pan** move the target focus along the camera's flat forward and right, so W is always "up the screen" after a rotation. The speed is multiplied by the current distance divided by **Min Distance**, so a pan crosses the same fraction of the screen at any zoom.

**Drag pan** grabs the ground. When the middle button goes down, the ground point under the cursor is recorded. Every frame after that, the focus moves by the difference between that point and the point now under the cursor, so the grabbed spot stays under the pointer. Both the target and the actual focus move together, with no smoothing, because a drag that lags behind the hand feels loose. Ground points come from a ray against a horizontal plane at the focus height, not against colliders, so dragging over a tall building does not jump.

**Zoom towards the cursor.** Each wheel step multiplies the target distance by **Zoom Step**, or divides by it. The focus then moves towards the ground point under the cursor by the same fraction the distance shrank:

\[
p_{\text{focus}} \mathrel{+}= \left(p_{\text{cursor}} - p_{\text{focus}}\right)\left(1 - \frac{d_{\text{new}}}{d_{\text{old}}}\right)
\]

That keeps the point under the cursor in roughly the same place on screen. It is exact for a camera looking straight down. With the pitch changing during the zoom it is close, not exact, which is enough to feel right.

**Rotation** turns the target yaw at **Rotate Speed**, around the focus point.

**Bounds and ground.** The target focus is clamped to the bounds rectangle after every input. With a ground mask, a ray from high above finds the terrain under the focus, and the focus height follows it, smoothed like everything else.

## Parameters

| Field | Default | Effect |
| --- | --- | --- |
| Pan Speed | `12` | Metres per second at **Min Distance**. Scales up with zoom. |
| Fast Multiplier | `2.5` | Pan speed multiplier while Shift is held. |
| Edge Pan | On | Pan when the pointer is within **Edge Size** of the window edge. |
| Edge Size | `12` | Pixels. |
| Rotate Speed | `90` | Degrees per second for Q and E. |
| Min / Max Distance | `8` / `60` | Zoom limits, metres from the focus point. |
| Zoom Step | `1.15` | Distance factor per wheel notch. |
| Zoom To Cursor | On | Move the focus towards the cursor while zooming. |
| Near / Far Pitch | `40` / `65` | Degrees down from the horizon at the two zoom limits. |
| Sharpness | `12` | How quickly the camera reaches its targets. |
| Bounds Min / Max | `(-100, -100)` / `(100, 100)` | Playable rectangle on XZ. |
| Ground Mask | Nothing | Terrain layers for focus height. Nothing uses **Ground Height**. |
| Ground Height | `0` | Focus height on a flat map. |

## Scripts

### Input

Each listing is the input side only. Both report a pan vector, a rotation, the scroll direction, the middle button, Shift, and the pointer.

=== "Input System"

    ```csharp
    using UnityEngine;
    using UnityEngine.InputSystem;

    /// <summary>
    /// Strategy camera input for the Input System.
    /// </summary>
    public static class StrategyCameraInput
    {
        public static Vector2 Pan()
        {
            Vector2 move = Vector2.zero;
            Keyboard keyboard = Keyboard.current;
            if (keyboard == null)
                return move;
            if (keyboard.dKey.isPressed || keyboard.rightArrowKey.isPressed) move.x += 1f;
            if (keyboard.aKey.isPressed || keyboard.leftArrowKey.isPressed) move.x -= 1f;
            if (keyboard.wKey.isPressed || keyboard.upArrowKey.isPressed) move.y += 1f;
            if (keyboard.sKey.isPressed || keyboard.downArrowKey.isPressed) move.y -= 1f;
            return move;
        }

        /// <summary>+1 for E (clockwise from above), -1 for Q.</summary>
        public static float Rotate()
        {
            Keyboard keyboard = Keyboard.current;
            if (keyboard == null)
                return 0f;
            float turn = 0f;
            if (keyboard.eKey.isPressed) turn += 1f;
            if (keyboard.qKey.isPressed) turn -= 1f;
            return turn;
        }

        public static bool Fast()
        {
            Keyboard keyboard = Keyboard.current;
            return keyboard != null && keyboard.shiftKey.isPressed;
        }

        /// <summary>Sign of this frame's wheel movement: +1 away from the user, -1 towards, or 0.</summary>
        public static float Scroll()
        {
            Mouse mouse = Mouse.current;
            float wheel = mouse != null ? mouse.scroll.ReadValue().y : 0f;
            return wheel > 0f ? 1f : wheel < 0f ? -1f : 0f;
        }

        public static bool DragHeld()
        {
            Mouse mouse = Mouse.current;
            return mouse != null && mouse.middleButton.isPressed;
        }

        public static bool TryPointer(out Vector2 position)
        {
            Mouse mouse = Mouse.current;
            position = mouse != null ? mouse.position.ReadValue() : Vector2.zero;
            return mouse != null;
        }
    }
    ```

=== "Legacy Input Manager"

    ```csharp
    using UnityEngine;

    /// <summary>
    /// Strategy camera input for the legacy Input Manager.
    /// </summary>
    public static class StrategyCameraInput
    {
        public static Vector2 Pan()
        {
            return new Vector2(Input.GetAxisRaw("Horizontal"), Input.GetAxisRaw("Vertical"));
        }

        /// <summary>+1 for E (clockwise from above), -1 for Q.</summary>
        public static float Rotate()
        {
            float turn = 0f;
            if (Input.GetKey(KeyCode.E)) turn += 1f;
            if (Input.GetKey(KeyCode.Q)) turn -= 1f;
            return turn;
        }

        public static bool Fast()
        {
            return Input.GetKey(KeyCode.LeftShift) || Input.GetKey(KeyCode.RightShift);
        }

        /// <summary>Sign of this frame's wheel movement: +1 away from the user, -1 towards, or 0.</summary>
        public static float Scroll()
        {
            float wheel = Input.GetAxisRaw("Mouse ScrollWheel");
            return wheel > 0f ? 1f : wheel < 0f ? -1f : 0f;
        }

        public static bool DragHeld()
        {
            return Input.GetMouseButton(2);
        }

        public static bool TryPointer(out Vector2 position)
        {
            position = Input.mousePosition;
            return Input.mousePresent;
        }
    }
    ```

### Strategy camera

```csharp
using UnityEngine;

/// <summary>
/// RTS camera. Stores a ground focus point, yaw, and distance, and builds the pose
/// from them. Pitch follows the zoom. All motion uses unscaled time.
/// </summary>
[DisallowMultipleComponent]
[RequireComponent(typeof(Camera))]
public class StrategyCamera : MonoBehaviour
{
    [Header("Pan")]
    [Tooltip("Metres per second at Min Distance. Scales with zoom.")]
    [SerializeField] float panSpeed = 12f;
    [SerializeField] float fastMultiplier = 2.5f;
    [SerializeField] bool edgePan = true;
    [Tooltip("Pixels from the window edge that start an edge pan.")]
    [SerializeField] float edgeSize = 12f;

    [Header("Rotate and zoom")]
    [SerializeField] float rotateSpeed = 90f;
    [SerializeField] float minDistance = 8f;
    [SerializeField] float maxDistance = 60f;
    [Tooltip("Distance factor per wheel notch.")]
    [SerializeField] float zoomStep = 1.15f;
    [SerializeField] bool zoomToCursor = true;
    [Tooltip("Degrees down from the horizon at Min Distance.")]
    [SerializeField] float nearPitch = 40f;
    [Tooltip("Degrees down from the horizon at Max Distance.")]
    [SerializeField] float farPitch = 65f;
    [SerializeField] float sharpness = 12f;

    [Header("Map")]
    [SerializeField] Vector2 boundsMin = new Vector2(-100f, -100f);
    [SerializeField] Vector2 boundsMax = new Vector2(100f, 100f);
    [SerializeField] LayerMask groundMask;
    [SerializeField] float groundHeight;

    Camera _camera;
    Vector3 _focus;
    Vector3 _targetFocus;
    float _yaw;
    float _targetYaw;
    float _distance;
    float _targetDistance;
    bool _dragging;
    Vector3 _dragAnchor;

    void Awake()
    {
        _camera = GetComponent<Camera>();
        _yaw = _targetYaw = transform.eulerAngles.y;
        _distance = _targetDistance = Mathf.Lerp(minDistance, maxDistance, 0.5f);

        // Start looking at the ground point in front of where the camera was placed.
        Plane ground = new Plane(Vector3.up, new Vector3(0f, groundHeight, 0f));
        Ray ray = new Ray(transform.position, transform.forward);
        _targetFocus = ground.Raycast(ray, out float hit) ? ray.GetPoint(hit) : new Vector3(transform.position.x, groundHeight, transform.position.z);
        _targetFocus = Clamp(_targetFocus);
        _targetFocus.y = GroundY(_targetFocus);
        _focus = _targetFocus;
        ApplyPose();
    }

    void LateUpdate()
    {
        float dt = Time.unscaledDeltaTime;
        bool hasPointer = StrategyCameraInput.TryPointer(out Vector2 pointer);

        Drag(hasPointer, pointer);
        if (!_dragging)
            Pan(dt, hasPointer, pointer);
        _targetYaw += StrategyCameraInput.Rotate() * rotateSpeed * dt;
        Zoom(hasPointer, pointer);

        _targetFocus = Clamp(_targetFocus);
        _targetFocus.y = GroundY(_targetFocus);

        float blend = sharpness <= 0f ? 1f : 1f - Mathf.Exp(-sharpness * dt);
        _focus = Vector3.Lerp(_focus, _targetFocus, blend);
        _yaw = Mathf.LerpAngle(_yaw, _targetYaw, blend);
        _distance = Mathf.Lerp(_distance, _targetDistance, blend);
        ApplyPose();
    }

    void Pan(float dt, bool hasPointer, Vector2 pointer)
    {
        Vector2 move = StrategyCameraInput.Pan();
        if (edgePan && hasPointer && Application.isFocused)
            move += EdgeDirection(pointer);
        if (move.sqrMagnitude < 0.0001f)
            return;
        if (move.sqrMagnitude > 1f)
            move.Normalize();

        Quaternion flat = Quaternion.Euler(0f, _yaw, 0f);
        Vector3 direction = flat * new Vector3(move.x, 0f, move.y);
        float speed = panSpeed * (_distance / Mathf.Max(0.01f, minDistance));
        if (StrategyCameraInput.Fast())
            speed *= fastMultiplier;
        _targetFocus += direction * (speed * dt);
    }

    Vector2 EdgeDirection(Vector2 pointer)
    {
        // Outside the window, the pointer is not at an edge: it has left the game.
        if (pointer.x < 0f || pointer.y < 0f || pointer.x > Screen.width || pointer.y > Screen.height)
            return Vector2.zero;
        Vector2 direction = Vector2.zero;
        if (pointer.x <= edgeSize) direction.x -= 1f;
        if (pointer.x >= Screen.width - edgeSize) direction.x += 1f;
        if (pointer.y <= edgeSize) direction.y -= 1f;
        if (pointer.y >= Screen.height - edgeSize) direction.y += 1f;
        return direction;
    }

    void Drag(bool hasPointer, Vector2 pointer)
    {
        if (!StrategyCameraInput.DragHeld() || !hasPointer)
        {
            _dragging = false;
            return;
        }

        if (!TryGroundPoint(pointer, out Vector3 under))
            return;

        if (!_dragging)
        {
            _dragging = true;
            _dragAnchor = under;
            return;
        }

        // Move both, so the grabbed point stays under the pointer with no lag.
        Vector3 shift = _dragAnchor - under;
        shift.y = 0f;
        _targetFocus += shift;
        _focus += shift;
    }

    void Zoom(bool hasPointer, Vector2 pointer)
    {
        float scroll = StrategyCameraInput.Scroll();
        if (scroll == 0f)
            return;

        float before = _targetDistance;
        _targetDistance = Mathf.Clamp(scroll > 0f ? before / zoomStep : before * zoomStep, minDistance, maxDistance);
        if (!zoomToCursor || !hasPointer || !TryGroundPoint(pointer, out Vector3 under))
            return;

        float shrink = 1f - _targetDistance / before;
        Vector3 toward = under - _targetFocus;
        toward.y = 0f;
        _targetFocus += toward * shrink;
    }

    void ApplyPose()
    {
        float t = Mathf.InverseLerp(minDistance, maxDistance, _distance);
        float pitch = Mathf.Lerp(nearPitch, farPitch, t);
        Quaternion rotation = Quaternion.Euler(pitch, _yaw, 0f);
        transform.SetPositionAndRotation(_focus - rotation * Vector3.forward * _distance, rotation);
    }

    bool TryGroundPoint(Vector2 pointer, out Vector3 point)
    {
        // A plane at the focus height, not the colliders, so a tall building does not jump the drag.
        Plane plane = new Plane(Vector3.up, _focus);
        Ray ray = _camera.ScreenPointToRay(pointer);
        if (plane.Raycast(ray, out float distance))
        {
            point = ray.GetPoint(distance);
            return true;
        }

        point = Vector3.zero;
        return false;
    }

    Vector3 Clamp(Vector3 focus)
    {
        focus.x = Mathf.Clamp(focus.x, Mathf.Min(boundsMin.x, boundsMax.x), Mathf.Max(boundsMin.x, boundsMax.x));
        focus.z = Mathf.Clamp(focus.z, Mathf.Min(boundsMin.y, boundsMax.y), Mathf.Max(boundsMin.y, boundsMax.y));
        return focus;
    }

    float GroundY(Vector3 focus)
    {
        if (groundMask.value == 0)
            return groundHeight;
        Vector3 origin = new Vector3(focus.x, focus.y + 500f, focus.z);
        return Physics.Raycast(origin, Vector3.down, out RaycastHit hit, 1000f, groundMask, QueryTriggerInteraction.Ignore)
            ? hit.point.y
            : focus.y;
    }

    /// <summary>Jump the camera to look at a point, for a minimap click or a unit hotkey.</summary>
    public void FocusOn(Vector3 point, bool instant)
    {
        _targetFocus = Clamp(point);
        _targetFocus.y = GroundY(_targetFocus);
        if (instant)
        {
            _focus = _targetFocus;
            ApplyPose();
        }
    }

    void OnValidate()
    {
        panSpeed = Mathf.Max(0f, panSpeed);
        fastMultiplier = Mathf.Max(1f, fastMultiplier);
        edgeSize = Mathf.Max(1f, edgeSize);
        minDistance = Mathf.Max(0.5f, minDistance);
        maxDistance = Mathf.Max(minDistance, maxDistance);
        zoomStep = Mathf.Max(1.01f, zoomStep);
        nearPitch = Mathf.Clamp(nearPitch, 5f, 90f);
        farPitch = Mathf.Clamp(farPitch, 5f, 90f);
    }
}
```

!!! warning "Common pitfalls"

    Edge pan in the editor fires whenever the pointer crosses the Game view's border on its way to the Inspector. The script ignores the pointer outside the window and while the application is unfocused, but a narrow Game view still makes it easy to trigger. Turn **Edge Pan** off while testing, or play maximised.

    A trackpad sends many small scroll events instead of a few notches, and each frame with any scroll counts as one notch here, so zoom runs fast on a trackpad. Lower **Zoom Step** for trackpad users, or scale the step by the scroll amount.

    The drag and zoom rays hit a plane at the focus height. On hilly terrain, the grabbed point on a hilltop is not exactly where the plane is, so the hill slides a little under the pointer. It is close enough at strategy-game pitches. Use a collider ray against **Ground Mask** if it is not.

    The bounds clamp the focus point, not the view. At the edge of the map, the camera still shows ground beyond the rectangle, more so at **Far Pitch**. Shrink the bounds by the half-width you can see at **Max Distance**, or put scenery past the edge.

    Middle-mouse drag and edge pan both pan, and they would add together. The drag takes over while the button is held, and the keys and edges are ignored until it is released.

    Unscaled time keeps the camera moving while the game is paused. A pause menu that should freeze the camera has to disable this component.
