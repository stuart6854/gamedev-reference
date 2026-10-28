---
engine: Unity
version: 6+
---

# Interaction

Focus an object, show its prompt, and use it with a press or a hold. The contract is `IInteractable`. The player side is one `Interactor`, which either casts from the camera or overlaps a sphere and picks the best target.

Unity does not ship a general interaction package, so this page is the plain implementation. The XR Interaction Toolkit solves a different problem and is not a stand-in here. Focus feedback is the [highlight and outline](../rendering/highlight-outline.md) page; `OnFocusEnter` and `OnFocusExit` are the hook it uses.

The interactor pairs with [character movement](character-movement.md). First person uses **From Camera**, with **Rotate Towards Move** off so a parented camera owns the yaw. Third person uses **Proximity**, aimed with the [orbit camera](../cameras/third-person.md).

## Setup

1. Put a collider on each interactable. A door that the camera cast should hit needs a solid collider. A trigger is only seen by the proximity overlap, because that query includes triggers and the camera cast ignores them.
2. Add `DoorInteractable` or `PickupInteractable`, or implement `IInteractable` yourself. The component can sit on the collider or on a parent. The query walks upward from the hit.
3. Add `Interactor` to the player. Assign **View** to the gameplay camera, or leave it empty to use `Camera.main`.
4. Choose the query. **From Camera** is the first-person cast: a sphere cast along the camera forward, or a ray when **Sphere Radius** is `0`. **Proximity** is the third-person overlap.
5. Set the masks. **Camera Mask** includes walls and interactables, so a wall blocks the cast. **Interact Mask** is the overlap, and should be the interactable layer rather than the whole world, or the floor fills the buffer. **Sight Mask** is the wall test for proximity: walls and solid interactables, not the player.
6. Copy the Input System interactor. A new Unity 6 project uses that backend. The legacy listing is the same behaviour for a project still on the Input Manager. Do not add both. Copy the interface and the two examples once; they do not depend on the input backend.
7. Press E, or the west face button on a gamepad (X on Xbox, Square on PlayStation). **Draw Prompt** uses `OnGUI` so the string is visible without a UI toolkit. A real label should read `Prompt` and `HoldProgress` instead.

## What each step is doing

Each `Update` does the following.

1. Read the interact button. The down edge and the held state are separate, because a press and a hold are different.
2. Find one target. The camera cast keeps the nearest hit and stops, including when that hit is a wall with no `IInteractable`. The proximity query collects overlaps and scores them. Score is distance from the player plus **Angle Weight** times the angle off the camera forward, and the lower score wins. Candidates outside **Max View Angle** are dropped. When **Require Line Of Sight** is on, a ray from the camera to the candidate must not hit something else first.
3. If the target changed, the previous one gets `OnHoldChanged` at zero and `OnFocusExit`, then the new one gets `OnFocusEnter`. A destroyed target is treated as gone and is not messaged.
4. `HoldDuration` of zero fires `Interact` on the down edge. A positive duration fills while the button is held, reports that fraction through `OnHoldChanged`, and fires `Interact` once when the hold completes. Releasing early clears the hold. The button must be released before the same target will hold again.

The prompt string belongs to the interactable. The door swaps "Open" and "Close". The pickup says "Pick up" plus the item name, and its hold is `0.4` seconds so the hold path is the one you can see.

## Parameters

| Field | Default | Effect |
| --- | --- | --- |
| View | Empty | Camera forward. Empty follows `Camera.main`. |
| Query | From Camera | Camera cast, or a proximity overlap. |
| Max Distance | `3` | Metres the camera cast may travel. |
| Sphere Radius | `0.15` | Camera cast thickness. `0` is a ray. |
| Proximity Radius | `1.6` | Overlap radius around the player. |
| Proximity Offset | `(0, 1, 0.4)` | Local centre of that overlap. |
| Max View Angle | `70` | Proximity cone around the camera forward, in degrees. |
| Angle Weight | `0.02` | Metres of score added per degree off centre. |
| Require Line Of Sight | On | Proximity targets behind a wall are ignored. |
| Camera Mask | Everything | What the camera cast can hit, walls included. |
| Interact Mask | Everything | What the overlap can collect. Narrow this. |
| Sight Mask | Everything | What blocks line of sight. Exclude the player. |
| Draw Prompt | On | `OnGUI` stand-in for a real prompt label. |

