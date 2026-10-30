---
engine: Unity
version: 6+
uses:
  - name: Platformers
    text: Variable jumps, slopes, and wall slides on a 2D body.
---

# 2D platformer

A side-view body on a `Rigidbody2D`: run, a jump whose height depends on how long the button is held, coyote time, a jump buffer, lighter gravity at the apex, heavier gravity on the way down, ground and wall probes, and an optional wall slide and wall jump.

Which body to use is on the [controllers](controllers/index.md) index. The 3D physics body is [Rigidbody movement](rigidbody-movement.md). A top-down `Rigidbody2D` with no jump is [top-down movement](top-down.md). Coyote time and the buffer are the same idea as [character movement](character-movement.md). Jump and fall as states, using `linearVelocity`, are the [state machine](../architecture/state-machines.md).

Unity 6 names the speed `linearVelocity` and the drag `linearDamping`. `velocity` and `drag` are obsolete. `gravityScale` is unchanged. The script sets `linearDamping` to zero and does its slowing in code.

## Setup

1. Add a **Rigidbody 2D** and a **Capsule Collider 2D**. Leave the body dynamic. The script sets **Interpolate**, **Continuous** collision detection, **Freeze Rotation**, **Linear Damping** `0`, and a zero-friction material so walls do not grab the capsule.
2. Add `PlatformerMovement2D`. Put floors and walls on **Ground Mask**, and exclude the character.
3. **Gravity Scale** on the component is the base. The script writes the rigidbody's `gravityScale` every physics step: the base at the apex times **Apex Gravity**, and the base while falling times **Fall Gravity**.
4. Copy the Input System listing, or the legacy listing. They declare the same class.
5. For a one-way platform, add **Platform Effector 2D**, enable **Use One Way**, and set **Surface Arc** to `180`. The collider stays solid, not a trigger. Down and jump drops through that effector only. Solid ground still jumps.

The sprite flips on local scale X. A negative scale on a parent is left alone; this script sets the sign of its own X scale.

## What each step is doing

`Update` stores horizontal and vertical input, whether the jump button is down, and the time of a press. The press is a timestamp so a `FixedUpdate` that does not run on that rendered frame still sees it.

Each `FixedUpdate` does the following.

1. Restore a platform that was ignored for a drop-through, once **Drop Through Time** has elapsed.
2. Cast the body down by **Ground Check** and sideways by **Wall Check**, using `Rigidbody2D.Cast` so the body's own colliders are skipped. A hit is ground when the normal is within **Slope Limit** of up. Steeper hits are walls. If the previous step was airborne and the vertical speed is upward, the ground cast is skipped, so the floor just left cannot cancel the jump. A body that was grounded keeps probing while it rises, because walking up a slope or riding a lift rises too.
3. On ground, refill the coyote clock. A jump is taken when that clock is still inside **Coyote Time** and the press is still inside **Jump Buffer**. Take-off speed is \(\sqrt{h \cdot 2 \lvert g \rvert}\) with \(g\) equal to `Physics2D.gravity.y` times the base **Gravity Scale**. Apex and fall multipliers are applied after take-off, so the peak is a little higher than **Jump Height** if the apex is light. That is deliberate.
4. Releasing the button while still rising multiplies the upward speed by **Jump Cut**, once. A tap is a short hop. Holding the button leaves the speed alone and the body reaches the full arc.
5. Horizontal speed moves toward the stick at **Acceleration** on the ground, or **Acceleration** times **Air Control** in the air. No input on the ground uses **Deceleration**. No input in the air keeps the momentum. For **Wall Jump Lock** seconds after a wall jump, horizontal input is ignored so air control cannot push straight back into the wall.
6. **Apex Gravity** applies when the vertical speed is inside **Apex Band** and the body is airborne, which hangs the top of the jump. **Fall Gravity** applies once the body is falling faster than that band. Otherwise the base scale is used.
7. With **Wall Slide** on, touching a wall, falling, and holding toward that wall clamps the fall to **Wall Slide Speed**. With **Wall Jump** on, a buffered press on that wall sets the velocity away from the wall and upward. It does not need coyote time.
8. Down plus jump, while the ground hit has a `PlatformEffector2D`, ignores that collider for **Drop Through Time** instead of jumping. A thick platform needs a longer time or the ignore ends while the capsule is still inside it.

