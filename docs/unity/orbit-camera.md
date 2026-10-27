# Third-person orbit camera

A camera that orbits a pivot on the character, zooms with the scroll wheel, and moves closer when a wall is in the way. It is one script, attached to the camera, and it runs in `LateUpdate` so the character has already moved.

Yaw, pitch, and zoom use the [exponential damping](../maths/interpolation.md#frame-rate-independent-damping) step \(1 - e^{-k\Delta t}\). Collision does not. The boom shortens on the frame the sphere hits, and it eases back out only after the hit has cleared, so smoothing cannot carry the camera through a wall. The pivot itself is not damped. Damping the pivot lets the character drift off the point the camera is looking at.

Positive pitch raises the camera and tilts it down toward the pivot. Dragging the mouse up increases pitch. That is the orbit convention, the one used by a character viewer. An aim camera, where dragging up looks up, is the same script with the pitch sign flipped.

## Setup

1. Add the script to the camera. Copy one of the two listings below, not both: they declare the same class.
2. Assign **Target**. **Pivot Offset** is in world space, `(0, 1.5, 0)` by default, so a character that banks does not tilt the pivot with it.
3. Place the camera roughly where it should start. On enable the script reads that pose, and the view does not jump. The distance is then clamped into **Min Distance** and **Max Distance**.
4. Set **Collision Mask** to the environment. The cast also skips colliders on the target and its children, but a mask is the reliable filter. Leave the character’s layer out of the mask.
5. Set the camera’s near clip plane smaller than **Collision Radius** (a radius of `0.2` and a near plane of `0.05` to `0.1` is a workable pair). The sphere, not the near plane, should be what decides that a wall is close.

Hold the right mouse button to orbit. The scroll wheel zooms whether or not the button is held; wheel up moves closer. **Look Sensitivity** on the legacy script is degrees per unit of the Input Manager mouse axis, and that axis is already a per-frame delta, so it is not multiplied by `Time.deltaTime`. The default axis sensitivity of `0.1` means a value of `4` is about `0.4` degrees per pixel. The Input System script takes **Degrees Per Pixel** directly.

**Rotate Sharpness** and **Zoom Sharpness** are the rate \(k\) from the damping page. The half-life is \(\ln 2 / k\) seconds. The defaults (`18` and `10`) have half-lives of about `39 ms` and `69 ms`. Set a sharpness to `0` to snap.

If the character also moves in `LateUpdate`, this script has to run after it. `Time.deltaTime` is the frame time, so a paused game with `timeScale` at `0` holds the camera too. Use `Time.unscaledDeltaTime` if the camera should keep moving while the simulation is paused.

!!! warning "Match the input backend, and keep the character out of the mask"

    Player Settings → Active Input Handling has to include the backend the script reads. The legacy listing uses `UnityEngine.Input` and needs **Input Manager (Old)** or **Both**. The Input System listing needs the Input System package and **Input System Package (New)** or **Both**. Adding the wrong file does not degrade; it fails to compile.

    A sphere cast cannot see a collider it already overlaps, and the nearest hit is useless if that hit is the character. Exclude the character’s layer. The script also ignores colliders under the target, which covers the common case of a capsule on the same object, and it ignores triggers.

## What the collision step is doing

The cast starts at the pivot, pushed forward along the boom by the sphere radius, and travels the rest of the way to the desired camera position. `SphereCast` reports how far the sphere’s centre travelled, so the boom that just touches the surface is `inset + hit.distance`. **Collision Buffer** is subtracted so the sphere does not sit exactly on the contact.

While the cast hits something closer than the requested zoom, the rendered boom becomes that shorter length on the same frame. When the cast is clear again, the boom eases toward the requested zoom instead of popping. Zoom while the view is clear follows the damped zoom directly, with no second smoothing pass.

## Limits

- Nothing is done about a collider the sphere already overlaps at the start of the cast. Keep the pivot out of solid geometry.
- There is no shoulder offset, no soft push, and no recentring when the mouse is released.
- Look and zoom are not suppressed while the pointer is over UI.
- The fallback path allocates if one cast returns as many hits as the buffer can hold. That is rare; the buffer exists so the common frame does not allocate.

## Scripts

The two listings share the orbit, damping, and collision code. Each tab is a complete script. Copy the one that matches the active input backend.

=== "Legacy Input Manager"

    `Input.GetAxis("Mouse X")` and `"Mouse Y"` already include the Input Manager sensitivity and are the movement since the last frame. `Input.mouseScrollDelta.y` is about one unit per notch.

    ```csharp
    using UnityEngine;

    /// <summary>
    /// Orbits a target from the right mouse button, zooms with the scroll wheel,
    /// and pulls the boom in when a sphere cast hits the environment.
    /// </summary>
    /// <remarks>
    /// Legacy Input Manager. Active Input Handling must be
    /// "Input Manager (Old)" or "Both".
    /// </remarks>
    [DisallowMultipleComponent]
    [RequireComponent(typeof(Camera))]
    public class ThirdPersonOrbitCamera : MonoBehaviour
    {
        const int HitBufferSize = 32;
        const float MinimumBoom = 0.05f;

        [Header("Target")]
        [SerializeField] Transform target;

        [Tooltip("World-space offset from the target origin to the orbit pivot.")]
        [SerializeField] Vector3 pivotOffset = new Vector3(0f, 1.5f, 0f);

        [Header("Zoom")]
        [Tooltip("Boom length used when the camera starts on the pivot.")]
        [SerializeField] float distance = 4.5f;
        [SerializeField] float minDistance = 1.1f;
        [SerializeField] float maxDistance = 12f;

        [Tooltip("Metres removed from the boom per scroll-wheel notch. Wheel up zooms in.")]
        [SerializeField] float zoomPerNotch = 0.75f;

        [Header("Orbit")]
        [Tooltip("Degrees per unit of the Mouse X/Y axes. Those axes are already a per-frame delta.")]
        [SerializeField] float lookSensitivity = 4f;
        [SerializeField] float minPitch = -35f;
        [SerializeField] float maxPitch = 70f;

        [Header("Smoothing")]
        [Tooltip("Exponential rate for yaw and pitch. Half-life in seconds is ln(2) / rate.")]
        [SerializeField] float rotateSharpness = 18f;

        [Tooltip("Exponential rate for zoom, and for easing out after a collision.")]
        [SerializeField] float zoomSharpness = 10f;

        [Header("Collision")]
        [SerializeField] float collisionRadius = 0.2f;

        [Tooltip("Gap left between the cast sphere and the surface it hit.")]
        [SerializeField] float collisionBuffer = 0.1f;

        [Tooltip("Geometry that occludes the camera. Exclude the character layer.")]
        [SerializeField] LayerMask collisionMask = ~0;

        float _yaw;
        float _pitch;
        float _distance;
        float _targetYaw;
        float _targetPitch;
        float _targetDistance;
        float _boom;
        bool _recovering;
        bool _warnedMissingTarget;
        RaycastHit[] _hits;

        void Awake()
        {
            _hits = new RaycastHit[HitBufferSize];
        }

        void OnEnable()
        {
            if (_hits == null)
                _hits = new RaycastHit[HitBufferSize];

            CapturePose();
        }

        void LateUpdate()
        {
            if (target == null)
            {
                if (!_warnedMissingTarget)
                {
                    Debug.LogWarning("ThirdPersonOrbitCamera has no target.", this);
                    _warnedMissingTarget = true;
                }

                return;
            }

            ReadInput();

            float dt = Time.deltaTime;
            _yaw = ExpDamp(_yaw, _targetYaw, rotateSharpness, dt);
            _pitch = Mathf.Clamp(
                ExpDamp(_pitch, _targetPitch, rotateSharpness, dt),
                minPitch,
                maxPitch);
            _distance = Mathf.Clamp(
                ExpDamp(_distance, _targetDistance, zoomSharpness, dt),
                minDistance,
                maxDistance);

            Quaternion orbit = Quaternion.Euler(_pitch, _yaw, 0f);
            Vector3 pivot = target.position + pivotOffset;
            float available = CollisionLimit(pivot, orbit, _distance);
            _boom = ApplyCollision(_boom, _distance, available, dt);

            Vector3 position = pivot + orbit * new Vector3(0f, 0f, -_boom);
            transform.SetPositionAndRotation(position, orbit);
        }

        void ReadInput()
        {
            if (Input.GetMouseButton(1))
            {
                _targetYaw += Input.GetAxis("Mouse X") * lookSensitivity;
                // Mouse Y is positive when the cursor moves up, which raises the camera.
                _targetPitch += Input.GetAxis("Mouse Y") * lookSensitivity;
                _targetPitch = Mathf.Clamp(_targetPitch, minPitch, maxPitch);
            }

            float notches = Input.mouseScrollDelta.y;
            if (Mathf.Abs(notches) > 0f)
            {
                _targetDistance = Mathf.Clamp(
                    _targetDistance - notches * zoomPerNotch,
                    minDistance,
                    maxDistance);
            }
        }

        void CapturePose()
        {
            _targetYaw = _yaw = transform.eulerAngles.y;
            float eulerPitch = transform.eulerAngles.x;
            if (eulerPitch > 180f)
                eulerPitch -= 360f;

            // Euler X is positive when the camera looks down. This component's
            // pitch is positive when the camera sits above the pivot.
            _targetPitch = _pitch = Mathf.Clamp(-eulerPitch, minPitch, maxPitch);
            _targetDistance = _distance = Mathf.Clamp(distance, minDistance, maxDistance);
            _boom = _distance;
            _recovering = false;

            if (target == null)
                return;

            Vector3 offset = transform.position - (target.position + pivotOffset);
            float dist = offset.magnitude;
            if (dist < 0.001f)
                return;

            _targetYaw = _yaw = Mathf.Atan2(-offset.x, -offset.z) * Mathf.Rad2Deg;
            float sine = Mathf.Clamp(offset.y / dist, -1f, 1f);
            _targetPitch = _pitch = Mathf.Clamp(Mathf.Asin(sine) * Mathf.Rad2Deg, minPitch, maxPitch);
            _targetDistance = _distance = Mathf.Clamp(dist, minDistance, maxDistance);
            _boom = _distance;
        }

        float ApplyCollision(float boom, float desired, float available, float dt)
        {
            bool blocked = available < desired - 0.001f;
            if (blocked || available < boom)
                boom = available;
            else if (_recovering)
                boom = ExpDamp(boom, desired, zoomSharpness, dt);
            else
                boom = desired;

            _recovering = blocked || (_recovering && boom < desired - 0.001f);
            return boom;
        }

        float CollisionLimit(Vector3 pivot, Quaternion orbit, float desiredDistance)
        {
            Vector3 direction = orbit * Vector3.back;
            float inset = collisionRadius;
            if (desiredDistance <= inset)
                return desiredDistance;

            Vector3 origin = pivot + direction * inset;
            float castLength = desiredDistance - inset;
            int count = Physics.SphereCastNonAlloc(
                origin,
                collisionRadius,
                direction,
                _hits,
                castLength,
                collisionMask,
                QueryTriggerInteraction.Ignore);

            float nearest = NearestAllowed(_hits, count);
            if (count == _hits.Length)
            {
                RaycastHit[] all = Physics.SphereCastAll(
                    origin,
                    collisionRadius,
                    direction,
                    castLength,
                    collisionMask,
                    QueryTriggerInteraction.Ignore);
                nearest = NearestAllowed(all, all.Length);
            }

            if (float.IsPositiveInfinity(nearest))
                return desiredDistance;

            float allowed = inset + nearest - collisionBuffer;
            return Mathf.Clamp(allowed, MinimumBoom, desiredDistance);
        }

        float NearestAllowed(RaycastHit[] hits, int count)
        {
            float nearest = float.PositiveInfinity;
            for (int i = 0; i < count; i++)
            {
                Transform hitTransform = hits[i].transform;
                // IsChildOf is true for the transform itself.
                if (hitTransform != null && hitTransform.IsChildOf(target))
                    continue;

                if (hits[i].distance < nearest)
                    nearest = hits[i].distance;
            }

            return nearest;
        }

        static float ExpDamp(float current, float target, float sharpness, float dt)
        {
            if (sharpness <= 0f || dt <= 0f)
                return target;

            float weight = 1f - Mathf.Exp(-sharpness * dt);
            return Mathf.Lerp(current, target, weight);
        }

        void OnValidate()
        {
            minPitch = Mathf.Clamp(minPitch, -89f, 89f);
            maxPitch = Mathf.Clamp(maxPitch, minPitch, 89f);
            minDistance = Mathf.Max(MinimumBoom, minDistance);
            maxDistance = Mathf.Max(minDistance, maxDistance);
            distance = Mathf.Clamp(distance, minDistance, maxDistance);
            collisionRadius = Mathf.Max(0.01f, collisionRadius);
            collisionBuffer = Mathf.Max(0f, collisionBuffer);
            zoomPerNotch = Mathf.Max(0f, zoomPerNotch);
        }
    }
    ```

=== "Input System"

    `Mouse.current.delta` is in pixels. `Mouse.current.scroll` keeps the platform’s own scale unless the project sets **Edit → Project Settings → Input System Package → Scroll Delta Behavior** to **Uniform Across All Platforms**. With the default, one Windows notch is `120`, the Win32 `WHEEL_DELTA`. **Scroll Units Per Notch** is that divisor; set it to `1` if the project has switched to the uniform range. The script reads `Mouse.current` so it does not need an actions asset. A shipped game should bind an Input Action instead, so the binding can be rebound.

    ```csharp
    using UnityEngine;
    using UnityEngine.InputSystem;

    /// <summary>
    /// Orbits a target from the right mouse button, zooms with the scroll wheel,
    /// and pulls the boom in when a sphere cast hits the environment.
    /// </summary>
    /// <remarks>
    /// New Input System. Requires the Input System package, and Active Input
    /// Handling set to "Input System Package (New)" or "Both".
    /// Reads Mouse.current directly so the sample does not need an actions asset.
    /// A shipped game should bind an Input Action instead, so the binding can be rebound.
    /// </remarks>
    [DisallowMultipleComponent]
    [RequireComponent(typeof(Camera))]
    public class ThirdPersonOrbitCamera : MonoBehaviour
    {
        const int HitBufferSize = 32;
        const float MinimumBoom = 0.05f;

        [Header("Target")]
        [SerializeField] Transform target;

        [Tooltip("World-space offset from the target origin to the orbit pivot.")]
        [SerializeField] Vector3 pivotOffset = new Vector3(0f, 1.5f, 0f);

        [Header("Zoom")]
        [Tooltip("Boom length used when the camera starts on the pivot.")]
        [SerializeField] float distance = 4.5f;
        [SerializeField] float minDistance = 1.1f;
        [SerializeField] float maxDistance = 12f;

        [Tooltip("Metres removed from the boom per scroll-wheel notch. Wheel up zooms in.")]
        [SerializeField] float zoomPerNotch = 0.75f;

        [Tooltip("Mouse.scroll units in one notch. 120 is the default Windows range.")]
        [SerializeField] float scrollUnitsPerNotch = 120f;

        [Header("Orbit")]
        [Tooltip("Degrees of orbit per pixel of mouse movement. Not scaled by frame time.")]
        [SerializeField] float degreesPerPixel = 0.2f;
        [SerializeField] float minPitch = -35f;
        [SerializeField] float maxPitch = 70f;

        [Header("Smoothing")]
        [Tooltip("Exponential rate for yaw and pitch. Half-life in seconds is ln(2) / rate.")]
        [SerializeField] float rotateSharpness = 18f;

        [Tooltip("Exponential rate for zoom, and for easing out after a collision.")]
        [SerializeField] float zoomSharpness = 10f;

        [Header("Collision")]
        [SerializeField] float collisionRadius = 0.2f;

        [Tooltip("Gap left between the cast sphere and the surface it hit.")]
        [SerializeField] float collisionBuffer = 0.1f;

        [Tooltip("Geometry that occludes the camera. Exclude the character layer.")]
        [SerializeField] LayerMask collisionMask = ~0;

        float _yaw;
        float _pitch;
        float _distance;
        float _targetYaw;
        float _targetPitch;
        float _targetDistance;
        float _boom;
        bool _recovering;
        bool _warnedMissingTarget;
        RaycastHit[] _hits;

        void Awake()
        {
            _hits = new RaycastHit[HitBufferSize];
        }

        void OnEnable()
        {
            if (_hits == null)
                _hits = new RaycastHit[HitBufferSize];

            CapturePose();
        }

        void LateUpdate()
        {
            if (target == null)
            {
                if (!_warnedMissingTarget)
                {
                    Debug.LogWarning("ThirdPersonOrbitCamera has no target.", this);
                    _warnedMissingTarget = true;
                }

                return;
            }

            ReadInput();

            float dt = Time.deltaTime;
            _yaw = ExpDamp(_yaw, _targetYaw, rotateSharpness, dt);
            _pitch = Mathf.Clamp(
                ExpDamp(_pitch, _targetPitch, rotateSharpness, dt),
                minPitch,
                maxPitch);
            _distance = Mathf.Clamp(
                ExpDamp(_distance, _targetDistance, zoomSharpness, dt),
                minDistance,
                maxDistance);

            Quaternion orbit = Quaternion.Euler(_pitch, _yaw, 0f);
            Vector3 pivot = target.position + pivotOffset;
            float available = CollisionLimit(pivot, orbit, _distance);
            _boom = ApplyCollision(_boom, _distance, available, dt);

            Vector3 position = pivot + orbit * new Vector3(0f, 0f, -_boom);
            transform.SetPositionAndRotation(position, orbit);
        }

        void ReadInput()
        {
            Mouse mouse = Mouse.current;
            if (mouse == null)
                return;

            if (mouse.rightButton.isPressed)
            {
                Vector2 delta = mouse.delta.ReadValue();
                _targetYaw += delta.x * degreesPerPixel;
                // Delta Y is positive when the cursor moves up, which raises the camera.
                _targetPitch += delta.y * degreesPerPixel;
                _targetPitch = Mathf.Clamp(_targetPitch, minPitch, maxPitch);
            }

            float units = scrollUnitsPerNotch > 0f ? scrollUnitsPerNotch : 1f;
            float notches = mouse.scroll.ReadValue().y / units;
            if (Mathf.Abs(notches) > 0f)
            {
                _targetDistance = Mathf.Clamp(
                    _targetDistance - notches * zoomPerNotch,
                    minDistance,
                    maxDistance);
            }
        }

        void CapturePose()
        {
            _targetYaw = _yaw = transform.eulerAngles.y;
            float eulerPitch = transform.eulerAngles.x;
            if (eulerPitch > 180f)
                eulerPitch -= 360f;

            // Euler X is positive when the camera looks down. This component's
            // pitch is positive when the camera sits above the pivot.
            _targetPitch = _pitch = Mathf.Clamp(-eulerPitch, minPitch, maxPitch);
            _targetDistance = _distance = Mathf.Clamp(distance, minDistance, maxDistance);
            _boom = _distance;
            _recovering = false;

            if (target == null)
                return;

            Vector3 offset = transform.position - (target.position + pivotOffset);
            float dist = offset.magnitude;
            if (dist < 0.001f)
                return;

            _targetYaw = _yaw = Mathf.Atan2(-offset.x, -offset.z) * Mathf.Rad2Deg;
            float sine = Mathf.Clamp(offset.y / dist, -1f, 1f);
            _targetPitch = _pitch = Mathf.Clamp(Mathf.Asin(sine) * Mathf.Rad2Deg, minPitch, maxPitch);
            _targetDistance = _distance = Mathf.Clamp(dist, minDistance, maxDistance);
            _boom = _distance;
        }

        float ApplyCollision(float boom, float desired, float available, float dt)
        {
            bool blocked = available < desired - 0.001f;
            if (blocked || available < boom)
                boom = available;
            else if (_recovering)
                boom = ExpDamp(boom, desired, zoomSharpness, dt);
            else
                boom = desired;

            _recovering = blocked || (_recovering && boom < desired - 0.001f);
            return boom;
        }

        float CollisionLimit(Vector3 pivot, Quaternion orbit, float desiredDistance)
        {
            Vector3 direction = orbit * Vector3.back;
            float inset = collisionRadius;
            if (desiredDistance <= inset)
                return desiredDistance;

            Vector3 origin = pivot + direction * inset;
            float castLength = desiredDistance - inset;
            int count = Physics.SphereCastNonAlloc(
                origin,
                collisionRadius,
                direction,
                _hits,
                castLength,
                collisionMask,
                QueryTriggerInteraction.Ignore);

            float nearest = NearestAllowed(_hits, count);
            if (count == _hits.Length)
            {
                RaycastHit[] all = Physics.SphereCastAll(
                    origin,
                    collisionRadius,
                    direction,
                    castLength,
                    collisionMask,
                    QueryTriggerInteraction.Ignore);
                nearest = NearestAllowed(all, all.Length);
            }

            if (float.IsPositiveInfinity(nearest))
                return desiredDistance;

            float allowed = inset + nearest - collisionBuffer;
            return Mathf.Clamp(allowed, MinimumBoom, desiredDistance);
        }

        float NearestAllowed(RaycastHit[] hits, int count)
        {
            float nearest = float.PositiveInfinity;
            for (int i = 0; i < count; i++)
            {
                Transform hitTransform = hits[i].transform;
                // IsChildOf is true for the transform itself.
                if (hitTransform != null && hitTransform.IsChildOf(target))
                    continue;

                if (hits[i].distance < nearest)
                    nearest = hits[i].distance;
            }

            return nearest;
        }

        static float ExpDamp(float current, float target, float sharpness, float dt)
        {
            if (sharpness <= 0f || dt <= 0f)
                return target;

            float weight = 1f - Mathf.Exp(-sharpness * dt);
            return Mathf.Lerp(current, target, weight);
        }

        void OnValidate()
        {
            minPitch = Mathf.Clamp(minPitch, -89f, 89f);
            maxPitch = Mathf.Clamp(maxPitch, minPitch, 89f);
            minDistance = Mathf.Max(MinimumBoom, minDistance);
            maxDistance = Mathf.Max(minDistance, maxDistance);
            distance = Mathf.Clamp(distance, minDistance, maxDistance);
            collisionRadius = Mathf.Max(0.01f, collisionRadius);
            collisionBuffer = Mathf.Max(0f, collisionBuffer);
            zoomPerNotch = Mathf.Max(0f, zoomPerNotch);
            degreesPerPixel = Mathf.Max(0f, degreesPerPixel);
            scrollUnitsPerNotch = Mathf.Max(0.01f, scrollUnitsPerNotch);
        }
    }
    ```