## Scripts

`IInteractable` and `InteractQuery` go in one file. Each example is its own file. The interactor tabs are the same class; copy one of them.

### Contract

```csharp
using UnityEngine;

/// <summary>
/// Something the player can focus and use.
/// </summary>
/// <remarks>
/// OnFocusEnter and OnFocusExit are the hook for a highlight or outline.
/// The highlight and outline page calls Outline.SetFocused from these two methods.
/// HoldDuration of zero means a press. A positive value is seconds of hold.
/// </remarks>
public interface IInteractable
{
    string Prompt { get; }

    float HoldDuration { get; }

    bool CanInteract(Interactor interactor);

    void OnFocusEnter(Interactor interactor);

    void OnFocusExit(Interactor interactor);

    void OnHoldChanged(Interactor interactor, float progress);

    void Interact(Interactor interactor);
}

public enum InteractQuery
{
    FromCamera,
    Proximity
}
```

### Interactor

=== "Input System"

    E on the keyboard, and the west face button on a gamepad. Device reads are this frame's state and are not multiplied by `Time.deltaTime`.

    ```csharp
    using UnityEngine;
    using UnityEngine.InputSystem;

    /// <summary>
    /// Finds the best IInteractable and sends focus, hold, and interact to it.
    /// </summary>
    /// <remarks>
    /// Input System, the default backend in a new Unity 6 project.
    /// Keyboard is E. A gamepad uses the west face button: X on Xbox,
    /// Square on PlayStation. Reads devices directly so the sample does not
    /// need an actions asset.
    /// </remarks>
    [DisallowMultipleComponent]
    public class Interactor : MonoBehaviour
    {
        void ReadInput(out bool pressed, out bool held)
        {
            pressed = false;
            held = false;

            Keyboard keyboard = Keyboard.current;
            if (keyboard != null)
            {
                pressed |= keyboard.eKey.wasPressedThisFrame;
                held |= keyboard.eKey.isPressed;
            }

            Gamepad gamepad = Gamepad.current;
            if (gamepad != null)
            {
                pressed |= gamepad.buttonWest.wasPressedThisFrame;
                held |= gamepad.buttonWest.isPressed;
            }
        }

        [Header("View")]
        [Tooltip("Camera the query is aimed from. Empty uses Camera.main.")]
        [SerializeField] Transform view;

        [Header("Query")]
        [SerializeField] InteractQuery query = InteractQuery.FromCamera;

        [Tooltip("Metres the camera cast may travel.")]
        [SerializeField] float maxDistance = 3f;

        [Tooltip("SphereCast radius for the camera query. Zero is a ray.")]
        [SerializeField] float sphereRadius = 0.15f;

        [Tooltip("Overlap radius for the proximity query, in metres.")]
        [SerializeField] float proximityRadius = 1.6f;

        [Tooltip("Local offset of the proximity sphere. (0, 1, 0.4) sits at the chest, slightly forward.")]
        [SerializeField] Vector3 proximityOffset = new Vector3(0f, 1f, 0.4f);

        [Tooltip("Proximity candidates outside this angle from the camera forward are ignored.")]
        [SerializeField] float maxViewAngle = 70f;

        [Tooltip("Metres added to the score per degree off the camera forward. Lower score wins.")]
        [SerializeField] float angleWeight = 0.02f;

        [SerializeField] bool requireLineOfSight = true;

        [Tooltip("Camera cast. Include walls, or the cast passes through them, and include interactables.")]
        [SerializeField] LayerMask cameraMask = ~0;

        [Tooltip("Proximity overlap. Prefer the interactable layer, or the floor fills the buffer.")]
        [SerializeField] LayerMask interactMask = ~0;

        [Tooltip("Wall test for the proximity query. Include walls and solid interactables. Exclude the player.")]
        [SerializeField] LayerMask sightMask = ~0;

        [Header("Prompt")]
        [Tooltip("Draws the prompt with OnGUI. Replace this with your own label; read Prompt and HoldProgress.")]
        [SerializeField] bool drawPrompt = true;

        const int OverlapBufferSize = 16;

        Collider[] _overlaps;
        Transform _mainCamera;
        IInteractable _focus;
        float _hold;
        bool _holdSpent;

        public IInteractable Focus => Alive(_focus) ? _focus : null;

        public string Prompt => Focus == null ? string.Empty : _focus.Prompt;

        public float HoldProgress
        {
            get
            {
                IInteractable focus = Focus;
                if (focus == null || focus.HoldDuration <= 0f)
                    return 0f;
                return Mathf.Clamp01(_hold / focus.HoldDuration);
            }
        }

        void Awake()
        {
            _overlaps = new Collider[OverlapBufferSize];
        }

        void OnDisable()
        {
            SetFocus(null);
        }

        void Update()
        {
            ReadInput(out bool pressed, out bool held);
            SetFocus(FindTarget());

            IInteractable focus = Focus;
            if (focus == null)
            {
                _hold = 0f;
                _holdSpent = false;
                return;
            }

            float duration = Mathf.Max(0f, focus.HoldDuration);
            if (duration <= 0f)
            {
                _hold = 0f;
                _holdSpent = false;
                if (pressed)
                    focus.Interact(this);
                return;
            }

            if (!held)
            {
                _hold = 0f;
                _holdSpent = false;
                focus.OnHoldChanged(this, 0f);
                return;
            }

            if (_holdSpent)
                return;

            _hold += Time.deltaTime;
            float progress = Mathf.Clamp01(_hold / duration);
            focus.OnHoldChanged(this, progress);
            if (_hold < duration)
                return;

            _holdSpent = true;
            focus.Interact(this);
        }

        IInteractable FindTarget()
        {
            return query == InteractQuery.Proximity ? FindByProximity() : FindFromCamera();
        }

        IInteractable FindFromCamera()
        {
            Transform eyes = ViewTransform();
            if (eyes == null)
                return null;

            RaycastHit hit;
            bool hitSomething;
            if (sphereRadius <= 0.001f)
                hitSomething = Physics.Raycast(eyes.position, eyes.forward, out hit, maxDistance, cameraMask, QueryTriggerInteraction.Ignore);
            else
                hitSomething = Physics.SphereCast(eyes.position, sphereRadius, eyes.forward, out hit, maxDistance, cameraMask, QueryTriggerInteraction.Ignore);
            if (!hitSomething || hit.collider == null)
                return null;
            if (hit.collider.transform.IsChildOf(transform))
                return null;

            IInteractable interactable = hit.collider.GetComponentInParent<IInteractable>();
            if (!Alive(interactable) || !interactable.CanInteract(this))
                return null;
            return interactable;
        }

        IInteractable FindByProximity()
        {
            Transform eyes = ViewTransform();
            Vector3 origin = transform.TransformPoint(proximityOffset);
            int count = Physics.OverlapSphereNonAlloc(
                origin,
                proximityRadius,
                _overlaps,
                interactMask,
                QueryTriggerInteraction.Collide);

            IInteractable best = null;
            float bestScore = float.PositiveInfinity;
            Vector3 forward = eyes != null ? eyes.forward : transform.forward;
            Vector3 from = eyes != null ? eyes.position : origin;

            int limit = Mathf.Min(count, _overlaps.Length);
            for (int i = 0; i < limit; i++)
            {
                Collider candidate = _overlaps[i];
                if (candidate == null || candidate.transform.IsChildOf(transform))
                    continue;

                IInteractable interactable = candidate.GetComponentInParent<IInteractable>();
                if (!Alive(interactable) || !interactable.CanInteract(this))
                    continue;

                Vector3 closest = candidate.ClosestPoint(origin);
                float distance = Vector3.Distance(origin, closest);
                Vector3 toCamera = closest - from;
                float fromCamera = toCamera.magnitude;
                float angle = fromCamera <= 0.001f ? 0f : Vector3.Angle(forward, toCamera);
                if (angle > maxViewAngle)
                    continue;
                if (requireLineOfSight && !HasLineOfSight(from, candidate))
                    continue;

                float score = distance + angle * angleWeight;
                if (score >= bestScore)
                    continue;

                bestScore = score;
                best = interactable;
            }

            return best;
        }

        bool HasLineOfSight(Vector3 from, Collider target)
        {
            Vector3 to = target.bounds.center;
            Vector3 delta = to - from;
            float distance = delta.magnitude;
            if (distance <= 0.05f)
                return true;

            if (!Physics.Raycast(from, delta / distance, out RaycastHit hit, distance, sightMask, QueryTriggerInteraction.Ignore))
                return true;

            Transform hitTransform = hit.collider.transform;
            Transform targetTransform = target.transform;
            return hitTransform == targetTransform
            || hitTransform.IsChildOf(targetTransform)
            || targetTransform.IsChildOf(hitTransform);
        }

        void SetFocus(IInteractable next)
        {
            if (Same(_focus, next))
                return;

            if (Alive(_focus))
            {
                _focus.OnHoldChanged(this, 0f);
                _focus.OnFocusExit(this);
            }

            _focus = next;
            _hold = 0f;
            _holdSpent = false;
            if (Alive(_focus))
                _focus.OnFocusEnter(this);
        }

        Transform ViewTransform()
        {
            if (view != null)
                return view;
            if (_mainCamera == null)
            {
                Camera main = Camera.main;
                if (main != null)
                    _mainCamera = main.transform;
            }

            return _mainCamera;
        }

        static bool Alive(IInteractable interactable)
        {
            return interactable is Object candidate && candidate != null;
        }

        static bool Same(IInteractable a, IInteractable b)
        {
            if (!Alive(a) || !Alive(b))
                return !Alive(a) && !Alive(b);
            return ReferenceEquals(a, b);
        }

        void OnGUI()
        {
            if (!drawPrompt || Focus == null || string.IsNullOrEmpty(Prompt))
                return;

            const float width = 280f;
            float x = (Screen.width - width) * 0.5f;
            float y = Screen.height - 120f;
            GUI.Box(new Rect(x, y, width, 32f), Prompt);

            if (Focus.HoldDuration <= 0f)
                return;

            float bar = (width - 16f) * HoldProgress;
            GUI.Box(new Rect(x + 8f, y + 36f, bar, 6f), GUIContent.none);
        }

        void OnValidate()
        {
            maxDistance = Mathf.Max(0.05f, maxDistance);
            sphereRadius = Mathf.Max(0f, sphereRadius);
            proximityRadius = Mathf.Max(0.05f, proximityRadius);
            maxViewAngle = Mathf.Clamp(maxViewAngle, 0f, 180f);
            angleWeight = Mathf.Max(0f, angleWeight);
        }
    }
    ```