## Parameters

| Field | Default | Effect |
| --- | --- | --- |
| Move Speed | `8` | Units per second at a full stick, on the ground. |
| Acceleration | `80` | Units per second squared toward the wish, on the ground. |
| Deceleration | `100` | Units per second squared toward a stop, on the ground. |
| Air Control | `0.65` | Fraction of **Acceleration** used in the air. |
| Jump Height | `3` | Nominal peak, in units, under the base gravity. |
| Jump Cut | `0.5` | Upward speed is multiplied by this when the button is released. |
| Gravity Scale | `1` | Base `gravityScale`. Apex and fall multiply this. |
| Apex Gravity | `0.5` | Scale used while vertical speed is inside **Apex Band**. |
| Apex Band | `2` | Units per second. Inside this, both ways, counts as the apex. |
| Fall Gravity | `1.75` | Scale used while falling faster than **Apex Band**. |
| Max Fall Speed | `-20` | Clamp on the downward speed. |
| Coyote Time | `0.1` | Seconds after leaving the ground in which a jump is still accepted. |
| Jump Buffer | `0.1` | Seconds a jump press is remembered. |
| Slope Limit | `50` | Degrees from up. Steeper is a wall. |
| Ground Check | `0.08` | Extra distance below the body. |
| Wall Check | `0.08` | Extra distance to either side. |
| Ground Mask | Everything | Layers the casts hit. Exclude the character. |
| Wall Slide | On | Clamp the fall while holding into a wall. |
| Wall Slide Speed | `2` | Downward speed cap during that slide. |
| Wall Jump | On | Jump off a wall without needing the ground. |
| Wall Jump Speed | `(7, 10)` | Horizontal speed away from the wall, and upward speed. |
| Wall Jump Lock | `0.12` | Seconds horizontal input is ignored after a wall jump. |
| Drop Through | On | Down and jump passes a one-way platform. |
| Drop Through Time | `0.3` | Seconds the platform collider is ignored. |
| Input Deadzone | `0.15` | Sticks shorter than this do not move. |

## One-way platforms

The effector lets the body pass when it hits the platform from below, and land when it hits from above. This script does not reimplement that. Dropping from above is the extra: `Physics2D.IgnoreCollision` for a short time, and only when the hit collider, or its parent, has a `PlatformEffector2D`. Solid floors are unchanged.

The ground cast still sees the platform, which is what makes the landing count as ground. Do not put the platform on a layer excluded from **Ground Mask**.

## Scripts

The two listings share the movement code. Copy one.

