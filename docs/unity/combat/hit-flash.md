---
engine: Unity
version: 6+
---

# Hit flash

A body turns bright for a tenth of a second when it takes damage. It is the cheapest piece of hit feedback, and the one players miss first when it is absent. The flash listens to `Health.Damaged` on the [health](../systems/health.md#health) page, so anything that deals damage through a hurtbox triggers it without knowing it exists.

There are two ways to do it in URP. Pick one per body:

| Mode | Looks like | Cost |
| --- | --- | --- |
| **Emission** | The surface glows and fades back over the duration. Texture detail stays visible. | Sets `_EmissionColor` through a `MaterialPropertyBlock`. The renderer leaves the SRP Batcher while the flash runs. |
| **Material Swap** | A flat silhouette in the flash material, on and then off. No fade. | Swaps `sharedMaterials` for the duration. Stays on the SRP Batcher, and needs no keyword on the original material. |

A sprite cannot do either, so it has its own component at the bottom.

## Setup

1. Put `HitFlash` on the character root, next to `Health` or under it. Leave **Health** empty to find it in the parents. Leave **Renderers** empty to collect every `MeshRenderer` and `SkinnedMeshRenderer` below this object.
2. **Emission** mode: on every material the flash should light, tick **Emission** and set the emission colour to something just above black, such as `(1, 1, 1)` in 0–255. URP turns the `_EMISSION` keyword off when the colour is exactly black, and then `_EmissionColor` does nothing.
3. **Material Swap** mode: create a material with **Universal Render Pipeline/Unlit**, colour white, and assign it as **Flash Material**.
4. Hit the body with a hazard or a gun. A fully resisted hit does not flash, because `Health` never raises `Damaged` for it.

## What each step is doing

`Health.Damaged` calls `Flash`. A second hit during a flash restarts the timer. It does not stack.

In **Emission** mode, each material slot gets its own block. The colour goes from the flash colour back to that material's own emission colour, with weight \(w = (t_{\text{left}} / t_{\text{duration}})^2\), so most of the glow is in the first few frames. When the time runs out, every block is cleared by passing `null`, which puts the renderer back on the SRP Batcher.

In **Material Swap** mode, the original `sharedMaterials` arrays are cached once in `Awake`, along with a same-length array of the flash material. The flash assigns the flash array, and the end assigns the cached originals back. Nothing is instantiated, so no material copies leak.

**Unscaled Time** is on by default, so the flash still finishes during a hit stop that sets `Time.timeScale` to `0`.

## Parameters

| Field | Default | Effect |
| --- | --- | --- |
| Health | Empty | Source of `Damaged`. Empty searches the parents. |
| Renderers | Empty | What flashes. Empty collects mesh and skinned renderers below. |
| Mode | Emission | Emission fades. Material Swap is a flat silhouette. |
| Flash Colour | HDR white, intensity 2 | Emission mode only. HDR, so values above 1 bloom. |
| Flash Material | Empty | Material Swap mode only. Unlit white is the usual choice. |
| Duration | `0.1` | Seconds. |
| Unscaled Time | On | Ignore `Time.timeScale`. |

## Scripts

### Hit flash

```csharp
using System.Collections.Generic;
using UnityEngine;

public enum HitFlashMode
{
    Emission,
    MaterialSwap
}

/// <summary>
/// Brief flash on every Health.Damaged. Emission fades; Material Swap is a flat silhouette.
/// </summary>
[DisallowMultipleComponent]
public class HitFlash : MonoBehaviour
{
    static readonly int EmissionColorId = Shader.PropertyToID("_EmissionColor");

    [SerializeField] Health health;
    [SerializeField] Renderer[] renderers;
    [SerializeField] HitFlashMode mode = HitFlashMode.Emission;
    [ColorUsage(false, true)] [SerializeField] Color flashColour = new Color(2f, 2f, 2f);
    [SerializeField] Material flashMaterial;
    [SerializeField] float duration = 0.1f;
    [SerializeField] bool unscaledTime = true;

    MaterialPropertyBlock _block;
    Material[][] _original;
    Material[][] _swapped;
    Color[][] _baseEmission;
    float _remaining;
    bool _active;

    void Awake()
    {
        if (health == null)
            health = GetComponentInParent<Health>();
        if (renderers == null || renderers.Length == 0)
            renderers = CollectRenderers();
        _block = new MaterialPropertyBlock();
        Cache();
    }

    void OnEnable()
    {
        if (health != null)
            health.Damaged += OnDamaged;
    }

    void OnDisable()
    {
        if (health != null)
            health.Damaged -= OnDamaged;
        End();
    }

    void OnDamaged(DamageInfo damage, float applied)
    {
        Flash();
    }

    public void Flash()
    {
        if (duration <= 0f)
            return;
        if (mode == HitFlashMode.MaterialSwap && flashMaterial == null)
            return;

        _remaining = duration;
        if (!_active && mode == HitFlashMode.MaterialSwap)
        {
            for (int i = 0; i < renderers.Length; i++)
            {
                if (renderers[i] != null)
                    renderers[i].sharedMaterials = _swapped[i];
            }
        }

        _active = true;
        if (mode == HitFlashMode.Emission)
            ApplyEmission(1f);
    }

    void Update()
    {
        if (!_active)
            return;

        _remaining -= unscaledTime ? Time.unscaledDeltaTime : Time.deltaTime;
        if (_remaining <= 0f)
        {
            End();
            return;
        }

        if (mode == HitFlashMode.Emission)
            ApplyEmission(_remaining / duration);
    }

    void ApplyEmission(float left)
    {
        float weight = left * left;
        for (int i = 0; i < renderers.Length; i++)
        {
            Renderer target = renderers[i];
            if (target == null)
                continue;
            for (int m = 0; m < _baseEmission[i].Length; m++)
            {
                _block.Clear();
                _block.SetColor(EmissionColorId, Color.Lerp(_baseEmission[i][m], flashColour, weight));
                target.SetPropertyBlock(_block, m);
            }
        }
    }

    void End()
    {
        if (!_active)
            return;
        _active = false;

        for (int i = 0; i < renderers.Length; i++)
        {
            Renderer target = renderers[i];
            if (target == null)
                continue;
            if (mode == HitFlashMode.MaterialSwap)
            {
                target.sharedMaterials = _original[i];
                continue;
            }
            // Null clears the per-material override and returns the renderer to the SRP Batcher.
            for (int m = 0; m < _baseEmission[i].Length; m++)
                target.SetPropertyBlock(null, m);
        }
    }

    void Cache()
    {
        _original = new Material[renderers.Length][];
        _swapped = new Material[renderers.Length][];
        _baseEmission = new Color[renderers.Length][];
        for (int i = 0; i < renderers.Length; i++)
        {
            Material[] materials = renderers[i] != null ? renderers[i].sharedMaterials : new Material[0];
            _original[i] = materials;
            _swapped[i] = new Material[materials.Length];
            _baseEmission[i] = new Color[materials.Length];
            for (int m = 0; m < materials.Length; m++)
            {
                _swapped[i][m] = flashMaterial;
                Material material = materials[m];
                _baseEmission[i][m] = material != null && material.HasProperty(EmissionColorId)
                    ? material.GetColor(EmissionColorId)
                    : Color.black;
            }
        }
    }

    Renderer[] CollectRenderers()
    {
        var found = new List<Renderer>();
        found.AddRange(GetComponentsInChildren<MeshRenderer>(true));
        found.AddRange(GetComponentsInChildren<SkinnedMeshRenderer>(true));
        return found.ToArray();
    }

    void OnValidate()
    {
        duration = Mathf.Max(0f, duration);
    }
}
```

## Sprites

`SpriteRenderer.color` multiplies the texture, so it can tint a sprite red but never make it white. A white flash needs a shader with a flash amount. With one, `HitFlash2D` drives `_FlashAmount`. Without one, it falls back to the tint.

To make the shader, create a **Sprite Lit** Shader Graph (or Sprite Unlit) and:

1. Add a **Texture2D** property with reference `_MainTex`, a **Float** with reference `_FlashAmount`, and a **Color** with reference `_FlashColor`.
2. Sample `_MainTex`. Multiply its RGB by the **Vertex Color** node, so `SpriteRenderer.color` still tints.
3. **Lerp** from that colour to `_FlashColor` by `_FlashAmount`, into **Base Color**. Texture alpha times vertex alpha goes to **Alpha**.
4. Make a material from the graph and assign it to the sprites.

```csharp
using UnityEngine;

/// <summary>
/// Sprite flash. Uses _FlashAmount when the material has it, otherwise tints SpriteRenderer.color.
/// </summary>
[DisallowMultipleComponent]
public class HitFlash2D : MonoBehaviour
{
    static readonly int FlashAmountId = Shader.PropertyToID("_FlashAmount");
    static readonly int FlashColorId = Shader.PropertyToID("_FlashColor");

    [SerializeField] Health health;
    [SerializeField] SpriteRenderer[] sprites;
    [SerializeField] Color flashColour = Color.white;
    [Tooltip("Used when the material has no _FlashAmount. A multiply, so white does nothing.")]
    [SerializeField] Color tintColour = new Color(1f, 0.25f, 0.25f);
    [SerializeField] float duration = 0.1f;
    [SerializeField] bool unscaledTime = true;

    MaterialPropertyBlock _block;
    Color[] _originalColours;
    bool[] _hasAmount;
    float _remaining;
    bool _active;

    void Awake()
    {
        if (health == null)
            health = GetComponentInParent<Health>();
        if (sprites == null || sprites.Length == 0)
            sprites = GetComponentsInChildren<SpriteRenderer>(true);
        _block = new MaterialPropertyBlock();
        _originalColours = new Color[sprites.Length];
        _hasAmount = new bool[sprites.Length];
        for (int i = 0; i < sprites.Length; i++)
        {
            if (sprites[i] == null)
                continue;
            _originalColours[i] = sprites[i].color;
            Material material = sprites[i].sharedMaterial;
            _hasAmount[i] = material != null && material.HasProperty(FlashAmountId);
        }
    }

    void OnEnable()
    {
        if (health != null)
            health.Damaged += OnDamaged;
    }

    void OnDisable()
    {
        if (health != null)
            health.Damaged -= OnDamaged;
        if (_active)
        {
            Apply(0f);
            _active = false;
        }
    }

    void OnDamaged(DamageInfo damage, float applied)
    {
        Flash();
    }

    public void Flash()
    {
        if (duration <= 0f)
            return;
        if (!_active)
        {
            // Capture the tint now, so a colour set by gameplay since Awake is restored.
            for (int i = 0; i < sprites.Length; i++)
            {
                if (sprites[i] != null)
                    _originalColours[i] = sprites[i].color;
            }
        }

        _remaining = duration;
        _active = true;
        Apply(1f);
    }

    void Update()
    {
        if (!_active)
            return;

        _remaining -= unscaledTime ? Time.unscaledDeltaTime : Time.deltaTime;
        if (_remaining <= 0f)
        {
            Apply(0f);
            _active = false;
            return;
        }

        float left = _remaining / duration;
        Apply(left * left);
    }

    void Apply(float weight)
    {
        for (int i = 0; i < sprites.Length; i++)
        {
            SpriteRenderer sprite = sprites[i];
            if (sprite == null)
                continue;

            if (_hasAmount[i])
            {
                // Read first, so values another script put in the block are kept.
                sprite.GetPropertyBlock(_block);
                _block.SetFloat(FlashAmountId, weight);
                _block.SetColor(FlashColorId, flashColour);
                sprite.SetPropertyBlock(_block);
            }
            else
            {
                sprite.color = Color.Lerp(_originalColours[i], _originalColours[i] * tintColour, weight);
            }
        }
    }

    void OnValidate()
    {
        duration = Mathf.Max(0f, duration);
    }
}
```

!!! warning "Common pitfalls"

    An emission colour of exactly black on the original material turns the `_EMISSION` keyword off, and the flash does nothing. Set it a step above black. In a build, a material that never had emission on may also be missing that shader variant.

    Do not set `renderer.material` to flash. The getter clones the material, every hit leaks a copy, and the clone drops off the SRP Batcher for good. Use the property block or the shared-material swap.

    A per-material property block overrides a per-renderer one. While a flash runs, a renderer block set elsewhere, such as the fresnel highlight on [highlight and outline](../rendering/highlight-outline.md), is ignored. It comes back when the flash clears.

    **Material Swap** caches `sharedMaterials` in `Awake`. Code that changes those materials later, such as an armour swap, has to happen when no flash is running, or the end of the flash restores the old ones. Call `Flash` only after such a change has finished.

    Particles, trails, and line renderers are not collected automatically. Add them to **Renderers** by hand if they should flash, and only in Material Swap mode if their shader has no emission.

    A flash every frame from a damage-over-time hazard reads as a solid glow. Give the hazard a **Repeat Interval** longer than **Duration**.
