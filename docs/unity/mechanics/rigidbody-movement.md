---
engine: Unity
version: 6+
---

# Rigidbody movement

Walk, run, and jump on a dynamic `Rigidbody`, relative to the camera's yaw. The capsule pushes other rigidbodies. Input is read in `Update` and the velocity is written in `FixedUpdate`, which is the physics step.

Unity 6 names the speed `linearVelocity` and the drag `linearDamping`. `velocity` and `drag` are obsolete. This script sets `linearDamping` to zero and slows down in code, so the acceleration numbers are the ones that actually happen.

Which body to use is on the [controllers](controllers/index.md) index. The kinematic version is [character movement](character-movement.md). The same idle, move, jump, and fall names, read from `linearVelocity`, are on the [state machine](../architecture/state-machines.md) page. Coyote time and jump buffering are the same idea as on the character page. Turning uses the [exponential blend](../../maths/interpolation.md#frame-rate-independent-damping). A matching camera is the [orbit camera](../orbit-camera.md).

## Setup

1. On an upright object, add a **Capsule Collider** (height `2`, radius `0.5`, centre `(0, 1, 0)`) and a **Rigidbody**. Leave **Is Kinematic** off. The script turns **Use Gravity** off, sets **Linear Damping** to `0`, sets **Collision Detection** to Continuous, and freezes rotation on X and Z.
2. Add this component. Do not add a Character Controller.
3. Put floors, slopes, and ceilings on layers included in **Ground Mask**. Exclude the character's layer.
4. Assign **View** to the camera that defines forward, or leave it empty to use `Camera.main`. Only the camera's yaw is used.
5. Copy the Input System listing. A new Unity 6 project uses that backend. The legacy listing is the same movement for a project still on the Input Manager. The two files declare the same class, so add one of them.
6. For a body that should face the move, leave **Rotate Towards Move** on and keep the camera off this object. A camera parented here will yaw with the body. For a first-person view, turn it off and use the [first-person camera](../cameras/first-person.md).

The collider's physics material is replaced in `Awake` with zero friction, zero bounce, and **Minimum** combine. A floor material set to **Maximum** would otherwise win the combine and stick the capsule to walls. Create the asset yourself only if you want to share it; the script does not require one.

## What each step is doing

`Update` stores the move, the run button, and the time of a jump press. `wasPressedThisFrame` is only true for one rendered frame, and `FixedUpdate` may not run on that frame, so the press is kept until **Jump Buffer** seconds have passed. `Time.time` during `FixedUpdate` is the physics clock. The timestamp is still comparable, and a press waits at most one physics step.

Each `FixedUpdate` does the following.

1. Sphere-cast down from the bottom of the capsule, with a radius slightly inside the capsule so the cast does not start inside the floor. A hit is ground when its slope is within **Slope Limit**. If the previous step was in the air and `linearVelocity.y` is upward, the cast is skipped, so the ground just left cannot cancel a jump. A body that was grounded keeps probing while it rises, because walking up a ramp rises too: at walking speed on a 30° ramp that is over 2 m/s upward.
2. On that ground, the coyote clock is refilled. In the air it simply ages. A jump is taken when the buffer has not expired and the coyote clock is still inside **Coyote Time**. Take-off speed is \(\sqrt{h \cdot -2g}\) for a jump height \(h\) and \(g\) equal to `Physics.gravity.y` times **Gravity Multiplier**, less half a step of gravity. The body moves a whole physics step at the take-off speed before gravity acts, and without that correction the peak is about 7 cm high at 50 Hz. Both clocks are spent, so coyote time is not a second jump.
3. Build a wish direction from the camera, the same way as the kinematic controller: flatten the camera forward, take right as \(\mathrm{up} \times \mathrm{forward}\), clamp the stick, and drop the dead zone. Run selects **Run Speed**.
4. Move the horizontal velocity toward that wish. On the ground the rate is **Acceleration**, or **Deceleration** when the stick is idle. In the air the rate is **Acceleration** times **Air Control**, and an idle stick does not slow the body down.
5. On walkable ground, project that horizontal velocity onto the surface and restore its length, then add a small speed into the surface so the capsule stays seated. Standing still on a slope does not slide. A slope steeper than the limit is not ground: the horizontal velocity into that wall is removed, and gravity carries the body. The zero-friction material is what stops the solver from grabbing the wall as well.
6. In the air, add `Physics.gravity * Gravity Multiplier * dt` to the vertical speed and clamp it to **Max Fall Speed**. **Use Gravity** is off because this script replaces `linearVelocity` every step. Leaving it on would apply gravity a second time, after the write.
7. A short cast upward zeroes a rising speed when the ceiling is in the way.
8. If **Rotate Towards Move** is set, `MoveRotation` yaws toward the wish. `MoveRotation` is interpolated. Writing `transform.rotation` is not.

## Parameters

| Field | Default | Effect |
| --- | --- | --- |
| Walk Speed | `4.5` | Metres per second at a full stick, walking. |
| Run Speed | `7.5` | Metres per second while the run button is held. |
| Acceleration | `40` | Metres per second squared toward the wish, on the ground. |
| Deceleration | `55` | Metres per second squared toward a stop, on the ground, with no input. |
| Air Control | `0.4` | Fraction of **Acceleration** applied in the air. `0` keeps the take-off momentum. |
| Jump Height | `1.4` | Peak height in metres, under the gravity below. |
| Gravity Multiplier | `2` | Scales `Physics.gravity` while airborne, and the jump speed that matches **Jump Height**. |
| Max Fall Speed | `-30` | Clamp on the downward speed, in metres per second. |
| Stick To Ground | `2` | Speed into the ground normal while grounded, so slopes stay in contact. |
| Slope Limit | `45` | Degrees. Steeper hits are walls, not ground. |
| Ground Check Distance | `0.2` | Extra metres below the feet the sphere cast may travel. |
| Ground Mask | Everything | Layers the casts hit. Exclude the character. |
| Coyote Time | `0.12` | Seconds after leaving the ground in which a jump is still accepted. |
| Jump Buffer | `0.12` | Seconds a jump press is remembered. |
| View | Empty | Yaw reference. Empty follows `Camera.main`. |
| Rotate Towards Move | On | Yaw the body toward the wish. |
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
    /// Camera-relative walk, run, and jump on a dynamic Rigidbody.
    /// </summary>
    /// <remarks>
    /// Input System, the default backend in a new Unity 6 project.
    /// Requires the Input System package, and Active Input Handling set to
    /// "Input System Package (New)" or "Both". Reads devices directly so
    /// the sample does not need an actions asset.
    /// Unity 6: linearVelocity and linearDamping. velocity and drag are obsolete.
    /// </remarks>
    [DisallowMultipleComponent]
    [RequireComponent(typeof(Rigidbody))]
    [RequireComponent(typeof(CapsuleCollider))]
    public class RigidbodyMovement : MonoBehaviour
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
        [SerializeField] float acceleration = 40f;
        [SerializeField] float deceleration = 55f;

        [Tooltip("Fraction of Acceleration used in the air. Zero keeps take-off momentum.")]
        [SerializeField] float airControl = 0.4f;

        [Tooltip("Peak height of a jump, in metres, under Physics.gravity times Gravity Multiplier.")]
        [SerializeField] float jumpHeight = 1.4f;

        [Tooltip("Scales Physics.gravity while airborne. One is the project gravity.")]
        [SerializeField] float gravityMultiplier = 2f;

        [Tooltip("Most negative vertical speed, in metres per second.")]
        [SerializeField] float maxFallSpeed = -30f;

        [Tooltip("Speed into the ground normal while grounded, so the capsule stays seated.")]
        [SerializeField] float stickToGround = 2f;

        [Header("Ground")]
        [SerializeField] float slopeLimit = 45f;
        [SerializeField] float groundCheckDistance = 0.2f;
        [SerializeField] LayerMask groundMask = ~0;

        [Header("Jump feel")]
        [SerializeField] float coyoteTime = 0.12f;
        [SerializeField] float jumpBuffer = 0.12f;

        [Header("Facing")]
        [Tooltip("Camera the movement is relative to. Empty uses Camera.main.")]
        [SerializeField] Transform view;

        [SerializeField] bool rotateTowardsMove = true;

        [Tooltip("Exponential rate for turning. Half-life in seconds is ln(2) / rate. Zero snaps.")]
        [SerializeField] float turnSharpness = 12f;

        [SerializeField] float inputDeadzone = 0.15f;

        Rigidbody _body;
        CapsuleCollider _capsule;
        Transform _mainCamera;
        Vector2 _move;
        bool _run;
        float _jumpUntil;
        float _lastGrounded = -10f;
        Vector3 _groundNormal = Vector3.up;
        bool _grounded;

        void Awake()
        {
            _body = GetComponent<Rigidbody>();
            _capsule = GetComponent<CapsuleCollider>();

            _body.useGravity = false;
            _body.linearDamping = 0f;
            _body.angularDamping = 0.05f;
            _body.interpolation = RigidbodyInterpolation.Interpolate;
            _body.collisionDetectionMode = CollisionDetectionMode.Continuous;
            _body.constraints = RigidbodyConstraints.FreezeRotationX | RigidbodyConstraints.FreezeRotationZ;
            _body.maxDepenetrationVelocity = 8f;

            PhysicsMaterial material = new PhysicsMaterial("Character Zero Friction")
            {
                dynamicFriction = 0f,
                staticFriction = 0f,
                bounciness = 0f,
                frictionCombine = PhysicsMaterialCombine.Minimum,
                bounceCombine = PhysicsMaterialCombine.Minimum
            };
            _capsule.material = material;
        }

        void Update()
        {
            ReadInput(out _move, out bool jumpPressed, out _run);
            if (jumpPressed)
                _jumpUntil = Time.time + jumpBuffer;
        }

        void FixedUpdate()
        {
            float dt = Time.fixedDeltaTime;
            Vector3 velocity = _body.linearVelocity;
            ProbeGround(velocity.y);

            if (_grounded)
                _lastGrounded = Time.time;

            Vector3 wish = WishDirection(_move, out float magnitude);
            float speed = (_run ? runSpeed : walkSpeed) * magnitude;
            Vector3 horizontal = new Vector3(velocity.x, 0f, velocity.z);
            float rate = Rate(magnitude);
            Vector3 nextPlanar = Vector3.MoveTowards(horizontal, wish * speed, rate * dt);

            if (!_grounded)
                SlideAgainstSteep(ref nextPlanar);

            Vector3 final = Compose(nextPlanar, velocity.y, dt);
            bool jumped = TryJump(ref final);

            if (!jumped && final.y > 0f && HitCeiling())
                final.y = 0f;

            _body.linearVelocity = final;

            if (rotateTowardsMove)
                Face(wish, dt);
        }

        float Rate(float magnitude)
        {
            if (_grounded)
                return magnitude > 0f ? acceleration : deceleration;
            return magnitude > 0f ? acceleration * airControl : 0f;
        }

        Vector3 Compose(Vector3 nextPlanar, float vertical, float dt)
        {
            if (_grounded)
            {
                Vector3 along = Vector3.ProjectOnPlane(nextPlanar, _groundNormal);
                Vector3 final = along.sqrMagnitude > 0.0001f
                    ? along.normalized * nextPlanar.magnitude
                    : Vector3.zero;
                return final - _groundNormal * stickToGround;
            }

            vertical += Physics.gravity.y * gravityMultiplier * dt;
            if (vertical < maxFallSpeed)
                vertical = maxFallSpeed;
            return new Vector3(nextPlanar.x, vertical, nextPlanar.z);
        }

        bool TryJump(ref Vector3 final)
        {
            bool buffered = Time.time <= _jumpUntil;
            bool coyote = Time.time - _lastGrounded <= coyoteTime;
            float gravity = Physics.gravity.y * gravityMultiplier;
            if (!buffered || !coyote || gravity >= 0f)
                return false;

            // The body moves one whole step at this speed before gravity acts. Taking off
            // half a step of gravity puts every step on the true arc, so the peak is Jump Height.
            float speed = Mathf.Sqrt(jumpHeight * -2f * gravity) + 0.5f * gravity * Time.fixedDeltaTime;
            final = new Vector3(final.x, speed, final.z);
            _jumpUntil = float.NegativeInfinity;
            _lastGrounded = Time.time - coyoteTime;
            _grounded = false;
            return true;
        }

        void ProbeGround(float verticalSpeed)
        {
            bool wasGrounded = _grounded;
            _grounded = false;
            _groundNormal = Vector3.up;

            // Rising after a jump ignores the ground just left, so the jump is not cancelled.
            // A grounded body walking uphill also rises, and has to keep probing.
            if (!wasGrounded && verticalSpeed > 0.05f)
                return;

            if (!TryCast(Vector3.down, Bottom(), groundCheckDistance, out RaycastHit hit))
                return;

            if (Vector3.Angle(hit.normal, Vector3.up) > slopeLimit)
                return;

            _groundNormal = hit.normal;
            _grounded = true;
        }

        void SlideAgainstSteep(ref Vector3 horizontal)
        {
            if (!TryCast(Vector3.down, Bottom(), groundCheckDistance, out RaycastHit hit))
                return;
            if (Vector3.Angle(hit.normal, Vector3.up) <= slopeLimit)
                return;

            Vector3 wall = Vector3.ProjectOnPlane(hit.normal, Vector3.up);
            if (wall.sqrMagnitude < 0.0001f)
                return;

            wall.Normalize();
            float into = Vector3.Dot(horizontal, wall);
            if (into < 0f)
                horizontal -= wall * into;
        }

        bool HitCeiling()
        {
            Vector3 centre = transform.TransformPoint(_capsule.center);
            float half = _capsule.height * 0.5f;
            Vector3 top = centre + Vector3.up * Mathf.Max(half - _capsule.radius, 0f);
            return TryCast(Vector3.up, top, 0.08f, out _);
        }

        bool TryCast(Vector3 direction, Vector3 origin, float extra, out RaycastHit hit)
        {
            // Start a little back from the surface and use a smaller radius, so a
            // capsule that is resting on the floor does not begin the cast inside it.
            float inset = 0.05f;
            float radius = Mathf.Max(0.05f, _capsule.radius - inset);
            Vector3 start = origin - direction * inset;
            return Physics.SphereCast(start, radius, direction, out hit, extra + inset * 2f, groundMask, QueryTriggerInteraction.Ignore);
        }

        Vector3 Bottom()
        {
            Vector3 centre = transform.TransformPoint(_capsule.center);
            float half = _capsule.height * 0.5f;
            float offset = Mathf.Max(half - _capsule.radius, 0f);
            return centre - Vector3.up * offset;
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
            Vector3 flat = wish;
            flat.y = 0f;
            if (flat.sqrMagnitude < 0.0001f)
                return;

            Quaternion target = Quaternion.LookRotation(flat.normalized, Vector3.up);
            float blend = turnSharpness <= 0f || dt <= 0f ? 1f : 1f - Mathf.Exp(-turnSharpness * dt);
            _body.MoveRotation(Quaternion.Slerp(_body.rotation, target, blend));
        }

        void OnValidate()
        {
            walkSpeed = Mathf.Max(0f, walkSpeed);
            runSpeed = Mathf.Max(walkSpeed, runSpeed);
            acceleration = Mathf.Max(0f, acceleration);
            deceleration = Mathf.Max(0f, deceleration);
            airControl = Mathf.Clamp01(airControl);
            jumpHeight = Mathf.Max(0f, jumpHeight);
            gravityMultiplier = Mathf.Max(0.01f, gravityMultiplier);
            if (maxFallSpeed >= 0f)
                maxFallSpeed = maxFallSpeed == 0f ? -30f : -Mathf.Abs(maxFallSpeed);
            stickToGround = Mathf.Max(0f, stickToGround);
            slopeLimit = Mathf.Clamp(slopeLimit, 0f, 89f);
            groundCheckDistance = Mathf.Max(0.02f, groundCheckDistance);
            coyoteTime = Mathf.Max(0f, coyoteTime);
            jumpBuffer = Mathf.Max(0f, jumpBuffer);
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
    /// Camera-relative walk, run, and jump on a dynamic Rigidbody.
    /// </summary>
    /// <remarks>
    /// Legacy Input Manager. Active Input Handling must be
    /// "Input Manager (Old)" or "Both". Uses the default Horizontal,
    /// Vertical, and Jump axes. Run is Left Shift and is not an axis.
    /// Unity 6: linearVelocity and linearDamping. velocity and drag are obsolete.
    /// </remarks>
    [DisallowMultipleComponent]
    [RequireComponent(typeof(Rigidbody))]
    [RequireComponent(typeof(CapsuleCollider))]
    public class RigidbodyMovement : MonoBehaviour
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
        [SerializeField] float acceleration = 40f;
        [SerializeField] float deceleration = 55f;

        [Tooltip("Fraction of Acceleration used in the air. Zero keeps take-off momentum.")]
        [SerializeField] float airControl = 0.4f;

        [Tooltip("Peak height of a jump, in metres, under Physics.gravity times Gravity Multiplier.")]
        [SerializeField] float jumpHeight = 1.4f;

        [Tooltip("Scales Physics.gravity while airborne. One is the project gravity.")]
        [SerializeField] float gravityMultiplier = 2f;

        [Tooltip("Most negative vertical speed, in metres per second.")]
        [SerializeField] float maxFallSpeed = -30f;

        [Tooltip("Speed into the ground normal while grounded, so the capsule stays seated.")]
        [SerializeField] float stickToGround = 2f;

        [Header("Ground")]
        [SerializeField] float slopeLimit = 45f;
        [SerializeField] float groundCheckDistance = 0.2f;
        [SerializeField] LayerMask groundMask = ~0;

        [Header("Jump feel")]
        [SerializeField] float coyoteTime = 0.12f;
        [SerializeField] float jumpBuffer = 0.12f;

        [Header("Facing")]
        [Tooltip("Camera the movement is relative to. Empty uses Camera.main.")]
        [SerializeField] Transform view;

        [SerializeField] bool rotateTowardsMove = true;

        [Tooltip("Exponential rate for turning. Half-life in seconds is ln(2) / rate. Zero snaps.")]
        [SerializeField] float turnSharpness = 12f;

        [SerializeField] float inputDeadzone = 0.15f;

        Rigidbody _body;
        CapsuleCollider _capsule;
        Transform _mainCamera;
        Vector2 _move;
        bool _run;
        float _jumpUntil;
        float _lastGrounded = -10f;
        Vector3 _groundNormal = Vector3.up;
        bool _grounded;

        void Awake()
        {
            _body = GetComponent<Rigidbody>();
            _capsule = GetComponent<CapsuleCollider>();

            _body.useGravity = false;
            _body.linearDamping = 0f;
            _body.angularDamping = 0.05f;
            _body.interpolation = RigidbodyInterpolation.Interpolate;
            _body.collisionDetectionMode = CollisionDetectionMode.Continuous;
            _body.constraints = RigidbodyConstraints.FreezeRotationX | RigidbodyConstraints.FreezeRotationZ;
            _body.maxDepenetrationVelocity = 8f;

            PhysicsMaterial material = new PhysicsMaterial("Character Zero Friction")
            {
                dynamicFriction = 0f,
                staticFriction = 0f,
                bounciness = 0f,
                frictionCombine = PhysicsMaterialCombine.Minimum,
                bounceCombine = PhysicsMaterialCombine.Minimum
            };
            _capsule.material = material;
        }

        void Update()
        {
            ReadInput(out _move, out bool jumpPressed, out _run);
            if (jumpPressed)
                _jumpUntil = Time.time + jumpBuffer;
        }

        void FixedUpdate()
        {
            float dt = Time.fixedDeltaTime;
            Vector3 velocity = _body.linearVelocity;
            ProbeGround(velocity.y);

            if (_grounded)
                _lastGrounded = Time.time;

            Vector3 wish = WishDirection(_move, out float magnitude);
            float speed = (_run ? runSpeed : walkSpeed) * magnitude;
            Vector3 horizontal = new Vector3(velocity.x, 0f, velocity.z);
            float rate = Rate(magnitude);
            Vector3 nextPlanar = Vector3.MoveTowards(horizontal, wish * speed, rate * dt);

            if (!_grounded)
                SlideAgainstSteep(ref nextPlanar);

            Vector3 final = Compose(nextPlanar, velocity.y, dt);
            bool jumped = TryJump(ref final);

            if (!jumped && final.y > 0f && HitCeiling())
                final.y = 0f;

            _body.linearVelocity = final;

            if (rotateTowardsMove)
                Face(wish, dt);
        }

        float Rate(float magnitude)
        {
            if (_grounded)
                return magnitude > 0f ? acceleration : deceleration;
            return magnitude > 0f ? acceleration * airControl : 0f;
        }

        Vector3 Compose(Vector3 nextPlanar, float vertical, float dt)
        {
            if (_grounded)
            {
                Vector3 along = Vector3.ProjectOnPlane(nextPlanar, _groundNormal);
                Vector3 final = along.sqrMagnitude > 0.0001f
                    ? along.normalized * nextPlanar.magnitude
                    : Vector3.zero;
                return final - _groundNormal * stickToGround;
            }

            vertical += Physics.gravity.y * gravityMultiplier * dt;
            if (vertical < maxFallSpeed)
                vertical = maxFallSpeed;
            return new Vector3(nextPlanar.x, vertical, nextPlanar.z);
        }

        bool TryJump(ref Vector3 final)
        {
            bool buffered = Time.time <= _jumpUntil;
            bool coyote = Time.time - _lastGrounded <= coyoteTime;
            float gravity = Physics.gravity.y * gravityMultiplier;
            if (!buffered || !coyote || gravity >= 0f)
                return false;

            // The body moves one whole step at this speed before gravity acts. Taking off
            // half a step of gravity puts every step on the true arc, so the peak is Jump Height.
            float speed = Mathf.Sqrt(jumpHeight * -2f * gravity) + 0.5f * gravity * Time.fixedDeltaTime;
            final = new Vector3(final.x, speed, final.z);
            _jumpUntil = float.NegativeInfinity;
            _lastGrounded = Time.time - coyoteTime;
            _grounded = false;
            return true;
        }

        void ProbeGround(float verticalSpeed)
        {
            bool wasGrounded = _grounded;
            _grounded = false;
            _groundNormal = Vector3.up;

            // Rising after a jump ignores the ground just left, so the jump is not cancelled.
            // A grounded body walking uphill also rises, and has to keep probing.
            if (!wasGrounded && verticalSpeed > 0.05f)
                return;

            if (!TryCast(Vector3.down, Bottom(), groundCheckDistance, out RaycastHit hit))
                return;

            if (Vector3.Angle(hit.normal, Vector3.up) > slopeLimit)
                return;

            _groundNormal = hit.normal;
            _grounded = true;
        }

        void SlideAgainstSteep(ref Vector3 horizontal)
        {
            if (!TryCast(Vector3.down, Bottom(), groundCheckDistance, out RaycastHit hit))
                return;
            if (Vector3.Angle(hit.normal, Vector3.up) <= slopeLimit)
                return;

            Vector3 wall = Vector3.ProjectOnPlane(hit.normal, Vector3.up);
            if (wall.sqrMagnitude < 0.0001f)
                return;

            wall.Normalize();
            float into = Vector3.Dot(horizontal, wall);
            if (into < 0f)
                horizontal -= wall * into;
        }

        bool HitCeiling()
        {
            Vector3 centre = transform.TransformPoint(_capsule.center);
            float half = _capsule.height * 0.5f;
            Vector3 top = centre + Vector3.up * Mathf.Max(half - _capsule.radius, 0f);
            return TryCast(Vector3.up, top, 0.08f, out _);
        }

        bool TryCast(Vector3 direction, Vector3 origin, float extra, out RaycastHit hit)
        {
            // Start a little back from the surface and use a smaller radius, so a
            // capsule that is resting on the floor does not begin the cast inside it.
            float inset = 0.05f;
            float radius = Mathf.Max(0.05f, _capsule.radius - inset);
            Vector3 start = origin - direction * inset;
            return Physics.SphereCast(start, radius, direction, out hit, extra + inset * 2f, groundMask, QueryTriggerInteraction.Ignore);
        }

        Vector3 Bottom()
        {
            Vector3 centre = transform.TransformPoint(_capsule.center);
            float half = _capsule.height * 0.5f;
            float offset = Mathf.Max(half - _capsule.radius, 0f);
            return centre - Vector3.up * offset;
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
            Vector3 flat = wish;
            flat.y = 0f;
            if (flat.sqrMagnitude < 0.0001f)
                return;

            Quaternion target = Quaternion.LookRotation(flat.normalized, Vector3.up);
            float blend = turnSharpness <= 0f || dt <= 0f ? 1f : 1f - Mathf.Exp(-turnSharpness * dt);
            _body.MoveRotation(Quaternion.Slerp(_body.rotation, target, blend));
        }

        void OnValidate()
        {
            walkSpeed = Mathf.Max(0f, walkSpeed);
            runSpeed = Mathf.Max(walkSpeed, runSpeed);
            acceleration = Mathf.Max(0f, acceleration);
            deceleration = Mathf.Max(0f, deceleration);
            airControl = Mathf.Clamp01(airControl);
            jumpHeight = Mathf.Max(0f, jumpHeight);
            gravityMultiplier = Mathf.Max(0.01f, gravityMultiplier);
            if (maxFallSpeed >= 0f)
                maxFallSpeed = maxFallSpeed == 0f ? -30f : -Mathf.Abs(maxFallSpeed);
            stickToGround = Mathf.Max(0f, stickToGround);
            slopeLimit = Mathf.Clamp(slopeLimit, 0f, 89f);
            groundCheckDistance = Mathf.Max(0.02f, groundCheckDistance);
            coyoteTime = Mathf.Max(0f, coyoteTime);
            jumpBuffer = Mathf.Max(0f, jumpBuffer);
            turnSharpness = Mathf.Max(0f, turnSharpness);
            inputDeadzone = Mathf.Clamp(inputDeadzone, 0f, 0.9f);
        }
    }
    ```

!!! warning "Common pitfalls"

    Write `linearVelocity` in `FixedUpdate`, and read the buttons in `Update`. A press sampled in `FixedUpdate` is missed whenever the rendered frame has no physics step, and it can fire twice when one rendered frame has two. The timestamp is what makes the buffer survive that.

    `linearDamping` left above zero stacks with **Deceleration**. The script forces it to zero. **Interpolate** has to be on, or a camera that follows the transform in `LateUpdate` sees the body only on physics ticks and the view stutters. Interpolate lags by one physics step. That lag is the cost of a smooth camera. Do not also move `transform.position`.

    **Use Gravity** is turned off on purpose. The script applies `Physics.gravity` itself. Turning it back on in the inspector is undone in `Awake`, and a copy of this component that skips `Awake` would fall twice as fast.

    Mass does not change the walk speed, because the speed is written directly. It does change collisions: a mass of `1` is shoved by a heavier prop. Raise the mass if crates should bounce off the body rather than the other way round.

    The physics material uses **Minimum** friction. A floor whose material combines with **Maximum** ignores that and the capsule sticks to walls, which feels like a missed input. **Ground Mask** has to exclude the character, or the sphere cast reports the body as the floor.

    A camera parented to a root that also yaws will spin, and the wish direction spins with it. Leave the camera unparented, as the orbit camera does.

    `MoveRotation` is the turn that interpolation follows. Setting `transform.rotation` on a dynamic body fights the pose the renderer interpolated.

    Jump height assumes **Gravity Multiplier** stays constant during the jump. Stock `Physics.gravity` (`-9.81`) with a multiplier of `1` is a floaty jump next to the kinematic page, which uses its own `-25`. The default multiplier is `2` for that reason.
