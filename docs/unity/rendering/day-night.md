---
engine: Unity
version: 6+
package: URP 17.x
---

# Day and night cycle

A clock that runs a game day in a few real minutes, and a lighting rig that follows it: one directional light that is the sun by day and the moon by night, colour and intensity from curves, gradient ambient light, fog, and a procedural skybox. Other systems listen to the clock for dawn and dusk, such as street lamps switching on.

## The clock

Time of day is a number \(t \in [0, 1)\): 0 is midnight, 0.25 is 06:00, 0.5 is noon, 0.75 is 18:00. With a day lasting \(D\) real minutes,

\[
t \leftarrow \bigl(t + \Delta t / (60 D)\bigr) \bmod 1
\]

A 24-minute day is one game hour per real minute. The clock raises `HourChanged` on each whole hour, and `NightChanged` when \(t\) crosses **Dusk** or **Dawn**, so listeners do not poll.

## The sun's path

The sun turns once per day about an east–west axis. Its pitch below or above the horizon is

\[
\theta = 360°\,t - 90°
\]

so it is on the horizon at 06:00 (\(\theta = 0°\)), straight overhead at noon (\(90°\)), and straight below at midnight. A **Tilt** rotates that circle away from vertical, as latitude does, so the noon sun is not directly overhead and shadows never quite vanish. **Yaw** turns the whole path to choose where east is.

```text
sun rotation = Euler(0, yaw, 0) * Euler(0, 0, tilt) * AngleAxis(360 t - 90, right)
```

### One light, two bodies

URP casts shadows from one main directional light. Rather than a second directional light for the moon, the same light flips to the opposite direction at night, with the moon's colour and a low intensity:

\[
\text{light direction} =
\begin{cases}
\text{sun} & \text{while the sun is above the horizon} \\
\text{sun rotated } 180° & \text{otherwise}
\end{cases}
\]

The flip happens at the horizon, where the intensity curve is near zero, so it is not visible. The intensity curve has two humps, a tall one for the day and a low one for the night, and dips to almost nothing at dawn and dusk.

### Shadow shimmer

A light that rotates a little every frame makes shadow edges crawl, because the shadow map's texels move across surfaces. The rig rotates the light in steps of **Rotation Step** degrees instead. At a 24-minute day, the sun moves 0.25° a second; a 0.1° step updates it a few times a second, and the shimmer becomes occasional small jumps.

## Ambient, fog, and sky

| What | Driven by | Set on |
| --- | --- | --- |
| Light colour | Gradient over \(t\) | the directional light |
| Light intensity | Curve over \(t\) | the directional light |
| Ambient sky, equator, ground | Three gradients over \(t\) | `RenderSettings`, in **Gradient** ambient mode |
| Fog colour | Gradient over \(t\) | `RenderSettings.fogColor` |
| Sky brightness | Curve over \(t\) | the skybox material's `_Exposure` |

The **Skybox/Procedural** shader draws its sun disc from the scene's sun source, `RenderSettings.sun`, so the rig assigns its light there. It also reads that light's direction, so at night the disc becomes a moon in the right place.

Gradient ambient mode is used because it updates instantly. **Skybox** ambient mode would need `DynamicGI.UpdateEnvironment()` to recompute the ambient probe, which is too slow to call every frame. Reflection probes are similar: a baked probe keeps showing the daytime sky. Use a realtime probe refreshed every few seconds, or a dim, neutral baked one.

## Setup

1. Use one **Directional Light**. Set its **Mode** to **Realtime**. Baked direct light cannot move with the sun.
2. In **Window → Rendering → Lighting → Environment**, set the skybox to a material using **Skybox/Procedural**, and **Environment Lighting → Source** to **Gradient**.
3. Put `TimeOfDay` on a manager object. Set **Day Length Minutes** and **Start Time**.
4. Put `DayNightLighting` on the same object. Assign the light, then shape the gradients and curves. The defaults on the component are a starting point: a warm noon, orange horizons, and a dim blue night.
5. For lamps and windows, put `NightToggle` on each, with the objects to switch on at night.
6. Fog is optional. Turn it on in the Lighting window; the rig only changes its colour.

## Scripts

### Time of day