=== "Input System"

    A and D, or the left stick, move. S, or a left stick held down, is the drop-through. Space or the south face button jumps. A gamepad stick replaces the keys when its horizontal magnitude is larger.

    ```csharp
    using UnityEngine;
    using UnityEngine.InputSystem;


    /// <summary>
    /// Side-view platformer on a Rigidbody2D.
    /// </summary>
    /// <remarks>
    /// Input System, the default backend in a new Unity 6 project.
    /// Unity 6: linearVelocity and linearDamping. gravityScale is unchanged.
    /// </remarks>
    [DisallowMultipleComponent]
    [RequireComponent(typeof(Rigidbody2D))]
    public class PlatformerMovement2D : MonoBehaviour
    {
        void ReadInput(out Vector2 move, out bool jumpPressed, out bool jumpHeld)
        {
            move = Vector2.zero;
            jumpPressed = false;
            jumpHeld = false;

            Keyboard keyboard = Keyboard.current;
            if (keyboard != null)
            {
                if (keyboard.dKey.isPressed) move.x += 1f;
                if (keyboard.aKey.isPressed) move.x -= 1f;
                if (keyboard.sKey.isPressed) move.y -= 1f;
                if (keyboard.wKey.isPressed) move.y += 1f;
                jumpPressed |= keyboard.spaceKey.wasPressedThisFrame;
                jumpHeld |= keyboard.spaceKey.isPressed;
            }

            Gamepad gamepad = Gamepad.current;
            if (gamepad != null)
            {
                Vector2 stick = gamepad.leftStick.ReadValue();
                if (Mathf.Abs(stick.x) > Mathf.Abs(move.x))
                    move.x = stick.x;
                if (Mathf.Abs(stick.y) > Mathf.Abs(move.y))
                    move.y = stick.y;
                jumpPressed |= gamepad.buttonSouth.wasPressedThisFrame;
                jumpHeld |= gamepad.buttonSouth.isPressed;
            }
        }

        [Header("Motion")]
        [SerializeField] float moveSpeed = 8f;
        [SerializeField] float acceleration = 80f;
        [SerializeField] float deceleration = 100f;
        [SerializeField] float airControl = 0.65f;

        [Header("Jump")]
        [SerializeField] float jumpHeight = 3f;
        [Tooltip("Upward speed is multiplied by this when the button is released.")]
        [SerializeField] float jumpCut = 0.5f;
        [SerializeField] float gravityScale = 1f;
        [SerializeField] float apexGravity = 0.5f;
        [Tooltip("Vertical speeds inside this band, in units per second, use Apex Gravity.")]
        [SerializeField] float apexBand = 2f;
        [SerializeField] float fallGravity = 1.75f;
        [SerializeField] float maxFallSpeed = -20f;
        [SerializeField] float coyoteTime = 0.1f;
        [SerializeField] float jumpBuffer = 0.1f;

        [Header("Probes")]
        [SerializeField] float slopeLimit = 50f;
        [SerializeField] float groundCheck = 0.08f;
        [SerializeField] float wallCheck = 0.08f;
        [SerializeField] LayerMask groundMask = ~0;

        [Header("Walls")]
        [SerializeField] bool wallSlide = true;
        [SerializeField] float wallSlideSpeed = 2f;
        [SerializeField] bool wallJump = true;
        [SerializeField] Vector2 wallJumpSpeed = new Vector2(7f, 10f);
        [SerializeField] float wallJumpLock = 0.12f;

        [Header("One-way")]
        [SerializeField] bool dropThrough = true;
        [SerializeField] float dropThroughTime = 0.3f;

        [SerializeField] float inputDeadzone = 0.15f;

        readonly RaycastHit2D[] _hits = new RaycastHit2D[8];
        Rigidbody2D _body;
        Vector2 _move;
        bool _jumpHeld;
        float _jumpUntil = float.NegativeInfinity;
        float _lastGrounded = -10f;
        float _wallLockUntil = float.NegativeInfinity;
        float _ignoreUntil;
        bool _canCut;
        bool _wasGrounded;
        Collider2D _ignored;

        void Awake()
        {
            _body = GetComponent<Rigidbody2D>();
            _body.linearDamping = 0f;
            _body.angularDamping = 0f;
            _body.interpolation = RigidbodyInterpolation2D.Interpolate;
            _body.collisionDetectionMode = CollisionDetectionMode2D.Continuous;
            _body.constraints = RigidbodyConstraints2D.FreezeRotation;
            _body.gravityScale = gravityScale;

            Collider2D collider = GetComponent<Collider2D>();
            if (collider != null)
            {
                collider.sharedMaterial = new PhysicsMaterial2D("Character Zero Friction")
                {
                    friction = 0f,
                    bounciness = 0f
                };
            }
        }

        void Update()
        {
            ReadInput(out _move, out bool jumpPressed, out _jumpHeld);
            if (jumpPressed)
                _jumpUntil = Time.time + jumpBuffer;
        }

        void FixedUpdate()
        {
            float dt = Time.fixedDeltaTime;
            RestoreDrop();

            ContactFilter2D filter = Filter();
            float horizontal = Axis(_move.x);
            bool drop = Axis(_move.y) < -0.5f;
            // Rising after a jump ignores the floor just left. A body that was grounded keeps
            // probing while it rises, because walking up a slope or riding a lift rises too.
            bool rising = _body.linearVelocity.y > 0.05f;
            RaycastHit2D groundHit = default;
            bool grounded = (!rising || _wasGrounded) && Probe(Vector2.down, groundCheck, filter, true, out groundHit);
            int wallSide = ProbeWall(filter);

            if (grounded)
            {
                _lastGrounded = Time.time;
                _canCut = false;
            }

            if (grounded && drop && dropThrough && Time.time <= _jumpUntil && TryDrop(groundHit))
            {
                _jumpUntil = float.NegativeInfinity;
                grounded = false;
            }

            Vector2 velocity = _body.linearVelocity;
            bool jumped = false;
            bool buffered = Time.time <= _jumpUntil;
            bool coyote = Time.time - _lastGrounded <= coyoteTime;

            if (buffered && wallJump && wallSide != 0 && !grounded && Time.time >= _wallLockUntil)
            {
                velocity = new Vector2(-wallSide * wallJumpSpeed.x, wallJumpSpeed.y);
                SpendJump();
                _wallLockUntil = Time.time + wallJumpLock;
                jumped = true;
            }
            else if (buffered && coyote && (grounded || !rising))
            {
                velocity.y = JumpSpeed();
                SpendJump();
                grounded = false;
                jumped = true;
            }

            if (_canCut && !_jumpHeld && velocity.y > 0f)
            {
                velocity.y *= jumpCut;
                _canCut = false;
            }

            bool locked = Time.time < _wallLockUntil;
            if (!locked)
            {
                float target = horizontal * moveSpeed;
                float rate;
                if (grounded)
                    rate = Mathf.Abs(horizontal) > 0.01f ? acceleration : deceleration;
                else
                    rate = Mathf.Abs(horizontal) > 0.01f ? acceleration * airControl : 0f;
                velocity.x = Mathf.MoveTowards(velocity.x, target, rate * dt);
            }

            float scale = gravityScale;
            if (!grounded && !jumped)
            {
                if (velocity.y < -apexBand)
                    scale *= fallGravity;
                else if (Mathf.Abs(velocity.y) <= apexBand)
                    scale *= apexGravity;
            }

            _body.gravityScale = scale;

            bool holdingWall = wallSide != 0 && Mathf.Abs(horizontal) > 0.01f && Mathf.Sign(horizontal) == wallSide;
            if (wallSlide && holdingWall && !grounded && velocity.y < 0f)
                velocity.y = Mathf.Max(velocity.y, -wallSlideSpeed);

            if (velocity.y < maxFallSpeed)
                velocity.y = maxFallSpeed;

            _body.linearVelocity = velocity;
            _wasGrounded = grounded;

            float face = locked ? velocity.x : horizontal;
            if (Mathf.Abs(face) > 0.01f)
                Face(face);
        }

        void SpendJump()
        {
            _jumpUntil = float.NegativeInfinity;
            _lastGrounded = Time.time - coyoteTime;
            _canCut = true;
        }

        float JumpSpeed()
        {
            float gravity = Physics2D.gravity.y * gravityScale;
            if (gravity >= 0f)
                return 0f;
            return Mathf.Sqrt(jumpHeight * -2f * gravity);
        }

        float Axis(float value)
        {
            float magnitude = Mathf.Abs(value);
            if (magnitude < inputDeadzone || inputDeadzone >= 1f)
                return 0f;
            if (magnitude > 1f)
                magnitude = 1f;
            float scaled = (magnitude - inputDeadzone) / (1f - inputDeadzone);
            return Mathf.Sign(value) * scaled;
        }

        ContactFilter2D Filter()
        {
            ContactFilter2D filter = new ContactFilter2D();
            filter.SetLayerMask(groundMask);
            filter.useTriggers = false;
            return filter;
        }

        bool Probe(Vector2 direction, float distance, ContactFilter2D filter, bool walkable, out RaycastHit2D best)
        {
            best = default;
            int count = _body.Cast(direction, filter, _hits, distance);
            float nearest = float.PositiveInfinity;
            bool found = false;

            for (int i = 0; i < count; i++)
            {
                RaycastHit2D hit = _hits[i];
                if (hit.collider == null)
                    continue;

                float slope = Vector2.Angle(hit.normal, Vector2.up);
                bool groundLike = slope <= slopeLimit;
                if (groundLike != walkable)
                    continue;
                if (hit.distance >= nearest)
                    continue;

                nearest = hit.distance;
                best = hit;
                found = true;
            }

            return found;
        }

        int ProbeWall(ContactFilter2D filter)
        {
            bool right = Probe(Vector2.right, wallCheck, filter, false, out RaycastHit2D rightHit);
            bool left = Probe(Vector2.left, wallCheck, filter, false, out RaycastHit2D leftHit);
            if (right && left)
                return rightHit.distance <= leftHit.distance ? 1 : -1;
            if (right)
                return 1;
            if (left)
                return -1;
            return 0;
        }

        bool TryDrop(RaycastHit2D groundHit)
        {
            if (groundHit.collider == null)
                return false;

            PlatformEffector2D effector = groundHit.collider.GetComponent<PlatformEffector2D>();
            if (effector == null)
                effector = groundHit.collider.GetComponentInParent<PlatformEffector2D>();
            if (effector == null)
                return false;

            _ignoreUntil = 0f;
            RestoreDrop();
            Collider2D[] own = GetComponents<Collider2D>();
            for (int i = 0; i < own.Length; i++)
            {
                if (own[i] != null && own[i].enabled)
                    Physics2D.IgnoreCollision(own[i], groundHit.collider, true);
            }

            _ignored = groundHit.collider;
            _ignoreUntil = Time.time + dropThroughTime;
            return true;
        }

        void RestoreDrop()
        {
            if (_ignored == null || Time.time < _ignoreUntil)
                return;

            Collider2D[] own = GetComponents<Collider2D>();
            for (int i = 0; i < own.Length; i++)
            {
                if (own[i] != null)
                    Physics2D.IgnoreCollision(own[i], _ignored, false);
            }

            _ignored = null;
        }

        void Face(float direction)
        {
            Vector3 scale = transform.localScale;
            scale.x = Mathf.Abs(scale.x) * Mathf.Sign(direction);
            transform.localScale = scale;
        }

        void OnValidate()
        {
            moveSpeed = Mathf.Max(0f, moveSpeed);
            acceleration = Mathf.Max(0f, acceleration);
            deceleration = Mathf.Max(0f, deceleration);
            airControl = Mathf.Clamp01(airControl);
            jumpHeight = Mathf.Max(0f, jumpHeight);
            jumpCut = Mathf.Clamp(jumpCut, 0f, 1f);
            gravityScale = Mathf.Max(0.01f, gravityScale);
            apexGravity = Mathf.Max(0f, apexGravity);
            apexBand = Mathf.Max(0f, apexBand);
            fallGravity = Mathf.Max(0f, fallGravity);
            if (maxFallSpeed >= 0f)
                maxFallSpeed = maxFallSpeed == 0f ? -20f : -Mathf.Abs(maxFallSpeed);
            coyoteTime = Mathf.Max(0f, coyoteTime);
            jumpBuffer = Mathf.Max(0f, jumpBuffer);
            slopeLimit = Mathf.Clamp(slopeLimit, 0f, 89f);
            groundCheck = Mathf.Max(0.01f, groundCheck);
            wallCheck = Mathf.Max(0.01f, wallCheck);
            wallSlideSpeed = Mathf.Max(0f, wallSlideSpeed);
            wallJumpLock = Mathf.Max(0f, wallJumpLock);
            dropThroughTime = Mathf.Max(0.05f, dropThroughTime);
            inputDeadzone = Mathf.Clamp(inputDeadzone, 0f, 0.9f);
        }
    }
    ```

