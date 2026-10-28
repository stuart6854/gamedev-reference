---
engine: Unity
version: 6+
---

# Top-down movement

Move with WASD or the left stick, and aim somewhere else: at the mouse, through a ray on the ground plane, or with the right stick. The 3D body is a `Rigidbody` locked to the horizontal plane. A 2D variant at the bottom uses `Rigidbody2D` with gravity off.

Which body to use is on the [controllers](controllers/index.md) index. This one does not jump. A camera pitched down from the side is still this controller; the [orbit camera](../cameras/third-person.md) works if **Camera Relative** is on and the camera is not a child of the body.

## Setup

1. On the avatar, add a **Capsule Collider** and a **Rigidbody**. The script turns **Use Gravity** off, sets **Linear Damping** to `0`, freezes **Position Y** and rotation on X and Z, and sets **Interpolate**.
2. Add `TopDownMovement`. Assign **View** to the gameplay camera, or leave it empty to use `Camera.main`.
3. Leave **Camera Relative** on when the camera is isometric or otherwise yawed, so W moves up the screen. Turn it off when the camera looks along world `-Z` and W should be world `+Z`.
4. Copy one Input System listing or one legacy listing. They declare the same class. The 2D scripts below are a different class and do not replace this one.
5. Put walls on layers the capsule collides with. Aim does not raycast the mouse against those walls; it uses an infinite plane at the body's height, so a tall obstacle does not block the crosshair.

`Awake` also assigns a zero-friction physics material, with **Minimum** combine, so a glancing wall does not eat the stick input.

## What each step is doing

`Update` stores the move, and resolves aim. A right stick past the dead zone wins, because a resting mouse at the edge of the window should not fight a gamepad. Releasing the stick keeps that aim. The mouse takes over again only once it moves. Mouse aim is a ray from the camera onto the plane `y = body height`. The stick is mapped through the same camera axes as movement. The mouse is already a world point, so it is not multiplied by those axes again.

`FixedUpdate` moves `linearVelocity` on XZ toward the wish at **Acceleration**, or toward zero at **Deceleration**. Y stays zero because position Y is frozen and gravity is off. `MoveRotation` yaws toward the aim. The blend is \(1 - e^{-kt}\). Zero **Turn Sharpness** snaps.

The body pushes other rigidbodies. Mass does not change the move speed. It changes who wins a shove.

## Isometric cameras

An isometric camera looks down at an angle, and its yaw is often 45 degrees. Flatten that forward onto the ground and it is the direction the player reads as "up" on the screen. **Camera Relative** builds the wish from that forward and from \(\mathrm{up} \times \mathrm{forward}\). W then walks up the screen, not toward world `+Z`.

The same flag does not change the mouse. The mouse ray already follows the lens. It does change the right stick, so stick-up matches screen-up.

A camera that is almost edge-on to the ground plane will miss the plane and the aim will stay where it was. Pitch the camera down enough that a click on the playfield hits the plane.

## Parameters

| Field | Default | Effect |
| --- | --- | --- |
| Speed | `6` | Metres per second at a full stick. |
| Acceleration | `35` | Metres per second squared toward the wish. |
| Deceleration | `45` | Metres per second squared toward a stop with no input. |
| Camera Relative | On | Move, and the right stick, use the camera yaw. Off uses world axes. |
| View | Empty | Camera. Empty follows `Camera.main`. |
| Turn Sharpness | `14` | Exponential turn toward the aim. Zero snaps. |
| Input Deadzone | `0.15` | Sticks shorter than this do not move or aim. |

## Scripts

The two 3D listings share `TopDownMovement`. Copy one.

