---
engine: Unity
version: 6+
package: URP 17.x
uses:
  - name: Top-down survival
    text: Walking into a house hides its roof and upper floor, and the room stays dark with the roof's shadow.
  - name: Isometric RPGs
    text: Walls between the camera and the party dissolve, so the party is never hidden.
  - name: Life and building sims
    text: Upper floors hide while the player works on the floor below.
  - name: Tactics games
    text: A see-through circle around the selected unit shows it behind cover.
---

# Roof and wall cutaways

With the camera above and behind the player, buildings get in the way: the roof hides everything inside, and the wall nearest the camera hides the player once they step behind it. This page covers both for a 3D top-down or isometric camera in URP. Hiding what the character cannot see is [fog of war and vision](vision.md).

- **Roofs and upper floors** hide when the player is inside, by trigger volume or by height.
- **Walls in front of the player** dissolve, either in a circle around the player on screen, or object by object when a ray from the camera hits them.

## Roofs and upper floors

Each building, or each floor of one, gets an **interior volume**: a trigger collider filling the inside. While the player is in it, the volume's roof and upper-floor renderers stop drawing.

Hide them by switching each renderer to **Shadows Only**, not by disabling it. The roof keeps casting its shadow, so the inside stays as dark as a real interior, and the sun does not suddenly flood the rooms. Its collider is untouched, so rain and projectiles still hit it.

Adjacent volumes overlap at doorways, so the player can be in two at once. The viewer counts how many volumes want each renderer hidden, and shows it again only when that count returns to zero. Without the count, walking from the kitchen to the hall flashes the roof for a frame.

### By height instead of volume

For multi-storey buildings where the player climbs stairs, tag each renderer with the floor it belongs to. Hide every floor above the one the player is on, worked out from the player's height and a floor height. Project Zomboid works this way: the levels above the player vanish whatever building they are in. It needs no volumes, but every renderer needs a floor index.

## Walls in front of the player

| Approach | How | Good for | Weak at |
| --- | --- | --- | --- |
| **Cutout circle** | A shader on walls discards pixels inside a circle around the player on screen, but only if the pixel is nearer the camera than the player. | Everything at once, with no per-object work. Interiors with many walls. | Every wall material needs the shader. |
| **Ray fade** | Cast from the camera to the player. Walls hit fade out; the rest fade back. | A few large occluders, such as trees or pillars, with their own fade. | A wall just beside the ray still hides part of the player. |
| **Lowered walls** | Swap walls facing the camera for short versions, as in The Sims' "walls down". | Building games and sims. | Two meshes per wall, and only for walls you author. |

Both shader approaches dissolve with a **dither**: pixels are discarded in an ordered pattern that thins out as the fade increases. Dithered opaque surfaces keep writing depth and casting shadows correctly, which transparent ones do not, and they stay in the opaque queue with no sorting problems.

### The dissolve shader

Make a Shader Graph from **URP → Lit Shader Graph**, and in the Graph Settings tick **Alpha Clipping**. Then:

1. Add a float property `_Fade`, default 0. The ray fader sets it per renderer.
2. Add a **Custom Function** node, file mode, pointing at the HLSL below, function name `Cutout`. Inputs: **Position** node in World space, and **Screen Position** node in Default mode. Output: `Fade`.
3. **Maximum** of `_Fade` and the cutout's `Fade`.
4. **One Minus** of that, into a **Dither** node's input, with the Screen Position into its screen position input.
5. Dither's output into **Alpha**. Set **Alpha Clip Threshold** to 0.

The Dither node outputs its input minus a per-pixel threshold between 0 and 1. With a clip threshold of 0, an input of 1 keeps every pixel, 0 discards every pixel, and values between discard that fraction in a fixed pattern.

```hlsl
// Cutout.hlsl. Globals set by CutoutDriver.
float4 _CutoutCentre;    // xy: player's viewport position, z: aspect ratio, w: 1 when enabled
float _CutoutRadius;     // in fractions of screen height
float _CutoutSoftness;   // edge width, same units
float _CutoutDepth;      // camera-to-player distance

void Cutout_float(float3 WorldPosition, float4 ScreenPosition, out float Fade)
{
    Fade = 0;
    if (_CutoutCentre.w < 0.5)
        return;

    // Only pixels in front of the player are cut.
    float pixelDepth = distance(WorldPosition, _WorldSpaceCameraPos);
    if (pixelDepth > _CutoutDepth - 0.5)
        return;

    float2 delta = ScreenPosition.xy - _CutoutCentre.xy;
    delta.x *= _CutoutCentre.z; // keep the circle round on wide screens
    float distanceFromCentre = length(delta);

    Fade = 1 - smoothstep(_CutoutRadius - _CutoutSoftness, _CutoutRadius, distanceFromCentre);
}
```

Use this material on walls, fences, and anything else that should dissolve. Floors and the player's own materials keep the normal Lit shader.