```csharp
using System;
using UnityEngine;

/// <summary>
/// A game clock: 0 is midnight, 0.5 is noon. Raises events on each hour and at dusk and dawn.
/// </summary>
public class TimeOfDay : MonoBehaviour
{
    [Tooltip("Real minutes for one full game day.")]
    [Min(0.1f)] [SerializeField] float dayLengthMinutes = 24f;
    [Range(0f, 1f)] [SerializeField] float startTime = 0.3f;
    [SerializeField] bool paused;

    [Header("Night")]
    [Tooltip("Night starts here. 0.78 is about 18:43.")]
    [Range(0f, 1f)] [SerializeField] float dusk = 0.78f;
    [Tooltip("Night ends here. 0.24 is about 05:46.")]
    [Range(0f, 1f)] [SerializeField] float dawn = 0.24f;

    public event Action<int> HourChanged;
    public event Action<bool> NightChanged;

    /// <summary>0 to 1. 0 is midnight.</summary>
    public float Normalized { get; private set; }
    public float Hours => Normalized * 24f;
    public bool IsNight { get; private set; }

    public bool Paused
    {
        get => paused;
        set => paused = value;
    }

    int _hour;

    void Awake()
    {
        SetTime(startTime);
    }

    /// <summary>Jumps the clock, for example after sleeping. Raises the events if they changed.</summary>
    public void SetTime(float normalized)
    {
        Normalized = Mathf.Repeat(normalized, 1f);
        UpdateEvents();
    }

    void Update()
    {
        if (paused)
            return;

        Normalized = Mathf.Repeat(Normalized + Time.deltaTime / (dayLengthMinutes * 60f), 1f);
        UpdateEvents();
    }

    void UpdateEvents()
    {
        int hour = Mathf.FloorToInt(Hours);
        if (hour != _hour)
        {
            _hour = hour;
            HourChanged?.Invoke(hour);
        }

        // Night wraps past midnight: dusk is after dawn in the day.
        bool night = Normalized >= dusk || Normalized < dawn;
        if (night != IsNight)
        {
            IsNight = night;
            NightChanged?.Invoke(night);
        }
    }
}
```

### Lighting rig

```csharp
using UnityEngine;
using UnityEngine.Rendering;

/// <summary>
/// Drives one directional light, ambient light, fog, and a procedural skybox from a TimeOfDay.
/// </summary>
[RequireComponent(typeof(TimeOfDay))]
public class DayNightLighting : MonoBehaviour
{
    [SerializeField] Light sun;

    [Header("Path")]
    [Tooltip("Turns the path about world up. Chooses where the sun rises.")]
    [SerializeField] float yaw = -30f;
    [Tooltip("Tilts the path away from vertical, like latitude.")]
    [Range(-60f, 60f)] [SerializeField] float tilt = 25f;
    [Tooltip("Degrees between light rotations. Larger steps shimmer less.")]
    [Min(0f)] [SerializeField] float rotationStep = 0.1f;

    [Header("Light")]
    [SerializeField] Gradient sunColor = DefaultSunColor();
    [SerializeField] Color moonColor = new Color(0.55f, 0.65f, 1f);
    [Tooltip("Intensity over the day. Near zero at dawn and dusk hides the sun-moon swap.")]
    [SerializeField] AnimationCurve intensity = DefaultIntensity();

    [Header("Environment")]
    [SerializeField] Gradient ambientSky = Flat(new Color(0.05f, 0.07f, 0.12f), new Color(0.55f, 0.65f, 0.8f));
    [SerializeField] Gradient ambientEquator = Flat(new Color(0.04f, 0.05f, 0.08f), new Color(0.45f, 0.45f, 0.45f));
    [SerializeField] Gradient ambientGround = Flat(new Color(0.02f, 0.02f, 0.03f), new Color(0.2f, 0.18f, 0.15f));
    [SerializeField] Gradient fogColor = Flat(new Color(0.03f, 0.04f, 0.07f), new Color(0.6f, 0.7f, 0.8f));
    [SerializeField] AnimationCurve skyExposure = DefaultExposure();

    static readonly int ExposureId = Shader.PropertyToID("_Exposure");

    TimeOfDay _clock;
    Material _sky;
    float _lastAngle = float.NaN;

    void Awake()
    {
        _clock = GetComponent<TimeOfDay>();

        // A copy, so the skybox asset is not edited in Play mode.
        if (RenderSettings.skybox != null)
        {
            _sky = new Material(RenderSettings.skybox);
            RenderSettings.skybox = _sky;
        }

        RenderSettings.ambientMode = AmbientMode.Trilight;
        if (sun != null)
            RenderSettings.sun = sun;
    }

    void OnDestroy()
    {
        if (_sky != null)
            Destroy(_sky);
    }

    void LateUpdate()
    {
        if (sun == null)
            return;

        float t = _clock.Normalized;
        float angle = t * 360f - 90f;
        bool sunUp = angle > 0f && angle < 180f;

        // Step the rotation to reduce shadow shimmer. Always apply on the first frame.
        if (float.IsNaN(_lastAngle) || Mathf.Abs(Mathf.DeltaAngle(angle, _lastAngle)) >= rotationStep)
        {
            _lastAngle = angle;
            float lightAngle = sunUp ? angle : angle + 180f;
            sun.transform.rotation =
                Quaternion.Euler(0f, yaw, 0f) * Quaternion.Euler(0f, 0f, tilt) * Quaternion.AngleAxis(lightAngle, Vector3.right);
        }

        sun.color = sunUp ? sunColor.Evaluate(t) : moonColor;
        sun.intensity = Mathf.Max(0f, intensity.Evaluate(t));
        sun.enabled = sun.intensity > 0.001f;

        RenderSettings.ambientSkyColor = ambientSky.Evaluate(DayBlend(t));
        RenderSettings.ambientEquatorColor = ambientEquator.Evaluate(DayBlend(t));
        RenderSettings.ambientGroundColor = ambientGround.Evaluate(DayBlend(t));
        RenderSettings.fogColor = fogColor.Evaluate(DayBlend(t));

        if (_sky != null && _sky.HasProperty(ExposureId))
            _sky.SetFloat(ExposureId, skyExposure.Evaluate(t));
    }

    /// <summary>0 at midnight, 1 at noon, smooth between. For gradients that go night to day.</summary>
    static float DayBlend(float t)
    {
        return 0.5f - 0.5f * Mathf.Cos(t * 2f * Mathf.PI);
    }

    static Gradient Flat(Color night, Color day)
    {
        Gradient gradient = new Gradient();
        gradient.SetKeys(
            new[] { new GradientColorKey(night, 0f), new GradientColorKey(day, 1f) },
            new[] { new GradientAlphaKey(1f, 0f), new GradientAlphaKey(1f, 1f) });
        return gradient;
    }

    static Gradient DefaultSunColor()
    {
        Gradient gradient = new Gradient();
        gradient.SetKeys(
            new[]
            {
                new GradientColorKey(new Color(1f, 0.45f, 0.2f), 0.25f),
                new GradientColorKey(new Color(1f, 0.95f, 0.85f), 0.35f),
                new GradientColorKey(new Color(1f, 0.97f, 0.92f), 0.5f),
                new GradientColorKey(new Color(1f, 0.95f, 0.85f), 0.65f),
                new GradientColorKey(new Color(1f, 0.4f, 0.15f), 0.75f)
            },
            new[] { new GradientAlphaKey(1f, 0f), new GradientAlphaKey(1f, 1f) });
        return gradient;
    }

    static AnimationCurve DefaultIntensity()
    {
        return new AnimationCurve(
            new Keyframe(0f, 0.15f), new Keyframe(0.24f, 0.01f), new Keyframe(0.26f, 0.05f),
            new Keyframe(0.5f, 1.3f), new Keyframe(0.74f, 0.05f), new Keyframe(0.76f, 0.01f),
            new Keyframe(1f, 0.15f));
    }

    static AnimationCurve DefaultExposure()
    {
        return new AnimationCurve(
            new Keyframe(0f, 0.15f), new Keyframe(0.25f, 0.6f), new Keyframe(0.5f, 1.3f),
            new Keyframe(0.75f, 0.6f), new Keyframe(1f, 0.15f));
    }
}
```