=== "Input System"

    WASD or the left stick moves. The mouse aims when the right stick is idle. A deflected right stick aims instead, so a gamepad is not pulled by the pointer. Reads are this frame's state and are not multiplied by `Time.deltaTime`.

    ```csharp
    using UnityEngine;
    using UnityEngine.InputSystem;


    /// <summary>
    /// Twin-stick top-down movement on a dynamic Rigidbody.
    /// </summary>
    /// <remarks>
    /// Input System, the default backend in a new Unity 6 project.
    /// Move is WASD or the left stick. Aim is the mouse on the ground
    /// plane, or the right stick when that stick is past the dead zone.
    /// Unity 6: linearVelocity and linearDamping.
    /// </remarks>
    [DisallowMultipleComponent]
    [RequireComponent(typeof(Rigidbody))]
    [RequireComponent(typeof(CapsuleCollider))]
    public class TopDownMovement : MonoBehaviour
    {
        void ReadInput(out Vector2 move, out Vector2 look, out bool haveLook, out Vector2 mouse, out bool haveMouse)
        {
            move = Vector2.zero;
            look = Vector2.zero;
            haveLook = false;
            mouse = Vector2.zero;
            haveMouse = false;

            Keyboard keyboard = Keyboard.current;
            if (keyboard != null)
            {
                if (keyboard.dKey.isPressed) move.x += 1f;
                if (keyboard.aKey.isPressed) move.x -= 1f;
                if (keyboard.wKey.isPressed) move.y += 1f;
                if (keyboard.sKey.isPressed) move.y -= 1f;
            }

            Mouse pointer = Mouse.current;
            if (pointer != null)
            {
                mouse = pointer.position.ReadValue();
                haveMouse = true;
            }

            Gamepad gamepad = Gamepad.current;
            if (gamepad != null)
            {
                Vector2 stick = gamepad.leftStick.ReadValue();
                if (stick.sqrMagnitude > move.sqrMagnitude)
                    move = stick;
                look = gamepad.rightStick.ReadValue();
                haveLook = true;
            }
        }

        [Header("Motion")]
        [SerializeField] float speed = 6f;
        [SerializeField] float acceleration = 35f;
        [SerializeField] float deceleration = 45f;

        [Tooltip("On for an isometric or yawed camera, so W is up the screen. Off uses world axes.")]
        [SerializeField] bool cameraRelative = true;

        [Tooltip("Camera used for movement axes and the mouse ray. Empty uses Camera.main.")]
        [SerializeField] Transform view;

        [Tooltip("Exponential rate for turning toward the aim. Zero snaps.")]
        [SerializeField] float turnSharpness = 14f;

        [SerializeField] float inputDeadzone = 0.15f;

        Rigidbody _body;
        CapsuleCollider _capsule;
        Transform _mainCamera;
        Vector2 _move;
        Vector2 _lastMouse;
        bool _mouseAims = true;
        Vector3 _aim = Vector3.forward;

        void Awake()
        {
            _body = GetComponent<Rigidbody>();
            _capsule = GetComponent<CapsuleCollider>();
            _body.useGravity = false;
            _body.linearDamping = 0f;
            _body.angularDamping = 0.05f;
            _body.interpolation = RigidbodyInterpolation.Interpolate;
            _body.collisionDetectionMode = CollisionDetectionMode.Continuous;
            _body.constraints = RigidbodyConstraints.FreezePositionY
                | RigidbodyConstraints.FreezeRotationX
                | RigidbodyConstraints.FreezeRotationZ;
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

            Vector3 forward = Vector3.ProjectOnPlane(transform.forward, Vector3.up);
            if (forward.sqrMagnitude > 0.0001f)
                _aim = forward.normalized;
        }

        void Update()
        {
            ReadInput(out _move, out Vector2 look, out bool haveLook, out Vector2 mouse, out bool haveMouse);
            _aim = ResolveAim(look, haveLook, mouse, haveMouse);
        }

        void FixedUpdate()
        {
            float dt = Time.fixedDeltaTime;
            Vector3 velocity = _body.linearVelocity;
            Vector3 horizontal = new Vector3(velocity.x, 0f, velocity.z);
            Vector3 wish = Wish(_move, out float magnitude);
            float rate = magnitude > 0f ? acceleration : deceleration;
            Vector3 next = Vector3.MoveTowards(horizontal, wish * (speed * magnitude), rate * dt);
            _body.linearVelocity = new Vector3(next.x, 0f, next.z);
            Face(dt);
        }

        Vector3 ResolveAim(Vector2 look, bool haveLook, Vector2 mouse, bool haveMouse)
        {
            if (haveLook && look.sqrMagnitude >= inputDeadzone * inputDeadzone)
            {
                _mouseAims = false;
                return Axes(look.normalized);
            }

            // The mouse takes over again only once it moves, so letting go of the right
            // stick keeps the aim instead of snapping to an idle cursor.
            if (haveMouse && mouse != _lastMouse)
                _mouseAims = true;
            _lastMouse = mouse;

            if (_mouseAims && haveMouse && TryMouseAim(mouse, out Vector3 at))
                return at;

            return _aim;
        }

        bool TryMouseAim(Vector2 screen, out Vector3 direction)
        {
            direction = Vector3.zero;
            Camera camera = Eye();
            if (camera == null)
                return false;

            Ray ray = camera.ScreenPointToRay(screen);
            Plane plane = new Plane(Vector3.up, new Vector3(0f, _body.position.y, 0f));
            if (!plane.Raycast(ray, out float distance))
                return false;

            Vector3 delta = ray.GetPoint(distance) - _body.position;
            delta.y = 0f;
            if (delta.sqrMagnitude < 0.0001f)
                return false;

            direction = delta.normalized;
            return true;
        }

        Vector3 Wish(Vector2 move, out float magnitude)
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
            return Axes(move.normalized);
        }

        Vector3 Axes(Vector2 direction)
        {
            Vector3 forward = PlanarForward();
            Vector3 right = Vector3.Cross(Vector3.up, forward);
            Vector3 result = right * direction.x + forward * direction.y;
            if (result.sqrMagnitude < 0.0001f)
                return Vector3.zero;
            return result.normalized;
        }

        Vector3 PlanarForward()
        {
            if (!cameraRelative)
                return Vector3.forward;

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

        Camera Eye()
        {
            Transform eyes = ViewTransform();
            if (eyes == null)
                return null;

            Camera camera = eyes.GetComponent<Camera>();
            if (camera == null)
                camera = eyes.GetComponentInChildren<Camera>();
            return camera != null ? camera : Camera.main;
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

        void Face(float dt)
        {
            Vector3 flat = _aim;
            flat.y = 0f;
            if (flat.sqrMagnitude < 0.0001f)
                return;

            Quaternion target = Quaternion.LookRotation(flat.normalized, Vector3.up);
            float blend = turnSharpness <= 0f || dt <= 0f ? 1f : 1f - Mathf.Exp(-turnSharpness * dt);
            _body.MoveRotation(Quaternion.Slerp(_body.rotation, target, blend));
        }

        void OnValidate()
        {
            speed = Mathf.Max(0f, speed);
            acceleration = Mathf.Max(0f, acceleration);
            deceleration = Mathf.Max(0f, deceleration);
            turnSharpness = Mathf.Max(0f, turnSharpness);
            inputDeadzone = Mathf.Clamp(inputDeadzone, 0f, 0.9f);
        }
    }
    ```