=== "Legacy Input Manager"

    The default Input Manager has no Interact button, so this listing uses E directly. `GetKey` is already this frame's state.

    ```csharp
    using UnityEngine;

    /// <summary>
    /// Finds the best IInteractable and sends focus, hold, and interact to it.
    /// </summary>
    /// <remarks>
    /// Legacy Input Manager. Active Input Handling must be
    /// "Input Manager (Old)" or "Both".
    /// </remarks>
    [DisallowMultipleComponent]
    public class Interactor : MonoBehaviour
    {
        void ReadInput(out bool pressed, out bool held)
        {
            // The default Input Manager has no Interact button. E is used so a
            // fresh project runs. A gamepad button needs an Interact axis of your own.
            pressed = Input.GetKeyDown(KeyCode.E);
            held = Input.GetKey(KeyCode.E);
        }

        [Header("View")]
        [Tooltip("Camera the query is aimed from. Empty uses Camera.main.")]
        [SerializeField] Transform view;

        [Header("Query")]
        [SerializeField] InteractQuery query = InteractQuery.FromCamera;

        [Tooltip("Metres the camera cast may travel.")]
        [SerializeField] float maxDistance = 3f;

        [Tooltip("SphereCast radius for the camera query. Zero is a ray.")]
        [SerializeField] float sphereRadius = 0.15f;

        [Tooltip("Overlap radius for the proximity query, in metres.")]
        [SerializeField] float proximityRadius = 1.6f;

        [Tooltip("Local offset of the proximity sphere. (0, 1, 0.4) sits at the chest, slightly forward.")]
        [SerializeField] Vector3 proximityOffset = new Vector3(0f, 1f, 0.4f);

        [Tooltip("Proximity candidates outside this angle from the camera forward are ignored.")]
        [SerializeField] float maxViewAngle = 70f;

        [Tooltip("Metres added to the score per degree off the camera forward. Lower score wins.")]
        [SerializeField] float angleWeight = 0.02f;

        [SerializeField] bool requireLineOfSight = true;

        [Tooltip("Camera cast. Include walls, or the cast passes through them, and include interactables.")]
        [SerializeField] LayerMask cameraMask = ~0;

        [Tooltip("Proximity overlap. Prefer the interactable layer, or the floor fills the buffer.")]
        [SerializeField] LayerMask interactMask = ~0;

        [Tooltip("Wall test for the proximity query. Include walls and solid interactables. Exclude the player.")]
        [SerializeField] LayerMask sightMask = ~0;

        [Header("Prompt")]
        [Tooltip("Draws the prompt with OnGUI. Replace this with your own label; read Prompt and HoldProgress.")]
        [SerializeField] bool drawPrompt = true;

        const int OverlapBufferSize = 16;

        Collider[] _overlaps;
        Transform _mainCamera;
        IInteractable _focus;
        float _hold;
        bool _holdSpent;

        public IInteractable Focus => Alive(_focus) ? _focus : null;

        public string Prompt => Focus == null ? string.Empty : _focus.Prompt;

        public float HoldProgress
        {
            get
            {
                IInteractable focus = Focus;
                if (focus == null || focus.HoldDuration <= 0f)
                    return 0f;
                return Mathf.Clamp01(_hold / focus.HoldDuration);
            }
        }

        void Awake()
        {
            _overlaps = new Collider[OverlapBufferSize];
        }

        void OnDisable()
        {
            SetFocus(null);
        }

        void Update()
        {
            ReadInput(out bool pressed, out bool held);
            SetFocus(FindTarget());

            IInteractable focus = Focus;
            if (focus == null)
            {
                _hold = 0f;
                _holdSpent = false;
                return;
            }

            float duration = Mathf.Max(0f, focus.HoldDuration);
            if (duration <= 0f)
            {
                _hold = 0f;
                _holdSpent = false;
                if (pressed)
                    focus.Interact(this);
                return;
            }

            if (!held)
            {
                _hold = 0f;
                _holdSpent = false;
                focus.OnHoldChanged(this, 0f);
                return;
            }

            if (_holdSpent)
                return;

            _hold += Time.deltaTime;
            float progress = Mathf.Clamp01(_hold / duration);
            focus.OnHoldChanged(this, progress);
            if (_hold < duration)
                return;

            _holdSpent = true;
            focus.Interact(this);
        }

        IInteractable FindTarget()
        {
            return query == InteractQuery.Proximity ? FindByProximity() : FindFromCamera();
        }

        IInteractable FindFromCamera()
        {
            Transform eyes = ViewTransform();
            if (eyes == null)
                return null;

            RaycastHit hit;
            bool hitSomething;
            if (sphereRadius <= 0.001f)
                hitSomething = Physics.Raycast(eyes.position, eyes.forward, out hit, maxDistance, cameraMask, QueryTriggerInteraction.Ignore);
            else
                hitSomething = Physics.SphereCast(eyes.position, sphereRadius, eyes.forward, out hit, maxDistance, cameraMask, QueryTriggerInteraction.Ignore);
            if (!hitSomething || hit.collider == null)
                return null;
            if (hit.collider.transform.IsChildOf(transform))
                return null;

            IInteractable interactable = hit.collider.GetComponentInParent<IInteractable>();
            if (!Alive(interactable) || !interactable.CanInteract(this))
                return null;
            return interactable;
        }

        IInteractable FindByProximity()
        {
            Transform eyes = ViewTransform();
            Vector3 origin = transform.TransformPoint(proximityOffset);
            int count = Physics.OverlapSphereNonAlloc(
                origin,
                proximityRadius,
                _overlaps,
                interactMask,
                QueryTriggerInteraction.Collide);

            IInteractable best = null;
            float bestScore = float.PositiveInfinity;
            Vector3 forward = eyes != null ? eyes.forward : transform.forward;
            Vector3 from = eyes != null ? eyes.position : origin;

            int limit = Mathf.Min(count, _overlaps.Length);
            for (int i = 0; i < limit; i++)
            {
                Collider candidate = _overlaps[i];
                if (candidate == null || candidate.transform.IsChildOf(transform))
                    continue;

                IInteractable interactable = candidate.GetComponentInParent<IInteractable>();
                if (!Alive(interactable) || !interactable.CanInteract(this))
                    continue;

                Vector3 closest = candidate.ClosestPoint(origin);
                float distance = Vector3.Distance(origin, closest);
                Vector3 toCamera = closest - from;
                float fromCamera = toCamera.magnitude;
                float angle = fromCamera <= 0.001f ? 0f : Vector3.Angle(forward, toCamera);
                if (angle > maxViewAngle)
                    continue;
                if (requireLineOfSight && !HasLineOfSight(from, candidate))
                    continue;

                float score = distance + angle * angleWeight;
                if (score >= bestScore)
                    continue;

                bestScore = score;
                best = interactable;
            }

            return best;
        }

        bool HasLineOfSight(Vector3 from, Collider target)
        {
            Vector3 to = target.bounds.center;
            Vector3 delta = to - from;
            float distance = delta.magnitude;
            if (distance <= 0.05f)
                return true;

            if (!Physics.Raycast(from, delta / distance, out RaycastHit hit, distance, sightMask, QueryTriggerInteraction.Ignore))
                return true;

            Transform hitTransform = hit.collider.transform;
            Transform targetTransform = target.transform;
            return hitTransform == targetTransform
            || hitTransform.IsChildOf(targetTransform)
            || targetTransform.IsChildOf(hitTransform);
        }

        void SetFocus(IInteractable next)
        {
            if (Same(_focus, next))
                return;

            if (Alive(_focus))
            {
                _focus.OnHoldChanged(this, 0f);
                _focus.OnFocusExit(this);
            }

            _focus = next;
            _hold = 0f;
            _holdSpent = false;
            if (Alive(_focus))
                _focus.OnFocusEnter(this);
        }

        Transform ViewTransform()
        {
            if (view != null)
                return view;
            if (_mainCamera == null)
            {
                Camera main = Camera.main;
                if (main != null)
                    _mainCamera = main.transform;
            }

            return _mainCamera;
        }

        static bool Alive(IInteractable interactable)
        {
            return interactable is Object candidate && candidate != null;
        }

        static bool Same(IInteractable a, IInteractable b)
        {
            if (!Alive(a) || !Alive(b))
                return !Alive(a) && !Alive(b);
            return ReferenceEquals(a, b);
        }

        void OnGUI()
        {
            if (!drawPrompt || Focus == null || string.IsNullOrEmpty(Prompt))
                return;

            const float width = 280f;
            float x = (Screen.width - width) * 0.5f;
            float y = Screen.height - 120f;
            GUI.Box(new Rect(x, y, width, 32f), Prompt);

            if (Focus.HoldDuration <= 0f)
                return;

            float bar = (width - 16f) * HoldProgress;
            GUI.Box(new Rect(x + 8f, y + 36f, bar, 6f), GUIContent.none);
        }

        void OnValidate()
        {
            maxDistance = Mathf.Max(0.05f, maxDistance);
            sphereRadius = Mathf.Max(0f, sphereRadius);
            proximityRadius = Mathf.Max(0.05f, proximityRadius);
            maxViewAngle = Mathf.Clamp(maxViewAngle, 0f, 180f);
            angleWeight = Mathf.Max(0f, angleWeight);
        }
    }
    ```