### Night toggle

```csharp
using UnityEngine;

/// <summary>
/// Switches objects on at night and off by day: lamps, lit windows, fireflies.
/// </summary>
public class NightToggle : MonoBehaviour
{
    [SerializeField] TimeOfDay clock;
    [SerializeField] GameObject[] onAtNight = System.Array.Empty<GameObject>();

    void OnEnable()
    {
        if (clock == null)
            clock = FindAnyObjectByType<TimeOfDay>();
        if (clock == null)
            return;

        clock.NightChanged += Apply;
        Apply(clock.IsNight);
    }

    void OnDisable()
    {
        if (clock != null)
            clock.NightChanged -= Apply;
    }

    void Apply(bool night)
    {
        foreach (GameObject target in onAtNight)
        {
            if (target != null)
                target.SetActive(night);
        }
    }
}
```

`FindAnyObjectByType` is only a fallback for a lamp placed without a reference. Assign the clock in prefabs that are spawned in numbers.

!!! warning "Common pitfalls"

    A directional light set to **Baked** or **Mixed** keeps its baked contribution where it was baked. Use **Realtime** for a moving sun, or bake a few lighting scenarios with Adaptive Probe Volumes and blend them.

    **Skybox** ambient mode does not follow the sky as it changes. Use **Gradient** mode, or call `DynamicGI.UpdateEnvironment()` rarely, such as once per game hour.

    Editing `RenderSettings.skybox` directly changes the material asset in the editor. The rig copies it first.

    Long shadows at dawn and dusk need a larger shadow distance or more cascades, or they cut off near the camera. A sun just above the horizon also makes shadow acne; raise the light's depth bias slightly.

    Night that is too dark is unplayable, and night that is just blue is not night. Keep enough ambient to read the ground, and let lamps do the rest.