## Setup

1. Give the player a collider and a `Rigidbody` (kinematic is fine) or a `CharacterController`, so it receives trigger events. Put `CutawayViewer` on it.
2. For each building, add a child with a trigger **Box Collider** filling the interior, and `InteriorVolume`. Drag the roof and upper-floor renderers into **Hide**. Put these volumes on a layer that only collides with the player.
3. Create the dissolve Shader Graph above and use it for wall materials.
4. Put `CutoutDriver` on the camera and assign the player. Tune **Radius** and **Softness**. Turn **Only Indoors** on to cut walls only while the player is inside a volume.
5. For ray fading, put `Fadeable` on occluders that use the dissolve shader, and `OcclusionFader` on the camera with **Occluder Mask** set to their layer.

## Scripts

### Interior volume

```csharp
using UnityEngine;

/// <summary>
/// A trigger filling a building's interior. Lists the renderers to hide while the player is inside.
/// </summary>
[RequireComponent(typeof(Collider))]
public class InteriorVolume : MonoBehaviour
{
    [Tooltip("Roofs and floors above this one.")]
    [SerializeField] Renderer[] hide = System.Array.Empty<Renderer>();

    public Renderer[] Hide => hide;

    void Reset()
    {
        GetComponent<Collider>().isTrigger = true;
    }
}
```

### Cutaway viewer

```csharp
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;

/// <summary>
/// On the player. Hides the renderers of every interior volume the player is inside,
/// counting overlaps so adjacent volumes do not flicker.
/// </summary>
public class CutawayViewer : MonoBehaviour
{
    readonly Dictionary<Renderer, int> _hiddenCount = new Dictionary<Renderer, int>();
    readonly Dictionary<Renderer, ShadowCastingMode> _original = new Dictionary<Renderer, ShadowCastingMode>();
    readonly HashSet<InteriorVolume> _inside = new HashSet<InteriorVolume>();

    public bool IsIndoors => _inside.Count > 0;

    void OnTriggerEnter(Collider other)
    {
        if (other.TryGetComponent(out InteriorVolume volume) && _inside.Add(volume))
        {
            foreach (Renderer r in volume.Hide)
                Hide(r);
        }
    }

    void OnTriggerExit(Collider other)
    {
        if (other.TryGetComponent(out InteriorVolume volume) && _inside.Remove(volume))
        {
            foreach (Renderer r in volume.Hide)
                Show(r);
        }
    }

    void OnDisable()
    {
        // Leave nothing hidden if the player is disabled or destroyed indoors.
        foreach (KeyValuePair<Renderer, ShadowCastingMode> pair in _original)
        {
            if (pair.Key != null)
                pair.Key.shadowCastingMode = pair.Value;
        }
        _hiddenCount.Clear();
        _original.Clear();
        _inside.Clear();
    }

    void Hide(Renderer r)
    {
        if (r == null)
            return;

        _hiddenCount.TryGetValue(r, out int count);
        if (count == 0)
        {
            _original[r] = r.shadowCastingMode;
            // Invisible, but still casting its shadow into the room.
            r.shadowCastingMode = ShadowCastingMode.ShadowsOnly;
        }
        _hiddenCount[r] = count + 1;
    }

    void Show(Renderer r)
    {
        if (r == null || !_hiddenCount.TryGetValue(r, out int count))
            return;

        if (count > 1)
        {
            _hiddenCount[r] = count - 1;
            return;
        }

        _hiddenCount.Remove(r);
        if (_original.TryGetValue(r, out ShadowCastingMode mode))
            r.shadowCastingMode = mode;
        _original.Remove(r);
    }
}
```

`OnTriggerExit` is not called when a volume is disabled or destroyed while the player is inside it. If buildings can be destroyed, have the volume tell the viewer from its own `OnDisable`.

### Cutout driver