=== "Legacy Input Manager"

    `GetAxisRaw("Horizontal")` and `"Vertical"` are the default axes with no smoothing. Aim is the mouse. The legacy axes have no default right stick, so a gamepad look is not read here.

    ```csharp
    using UnityEngine;


    /// <summary>
    /// Twin-stick top-down movement on a dynamic Rigidbody.
    /// </summary>
    /// <remarks>
    /// Legacy Input Manager. Active Input Handling must be
    /// "Input Manager (Old)" or "Both". Move uses Horizontal and Vertical.
    /// Aim is the mouse on the ground plane.
    /// Unity 6: linearVelocity and linearDamping.
    /// </remarks>
    [DisallowMultipleComponent]
    [RequireComponent(typeof(Rigidbody))]
    [RequireComponent(typeof(CapsuleCollider))]
    public class TopDownMovement : MonoBehaviour
    {
        void ReadInput(out Vector2 move, out Vector2 look, out bool haveLook, out Vector2 mouse, out bool haveMouse)
        {
            move.x = Input.GetAxisRaw("Horizontal");
            move.y = Input.GetAxisRaw("Vertical");
            look = Vector2.zero;
            haveLook = false;
            mouse = Input.mousePosition;
            haveMouse = true;
        }

        [Header("Motion")]
        [SerializeField] float speed = 6f;
        [SerializeField] float acceleration = 35f;
        [SerializeField] float deceleration = 45f;

        [Tooltip("On for an isometric or yawed camera, so W is up the screen. Off uses world axes.")]
        [SerializeField] bool cameraRelative = true;

        [Tooltip("Camera used for movement axes and the mouse ray. Empty uses Camera.main.")]
        [SerializeField] Transform view;

        [Tooltip("Exponential rate for turning toward the aim. Zero snaps.")]
        [SerializeField] float turnSharpness = 14f;

        [SerializeField] float inputDeadzone = 0.15f;

        Rigidbody _body;
        CapsuleCollider _capsule;
        Transform _mainCamera;
        Vector2 _move;
        Vector2 _lastMouse;
        bool _mouseAims = true;
        Vector3 _aim = Vector3.forward;

        void Awake()
        {
            _body = GetComponent<Rigidbody>();
            _capsule = GetComponent<CapsuleCollider>();
            _body.useGravity = false;
            _body.linearDamping = 0f;
            _body.angularDamping = 0.05f;
            _body.interpolation = RigidbodyInterpolation.Interpolate;
            _body.collisionDetectionMode = CollisionDetectionMode.Continuous;
            _body.constraints = RigidbodyConstraints.FreezePositionY
                | RigidbodyConstraints.FreezeRotationX
                | RigidbodyConstraints.FreezeRotationZ;
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

            Vector3 forward = Vector3.ProjectOnPlane(transform.forward, Vector3.up);
            if (forward.sqrMagnitude > 0.0001f)
                _aim = forward.normalized;
        }

        void Update()
        {
            ReadInput(out _move, out Vector2 look, out bool haveLook, out Vector2 mouse, out bool haveMouse);
            _aim = ResolveAim(look, haveLook, mouse, haveMouse);
        }

        void FixedUpdate()
        {
            float dt = Time.fixedDeltaTime;
            Vector3 velocity = _body.linearVelocity;
            Vector3 horizontal = new Vector3(velocity.x, 0f, velocity.z);
            Vector3 wish = Wish(_move, out float magnitude);
            float rate = magnitude > 0f ? acceleration : deceleration;
            Vector3 next = Vector3.MoveTowards(horizontal, wish * (speed * magnitude), rate * dt);
            _body.linearVelocity = new Vector3(next.x, 0f, next.z);
            Face(dt);
        }

        Vector3 ResolveAim(Vector2 look, bool haveLook, Vector2 mouse, bool haveMouse)
        {
            if (haveLook && look.sqrMagnitude >= inputDeadzone * inputDeadzone)
            {
                _mouseAims = false;
                return Axes(look.normalized);
            }

            // The mouse takes over again only once it moves, so letting go of the right
            // stick keeps the aim instead of snapping to an idle cursor.
            if (haveMouse && mouse != _lastMouse)
                _mouseAims = true;
            _lastMouse = mouse;

            if (_mouseAims && haveMouse && TryMouseAim(mouse, out Vector3 at))
                return at;

            return _aim;
        }

        bool TryMouseAim(Vector2 screen, out Vector3 direction)
        {
            direction = Vector3.zero;
            Camera camera = Eye();
            if (camera == null)
                return false;

            Ray ray = camera.ScreenPointToRay(screen);
            Plane plane = new Plane(Vector3.up, new Vector3(0f, _body.position.y, 0f));
            if (!plane.Raycast(ray, out float distance))
                return false;

            Vector3 delta = ray.GetPoint(distance) - _body.position;
            delta.y = 0f;
            if (delta.sqrMagnitude < 0.0001f)
                return false;

            direction = delta.normalized;
            return true;
        }

        Vector3 Wish(Vector2 move, out float magnitude)
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
            return Axes(move.normalized);
        }

        Vector3 Axes(Vector2 direction)
        {
            Vector3 forward = PlanarForward();
            Vector3 right = Vector3.Cross(Vector3.up, forward);
            Vector3 result = right * direction.x + forward * direction.y;
            if (result.sqrMagnitude < 0.0001f)
                return Vector3.zero;
            return result.normalized;
        }

        Vector3 PlanarForward()
        {
            if (!cameraRelative)
                return Vector3.forward;

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

        Camera Eye()
        {
            Transform eyes = ViewTransform();
            if (eyes == null)
                return null;

            Camera camera = eyes.GetComponent<Camera>();
            if (camera == null)
                camera = eyes.GetComponentInChildren<Camera>();
            return camera != null ? camera : Camera.main;
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

        void Face(float dt)
        {
            Vector3 flat = _aim;
            flat.y = 0f;
            if (flat.sqrMagnitude < 0.0001f)
                return;

            Quaternion target = Quaternion.LookRotation(flat.normalized, Vector3.up);
            float blend = turnSharpness <= 0f || dt <= 0f ? 1f : 1f - Mathf.Exp(-turnSharpness * dt);
            _body.MoveRotation(Quaternion.Slerp(_body.rotation, target, blend));
        }

        void OnValidate()
        {
            speed = Mathf.Max(0f, speed);
            acceleration = Mathf.Max(0f, acceleration);
            deceleration = Mathf.Max(0f, deceleration);
            turnSharpness = Mathf.Max(0f, turnSharpness);
            inputDeadzone = Mathf.Clamp(inputDeadzone, 0f, 0.9f);
        }
    }
    ```

