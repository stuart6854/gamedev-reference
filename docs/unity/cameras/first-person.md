---
engine: Unity
version: 6+
---

# First-person camera

Mouse and right-stick look, a pitch clamp, cursor lock, and a head bob driven by how far the body actually moved. The camera is not parented to the body. It follows the body's position in `LateUpdate` and owns the yaw, and the body is turned to match. That one arrangement works for both the [CharacterController](../mechanics/character-movement.md) and the [Rigidbody](../mechanics/rigidbody-movement.md) controllers.

Cinemachine is not used here. A first-person view is one transform at the eyes. Cinemachine adds blending between cameras, which a cutscene needs and plain look does not. The third-person rig with Cinemachine is the [orbit camera](third-person.md).

## Setup

1. Put the **Camera** at the top level of the scene, not under the player. Set its **Near** clip plane to about `0.05`, so walls do not clip away when the player presses against them.
2. Add `FirstPersonLook` to the camera. Assign the player root as **Body**. Set **Eye Height** to the eyes above the body's pivot: `1.6` for the default 2 m capsule with its pivot at the feet.
3. Copy one `LookInput` listing, Input System or legacy, not both. They declare the same class.
4. On the movement script, assign this camera as **View** and turn **Rotate Towards Move** off. The camera turns the body now. With both on they fight.
5. Press Play. The cursor locks. **Escape** frees it and a left click locks it again.

## What each step is doing

`Update` reads the look input and adds it to a stored yaw and pitch. Storing the two angles, rather than reading `transform.eulerAngles` back, keeps the pitch clamp exact. Euler angles read back from a rotation come out in `[0, 360)` and may swap representation near the poles. The camera's rotation is written straight away. A `CharacterController` body is turned in the same `Update`. A `Rigidbody` body is turned with `MoveRotation` in `FixedUpdate`, which is the physics step and keeps interpolation smooth.

