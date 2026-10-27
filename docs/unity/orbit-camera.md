---
engine: Unity
version: 6+
package: Cinemachine 3.x
---

# Third-person orbit camera

A camera that orbits a pivot on the character, zooms with the scroll wheel, and moves closer when a wall is in the way. Two implementations are on this page.

The [plain script](#plain-script) is one component on the Unity camera. It runs in `LateUpdate` so the character has already moved. The [Cinemachine 3](#cinemachine-3) section builds the same orbit from the package, and adds a short script only for mouse look and the scroll wheel. Cinemachine 3 lives in `Unity.Cinemachine`. It is not the 2.x API: `CinemachineVirtualCamera`, `CinemachineFreeLook`, and `CinemachineCollider` are the old types.

## Plain script

Yaw, pitch, and zoom use the [exponential damping](../maths/interpolation.md#frame-rate-independent-damping) step \(1 - e^{-k\Delta t}\). Collision does not. The boom shortens on the frame the sphere hits, and it eases back out only after the hit has cleared, so smoothing cannot carry the camera through a wall. The pivot itself is not damped. Damping the pivot lets the character drift off the point the camera is looking at.

Positive pitch raises the camera and tilts it down toward the pivot. Dragging the mouse up increases pitch. That is the orbit convention, the one used by a character viewer. An aim camera, where dragging up looks up, is the same script with the pitch sign flipped.

### Setup

1. Add the script to the camera. Copy one of the two listings below, not both: they declare the same class. A new Unity 6 project uses the Input System, so that is the listing to copy. The legacy listing is only for a project whose Active Input Handling is still the Input Manager.
2. Assign **Target**. **Pivot Offset** is in world space, `(0, 1.5, 0)` by default, so a character that banks does not tilt the pivot with it.
3. Place the camera roughly where it should start. On enable the script reads that pose, and the view does not jump. The distance is then clamped into **Min Distance** and **Max Distance**.
4. Set **Collision Mask** to the environment. The cast also skips colliders on the target and its children, but a mask is the reliable filter. Leave the character’s layer out of the mask.
5. Set the camera’s near clip plane smaller than **Collision Radius** (a radius of `0.2` and a near plane of `0.05` to `0.1` is a workable pair). The sphere, not the near plane, should be what decides that a wall is close.

Hold the right mouse button to orbit. The scroll wheel zooms whether or not the button is held; wheel up moves closer. The Input System script takes **Degrees Per Pixel** and does not multiply by `Time.deltaTime`, because the mouse delta is already this frame's movement. On the legacy script, **Look Sensitivity** is degrees per unit of the Input Manager mouse axis. That axis is also a per-frame delta. The default axis sensitivity of `0.1` means a value of `4` is about `0.4` degrees per pixel.

**Rotate Sharpness** and **Zoom Sharpness** are the rate \(k\) from the damping page. The half-life is \(\ln 2 / k\) seconds. The defaults (`18` and `10`) have half-lives of about `39 ms` and `69 ms`. Set a sharpness to `0` to snap.

If the character also moves in `LateUpdate`, this script has to run after it. `Time.deltaTime` is the frame time, so a paused game with `timeScale` at `0` holds the camera too. Use `Time.unscaledDeltaTime` if the camera should keep moving while the simulation is paused.

!!! warning "Match the input backend, and keep the character out of the mask"

    A new Unity 6 project defaults to the Input System. That listing needs the Input System package and **Input System Package (New)** or **Both**. The legacy listing uses `UnityEngine.Input` and needs **Input Manager (Old)** or **Both**. Adding the wrong file does not degrade; it fails to compile.

    A sphere cast cannot see a collider it already overlaps, and the nearest hit is useless if that hit is the character. Exclude the character’s layer. The script also ignores colliders under the target, which covers the common case of a capsule on the same object, and it ignores triggers.

### What the collision step is doing

The cast starts at the pivot, pushed forward along the boom by the sphere radius, and travels the rest of the way to the desired camera position. `SphereCast` reports how far the sphere’s centre travelled, so the boom that just touches the surface is `inset + hit.distance`. **Collision Buffer** is subtracted so the sphere does not sit exactly on the contact.

While the cast hits something closer than the requested zoom, the rendered boom becomes that shorter length on the same frame. When the cast is clear again, the boom eases toward the requested zoom instead of popping. Zoom while the view is clear follows the damped zoom directly, with no second smoothing pass.

### Limits

- Nothing is done about a collider the sphere already overlaps at the start of the cast. Keep the pivot out of solid geometry.
- There is no shoulder offset, no soft push, and no recentring when the mouse is released.
- Look and zoom are not suppressed while the pointer is over UI.
- The fallback path allocates if one cast returns as many hits as the buffer can hold. That is rare; the buffer exists so the common frame does not allocate.

### Scripts

The two listings share the orbit, damping, and collision code. Each tab is a complete script. The Input System tab is first because that is the default backend in a new Unity 6 project. Copy one of them, not both.

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
    /// Input System, the default backend in a new Unity 6 project.
    /// Requires the Input System package, and Active Input Handling set to
    /// "Input System Package (New)" or "Both".
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

## Cinemachine 3

The same orbit, built from the package instead of a bespoke camera script. Install **Cinemachine** 3.1.x (`com.unity.cinemachine`) from the Package Manager. Do not install 2.x. The namespace is `Unity.Cinemachine`, and the components below do not exist under the old names.

This variant does not replace the Unity camera. A `CinemachineBrain` on the camera copies the live `CinemachineCamera` onto it. The plain script and this rig should not both be driving that camera.

### Setup

1. On the Unity camera, add a **Cinemachine Brain** if adding a Cinemachine Camera did not add one for you. Leave **Update Method** on **Smart Update** and **Blend Update Method** on **Late Update**, so the rig runs after the character has moved. **Fixed Update** judders against a controller that moves in `Update`.
2. Create an empty child on the character called `CameraPivot`, at about `(0, 1.5, 0)`. The orbit and the aim both use this transform, so the camera looks at the chest rather than the feet.
3. Add a **Cinemachine Camera** (GameObject → Cinemachine → Cinemachine Camera). Leave it unparented. Set **Tracking Target** to `CameraPivot`. Leave the separate Look At target off, so aim uses the same pivot.
4. Set **Position Control** to **Orbital Follow**. That adds `CinemachineOrbitalFollow`.
5. Set **Rotation Control** to **Rotation Composer**. That adds `CinemachineRotationComposer`.
6. **Add Extension → Deoccluder**. That adds `CinemachineDeoccluder`.
7. Add `OrbitalFollowInput` from the listing below to the Cinemachine Camera, next to the orbital follow. It is the scroll-wheel and right-drag driver. A **Cinemachine Input Axis Controller** can drive the same three axes from input actions instead; use that or this script, not both.

### Settings that matter

| Component | Setting | Value |
| --- | --- | --- |
| Orbital Follow | Binding Mode | **World Space**, so the character's yaw does not swing the camera. |
| Orbital Follow | Target Offset | `(0, 0, 0)`. The pivot child already holds the height. |
| Orbital Follow | Orbit Style | **Sphere**. |
| Orbital Follow | Radius | `4.5`. This is the distance when Orbit Scale is `1`. |
| Orbital Follow | Position Damping | `0`. Damping here lags the pivot, which lets the character drift off the point the camera is looking at. |
| Orbital Follow | Horizontal Axis | Default `-180` to `180`, wrapped. Recentering stays off. |
| Orbital Follow | Vertical Axis | The pitch limits, in degrees. The default is `-10` to `45` with the value at `17.5`, which starts slightly above the pivot. Widen it toward `-35` to `70` to match the plain script. Positive raises the camera. |
| Orbital Follow | Radial Axis | **Range** `(0.25, 2.5)`, **Value** `1`. The default range is `1` to `1`, and a zoom written into that range is clamped away. Value is a multiplier on Radius, not the distance. |
| Rotation Composer | Damping | Low, or zero if the aim should stick to the pivot the way the plain script does. The composer only rotates; it does not move the camera. |
| Deoccluder | Collide Against | Environment layers. Leave the character out. |
| Deoccluder | Ignore Tag | The character's tag. |
| Deoccluder | Minimum Distance From Target | About `0.5`, so the pivot's own overlap is not an obstacle. |
| Deoccluder | Strategy | **Pull Camera Forward**. This shortens the boom, which is what the plain script does. |
| Deoccluder | Camera Radius | `0.2`, and keep the Unity camera's near clip smaller than that. |
| Deoccluder | Damping When Occluded | `0`, so a wall cuts the boom on the frame it is hit. **Damping** is only the ease back out. |

Hold the right mouse button to orbit. The scroll wheel zooms whether or not the button is held; wheel up moves closer. `CinemachineOrbitalFollow` places the camera with `Quaternion.Euler(vertical, horizontal, 0)` times `(0, 0, -Radius * scale)`, which is the same placement as the plain script.

### Script

Each tab is a complete script. Copy one. The Input System tab is first because that is the default backend in a new Unity 6 project. The script writes the three `InputAxis` values in `Update`, before the brain's late update reads them. `InputAxis` is a struct, so the axis is copied, changed, and assigned back.

=== "Input System"

    `Mouse.current.delta` is in pixels and is not multiplied by `Time.deltaTime`. `Mouse.current.scroll` keeps the platform's own scale unless **Scroll Delta Behavior** is **Uniform Across All Platforms**. One Windows notch is `120`.

    ```csharp
    using UnityEngine;
    using UnityEngine.InputSystem;
    using Unity.Cinemachine;

    /// <summary>
    /// Drives a Cinemachine 3 orbital follow from the mouse.
    /// Right-drag yaws and pitches. The scroll wheel changes Orbit Scale.
    /// </summary>
    /// <remarks>
    /// Input System, the default backend in a new Unity 6 project.
    /// Requires Cinemachine 3.x. Do not also add a Cinemachine Input Axis
    /// Controller on this object: both would write the orbital axes.
    /// </remarks>
    [DisallowMultipleComponent]
    [RequireComponent(typeof(CinemachineOrbitalFollow))]
    public class OrbitalFollowInput : MonoBehaviour
    {
        [Tooltip("Degrees added per pixel of mouse delta. The delta is already this frame's movement.")]
        [SerializeField] float degreesPerPixel = 0.2f;

        [Tooltip("Platform units that make one notch. 120 is the default Windows WHEEL_DELTA.")]
        [SerializeField] float scrollUnitsPerNotch = 120f;

        [Tooltip("How much Orbit Scale changes per scroll-wheel notch. Wheel up zooms in.")]
        [SerializeField] float zoomPerNotch = 0.15f;

        [Tooltip("Orbit Scale at the near and far ends. Used only when Radial Axis is still the default 1 to 1 range.")]
        [SerializeField] float minScale = 0.25f;
        [SerializeField] float maxScale = 2.5f;

        CinemachineOrbitalFollow _orbit;

        void Awake()
        {
            _orbit = GetComponent<CinemachineOrbitalFollow>();
            EnsureRadialRange();
        }

        void ReadInput(out Vector2 lookDegrees, out float notches)
        {
            lookDegrees = Vector2.zero;
            notches = 0f;

            Mouse mouse = Mouse.current;
            if (mouse == null)
                return;

            float units = scrollUnitsPerNotch > 0f ? scrollUnitsPerNotch : 1f;
            notches = mouse.scroll.ReadValue().y / units;
            if (!mouse.rightButton.isPressed)
                return;

            Vector2 delta = mouse.delta.ReadValue();
            lookDegrees = delta * degreesPerPixel;
        }

        void Update()
        {
            ReadInput(out Vector2 lookDegrees, out float notches);

            if (lookDegrees.sqrMagnitude > 0.0001f)
            {
                InputAxis yaw = _orbit.HorizontalAxis;
                yaw.Value = yaw.ClampValue(yaw.Value + lookDegrees.x);
                yaw.CancelRecentering();
                _orbit.HorizontalAxis = yaw;

                // Positive vertical axis raises the camera. Mouse up is positive.
                InputAxis pitch = _orbit.VerticalAxis;
                pitch.Value = pitch.ClampValue(pitch.Value + lookDegrees.y);
                pitch.CancelRecentering();
                _orbit.VerticalAxis = pitch;
            }

            if (Mathf.Abs(notches) > 0f)
            {
                InputAxis radial = _orbit.RadialAxis;
                radial.Value = radial.ClampValue(radial.Value - notches * zoomPerNotch);
                radial.CancelRecentering();
                _orbit.RadialAxis = radial;
            }
        }

        void EnsureRadialRange()
        {
            InputAxis radial = _orbit.RadialAxis;
            if (radial.Range.y - radial.Range.x >= 0.01f)
                return;

            float near = Mathf.Max(0.01f, minScale);
            float far = Mathf.Max(near, maxScale);
            radial.Range = new Vector2(near, far);
            radial.Center = Mathf.Clamp(radial.Center, near, far);
            radial.Value = Mathf.Clamp(radial.Value <= 0f ? 1f : radial.Value, near, far);
            _orbit.RadialAxis = radial;
        }

        void OnValidate()
        {
            degreesPerPixel = Mathf.Max(0f, degreesPerPixel);
            zoomPerNotch = Mathf.Max(0f, zoomPerNotch);
            scrollUnitsPerNotch = Mathf.Max(0.01f, scrollUnitsPerNotch);
            minScale = Mathf.Max(0.01f, minScale);
            maxScale = Mathf.Max(minScale, maxScale);
        }
    }
    ```

=== "Legacy Input Manager"

    `Input.GetAxis("Mouse X")` and `"Mouse Y"` are already this frame's movement. `Input.mouseScrollDelta.y` is about one unit per notch, so this listing has no notch divisor.

    ```csharp
    using UnityEngine;
    using Unity.Cinemachine;

    /// <summary>
    /// Drives a Cinemachine 3 orbital follow from the mouse.
    /// Right-drag yaws and pitches. The scroll wheel changes Orbit Scale.
    /// </summary>
    /// <remarks>
    /// Legacy Input Manager. Active Input Handling must be
    /// "Input Manager (Old)" or "Both". Requires Cinemachine 3.x.
    /// Do not also add a Cinemachine Input Axis Controller on this object.
    /// </remarks>
    [DisallowMultipleComponent]
    [RequireComponent(typeof(CinemachineOrbitalFollow))]
    public class OrbitalFollowInput : MonoBehaviour
    {
        [Tooltip("Degrees per unit of the Mouse X/Y axes. Those axes are already a per-frame delta.")]
        [SerializeField] float lookSensitivity = 4f;

        [Tooltip("How much Orbit Scale changes per scroll-wheel notch. Wheel up zooms in.")]
        [SerializeField] float zoomPerNotch = 0.15f;

        [Tooltip("Orbit Scale at the near and far ends. Used only when Radial Axis is still the default 1 to 1 range.")]
        [SerializeField] float minScale = 0.25f;
        [SerializeField] float maxScale = 2.5f;

        CinemachineOrbitalFollow _orbit;

        void Awake()
        {
            _orbit = GetComponent<CinemachineOrbitalFollow>();
            EnsureRadialRange();
        }

        void ReadInput(out Vector2 lookDegrees, out float notches)
        {
            lookDegrees = Vector2.zero;
            // mouseScrollDelta.y is about one unit per notch.
            notches = Input.mouseScrollDelta.y;
            if (!Input.GetMouseButton(1))
                return;

            lookDegrees.x = Input.GetAxis("Mouse X") * lookSensitivity;
            lookDegrees.y = Input.GetAxis("Mouse Y") * lookSensitivity;
        }

        void Update()
        {
            ReadInput(out Vector2 lookDegrees, out float notches);

            if (lookDegrees.sqrMagnitude > 0.0001f)
            {
                InputAxis yaw = _orbit.HorizontalAxis;
                yaw.Value = yaw.ClampValue(yaw.Value + lookDegrees.x);
                yaw.CancelRecentering();
                _orbit.HorizontalAxis = yaw;

                // Positive vertical axis raises the camera. Mouse up is positive.
                InputAxis pitch = _orbit.VerticalAxis;
                pitch.Value = pitch.ClampValue(pitch.Value + lookDegrees.y);
                pitch.CancelRecentering();
                _orbit.VerticalAxis = pitch;
            }

            if (Mathf.Abs(notches) > 0f)
            {
                InputAxis radial = _orbit.RadialAxis;
                radial.Value = radial.ClampValue(radial.Value - notches * zoomPerNotch);
                radial.CancelRecentering();
                _orbit.RadialAxis = radial;
            }
        }

        void EnsureRadialRange()
        {
            InputAxis radial = _orbit.RadialAxis;
            if (radial.Range.y - radial.Range.x >= 0.01f)
                return;

            float near = Mathf.Max(0.01f, minScale);
            float far = Mathf.Max(near, maxScale);
            radial.Range = new Vector2(near, far);
            radial.Center = Mathf.Clamp(radial.Center, near, far);
            radial.Value = Mathf.Clamp(radial.Value <= 0f ? 1f : radial.Value, near, far);
            _orbit.RadialAxis = radial;
        }

        void OnValidate()
        {
            lookSensitivity = Mathf.Max(0f, lookSensitivity);
            zoomPerNotch = Mathf.Max(0f, zoomPerNotch);
            minScale = Mathf.Max(0.01f, minScale);
            maxScale = Mathf.Max(minScale, maxScale);
        }
    }
    ```

!!! warning "Cinemachine 3, and one writer for the axes"

    A project still on Cinemachine 2.x will not compile this script. `using Cinemachine` and `CinemachineVirtualCamera` are the old API. The package to install is `com.unity.cinemachine` 3.1.x, and the namespace is `Unity.Cinemachine`.

    `CinemachineInputAxisController` and `OrbitalFollowInput` both write Look Orbit X, Look Orbit Y, and Orbit Scale. Keep one of them. The controller is the right choice when the game already has input actions; this script is the choice when it should behave like the plain camera without an actions asset.

    Radial Axis does nothing while its range is the default `1` to `1`. Set the range in the inspector, or leave it and let the script open the range from **Min Scale** and **Max Scale** on the first run.

    Deoccluder cannot see a collider it starts inside, and the character is the usual culprit. The same exclusion as the plain script applies: take the character's layer out of **Collide Against**, and set **Ignore Tag**.
