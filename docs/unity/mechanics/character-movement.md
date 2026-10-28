---
engine: Unity
version: 6+
---

# Character movement

Walk, run, and jump on a `CharacterController`, usable whether the camera is first person or third person. Movement is relative to the camera's yaw. The body can turn to face the move, or a parented camera can own the yaw and the mesh can turn on its own.

Which body to use is on the [controllers](controllers/index.md) index. This page is the kinematic capsule. The physics capsule is [Rigidbody movement](rigidbody-movement.md). Classifying idle, move, jump, and fall, without taking `Move` away from this script, is the [state machine](../architecture/state-machines.md).

`Move` takes a displacement for this frame and is called from `Update`. This is not a Rigidbody controller, so the Unity 6 rename of `Rigidbody.velocity` to `linearVelocity` does not apply. `CharacterController.velocity` is unchanged, and this script does not read it.

Turning uses the [exponential blend](../../maths/interpolation.md#frame-rate-independent-damping) from the maths notes. A matching third-person view is the [orbit camera](../orbit-camera.md).

## Setup

1. On an upright object, add a **Character Controller**. The default capsule is height `2`, radius `0.5`, centre `(0, 1, 0)`, so the feet sit on the transform. Leave **Step Offset** below the height (the default `0.3` is inside a height of `2`) and **Slope Limit** at `45` unless the level needs another limit.
2. Add this component. Do not add a second collider, and do not add a Rigidbody.
3. Assign **View** to the camera that defines forward, or leave it empty to use `Camera.main`. Only the camera's yaw is used.
4. Copy the Input System listing. A new Unity 6 project uses that backend. The legacy listing is the same movement for a project still on the Input Manager. The two files declare the same class, so add one of them.
5. Put floors on layers included in **Ground Mask**. Exclude the character's layer when the model has colliders of its own.
6. For a third-person body that should face the move, leave **Rotate Towards Move** on and keep the camera off this object. The orbit camera already works that way: its pivot is in the world, not a child. For a first-person camera parented here, turn **Rotate Towards Move** off, or point **Facing Root** at a child mesh so the camera does not yaw with the body.

## What each step is doing

Each `Update` does the following.

1. Read move, jump, and run. A jump press is remembered for **Jump Buffer Time** seconds, so a press that lands slightly early still fires.
2. Sweep a sphere the size of the capsule's base down from the centre, so a slope is measured where the capsule touches it. The hit is walkable when its slope is within **Slope Limit**. It counts as ground only when the gap is within the skin width plus `5 cm`, measured along the surface normal. While vertical speed is upward the cast is skipped, so the ground just left cannot cancel the jump.
3. On that ground, coyote time is refilled and a small downward speed keeps the capsule seated, which is what lets the controller catch steps. In the air, coyote time counts down.
4. Jump when the buffer and the coyote timer are both still live. Take-off speed is \(\sqrt{h \cdot -2g}\) for a jump height \(h\) and gravity \(g\), which is the speed that peaks at \(h\) under constant gravity. The jump spends both timers, so coyote time is not a second jump.
5. In the air, including the frame of a jump, gravity changes the vertical speed, clamped to **Max Fall Speed**. The vertical move is the average of the speed before and after, times the frame time. That is exact under constant gravity, so the peak is **Jump Height** at any frame rate. Moving by the end speed alone lands a few centimetres off, by a different amount at each frame rate. The [integrators](../../physics/integrators.md#constant-acceleration-exactly) page has the numbers.
6. Build a wish direction from the camera. Flatten the camera forward onto the ground plane, and take right as \(\mathrm{up} \times \mathrm{forward}\), which is Unity's left-handed cross product. Clamp the input to length `1` so a diagonal is not faster than a cardinal, drop anything inside the dead zone, then scale the rest of the range so a full push is still full speed. A partial stick scales the speed. Run selects **Run Speed**.
7. On walkable ground, project that horizontal velocity onto the surface and restore its length. The stride stays the same on a slope instead of shrinking by the cosine.
8. `Move` by `horizontal * dt` plus that vertical step. A ceiling contact while rising zeroes the upward speed.
9. If this frame was not a jump and the body is still just above walkable ground, within **Snap Distance**, move down the remaining gap and treat the frame as grounded. That is a step down. A real ledge is deeper than the snap, the cast misses, and the coyote window runs instead.
10. If **Rotate Towards Move** is set, yaw **Facing Root** toward the horizontal wish. The blend is \(1 - e^{-kt}\) with \(k\) = **Turn Sharpness**. Zero snaps.

A short jump and a held jump are the same height. Cutting the upward speed when the button is released is a separate tweak and is not in this script.

## Parameters

| Field | Default | Effect |
| --- | --- | --- |
| Walk Speed | `4.5` | Metres per second at a full stick, walking. |
| Run Speed | `7.5` | Metres per second while the run button is held. |
| Gravity | `-25` | Metres per second squared. Must stay negative. |
| Jump Height | `1.4` | Peak height in metres. Sets the take-off speed. |
| Max Fall Speed | `-40` | Clamp on the downward speed. |
| Stick To Ground | `2` | Downward speed used while grounded, so the capsule stays seated. |
| Ground Check Distance | `0.2` | Extra metres below the capsule the ground cast may travel. |
| Snap Distance | `0.4` | Drops at least this shallow are stepped down rather than fallen. |
| Ground Mask | Everything | Layers the ground cast hits. Exclude the character. |
| Coyote Time | `0.12` | Seconds after leaving the ground in which a jump is still accepted. |
| Jump Buffer Time | `0.12` | Seconds a jump press is remembered before landing. |
| View | Empty | Yaw reference. Empty follows `Camera.main`. |
| Facing Root | Empty | Transform that yaws toward the move. Empty uses this object. |
| Rotate Towards Move | On | Turn **Facing Root** to the wish direction. |
| Turn Sharpness | `12` | Exponential turn rate. Half-life about `58 ms`. |
| Input Deadzone | `0.15` | Input shorter than this does not move. |

## Scripts

The two listings share the movement code. Each tab is a complete script. The Input System tab is first because that is the default backend in a new Unity 6 project. Copy one of them, not both.

=== "Input System"

    The keyboard is WASD, Space, and Left Shift. A gamepad, when one is connected, uses the left stick, the south face button, and the left shoulder. If both are present, the larger move vector wins, so a resting stick does not cancel the keys. Device reads are already this frame's state and are not multiplied by `Time.deltaTime`.

    ```csharp
    using UnityEngine;
    using UnityEngine.InputSystem;


    /// <summary>
    /// Camera-relative walk, run, and jump on a CharacterController.
    /// </summary>
    /// <remarks>
    /// Input System, the default backend in a new Unity 6 project.
    /// Requires the Input System package, and Active Input Handling set to
    /// "Input System Package (New)" or "Both". Reads devices directly so
    /// the sample does not need an actions asset.
    /// </remarks>
    [DisallowMultipleComponent]
    [RequireComponent(typeof(CharacterController))]
    public class CharacterMovement : MonoBehaviour
    {
        void ReadInput(out Vector2 move, out bool jumpPressed, out bool run)
        {
            move = Vector2.zero;
            jumpPressed = false;
            run = false;

            Keyboard keyboard = Keyboard.current;
            if (keyboard != null)
            {
                if (keyboard.dKey.isPressed) move.x += 1f;
                if (keyboard.aKey.isPressed) move.x -= 1f;
                if (keyboard.wKey.isPressed) move.y += 1f;
                if (keyboard.sKey.isPressed) move.y -= 1f;
                jumpPressed |= keyboard.spaceKey.wasPressedThisFrame;
                run |= keyboard.leftShiftKey.isPressed;
            }

            Gamepad gamepad = Gamepad.current;
            if (gamepad != null)
            {
                Vector2 stick = gamepad.leftStick.ReadValue();
                if (stick.sqrMagnitude > move.sqrMagnitude)
                    move = stick;
                jumpPressed |= gamepad.buttonSouth.wasPressedThisFrame;
                run |= gamepad.leftShoulder.isPressed;
            }
        }

        [Header("Motion")]
        [SerializeField] float walkSpeed = 4.5f;
        [SerializeField] float runSpeed = 7.5f;

        [Tooltip("Metres per second squared. Keep this negative.")]
        [SerializeField] float gravity = -25f;

        [Tooltip("Peak height of a jump, in metres, reached with the gravity above.")]
        [SerializeField] float jumpHeight = 1.4f;

        [Tooltip("Most negative vertical speed, in metres per second.")]
        [SerializeField] float maxFallSpeed = -40f;

        [Tooltip("Downward speed applied while grounded so steps and slopes stay in contact.")]
        [SerializeField] float stickToGround = 2f;

        [Header("Ground")]
        [Tooltip("Extra reach below the capsule when testing for ground.")]
        [SerializeField] float groundCheckDistance = 0.2f;

        [Tooltip("A drop no deeper than this, in metres, is stepped down instead of becoming a fall.")]
        [SerializeField] float snapDistance = 0.4f;

        [Tooltip("Surfaces the ground cast may land on. Exclude the character.")]
        [SerializeField] LayerMask groundMask = ~0;

        [Header("Jump feel")]
        [Tooltip("Seconds after leaving the ground during which a jump is still accepted.")]
        [SerializeField] float coyoteTime = 0.12f;

        [Tooltip("Seconds a jump press is remembered while the body is still in the air.")]
        [SerializeField] float jumpBufferTime = 0.12f;

        [Header("Facing")]
        [Tooltip("Camera the movement is relative to. Empty uses Camera.main.")]
        [SerializeField] Transform view;

        [Tooltip("Yawed toward the move. Assign a child mesh if a camera is parented to this object.")]
        [SerializeField] Transform facingRoot;

        [SerializeField] bool rotateTowardsMove = true;

        [Tooltip("Exponential rate for turning. Half-life in seconds is ln(2) / rate. Zero snaps.")]
        [SerializeField] float turnSharpness = 12f;

        [Tooltip("Stick or key magnitude below this is dropped, then the remainder is scaled back to full.")]
        [SerializeField] float inputDeadzone = 0.15f;

        const float GroundedSlack = 0.05f;

        CharacterController _controller;
        Transform _mainCamera;
        Vector3 _groundNormal = Vector3.up;
        float _verticalSpeed;
        float _coyote;
        float _jumpBuffer;
        bool _grounded;

        void Awake()
        {
            _controller = GetComponent<CharacterController>();
            if (facingRoot == null)
                facingRoot = transform;
        }

        void Update()
        {
            float dt = Time.deltaTime;
            ReadInput(out Vector2 move, out bool jumpPressed, out bool run);

            if (jumpPressed)
                _jumpBuffer = jumpBufferTime;
            else
                _jumpBuffer -= dt;

            ProbeGround();

            if (_grounded)
            {
                _coyote = coyoteTime;
                _verticalSpeed = -stickToGround;
            }
            else
            {
                _coyote -= dt;
            }

            bool jumped = TryJump();

            // Move by the average of the start and end speed. Under constant gravity that is
            // exact, so the jump peaks at Jump Height at any frame rate.
            float startSpeed = _verticalSpeed;
            if (!_grounded)
                _verticalSpeed = Mathf.Max(_verticalSpeed + gravity * dt, maxFallSpeed);
            float verticalStep = 0.5f * (startSpeed + _verticalSpeed) * dt;

            Vector3 wish = WishDirection(move, out float magnitude);
            float speed = (run ? runSpeed : walkSpeed) * magnitude;
            Vector3 horizontal = wish * speed;

            if (_grounded && horizontal.sqrMagnitude > 0.0001f)
            {
                Vector3 along = Vector3.ProjectOnPlane(horizontal, _groundNormal);
                if (along.sqrMagnitude > 0.0001f)
                    horizontal = along.normalized * speed;
            }

            Vector3 displacement = horizontal * dt + Vector3.up * verticalStep;
            CollisionFlags flags = _controller.Move(displacement);
            if ((flags & CollisionFlags.Above) != 0 && _verticalSpeed > 0f)
                _verticalSpeed = 0f;

            if (!jumped && !_grounded && SnapToGround())
            {
                _grounded = true;
                _coyote = coyoteTime;
                if (_verticalSpeed < 0f)
                    _verticalSpeed = -stickToGround;
            }

            if (rotateTowardsMove)
                Face(wish, dt);
        }

        bool TryJump()
        {
            if (_jumpBuffer <= 0f || _coyote <= 0f || gravity >= 0f)
                return false;

            _verticalSpeed = Mathf.Sqrt(jumpHeight * -2f * gravity);
            _jumpBuffer = 0f;
            _coyote = 0f;
            _grounded = false;
            return true;
        }

        void ProbeGround()
        {
            _grounded = false;
            _groundNormal = Vector3.up;

            // Rising frames ignore the ground just left, so the jump is not cancelled.
            if (_verticalSpeed > 0.05f)
                return;

            if (!TryWalkableHit(groundCheckDistance, out RaycastHit hit, out float gap))
                return;

            // The skin is kept along the normal, so its vertical size grows on a slope.
            _groundNormal = hit.normal;
            _grounded = gap <= (_controller.skinWidth + GroundedSlack) / Mathf.Max(0.1f, hit.normal.y);
        }

        bool SnapToGround()
        {
            if (_verticalSpeed > 0f)
                return false;
            if (!TryWalkableHit(snapDistance, out RaycastHit hit, out float gap))
                return false;

            if (gap > snapDistance)
                return false;
            if (gap > 0.001f)
                _controller.Move(Vector3.down * gap);

            _groundNormal = hit.normal;
            return true;
        }

        // Sweeps the capsule's bottom sphere down. A ray from the centre would measure a slope
        // under the centre, not where the capsule touches it, and miss ground on ramps over ~23°.
        bool TryWalkableHit(float extraReach, out RaycastHit hit, out float gap)
        {
            float radius = _controller.radius;
            float toBottomSphere = Mathf.Max(0f, _controller.height * 0.5f - radius);
            Vector3 origin = transform.TransformPoint(_controller.center);
            float reach = toBottomSphere + Mathf.Max(0f, extraReach);

            gap = 0f;
            if (!Physics.SphereCast(origin, radius, Vector3.down, out hit, reach, groundMask, QueryTriggerInteraction.Ignore))
                return false;

            gap = hit.distance - toBottomSphere;
            return Vector3.Angle(hit.normal, Vector3.up) <= _controller.slopeLimit + 0.01f;
        }

        Vector3 WishDirection(Vector2 move, out float magnitude)
        {
            magnitude = move.magnitude;
            if (magnitude > 1f)
                magnitude = 1f;
            if (magnitude < inputDeadzone || inputDeadzone >= 1f)
            {
                magnitude = 0f;
                return Vector3.zero;
            }

            magnitude = (magnitude - inputDeadzone) / (1f - inputDeadzone);
            Vector2 direction = move.normalized;
            Vector3 forward = PlanarForward();
            Vector3 right = Vector3.Cross(Vector3.up, forward);
            return right * direction.x + forward * direction.y;
        }

        Vector3 PlanarForward()
        {
            Transform eyes = ViewTransform();
            if (eyes == null)
                return Vector3.forward;

            Vector3 forward = Vector3.ProjectOnPlane(eyes.forward, Vector3.up);
            if (forward.sqrMagnitude < 0.0001f)
                forward = Vector3.ProjectOnPlane(eyes.up, Vector3.up);
            if (forward.sqrMagnitude < 0.0001f)
                return Vector3.forward;
            return forward.normalized;
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

        void Face(Vector3 wish, float dt)
        {
            if (facingRoot == null)
                return;

            Vector3 flat = wish;
            flat.y = 0f;
            if (flat.sqrMagnitude < 0.0001f)
                return;

            Quaternion target = Quaternion.LookRotation(flat.normalized, Vector3.up);
            float blend = turnSharpness <= 0f || dt <= 0f ? 1f : 1f - Mathf.Exp(-turnSharpness * dt);
            facingRoot.rotation = Quaternion.Slerp(facingRoot.rotation, target, blend);
        }

        void OnValidate()
        {
            walkSpeed = Mathf.Max(0f, walkSpeed);
            runSpeed = Mathf.Max(walkSpeed, runSpeed);
            jumpHeight = Mathf.Max(0f, jumpHeight);
            if (gravity >= 0f)
                gravity = gravity == 0f ? -25f : -Mathf.Abs(gravity);
            if (maxFallSpeed >= 0f)
                maxFallSpeed = maxFallSpeed == 0f ? -40f : -Mathf.Abs(maxFallSpeed);
            stickToGround = Mathf.Max(0f, stickToGround);
            groundCheckDistance = Mathf.Max(0.02f, groundCheckDistance);
            snapDistance = Mathf.Max(groundCheckDistance, snapDistance);
            coyoteTime = Mathf.Max(0f, coyoteTime);
            jumpBufferTime = Mathf.Max(0f, jumpBufferTime);
            turnSharpness = Mathf.Max(0f, turnSharpness);
            inputDeadzone = Mathf.Clamp(inputDeadzone, 0f, 0.9f);
        }
    }
    ```

=== "Legacy Input Manager"

    `GetAxisRaw("Horizontal")` and `"Vertical"` are the default axes with no smoothing, and they are already this frame's value, so they are not multiplied by `Time.deltaTime`. `GetButtonDown("Jump")` is the default Jump button. Run is Left Shift via `GetKey`, because the Input Manager has no default run axis.

    ```csharp
    using UnityEngine;


    /// <summary>
    /// Camera-relative walk, run, and jump on a CharacterController.
    /// </summary>
    /// <remarks>
    /// Legacy Input Manager. Active Input Handling must be
    /// "Input Manager (Old)" or "Both". Uses the default Horizontal,
    /// Vertical, and Jump axes. Run is Left Shift and is not an axis.
    /// </remarks>
    [DisallowMultipleComponent]
    [RequireComponent(typeof(CharacterController))]
    public class CharacterMovement : MonoBehaviour
    {
        void ReadInput(out Vector2 move, out bool jumpPressed, out bool run)
        {
            move.x = Input.GetAxisRaw("Horizontal");
            move.y = Input.GetAxisRaw("Vertical");
            jumpPressed = Input.GetButtonDown("Jump");
            run = Input.GetKey(KeyCode.LeftShift);
        }

        [Header("Motion")]
        [SerializeField] float walkSpeed = 4.5f;
        [SerializeField] float runSpeed = 7.5f;

        [Tooltip("Metres per second squared. Keep this negative.")]
        [SerializeField] float gravity = -25f;

        [Tooltip("Peak height of a jump, in metres, reached with the gravity above.")]
        [SerializeField] float jumpHeight = 1.4f;

        [Tooltip("Most negative vertical speed, in metres per second.")]
        [SerializeField] float maxFallSpeed = -40f;

        [Tooltip("Downward speed applied while grounded so steps and slopes stay in contact.")]
        [SerializeField] float stickToGround = 2f;

        [Header("Ground")]
        [Tooltip("Extra reach below the capsule when testing for ground.")]
        [SerializeField] float groundCheckDistance = 0.2f;

        [Tooltip("A drop no deeper than this, in metres, is stepped down instead of becoming a fall.")]
        [SerializeField] float snapDistance = 0.4f;

        [Tooltip("Surfaces the ground cast may land on. Exclude the character.")]
        [SerializeField] LayerMask groundMask = ~0;

        [Header("Jump feel")]
        [Tooltip("Seconds after leaving the ground during which a jump is still accepted.")]
        [SerializeField] float coyoteTime = 0.12f;

        [Tooltip("Seconds a jump press is remembered while the body is still in the air.")]
        [SerializeField] float jumpBufferTime = 0.12f;

        [Header("Facing")]
        [Tooltip("Camera the movement is relative to. Empty uses Camera.main.")]
        [SerializeField] Transform view;

        [Tooltip("Yawed toward the move. Assign a child mesh if a camera is parented to this object.")]
        [SerializeField] Transform facingRoot;

        [SerializeField] bool rotateTowardsMove = true;

        [Tooltip("Exponential rate for turning. Half-life in seconds is ln(2) / rate. Zero snaps.")]
        [SerializeField] float turnSharpness = 12f;

        [Tooltip("Stick or key magnitude below this is dropped, then the remainder is scaled back to full.")]
        [SerializeField] float inputDeadzone = 0.15f;

        const float GroundedSlack = 0.05f;

        CharacterController _controller;
        Transform _mainCamera;
        Vector3 _groundNormal = Vector3.up;
        float _verticalSpeed;
        float _coyote;
        float _jumpBuffer;
        bool _grounded;

        void Awake()
        {
            _controller = GetComponent<CharacterController>();
            if (facingRoot == null)
                facingRoot = transform;
        }

        void Update()
        {
            float dt = Time.deltaTime;
            ReadInput(out Vector2 move, out bool jumpPressed, out bool run);

            if (jumpPressed)
                _jumpBuffer = jumpBufferTime;
            else
                _jumpBuffer -= dt;

            ProbeGround();

            if (_grounded)
            {
                _coyote = coyoteTime;
                _verticalSpeed = -stickToGround;
            }
            else
            {
                _coyote -= dt;
            }

            bool jumped = TryJump();

            // Move by the average of the start and end speed. Under constant gravity that is
            // exact, so the jump peaks at Jump Height at any frame rate.
            float startSpeed = _verticalSpeed;
            if (!_grounded)
                _verticalSpeed = Mathf.Max(_verticalSpeed + gravity * dt, maxFallSpeed);
            float verticalStep = 0.5f * (startSpeed + _verticalSpeed) * dt;

            Vector3 wish = WishDirection(move, out float magnitude);
            float speed = (run ? runSpeed : walkSpeed) * magnitude;
            Vector3 horizontal = wish * speed;

            if (_grounded && horizontal.sqrMagnitude > 0.0001f)
            {
                Vector3 along = Vector3.ProjectOnPlane(horizontal, _groundNormal);
                if (along.sqrMagnitude > 0.0001f)
                    horizontal = along.normalized * speed;
            }

            Vector3 displacement = horizontal * dt + Vector3.up * verticalStep;
            CollisionFlags flags = _controller.Move(displacement);
            if ((flags & CollisionFlags.Above) != 0 && _verticalSpeed > 0f)
                _verticalSpeed = 0f;

            if (!jumped && !_grounded && SnapToGround())
            {
                _grounded = true;
                _coyote = coyoteTime;
                if (_verticalSpeed < 0f)
                    _verticalSpeed = -stickToGround;
            }

            if (rotateTowardsMove)
                Face(wish, dt);
        }

        bool TryJump()
        {
            if (_jumpBuffer <= 0f || _coyote <= 0f || gravity >= 0f)
                return false;

            _verticalSpeed = Mathf.Sqrt(jumpHeight * -2f * gravity);
            _jumpBuffer = 0f;
            _coyote = 0f;
            _grounded = false;
            return true;
        }

        void ProbeGround()
        {
            _grounded = false;
            _groundNormal = Vector3.up;

            // Rising frames ignore the ground just left, so the jump is not cancelled.
            if (_verticalSpeed > 0.05f)
                return;

            if (!TryWalkableHit(groundCheckDistance, out RaycastHit hit, out float gap))
                return;

            // The skin is kept along the normal, so its vertical size grows on a slope.
            _groundNormal = hit.normal;
            _grounded = gap <= (_controller.skinWidth + GroundedSlack) / Mathf.Max(0.1f, hit.normal.y);
        }

        bool SnapToGround()
        {
            if (_verticalSpeed > 0f)
                return false;
            if (!TryWalkableHit(snapDistance, out RaycastHit hit, out float gap))
                return false;

            if (gap > snapDistance)
                return false;
            if (gap > 0.001f)
                _controller.Move(Vector3.down * gap);

            _groundNormal = hit.normal;
            return true;
        }

        // Sweeps the capsule's bottom sphere down. A ray from the centre would measure a slope
        // under the centre, not where the capsule touches it, and miss ground on ramps over ~23°.
        bool TryWalkableHit(float extraReach, out RaycastHit hit, out float gap)
        {
            float radius = _controller.radius;
            float toBottomSphere = Mathf.Max(0f, _controller.height * 0.5f - radius);
            Vector3 origin = transform.TransformPoint(_controller.center);
            float reach = toBottomSphere + Mathf.Max(0f, extraReach);

            gap = 0f;
            if (!Physics.SphereCast(origin, radius, Vector3.down, out hit, reach, groundMask, QueryTriggerInteraction.Ignore))
                return false;

            gap = hit.distance - toBottomSphere;
            return Vector3.Angle(hit.normal, Vector3.up) <= _controller.slopeLimit + 0.01f;
        }

        Vector3 WishDirection(Vector2 move, out float magnitude)
        {
            magnitude = move.magnitude;
            if (magnitude > 1f)
                magnitude = 1f;
            if (magnitude < inputDeadzone || inputDeadzone >= 1f)
            {
                magnitude = 0f;
                return Vector3.zero;
            }

            magnitude = (magnitude - inputDeadzone) / (1f - inputDeadzone);
            Vector2 direction = move.normalized;
            Vector3 forward = PlanarForward();
            Vector3 right = Vector3.Cross(Vector3.up, forward);
            return right * direction.x + forward * direction.y;
        }

        Vector3 PlanarForward()
        {
            Transform eyes = ViewTransform();
            if (eyes == null)
                return Vector3.forward;

            Vector3 forward = Vector3.ProjectOnPlane(eyes.forward, Vector3.up);
            if (forward.sqrMagnitude < 0.0001f)
                forward = Vector3.ProjectOnPlane(eyes.up, Vector3.up);
            if (forward.sqrMagnitude < 0.0001f)
                return Vector3.forward;
            return forward.normalized;
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

        void Face(Vector3 wish, float dt)
        {
            if (facingRoot == null)
                return;

            Vector3 flat = wish;
            flat.y = 0f;
            if (flat.sqrMagnitude < 0.0001f)
                return;

            Quaternion target = Quaternion.LookRotation(flat.normalized, Vector3.up);
            float blend = turnSharpness <= 0f || dt <= 0f ? 1f : 1f - Mathf.Exp(-turnSharpness * dt);
            facingRoot.rotation = Quaternion.Slerp(facingRoot.rotation, target, blend);
        }

        void OnValidate()
        {
            walkSpeed = Mathf.Max(0f, walkSpeed);
            runSpeed = Mathf.Max(walkSpeed, runSpeed);
            jumpHeight = Mathf.Max(0f, jumpHeight);
            if (gravity >= 0f)
                gravity = gravity == 0f ? -25f : -Mathf.Abs(gravity);
            if (maxFallSpeed >= 0f)
                maxFallSpeed = maxFallSpeed == 0f ? -40f : -Mathf.Abs(maxFallSpeed);
            stickToGround = Mathf.Max(0f, stickToGround);
            groundCheckDistance = Mathf.Max(0.02f, groundCheckDistance);
            snapDistance = Mathf.Max(groundCheckDistance, snapDistance);
            coyoteTime = Mathf.Max(0f, coyoteTime);
            jumpBufferTime = Mathf.Max(0f, jumpBufferTime);
            turnSharpness = Mathf.Max(0f, turnSharpness);
            inputDeadzone = Mathf.Clamp(inputDeadzone, 0f, 0.9f);
        }
    }
    ```

!!! warning "Common pitfalls"

    Do not add another collider or a Rigidbody beside the Character Controller. A second collider fights the capsule, and `Move` is not a physics step. On a Rigidbody elsewhere in Unity 6 the speed property is `linearVelocity`. `velocity` and `drag` are the obsolete names (`linearDamping` replaces drag).

    `CharacterController.isGrounded` becomes true only after `Move` has already touched something below. It is a frame late and it says nothing about the slope. This script casts for ground instead, and it does not treat `isGrounded` as the sensor.

    Call `Move` from `Update`. `FixedUpdate` runs on the physics clock and drops or repeats frames against a controller that expects one displacement per rendered frame.

    **Step Offset** has to stay below the capsule height. Equal or larger, and the controller fails to move.

    **Ground Mask** has to exclude the character when the model has colliders. The sweep starts inside the capsule, and a cast ignores a collider it starts inside, but it will hit a child collider and treat the body as the floor.

    Gravity has to stay negative. A positive value accelerates the body upward for every airborne frame. `OnValidate` replaces a positive value with its negation.

    A camera parented to a root that also yaws will spin, and the wish direction spins with it. Leave the camera unparented, or turn **Rotate Towards Move** off and yaw a child mesh.

    The ground test is one sphere sweep. Standing over a ledge, the sweep lands on the lip, so the body counts as grounded with a tilted normal until it slides off. Do not replace the sweep with a ray through the centre: on any ramp steeper than about 23°, that ray reads the ground as further away than the skin, and the body flickers between grounded and falling.