`[DefaultExecutionOrder(-50)]` runs this `Update` before the movement script's. Movement builds its wish direction from the camera's yaw, so the turn and the move land on the same frame. The reason that needs an attribute is on the [MonoBehaviour lifecycle](../architecture/lifecycle.md#execution-order) page.

Mouse delta is the distance the pointer moved this frame, in pixels. It is already per frame, so it is **not** multiplied by `Time.deltaTime`. The stick is a rate, so it is. Sensitivity is degrees per pixel for the mouse, and degrees per second at full deflection for the stick.

`LateUpdate` places the camera at the body plus **Eye Height** plus the bob. By `LateUpdate` the controller has moved, and an interpolated `Rigidbody` has its render pose, so the eyes never trail the body by a frame.

### Head bob

The bob is driven by distance, not time. Each **Stride Length** of horizontal travel is one full cycle, which is two footsteps:

\[
\varphi \mathrel{+}= 2\pi \, \frac{d}{\text{stride}}, \qquad
\text{offset} = A\,w \left( \sin(2\varphi)\,\hat{u} + \tfrac{1}{2}\sin(\varphi)\,\hat{r} \right)
\]

\(\hat{u}\) is up and \(\hat{r}\) is the camera's flat right. The vertical term dips once per step, and the sideways term sways once per stride. The weight \(w\) eases toward the horizontal speed divided by **Bob Full Speed**, using the [exponential blend](../../maths/interpolation.md#frame-rate-independent-damping), so the bob fades in as the player starts walking and out when they stop. Running covers more distance per second, so the steps come faster without a separate frequency setting.

## Parameters

| Field | Default | Effect |
| --- | --- | --- |
| Body | Empty | Root the camera follows and turns. |
| Eye Height | `1.6` | Metres above the body's pivot. |
| Mouse Sensitivity | `0.1` | Degrees per pixel of mouse movement. |
| Stick Speed | `180` | Degrees per second at full right-stick deflection. |
| Invert Y | Off | Pushing up looks down. |
| Min / Max Pitch | `-85` / `85` | Clamp in degrees. Negative is up in Unity's pitch. |
| Lock Cursor | On | Lock and hide the cursor while looking. |
| Bob Amplitude | `0.04` | Metres. `0` turns the bob off. |
| Stride Length | `1.6` | Metres of travel per full bob cycle, two steps. |
| Bob Full Speed | `4.5` | Horizontal speed at which the bob reaches full amplitude. |
| Bob Sharpness | `10` | How quickly the bob fades in and out. |

## Scripts

### Look input

Each listing is the input side only. `FirstPersonLook` below is the same for both.

=== "Input System"

    ```csharp
    using UnityEngine;
    using UnityEngine.InputSystem;

    /// <summary>
    /// Look input for the Input System. Mouse delta is pixels this frame.
    /// </summary>
    public static class LookInput
    {
        public static Vector2 MouseDelta()
        {
            Mouse mouse = Mouse.current;
            return mouse != null ? mouse.delta.ReadValue() : Vector2.zero;
        }

        public static Vector2 Stick()
        {
            Gamepad gamepad = Gamepad.current;
            return gamepad != null ? gamepad.rightStick.ReadValue() : Vector2.zero;
        }

        public static bool ReleaseCursorPressed()
        {
            Keyboard keyboard = Keyboard.current;
            return keyboard != null && keyboard.escapeKey.wasPressedThisFrame;
        }

        public static bool CaptureCursorPressed()
        {
            Mouse mouse = Mouse.current;
            return mouse != null && mouse.leftButton.wasPressedThisFrame;
        }
    }
    ```

=== "Legacy Input Manager"

    `Mouse X` and `Mouse Y` are the pointer delta times the axis **Sensitivity**, which is `0.1` by default in the Input Manager. Dividing by that gives pixels, so the same **Mouse Sensitivity** works with either listing. The Input Manager has no default right-stick axis.

    ```csharp
    using UnityEngine;

    /// <summary>
    /// Look input for the legacy Input Manager, returned in pixels like the Input System.
    /// </summary>
    public static class LookInput
    {
        const float AxisSensitivity = 0.1f; // Input Manager default for Mouse X and Mouse Y.

        public static Vector2 MouseDelta()
        {
            return new Vector2(Input.GetAxisRaw("Mouse X"), Input.GetAxisRaw("Mouse Y")) / AxisSensitivity;
        }

        public static Vector2 Stick()
        {
            return Vector2.zero;
        }

        public static bool ReleaseCursorPressed()
        {
            return Input.GetKeyDown(KeyCode.Escape);
        }

        public static bool CaptureCursorPressed()
        {
            return Input.GetMouseButtonDown(0);
        }
    }
    ```

### First-person look

```csharp
using UnityEngine;

/// <summary>
/// First-person look on an unparented camera. Owns yaw and pitch, follows the body,
/// turns the body to the yaw, and adds a distance-driven head bob.
/// </summary>
[DefaultExecutionOrder(-50)]
[DisallowMultipleComponent]
public class FirstPersonLook : MonoBehaviour
{
    [SerializeField] Transform body;
    [SerializeField] float eyeHeight = 1.6f;

    [Header("Look")]
    [Tooltip("Degrees per pixel of mouse movement.")]
    [SerializeField] float mouseSensitivity = 0.1f;
    [Tooltip("Degrees per second at full right-stick deflection.")]
    [SerializeField] float stickSpeed = 180f;
    [SerializeField] bool invertY;
    [SerializeField] float minPitch = -85f;
    [SerializeField] float maxPitch = 85f;
    [SerializeField] bool lockCursor = true;

    [Header("Head bob")]
    [SerializeField] float bobAmplitude = 0.04f;
    [Tooltip("Metres of travel per full cycle, which is two steps.")]
    [SerializeField] float strideLength = 1.6f;
    [SerializeField] float bobFullSpeed = 4.5f;
    [SerializeField] float bobSharpness = 10f;

    Rigidbody _bodyRigidbody;
    float _yaw;
    float _pitch;
    Vector3 _lastBodyPosition;
    float _phase;
    float _bobWeight;

    public float Yaw => _yaw;
    public float Pitch => _pitch;

    void Awake()
    {
        if (body != null)
        {
            _bodyRigidbody = body.GetComponent<Rigidbody>();
            _yaw = body.eulerAngles.y;
            _lastBodyPosition = body.position;
        }
    }

    void OnEnable()
    {
        if (lockCursor)
            SetCursorLocked(true);
    }

    void OnDisable()
    {
        if (lockCursor)
            SetCursorLocked(false);
    }

    void Update()
    {
        bool looking = true;
        if (lockCursor)
        {
            if (LookInput.ReleaseCursorPressed())
                SetCursorLocked(false);
            else if (Cursor.lockState != CursorLockMode.Locked && LookInput.CaptureCursorPressed())
                SetCursorLocked(true);
            looking = Cursor.lockState == CursorLockMode.Locked;
        }

        // The mouse is already per frame. The stick is a rate, so it is scaled by time.
        Vector2 look = LookInput.Stick() * (stickSpeed * Time.unscaledDeltaTime);
        if (looking)
            look += LookInput.MouseDelta() * mouseSensitivity;

        _yaw = Mathf.Repeat(_yaw + look.x, 360f);
        _pitch = Mathf.Clamp(_pitch + (invertY ? look.y : -look.y), minPitch, maxPitch);

        transform.rotation = Quaternion.Euler(_pitch, _yaw, 0f);
        if (body != null && _bodyRigidbody == null)
            body.rotation = Quaternion.Euler(0f, _yaw, 0f);
    }

    void FixedUpdate()
    {
        if (_bodyRigidbody != null)
            _bodyRigidbody.MoveRotation(Quaternion.Euler(0f, _yaw, 0f));
    }

    void LateUpdate()
    {
        if (body == null)
            return;

        Vector3 position = body.position + Vector3.up * eyeHeight + HeadBob(Time.deltaTime);
        transform.SetPositionAndRotation(position, Quaternion.Euler(_pitch, _yaw, 0f));
    }

    Vector3 HeadBob(float dt)
    {
        Vector3 moved = body.position - _lastBodyPosition;
        _lastBodyPosition = body.position;
        if (bobAmplitude <= 0f || dt <= 0f)
            return Vector3.zero;

        moved.y = 0f;
        float distance = moved.magnitude;
        float speed = distance / dt;

        float target = bobFullSpeed > 0f ? Mathf.Clamp01(speed / bobFullSpeed) : 0f;
        float blend = bobSharpness <= 0f ? 1f : 1f - Mathf.Exp(-bobSharpness * dt);
        _bobWeight = Mathf.Lerp(_bobWeight, target, blend);

        if (strideLength > 0f)
            _phase = Mathf.Repeat(_phase + distance / strideLength * 2f * Mathf.PI, 2f * Mathf.PI);

        Vector3 right = Quaternion.Euler(0f, _yaw, 0f) * Vector3.right;
        float amplitude = bobAmplitude * _bobWeight;
        return Vector3.up * (Mathf.Sin(2f * _phase) * amplitude)
            + right * (Mathf.Sin(_phase) * amplitude * 0.5f);
    }

    /// <summary>Snap the stored angles, for a respawn or a cutscene handing control back.</summary>
    public void SetAngles(float yaw, float pitch)
    {
        _yaw = Mathf.Repeat(yaw, 360f);
        _pitch = Mathf.Clamp(pitch, minPitch, maxPitch);
        if (body != null)
            _lastBodyPosition = body.position;
    }

    static void SetCursorLocked(bool locked)
    {
        Cursor.lockState = locked ? CursorLockMode.Locked : CursorLockMode.None;
        Cursor.visible = !locked;
    }

    void OnValidate()
    {
        mouseSensitivity = Mathf.Max(0f, mouseSensitivity);
        stickSpeed = Mathf.Max(0f, stickSpeed);
        minPitch = Mathf.Clamp(minPitch, -89f, 0f);
        maxPitch = Mathf.Clamp(maxPitch, 0f, 89f);
        bobAmplitude = Mathf.Max(0f, bobAmplitude);
        strideLength = Mathf.Max(0.01f, strideLength);
    }
}
```

!!! warning "Common pitfalls"

    Multiplying mouse delta by `Time.deltaTime` makes sensitivity depend on frame rate: the same hand movement turns half as far at 120 fps as at 60 fps. Only the stick is a rate.

    A camera parented to a `Rigidbody` that is turned with `MoveRotation` turns on physics steps, not frames, and the view judders. Keep the camera unparented, as here, and let it own the yaw.

    **Rotate Towards Move** on the movement script also turns the body. With it on, the body faces the move while the camera faces the look, and strafing spins the player. Turn it off.

    Pitch near `±90` makes yaw spin around the view axis, and some movement code that flattens the camera forward gets a zero vector. The clamp stops at `85` for that reason.

    The bob runs whenever the body moves sideways, including mid-air. If that shows, expose the controller's grounded flag (`_grounded` on [character movement](../mechanics/character-movement.md)) and multiply the bob target by it.

    A teleport moves the body a long way in one frame, and the bob phase jumps. Call `SetAngles` after a teleport. It also resets the distance baseline.

    In a WebGL build the browser only allows a pointer lock from a click. The lock in `OnEnable` is refused there, and the first click locks it.