## 2D top-down

Same idea on `Rigidbody2D`. Gravity scale and linear damping are forced to zero. The sprite's nose is local `+Y`; the angle is `Atan2(aim) - 90` degrees. **Camera Relative** uses the camera's right and up on the XY plane, which matches a camera rolled about Z. A pitched 3D isometric camera is the 3D script above, not this one.

Add a `Rigidbody2D`, a collider, and `TopDownMovement2D`. Set **Interpolate**. Leave **Freeze Rotation** off: `MoveRotation` turns a 2D body by giving it angular velocity, so a frozen body never faces the aim. `Awake` clears it. **Collision Detection** is set to Continuous in `Awake`. One-way platforms and jumps are the [2D platformer](platformer-2d.md).

| Field | Default | Effect |
| --- | --- | --- |
| Speed | `6` | Units per second at a full stick. |
| Acceleration | `40` | Units per second squared toward the wish. |
| Deceleration | `50` | Units per second squared toward a stop. |
| Camera Relative | On | Move and the right stick use the camera's XY axes. |
| Turn Sharpness | `14` | Turn toward the aim. Zero snaps. |
| Input Deadzone | `0.15` | Sticks shorter than this are dropped. |

=== "Input System"

    ```csharp
    using UnityEngine;
    using UnityEngine.InputSystem;


    /// <summary>
    /// Top-down movement on a Rigidbody2D, with mouse or right-stick aim.
    /// </summary>
    /// <remarks>
    /// Input System. Gravity scale and linear damping are forced to zero.
    /// Unity 6: Rigidbody2D.linearVelocity and linearDamping.
    /// The sprite is assumed to face local +Y.
    /// </remarks>
    [DisallowMultipleComponent]
    [RequireComponent(typeof(Rigidbody2D))]
    public class TopDownMovement2D : MonoBehaviour
    {
        void ReadInput(out Vector2 move, out Vector2 look, out bool haveLook, out Vector2 mouse, out bool haveMouse)
        {
            move = Vector2.zero;
            look = Vector2.zero;
            haveLook = false;
            mouse = Vector2.zero;
            haveMouse = false;

            Keyboard keyboard = Keyboard.current;
            if (keyboard != null)
            {
                if (keyboard.dKey.isPressed) move.x += 1f;
                if (keyboard.aKey.isPressed) move.x -= 1f;
                if (keyboard.wKey.isPressed) move.y += 1f;
                if (keyboard.sKey.isPressed) move.y -= 1f;
            }

            Mouse pointer = Mouse.current;
            if (pointer != null)
            {
                mouse = pointer.position.ReadValue();
                haveMouse = true;
            }

            Gamepad gamepad = Gamepad.current;
            if (gamepad != null)
            {
                Vector2 stick = gamepad.leftStick.ReadValue();
                if (stick.sqrMagnitude > move.sqrMagnitude)
                    move = stick;
                look = gamepad.rightStick.ReadValue();
                haveLook = true;
            }
        }

        [SerializeField] float speed = 6f;
        [SerializeField] float acceleration = 40f;
        [SerializeField] float deceleration = 50f;
        [SerializeField] bool cameraRelative = true;
        [SerializeField] Transform view;
        [SerializeField] float turnSharpness = 14f;
        [SerializeField] float inputDeadzone = 0.15f;

        Rigidbody2D _body;
        Transform _mainCamera;
        Vector2 _move;
        Vector2 _lastMouse;
        bool _mouseAims = true;
        Vector2 _aim = Vector2.up;

        void Awake()
        {
            _body = GetComponent<Rigidbody2D>();
            _body.gravityScale = 0f;
            _body.linearDamping = 0f;
            _body.angularDamping = 0f;
            _body.interpolation = RigidbodyInterpolation2D.Interpolate;
            _body.collisionDetectionMode = CollisionDetectionMode2D.Continuous;
            // Rotation is not frozen: MoveRotation turns the body through angular velocity,
            // which a frozen body never gets. Face sets the angle every physics step.
            _body.constraints = RigidbodyConstraints2D.None;

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
            ReadInput(out _move, out Vector2 look, out bool haveLook, out Vector2 mouse, out bool haveMouse);
            _aim = ResolveAim(look, haveLook, mouse, haveMouse);
        }

        void FixedUpdate()
        {
            float dt = Time.fixedDeltaTime;
            Vector2 wish = Wish(_move, out float magnitude);
            float rate = magnitude > 0f ? acceleration : deceleration;
            Vector2 next = Vector2.MoveTowards(_body.linearVelocity, wish * (speed * magnitude), rate * dt);
            _body.linearVelocity = next;
            Face(dt);
        }

        Vector2 ResolveAim(Vector2 look, bool haveLook, Vector2 mouse, bool haveMouse)
        {
            if (haveLook && look.sqrMagnitude >= inputDeadzone * inputDeadzone)
            {
                _mouseAims = false;
                return Axes(look.normalized);
            }

            // The mouse takes over again only once it moves, so letting go of the right
            // stick keeps the aim instead of snapping to an idle cursor.
            if (haveMouse && mouse != _lastMouse)
                _mouseAims = true;
            _lastMouse = mouse;

            if (_mouseAims && haveMouse && TryMouseAim(mouse, out Vector2 at))
                return at;

            return _aim;
        }

        bool TryMouseAim(Vector2 screen, out Vector2 direction)
        {
            direction = Vector2.zero;
            Camera camera = Eye();
            if (camera == null)
                return false;

            float depth = Mathf.Abs(camera.transform.position.z - transform.position.z);
            Vector3 world = camera.ScreenToWorldPoint(new Vector3(screen.x, screen.y, depth));
            Vector2 delta = (Vector2)world - _body.position;
            if (delta.sqrMagnitude < 0.0001f)
                return false;

            direction = delta.normalized;
            return true;
        }

        Vector2 Wish(Vector2 move, out float magnitude)
        {
            magnitude = move.magnitude;
            if (magnitude > 1f)
                magnitude = 1f;
            if (magnitude < inputDeadzone || inputDeadzone >= 1f)
            {
                magnitude = 0f;
                return Vector2.zero;
            }

            magnitude = (magnitude - inputDeadzone) / (1f - inputDeadzone);
            return Axes(move.normalized);
        }

        Vector2 Axes(Vector2 direction)
        {
            Transform eyes = ViewTransform();
            Vector2 right = cameraRelative && eyes != null ? (Vector2)eyes.right : Vector2.right;
            Vector2 up = cameraRelative && eyes != null ? (Vector2)eyes.up : Vector2.up;
            Vector2 result = right * direction.x + up * direction.y;
            if (result.sqrMagnitude < 0.0001f)
                return Vector2.zero;
            return result.normalized;
        }

        Camera Eye()
        {
            Transform eyes = ViewTransform();
            if (eyes == null)
                return null;

            Camera camera = eyes.GetComponent<Camera>();
            if (camera == null)
                camera = eyes.GetComponentInChildren<Camera>();
            return camera != null ? camera : Camera.main;
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

        void Face(float dt)
        {
            if (_aim.sqrMagnitude < 0.0001f)
                return;

            float target = Mathf.Atan2(_aim.y, _aim.x) * Mathf.Rad2Deg - 90f;
            float blend = turnSharpness <= 0f || dt <= 0f ? 1f : 1f - Mathf.Exp(-turnSharpness * dt);
            _body.MoveRotation(Mathf.LerpAngle(_body.rotation, target, blend));
        }

        void OnValidate()
        {
            speed = Mathf.Max(0f, speed);
            acceleration = Mathf.Max(0f, acceleration);
            deceleration = Mathf.Max(0f, deceleration);
            turnSharpness = Mathf.Max(0f, turnSharpness);
            inputDeadzone = Mathf.Clamp(inputDeadzone, 0f, 0.9f);
        }
    }
    ```