```csharp
using UnityEngine;

/// <summary>
/// On the camera. Feeds the player's screen position and depth to the dissolve shader.
/// </summary>
[RequireComponent(typeof(Camera))]
public class CutoutDriver : MonoBehaviour
{
    [SerializeField] Transform player;
    [Tooltip("Height above the player's pivot to centre the circle on.")]
    [SerializeField] float centreHeight = 1f;
    [Tooltip("Radius as a fraction of screen height.")]
    [SerializeField] float radius = 0.12f;
    [SerializeField] float softness = 0.03f;
    [Tooltip("Cut walls only while the player is inside an interior volume.")]
    [SerializeField] bool onlyIndoors;
    [SerializeField] float fadeSpeed = 6f;

    static readonly int CentreId = Shader.PropertyToID("_CutoutCentre");
    static readonly int RadiusId = Shader.PropertyToID("_CutoutRadius");
    static readonly int SoftnessId = Shader.PropertyToID("_CutoutSoftness");
    static readonly int DepthId = Shader.PropertyToID("_CutoutDepth");

    Camera _camera;
    CutawayViewer _viewer;
    float _amount;

    void Awake()
    {
        _camera = GetComponent<Camera>();
        if (player != null)
            player.TryGetComponent(out _viewer);
    }

    void OnDisable()
    {
        Shader.SetGlobalVector(CentreId, Vector4.zero);
    }

    void LateUpdate()
    {
        if (player == null)
            return;

        bool wanted = !onlyIndoors || (_viewer != null && _viewer.IsIndoors);
        _amount = Mathf.MoveTowards(_amount, wanted ? 1f : 0f, fadeSpeed * Time.unscaledDeltaTime);

        Vector3 centre = player.position + Vector3.up * centreHeight;
        Vector3 viewport = _camera.WorldToViewportPoint(centre);
        bool enabled = _amount > 0.001f && viewport.z > 0f;

        Shader.SetGlobalVector(CentreId, new Vector4(viewport.x, viewport.y, _camera.aspect, enabled ? 1f : 0f));
        Shader.SetGlobalFloat(RadiusId, radius * _amount);
        Shader.SetGlobalFloat(SoftnessId, softness);
        Shader.SetGlobalFloat(DepthId, Vector3.Distance(transform.position, centre));
    }
}
```

The radius grows from zero when the player walks in, so the hole opens instead of popping.

### Ray fade

```csharp
using UnityEngine;

/// <summary>
/// An occluder using the dissolve shader. Fades towards hidden while something asks, then back.
/// </summary>
public class Fadeable : MonoBehaviour
{
    [SerializeField] float fadeSpeed = 4f;
    [Range(0f, 1f)] [SerializeField] float maxFade = 0.85f;

    static readonly int FadeId = Shader.PropertyToID("_Fade");

    Renderer[] _renderers;
    MaterialPropertyBlock _block;
    float _fade;
    int _requestedFrame = -1;

    void Awake()
    {
        _renderers = GetComponentsInChildren<Renderer>();
        _block = new MaterialPropertyBlock();
    }

    /// <summary>Call every frame this should be faded.</summary>
    public void Request()
    {
        _requestedFrame = Time.frameCount;
        enabled = true;
    }

    void Update()
    {
        bool wanted = _requestedFrame >= Time.frameCount - 1;
        _fade = Mathf.MoveTowards(_fade, wanted ? maxFade : 0f, fadeSpeed * Time.unscaledDeltaTime);
        Apply();

        if (!wanted && _fade <= 0f)
            enabled = false; // nothing to do until requested again
    }

    void Apply()
    {
        foreach (Renderer r in _renderers)
        {
            if (_fade <= 0f)
            {
                r.SetPropertyBlock(null); // back on the SRP Batcher
                continue;
            }
            r.GetPropertyBlock(_block);
            _block.SetFloat(FadeId, _fade);
            r.SetPropertyBlock(_block);
        }
    }
}
```

```csharp
using UnityEngine;

/// <summary>
/// On the camera. Fades every Fadeable between the camera and the player.
/// </summary>
public class OcclusionFader : MonoBehaviour
{
    [SerializeField] Transform player;
    [SerializeField] float playerHeight = 1f;
    [SerializeField] float radius = 0.5f;
    [SerializeField] LayerMask occluderMask;

    readonly RaycastHit[] _hits = new RaycastHit[16];

    void LateUpdate()
    {
        if (player == null)
            return;

        Vector3 target = player.position + Vector3.up * playerHeight;
        Vector3 to = target - transform.position;
        float distance = to.magnitude;
        if (distance < 1e-3f)
            return;

        int count = Physics.SphereCastNonAlloc(transform.position, radius, to / distance, _hits, distance,
            occluderMask, QueryTriggerInteraction.Ignore);
        for (int i = 0; i < count; i++)
        {
            Fadeable fadeable = _hits[i].collider.GetComponentInParent<Fadeable>();
            if (fadeable != null)
                fadeable.Request();
        }
    }
}
```

A property block takes the renderer off the SRP Batcher while it is set, as on the [hit flash](../combat/hit-flash.md) page. The fader clears the block once the fade is back to zero, so only the few renderers fading at any moment pay for it.

!!! warning "Common pitfalls"

    Disabling roof renderers instead of switching them to **Shadows Only** floods the interior with sunlight the moment the player walks in.

    Without overlap counting, walking between two adjacent interior volumes shows the roof for a frame at the doorway.

    A cutout without the depth test also cuts the floor and the walls behind the player, leaving a hole in the ground. Keep the floor on a material without the cutout, and keep the depth test.

    A dissolve done with transparency instead of a dither sorts wrongly against other transparent objects, and stops writing depth, so shadows and post-processing see through it.

    A `CharacterController` gets trigger events only while it moves. A player who stands still in a doorway while a volume is enabled around them is not detected until they step.