=== "Legacy Input Manager"

    `GetAxisRaw("Horizontal")` moves. `GetAxisRaw("Vertical")` below `-0.5` is the drop-through. `GetButtonDown("Jump")` and `GetButton("Jump")` are the press and the hold.

    ```csharp
    using UnityEngine;


    /// <summary>
    /// Side-view platformer on a Rigidbody2D.
    /// </summary>
    /// <remarks>
    /// Legacy Input Manager. Active Input Handling must be
    /// "Input Manager (Old)" or "Both". Uses Horizontal, Vertical, and Jump.
    /// Unity 6: linearVelocity and linearDamping. gravityScale is unchanged.
    /// </remarks>
    [DisallowMultipleComponent]
    [RequireComponent(typeof(Rigidbody2D))]
    public class PlatformerMovement2D : MonoBehaviour
    {
        void ReadInput(out Vector2 move, out bool jumpPressed, out bool jumpHeld)
        {
            move.x = Input.GetAxisRaw("Horizontal");
            move.y = Input.GetAxisRaw("Vertical");
            jumpPressed = Input.GetButtonDown("Jump");
            jumpHeld = Input.GetButton("Jump");
        }

        [Header("Motion")]
        [SerializeField] float moveSpeed = 8f;
        [SerializeField] float acceleration = 80f;
        [SerializeField] float deceleration = 100f;
        [SerializeField] float airControl = 0.65f;

        [Header("Jump")]
        [SerializeField] float jumpHeight = 3f;
        [Tooltip("Upward speed is multiplied by this when the button is released.")]
        [SerializeField] float jumpCut = 0.5f;
        [SerializeField] float gravityScale = 1f;
        [SerializeField] float apexGravity = 0.5f;
        [Tooltip("Vertical speeds inside this band, in units per second, use Apex Gravity.")]
        [SerializeField] float apexBand = 2f;
        [SerializeField] float fallGravity = 1.75f;
        [SerializeField] float maxFallSpeed = -20f;
        [SerializeField] float coyoteTime = 0.1f;
        [SerializeField] float jumpBuffer = 0.1f;

        [Header("Probes")]
        [SerializeField] float slopeLimit = 50f;
        [SerializeField] float groundCheck = 0.08f;
        [SerializeField] float wallCheck = 0.08f;
        [SerializeField] LayerMask groundMask = ~0;

        [Header("Walls")]
        [SerializeField] bool wallSlide = true;
        [SerializeField] float wallSlideSpeed = 2f;
        [SerializeField] bool wallJump = true;
        [SerializeField] Vector2 wallJumpSpeed = new Vector2(7f, 10f);
        [SerializeField] float wallJumpLock = 0.12f;

        [Header("One-way")]
        [SerializeField] bool dropThrough = true;
        [SerializeField] float dropThroughTime = 0.3f;

        [SerializeField] float inputDeadzone = 0.15f;

        readonly RaycastHit2D[] _hits = new RaycastHit2D[8];
        Rigidbody2D _body;
        Vector2 _move;
        bool _jumpHeld;
        float _jumpUntil = float.NegativeInfinity;
        float _lastGrounded = -10f;
        float _wallLockUntil = float.NegativeInfinity;
        float _ignoreUntil;
        bool _canCut;
        bool _wasGrounded;
        Collider2D _ignored;

        void Awake()
        {
            _body = GetComponent<Rigidbody2D>();
            _body.linearDamping = 0f;
            _body.angularDamping = 0f;
            _body.interpolation = RigidbodyInterpolation2D.Interpolate;
            _body.collisionDetectionMode = CollisionDetectionMode2D.Continuous;
            _body.constraints = RigidbodyConstraints2D.FreezeRotation;
            _body.gravityScale = gravityScale;

            Collider2D collider = GetComponent<Collider2D>();
            if (collider != null)
            {
                collider.sharedMaterial = new PhysicsMaterial2D("Character Zero Friction")
                {
                    friction = 0f,
                    bounciness = 0f
                };
            }
        }

        void Update()
        {
            ReadInput(out _move, out bool jumpPressed, out _jumpHeld);
            if (jumpPressed)
                _jumpUntil = Time.time + jumpBuffer;
        }

        void FixedUpdate()
        {
            float dt = Time.fixedDeltaTime;
            RestoreDrop();

            ContactFilter2D filter = Filter();
            float horizontal = Axis(_move.x);
            bool drop = Axis(_move.y) < -0.5f;
            // Rising after a jump ignores the floor just left. A body that was grounded keeps
            // probing while it rises, because walking up a slope or riding a lift rises too.
            bool rising = _body.linearVelocity.y > 0.05f;
            RaycastHit2D groundHit = default;
            bool grounded = (!rising || _wasGrounded) && Probe(Vector2.down, groundCheck, filter, true, out groundHit);
            int wallSide = ProbeWall(filter);

            if (grounded)
            {
                _lastGrounded = Time.time;
                _canCut = false;
            }

            if (grounded && drop && dropThrough && Time.time <= _jumpUntil && TryDrop(groundHit))
            {
                _jumpUntil = float.NegativeInfinity;
                grounded = false;
            }

            Vector2 velocity = _body.linearVelocity;
            bool jumped = false;
            bool buffered = Time.time <= _jumpUntil;
            bool coyote = Time.time - _lastGrounded <= coyoteTime;

            if (buffered && wallJump && wallSide != 0 && !grounded && Time.time >= _wallLockUntil)
            {
                velocity = new Vector2(-wallSide * wallJumpSpeed.x, wallJumpSpeed.y);
                SpendJump();
                _wallLockUntil = Time.time + wallJumpLock;
                jumped = true;
            }
            else if (buffered && coyote && (grounded || !rising))
            {
                velocity.y = JumpSpeed();
                SpendJump();
                grounded = false;
                jumped = true;
            }

            if (_canCut && !_jumpHeld && velocity.y > 0f)
            {
                velocity.y *= jumpCut;
                _canCut = false;
            }

            bool locked = Time.time < _wallLockUntil;
            if (!locked)
            {
                float target = horizontal * moveSpeed;
                float rate;
                if (grounded)
                    rate = Mathf.Abs(horizontal) > 0.01f ? acceleration : deceleration;
                else
                    rate = Mathf.Abs(horizontal) > 0.01f ? acceleration * airControl : 0f;
                velocity.x = Mathf.MoveTowards(velocity.x, target, rate * dt);
            }

            float scale = gravityScale;
            if (!grounded && !jumped)
            {
                if (velocity.y < -apexBand)
                    scale *= fallGravity;
                else if (Mathf.Abs(velocity.y) <= apexBand)
                    scale *= apexGravity;
            }

            _body.gravityScale = scale;

            bool holdingWall = wallSide != 0 && Mathf.Abs(horizontal) > 0.01f && Mathf.Sign(horizontal) == wallSide;
            if (wallSlide && holdingWall && !grounded && velocity.y < 0f)
                velocity.y = Mathf.Max(velocity.y, -wallSlideSpeed);

            if (velocity.y < maxFallSpeed)
                velocity.y = maxFallSpeed;

            _body.linearVelocity = velocity;
            _wasGrounded = grounded;

            float face = locked ? velocity.x : horizontal;
            if (Mathf.Abs(face) > 0.01f)
                Face(face);
        }

        void SpendJump()
        {
            _jumpUntil = float.NegativeInfinity;
            _lastGrounded = Time.time - coyoteTime;
            _canCut = true;
        }

        float JumpSpeed()
        {
            float gravity = Physics2D.gravity.y * gravityScale;
            if (gravity >= 0f)
                return 0f;
            return Mathf.Sqrt(jumpHeight * -2f * gravity);
        }

        float Axis(float value)
        {
            float magnitude = Mathf.Abs(value);
            if (magnitude < inputDeadzone || inputDeadzone >= 1f)
                return 0f;
            if (magnitude > 1f)
                magnitude = 1f;
            float scaled = (magnitude - inputDeadzone) / (1f - inputDeadzone);
            return Mathf.Sign(value) * scaled;
        }

        ContactFilter2D Filter()
        {
            ContactFilter2D filter = new ContactFilter2D();
            filter.SetLayerMask(groundMask);
            filter.useTriggers = false;
            return filter;
        }

        bool Probe(Vector2 direction, float distance, ContactFilter2D filter, bool walkable, out RaycastHit2D best)
        {
            best = default;
            int count = _body.Cast(direction, filter, _hits, distance);
            float nearest = float.PositiveInfinity;
            bool found = false;

            for (int i = 0; i < count; i++)
            {
                RaycastHit2D hit = _hits[i];
                if (hit.collider == null)
                    continue;

                float slope = Vector2.Angle(hit.normal, Vector2.up);
                bool groundLike = slope <= slopeLimit;
                if (groundLike != walkable)
                    continue;
                if (hit.distance >= nearest)
                    continue;

                nearest = hit.distance;
                best = hit;
                found = true;
            }

            return found;
        }

        int ProbeWall(ContactFilter2D filter)
        {
            bool right = Probe(Vector2.right, wallCheck, filter, false, out RaycastHit2D rightHit);
            bool left = Probe(Vector2.left, wallCheck, filter, false, out RaycastHit2D leftHit);
            if (right && left)
                return rightHit.distance <= leftHit.distance ? 1 : -1;
            if (right)
                return 1;
            if (left)
                return -1;
            return 0;
        }

        bool TryDrop(RaycastHit2D groundHit)
        {
            if (groundHit.collider == null)
                return false;

            PlatformEffector2D effector = groundHit.collider.GetComponent<PlatformEffector2D>();
            if (effector == null)
                effector = groundHit.collider.GetComponentInParent<PlatformEffector2D>();
            if (effector == null)
                return false;

            _ignoreUntil = 0f;
            RestoreDrop();
            Collider2D[] own = GetComponents<Collider2D>();
            for (int i = 0; i < own.Length; i++)
            {
                if (own[i] != null && own[i].enabled)
                    Physics2D.IgnoreCollision(own[i], groundHit.collider, true);
            }

            _ignored = groundHit.collider;
            _ignoreUntil = Time.time + dropThroughTime;
            return true;
        }

        void RestoreDrop()
        {
            if (_ignored == null || Time.time < _ignoreUntil)
                return;

            Collider2D[] own = GetComponents<Collider2D>();
            for (int i = 0; i < own.Length; i++)
            {
                if (own[i] != null)
                    Physics2D.IgnoreCollision(own[i], _ignored, false);
            }

            _ignored = null;
        }

        void Face(float direction)
        {
            Vector3 scale = transform.localScale;
            scale.x = Mathf.Abs(scale.x) * Mathf.Sign(direction);
            transform.localScale = scale;
        }

        void OnValidate()
        {
            moveSpeed = Mathf.Max(0f, moveSpeed);
            acceleration = Mathf.Max(0f, acceleration);
            deceleration = Mathf.Max(0f, deceleration);
            airControl = Mathf.Clamp01(airControl);
            jumpHeight = Mathf.Max(0f, jumpHeight);
            jumpCut = Mathf.Clamp(jumpCut, 0f, 1f);
            gravityScale = Mathf.Max(0.01f, gravityScale);
            apexGravity = Mathf.Max(0f, apexGravity);
            apexBand = Mathf.Max(0f, apexBand);
            fallGravity = Mathf.Max(0f, fallGravity);
            if (maxFallSpeed >= 0f)
                maxFallSpeed = maxFallSpeed == 0f ? -20f : -Mathf.Abs(maxFallSpeed);
            coyoteTime = Mathf.Max(0f, coyoteTime);
            jumpBuffer = Mathf.Max(0f, jumpBuffer);
            slopeLimit = Mathf.Clamp(slopeLimit, 0f, 89f);
            groundCheck = Mathf.Max(0.01f, groundCheck);
            wallCheck = Mathf.Max(0.01f, wallCheck);
            wallSlideSpeed = Mathf.Max(0f, wallSlideSpeed);
            wallJumpLock = Mathf.Max(0f, wallJumpLock);
            dropThroughTime = Mathf.Max(0.05f, dropThroughTime);
            inputDeadzone = Mathf.Clamp(inputDeadzone, 0f, 0.9f);
        }
    }
    ```