=== "Legacy Input Manager"

    ```csharp
    using UnityEngine;


    /// <summary>
    /// Top-down movement on a Rigidbody2D, with mouse aim.
    /// </summary>
    /// <remarks>
    /// Legacy Input Manager. Move uses Horizontal and Vertical.
    /// Aim is the mouse. Gravity scale and linear damping are forced to zero.
    /// Unity 6: Rigidbody2D.linearVelocity and linearDamping.
    /// The sprite is assumed to face local +Y.
    /// </remarks>
    [DisallowMultipleComponent]
    [RequireComponent(typeof(Rigidbody2D))]
    public class TopDownMovement2D : MonoBehaviour
    {
        void ReadInput(out Vector2 move, out Vector2 look, out bool haveLook, out Vector2 mouse, out bool haveMouse)
        {
            move.x = Input.GetAxisRaw("Horizontal");
            move.y = Input.GetAxisRaw("Vertical");
            look = Vector2.zero;
            haveLook = false;
            mouse = Input.mousePosition;
            haveMouse = true;
        }

        [SerializeField] float speed = 6f;
        [SerializeField] float acceleration = 40f;
        [SerializeField] float deceleration = 50f;
        [SerializeField] bool cameraRelative = true;
        [SerializeField] Transform view;
        [SerializeField] float turnSharpness = 14f;
        [SerializeField] float inputDeadzone = 0.15f;

        Rigidbody2D _body;
        Transform _mainCamera;
        Vector2 _move;
        Vector2 _lastMouse;
        bool _mouseAims = true;
        Vector2 _aim = Vector2.up;

        void Awake()
        {
            _body = GetComponent<Rigidbody2D>();
            _body.gravityScale = 0f;
            _body.linearDamping = 0f;
            _body.angularDamping = 0f;
            _body.interpolation = RigidbodyInterpolation2D.Interpolate;
            _body.collisionDetectionMode = CollisionDetectionMode2D.Continuous;
            // Rotation is not frozen: MoveRotation turns the body through angular velocity,
            // which a frozen body never gets. Face sets the angle every physics step.
            _body.constraints = RigidbodyConstraints2D.None;

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
            ReadInput(out _move, out Vector2 look, out bool haveLook, out Vector2 mouse, out bool haveMouse);
            _aim = ResolveAim(look, haveLook, mouse, haveMouse);
        }

        void FixedUpdate()
        {
            float dt = Time.fixedDeltaTime;
            Vector2 wish = Wish(_move, out float magnitude);
            float rate = magnitude > 0f ? acceleration : deceleration;
            Vector2 next = Vector2.MoveTowards(_body.linearVelocity, wish * (speed * magnitude), rate * dt);
            _body.linearVelocity = next;
            Face(dt);
        }

        Vector2 ResolveAim(Vector2 look, bool haveLook, Vector2 mouse, bool haveMouse)
        {
            if (haveLook && look.sqrMagnitude >= inputDeadzone * inputDeadzone)
            {
                _mouseAims = false;
                return Axes(look.normalized);
            }

            // The mouse takes over again only once it moves, so letting go of the right
            // stick keeps the aim instead of snapping to an idle cursor.
            if (haveMouse && mouse != _lastMouse)
                _mouseAims = true;
            _lastMouse = mouse;

            if (_mouseAims && haveMouse && TryMouseAim(mouse, out Vector2 at))
                return at;

            return _aim;
        }

        bool TryMouseAim(Vector2 screen, out Vector2 direction)
        {
            direction = Vector2.zero;
            Camera camera = Eye();
            if (camera == null)
                return false;

            float depth = Mathf.Abs(camera.transform.position.z - transform.position.z);
            Vector3 world = camera.ScreenToWorldPoint(new Vector3(screen.x, screen.y, depth));
            Vector2 delta = (Vector2)world - _body.position;
            if (delta.sqrMagnitude < 0.0001f)
                return false;

            direction = delta.normalized;
            return true;
        }

        Vector2 Wish(Vector2 move, out float magnitude)
        {
            magnitude = move.magnitude;
            if (magnitude > 1f)
                magnitude = 1f;
            if (magnitude < inputDeadzone || inputDeadzone >= 1f)
            {
                magnitude = 0f;
                return Vector2.zero;
            }

            magnitude = (magnitude - inputDeadzone) / (1f - inputDeadzone);
            return Axes(move.normalized);
        }

        Vector2 Axes(Vector2 direction)
        {
            Transform eyes = ViewTransform();
            Vector2 right = cameraRelative && eyes != null ? (Vector2)eyes.right : Vector2.right;
            Vector2 up = cameraRelative && eyes != null ? (Vector2)eyes.up : Vector2.up;
            Vector2 result = right * direction.x + up * direction.y;
            if (result.sqrMagnitude < 0.0001f)
                return Vector2.zero;
            return result.normalized;
        }

        Camera Eye()
        {
            Transform eyes = ViewTransform();
            if (eyes == null)
                return null;

            Camera camera = eyes.GetComponent<Camera>();
            if (camera == null)
                camera = eyes.GetComponentInChildren<Camera>();
            return camera != null ? camera : Camera.main;
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

        void Face(float dt)
        {
            if (_aim.sqrMagnitude < 0.0001f)
                return;

            float target = Mathf.Atan2(_aim.y, _aim.x) * Mathf.Rad2Deg - 90f;
            float blend = turnSharpness <= 0f || dt <= 0f ? 1f : 1f - Mathf.Exp(-turnSharpness * dt);
            _body.MoveRotation(Mathf.LerpAngle(_body.rotation, target, blend));
        }

        void OnValidate()
        {
            speed = Mathf.Max(0f, speed);
            acceleration = Mathf.Max(0f, acceleration);
            deceleration = Mathf.Max(0f, deceleration);
            turnSharpness = Mathf.Max(0f, turnSharpness);
            inputDeadzone = Mathf.Clamp(inputDeadzone, 0f, 0.9f);
        }
    }
    ```