### Door

The hinge defaults to this transform. **Open Local Euler** is applied on top of the closed local rotation, so a door that is not aligned to the world still swings about its own up axis. The turn uses the same exponential blend as the [damping notes](../../maths/interpolation.md#frame-rate-independent-damping).

```csharp
using UnityEngine;

/// <summary>
/// Swings a transform between a closed pose and an open yaw. Press, not hold.
/// </summary>
[DisallowMultipleComponent]
public class DoorInteractable : MonoBehaviour, IInteractable
{
    [SerializeField] Transform door;
    [SerializeField] Vector3 openLocalEuler = new Vector3(0f, 90f, 0f);
    [SerializeField] float turnSharpness = 6f;
    [SerializeField] string closedPrompt = "Open";
    [SerializeField] string openPrompt = "Close";

    Quaternion _closed = Quaternion.identity;
    Quaternion _opened = Quaternion.identity;
    bool _open;
    bool _hasClosedPose;

    public string Prompt => _open ? openPrompt : closedPrompt;

    public float HoldDuration => 0f;

    public bool CanInteract(Interactor interactor) => isActiveAndEnabled && DoorTransform() != null;

    public void OnFocusEnter(Interactor interactor)
    {
        // Outline.SetFocused(true), on the highlight and outline page.
    }

    public void OnFocusExit(Interactor interactor)
    {
    }

    public void OnHoldChanged(Interactor interactor, float progress)
    {
    }

    public void Interact(Interactor interactor)
    {
        CachePoses();
        _open = !_open;
    }

    void Awake()
    {
        CachePoses();
    }

    void Update()
    {
        Transform hinge = DoorTransform();
        if (hinge == null)
            return;

        Quaternion target = _open ? _opened : _closed;
        float blend = turnSharpness <= 0f ? 1f : 1f - Mathf.Exp(-turnSharpness * Time.deltaTime);
        hinge.localRotation = Quaternion.Slerp(hinge.localRotation, target, blend);
    }

    Transform DoorTransform() => door != null ? door : transform;

    void CachePoses()
    {
        if (_hasClosedPose)
            return;

        Transform hinge = DoorTransform();
        _closed = hinge.localRotation;
        _opened = _closed * Quaternion.Euler(openLocalEuler);
        _hasClosedPose = true;
    }
}
```

### Pickup

`Interact` disables the object. Destroying it inside `Interact` would leave the interactor holding a dead reference for the rest of the frame; disable, and the next query drops the focus.

```csharp
using UnityEngine;

/// <summary>
/// A held interact that disables the object. HoldDuration is the hold, in seconds.
/// </summary>
[DisallowMultipleComponent]
public class PickupInteractable : MonoBehaviour, IInteractable
{
    [SerializeField] string itemName = "Crate";
    [SerializeField] float holdDuration = 0.4f;

    public string Prompt => "Pick up " + itemName;

    public float HoldDuration => Mathf.Max(0f, holdDuration);

    public bool CanInteract(Interactor interactor) => isActiveAndEnabled;

    public void OnFocusEnter(Interactor interactor)
    {
        // Outline.SetFocused(true), on the highlight and outline page.
    }

    public void OnFocusExit(Interactor interactor)
    {
    }

    public void OnHoldChanged(Interactor interactor, float progress)
    {
    }

    public void Interact(Interactor interactor)
    {
        // Disable, rather than Destroy, so the interactor can still send focus-exit.
        gameObject.SetActive(false);
    }
}
```

!!! warning "Common pitfalls"

    Do not add both interactor listings. They declare the same class.

    The camera cast ignores triggers and stops at the first hit. A trigger-only pickup is invisible to **From Camera**; give it a solid collider or use **Proximity**. A wall that is not in **Camera Mask** is also invisible, and the cast then uses whatever is behind it.

    A sphere cast that starts inside a collider does not see that collider. Exclude the player's layer from **Camera Mask**. The proximity overlap skips colliders under the interactor, including the character controller on the same object.

    `OverlapSphereNonAlloc` silently drops colliders once the buffer of 16 is full. That happens when **Interact Mask** contains the floor, the walls, and every prop. Restrict the mask to the interactable layer.

    Line of sight is a ray from the camera. **Sight Mask** has to include the wall and the interactable's solid collider, and it has to exclude the player, or the player's own capsule is the thing "in the way".

    `OnFocusEnter` and `OnFocusExit` are called when the focused instance changes, not every frame. A highlight that lerps belongs in the highlight's own `Update`, started from enter and stopped from exit. The call is `Outline.SetFocused` on the [highlight and outline](../rendering/highlight-outline.md#focus) page.

    `HoldDuration` is read from the target each frame. Changing it on the asset while a hold is in progress changes the bar, because progress is `hold time / duration`.

    The `OnGUI` prompt is a stand-in. It runs in the built-in immediate GUI, ignores the game's UI scale, and should be turned off once a label reads `Prompt` and `HoldProgress`.