!!! warning "Common pitfalls"

    Read the buttons in `Update` and write `linearVelocity` in `FixedUpdate`. A jump sampled in `FixedUpdate` is missed on frames that have no physics step. `linearDamping` left above zero stacks with **Deceleration** and the run never reaches **Move Speed**. The script forces the damping to zero.

    **Interpolate** lags one physics step and is what a follow camera wants. A camera that reads the body from `FixedUpdate` and a script that also writes `transform.position` will stutter or fight the interpolation.

    The ground cast is skipped while rising. Without that, the feet are still inside **Ground Check** on the first airborne step and the jump is treated as grounded and cancelled. Coyote time is the window after the cast has actually lost the floor.

    **Jump Height** is computed from the base gravity only. **Apex Gravity** below `1` makes the real peak a bit higher. Tune the height after the apex value, not before.

    Wall slide and wall jump are on by default. Turn **Wall Slide** and **Wall Jump** off for a plain platformer. A wall jump ignores horizontal input for **Wall Jump Lock**, otherwise **Air Control** cancels the push-off on the next step.

    Zero friction is assigned so the solver does not stick the capsule to a wall. The slide speed is the clamp in this script, not the material. A physics material on the wall set to high friction can still win if its combine mode outranks **Minimum**; the runtime material uses the default combine.

    Drop-through only runs when the ground hit has a `PlatformEffector2D`. S and jump on a solid floor is a normal jump. The ignore lasts **Drop Through Time**. A platform thicker than the body falls in that time needs a longer value, or the collision turns back on while the capsule is still overlapping and the body is thrown out.

    **Ground Mask** has to include the platform and exclude the character. `Rigidbody2D.Cast` already skips the body's own colliders. A second collider on a child that is not on the rigidbody is not skipped.

    Flipping `localScale.x` mirrors child colliders. Keep the collider on the same object as the script, or on a child that is not the flipped transform, if a trigger should stay unmirrored. Dash, wall run, and a ledge climb are not in this script; they are still on the roadmap.