!!! warning "Common pitfalls"

    Do not parent the camera to the body. The body yaws to aim, and a child camera yaws with it, so the mouse ray and the camera-relative axes spin. The [orbit camera](../cameras/third-person.md) stays unparented; this page wants the same.

    **Linear Damping** is forced to zero. A leftover drag value stacks with **Deceleration** and the stick never quite reaches **Speed**. **Interpolate** is what keeps a follow camera from stepping at the physics rate. Leave **Use Gravity** off on the 3D body, and **Gravity Scale** at zero on the 2D body. Freezing position Y is the 3D lock; gravity on top of that fights the constraint.

    The mouse plane is infinite and horizontal through the body. It does not know about walls, pits, or a raised ledge. A camera that looks along the plane, rather than down at it, misses the ray and the aim sticks.

    The right stick wins over the mouse as soon as it leaves the dead zone. A gamepad with a drifting stick will ignore the mouse. Raise **Input Deadzone**, or centre the stick.

    The 2D script's camera-relative axes are the camera's right and up, with Z dropped. That matches a camera rolled on Z. A camera pitched down in 3D for an isometric look belongs on `TopDownMovement`, not on the 2D variant.

    `MoveRotation` is the turn interpolation follows. Setting `transform.rotation` on a dynamic body snaps between physics steps.

    Copy one 3D listing and, if you need it, one 2D listing. The two 3D tabs are the same class. The two 2D tabs are the other class.
