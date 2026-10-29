---
engine: Unity
version: 6+
package: URP 17.x
---

# Post-processing with volumes

URP's built-in post-processing: bloom, tonemapping, colour grading, vignette, depth of field, and the rest. Effects live in Volume Profiles, scene Volumes decide which profile applies where, and gameplay changes the look by moving a volume's weight or editing a profile. Writing your own full-screen effect is a different topic, URP renderer features, which is still on the [roadmap](../../roadmap.md#presentation).

URP does not use the Post Processing Stack v2 package. Do not install it in a URP project.

## How volumes combine

A **Volume** component references a **Volume Profile** asset. A profile holds **Volume Overrides**, one per effect, such as Bloom or Vignette. Each property inside an override has its own checkbox: only ticked properties take part. An unticked property falls through to the volumes below.

Every frame, for each camera, URP takes the enabled Volumes on layers in the camera's **Volume Mask** and blends them:

| Setting | Effect |
| --- | --- |
| **Mode: Global** | Affects the camera everywhere. |
| **Mode: Local** | Affects the camera only near a Collider on the same GameObject. The **Volume** menu's Box, Sphere, and Convex Mesh Volume objects come with one. |
| **Blend Distance** | Local only. How far outside the collider the volume starts fading in. 0 switches it on at the boundary. |
| **Weight** | A 0 to 1 multiplier on the volume's influence. This is the knob scripts usually turn. |
| **Priority** | When volumes override the same property, the higher priority wins. |

Under every scene volume sit two defaults, at the lowest priority:

- The project's **Default Volume Profile**, in **Project Settings → Graphics → URP**.
- The active **URP Asset**'s **Volumes → Volume Profile**, which can differ per quality level.

URP evaluates and caches those two only when a scene loads or the quality level changes. A script that edits them at runtime sees no change. Put runtime-controlled effects in a scene volume instead.

The camera's position decides which local volumes apply. A third-person camera can set **Volume Trigger** to the character's transform, so the effects follow the character into a cave or under water, not the camera behind it.

## Setup

1. Select the camera. Under **Rendering**, tick **Post Processing**. New scenes have it off.
2. Add **GameObject → Volume → Global Volume**. Select **New** to create its profile.
3. **Add Override** for each effect, and tick the properties to change.
4. For bloom and tonemapping, keep **HDR** on in the URP Asset. Without HDR, nothing is brighter than 1, so bloom has little to pick out and tonemapping has nothing to compress.
5. For a place with its own look, add a **Box Volume**, size its collider, keep **Is Trigger** on, give it a profile, and set its **Priority** above the global volume's.
6. Put volumes on a layer the camera's **Volume Mask** includes. The default mask includes everything.

## The common effects

The override classes are in `UnityEngine.Rendering.Universal`.

| Override | Class | Use it for | Watch for |
| --- | --- | --- | --- |
| Tonemapping | `Tonemapping` | Mapping HDR to the screen. **ACES** is filmic and shifts hues; **Neutral** changes colour least. | Set it once, early. Every colour decision after it depends on it. |
| Bloom | `Bloom` | Glow around bright pixels: emissives, sparks, the sun. | **Threshold** is a gamma-space brightness, default 0.9. Keep it near 1 so only real highlights bloom. |
| Color Adjustments | `ColorAdjustments` | Exposure, contrast, saturation, a colour filter. Fades to grey on death. | **Post Exposure** is in EV stops, not a multiplier. +1 doubles the brightness. |
| Vignette | `Vignette` | Darkening the edges. Damage and low-health feedback, and focus. | Strong vignettes fight with UI in the corners. |
| Depth of Field | `DepthOfField` | Blurring by distance. Menus, photo modes, cut-scenes. | **Gaussian** is cheap; **Bokeh** is expensive. |
| Motion Blur | `MotionBlur` | Speed. | Some players feel sick with it. Offer a setting. |
| Chromatic Aberration | `ChromaticAberration` | Impact and disorientation, briefly. | Constant use looks like a broken lens. |
| Film Grain | `FilmGrain` | Texture and hiding banding. | Costs little, but compresses badly in video captures. |
| Lens Distortion | `LensDistortion` | Fisheye and impact warps. | Distorts the alpha channel and screen-space UI rays. |
| Color Lookup | `ColorLookup` | A LUT made in an image editor. | Grade the reference LUT in the same tonemapping you ship with. |

Others are White Balance, Lift Gamma Gain, Shadows Midtones Highlights, Color Curves, Channel Mixer, Split Toning, and Panini Projection.

On mobile, URP lists bloom with **High Quality Filtering** off, chromatic aberration, colour grading, lens distortion, and vignette as the cheap ones. Prefer Gaussian depth of field there.

## Driving effects from gameplay

### Turn a volume's weight

The simplest runtime effect is a separate global volume that holds only that effect, with its weight at 0. A script raises the weight to show it. Nothing is instantiated, and several such volumes blend with the base look on their own.

A damage flash is a volume with a red **Vignette** and some **Chromatic Aberration**. A low-health state is the same volume held at a baseline weight. A pause blur is a volume with **Depth of Field**, faded in when the menu opens.

```csharp
using UnityEngine;
using UnityEngine.Rendering;

/// <summary>
/// Pulses a volume's weight when this Health is hit, and holds a baseline at low health.
/// </summary>
public class DamageVolume : MonoBehaviour
{
    [SerializeField] Health health;
    [SerializeField] Volume volume;

    [Tooltip("Weight added per full health bar of damage.")]
    [SerializeField] float pulsePerHealth = 3f;
    [SerializeField] float halfLife = 0.15f;

    [Tooltip("Below this fraction of max health, the weight never drops under Low Health Weight.")]
    [Range(0f, 1f)] [SerializeField] float lowHealthFraction = 0.25f;
    [Range(0f, 1f)] [SerializeField] float lowHealthWeight = 0.35f;

    float _pulse;

    void OnEnable()
    {
        if (health != null)
            health.Damaged += OnDamaged;
    }

    void OnDisable()
    {
        if (health != null)
            health.Damaged -= OnDamaged;
        if (volume != null)
            volume.weight = 0f;
    }

    void OnDamaged(DamageInfo info, float amount)
    {
        if (health.Max > 0f)
            _pulse = Mathf.Clamp01(_pulse + amount / health.Max * pulsePerHealth);
    }

    void Update()
    {
        // Frame-rate-independent decay with a half-life. Unscaled, so it fades during hit-stop.
        _pulse *= Mathf.Exp(-Mathf.Log(2f) / halfLife * Time.unscaledDeltaTime);

        float baseline = 0f;
        if (health != null && !health.IsDead && health.Max > 0f && health.Current / health.Max <= lowHealthFraction)
            baseline = lowHealthWeight;

        if (volume != null)
            volume.weight = Mathf.Max(baseline, _pulse);
    }
}
```

The decay is the [damping step](../../maths/interpolation.md#frame-rate-independent-damping) on the pulse.

### Edit a profile's values

When the effect needs a value that weight cannot express, such as a vignette centre that follows the hit direction, edit the override itself:

```csharp
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

public class VignetteControl : MonoBehaviour
{
    [SerializeField] Volume volume;
    Vignette _vignette;

    void Awake()
    {
        // .profile makes a per-volume copy the first time it is read.
        if (volume != null && !volume.profile.TryGet(out _vignette))
            Debug.LogWarning("The volume's profile has no Vignette override.", volume);
    }

    public void SetCentre(Vector2 viewport)
    {
        if (_vignette != null)
            _vignette.center.Override(viewport);
    }

    void OnDestroy()
    {
        // The copy is not an asset and is not freed with the volume.
        if (volume != null && volume.HasInstantiatedProfile())
            Destroy(volume.profile);
    }
}
```

- `volume.profile` returns a copy that belongs to this volume, made on first access. Edits do not touch the asset. Destroy the copy when done.
- `volume.sharedProfile` is the asset itself. Edits in Play mode in the editor are written to the asset and stay after Play ends, and edits affect every volume that shares it.
- `parameter.Override(value)` ticks the property's checkbox and sets the value. Setting `.value` alone changes nothing if the property is not ticked in the inspector.
- `component.active = false` switches a whole override off, such as motion blur from a settings menu.

### Volume update mode

The URP Asset's **Volume Update Mode**, which each camera can override, is **Every Frame** by default. **Via Scripting** skips the per-frame blend, which saves CPU when volumes rarely change, but then the camera only picks up changes when a script asks. In that mode, call `UpdateVolumeStack()` on the camera's `UniversalAdditionalCameraData` after moving the camera between local volumes or changing weights.

!!! warning "Common pitfalls"

    The camera's **Post Processing** checkbox is off in new scenes. Volumes are set up correctly and nothing changes on screen.

    A property whose checkbox is not ticked in the override does not apply, and setting `.value` from a script does not tick it. Use `Override`.

    Runtime edits to the Default Volume Profile or the URP Asset's profile are cached away. Use a scene volume for anything a script changes.

    Editing `sharedProfile` in Play mode changes the asset permanently. Use `profile`, or weight-driven volumes.

    A local volume without a collider, or with its layer missing from the camera's **Volume Mask**, never applies. With a third-person camera, the camera may be outside a volume the character is inside; set **Volume Trigger**.

    Bloom with HDR off looks weak and blotchy, because nothing in the image is brighter than 1.
