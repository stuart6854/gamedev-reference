---
engine: Unity
version: 6+
package: URP 17.x
uses:
  - name: Top-down survival
    text: Outlining the container or door the player can use.
  - name: RPGs
    text: Highlighting interactable objects and selected characters.
---

# Highlight and outline

A stroke around a focused prop, and a cheaper fresnel glow when a stroke is more than the moment needs. The focus callbacks live on the [interaction](../mechanics/interaction.md) page. This page is the drawing. A placement ghost uses a transparent tint instead of this stroke. That preview is [building](../systems/building.md#ghost).

URP has no outline package. The selective stroke is two built-in **Render Objects** features and an inverted-hull shader. The scene-wide edge is a built-in **Full Screen Pass Renderer Feature**. Both already record their work through URP 17's Render Graph. This page does not add a `ScriptableRendererFeature`. A pass of your own has to override `RecordRenderGraph`. The older `Execute` method is the compatibility path, and it is not the one to write.

## Approaches

| Approach | Selective | Width | What it costs | Use it when |
| --- | --- | --- | --- | --- |
| Inverted hull | The objects you draw it on | Metres, along the normal | One extra draw | The stroke can follow the mesh and hard edges are handled |
| Stencil, via Render Objects | Yes. The feature filters a GameObject layer | The same hull, punched out by the stencil | Two renderer features | The stroke must not fill crevices or the far side of the mesh |
| Screen-space depth and normals | No. Every edge in the depth and normal buffers | About a pixel | One full-screen pass | The whole frame wants a contour, not one focused prop |
| Jump flood | From a mask you already have | A constant pixel radius, including wide strokes | Several full-screen passes | The stroke has to stay even and thick. Not built in; not set up here |
| Rim / fresnel | Per renderer | A view-dependent glow, not a stroke | None, if the object's shader does it | Focus feedback has to stay cheap |

Rendering layers (`Renderer.renderingLayerMask`) are the mask lights and decals use. They do not change the physics layer, and they can overlap. The Render Objects feature in URP 17 filters the **GameObject layer**. If that inspector also shows a Rendering Layer Mask, leave it at Everything so it does not filter on top. The component below moves the mesh onto an `Outline` layer while it is focused, and moves it back.

## Setup

The stencil outline. The fresnel and the full-screen edge have their own short steps further down; they are not part of this list.

1. Add a GameObject layer named `Outline` under **Edit → Project Settings → Tags and Layers**. This is not a rendering layer. If a collider sits on the same object as the mesh, give `Outline` the same collision-matrix row as the layer the mesh started on. A mesh on a child with no collider does not need a matrix change.
2. Create two materials. `OutlineMask` uses the mask shader. `OutlineHull` uses the hull shader. Set the hull colour and a width in metres, for example `0.03`.
3. On the **Universal Renderer Data** asset (the renderer listed on the pipeline asset, not the pipeline asset itself), **Add Renderer Feature → Render Objects**. Name it `Outline Mask`.
    - Event: **After Rendering Opaques**
    - Queue: **Opaque**
    - Layer Mask: `Outline` only
    - Rendering Layer Mask, if the inspector shows one: **Everything**
    - Pass Names or LightMode tags: empty
    - Override Mode: **Material**. Material: `OutlineMask`. Pass Index: `0`
    - Depth: on. Write Depth: off. Depth Test: **Less Equal**. If **Set As Input Attachment** is shown, leave it off. It drops the stencil override
    - Stencil: on. Value `1`. Compare **Always**. Pass **Replace**. Fail **Keep**. Z Fail **Keep**. Read Mask and Write Mask `255` if they are shown
4. Add a second Render Objects feature under the first. Name it `Outline Hull`. The same event, queue, and layer mask. Override material `OutlineHull`, pass `0`. Depth as above, write off, **Less Equal**. Stencil value `1`, compare **Not Equal**, and Pass, Fail, and Z Fail all **Keep**.
5. The renderer's **Opaque Layer Mask** has to include `Outline`. The two features are extra draws. If the layer is missing from the opaque mask, a focused mesh drops out of the normal draw and only the hull remains.
6. Add `Outline` to the interactable. Leave **Mode** on **Hull** and **Outline Layer** on `Outline`. Put the visible mesh on a child when the root also has a collider.
7. Call `SetFocused(true)` from `OnFocusEnter` and `SetFocused(false)` from `OnFocusExit`. The methods are the interaction page's. The snippet is under [Focus](#focus).

## What each step is doing

The opaque pass draws the prop as usual and writes depth. The mask feature draws it again, after opaques, with colour writes off, and replaces the stencil with `1` wherever that draw is in front of the existing depth. Only the visible surface is marked. A wall in front of the prop keeps the wall's stencil.

The hull feature draws the same mesh with the hull shader. The vertex stage pushes each vertex out along its world normal, and the pass culls front faces, so the enlarged back faces show as a border. The stencil test is **Not Equal** to `1`, so the border is dropped wherever the mask wrote. Depth **Less Equal** drops the parts that sit behind a wall. The crevices stay unmarked by the hull because those pixels already belong to the object.

A hull with no stencil uses the depth test alone. The enlarged back faces that sit inside a concave fold are in front of the empty space behind them, so they pass the depth test and the stroke leaks into the fold. The stencil is what stops that.

Order in the renderer list is the order of two features that share an event. The mask has to be above the hull.

## Inverted hull

Extrude in world space, then transform to clip. The width stays in metres when a parent is scaled uniformly. Object-space extrusion (`positionOS + normalOS * width`) multiplies by the lossy scale and is the one to avoid.

Hard edges split a vertex into several, each with its own face normal. Those normals point apart, so the hull splits into gaps at the edge. Average the normals of vertices that share a position, write that average into UV3, and leave the lighting normal in `NORMAL`. The hull shader reads UV3 when **Use Smoothed Normals** is on. Baking is a mesh preprocess: quantise positions, accumulate the normals, normalise, store the result in `mesh.SetUVs(2, ...)`.

Skinned meshes are the exception. URP skins `POSITION` and `NORMAL` before the vertex shader, so the live normal follows the pose. A normal stored in UV3 is not skinned and stays in bind pose. Leave **Use Smoothed Normals** off on a `SkinnedMeshRenderer`.

### Shader Graph

The HLSL below is the material the feature overrides with. The same hull in Shader Graph:

1. **Create → Shader Graph → URP → Unlit Shader Graph**.
2. Graph settings: **Surface Type** Opaque, **Render Face** Back (that culls the front faces), **Depth Write** off, **Cast Shadows** off. Set **Depth Test** to Less Equal if the graph shows it. The Render Objects feature overrides depth anyway.
3. Add a vertex **Position** block and set its space to World.
4. Add **Position** in World space to **Normal Vector** in World space, multiplied by a Float property `Width`. Connect the sum to the vertex Position.
5. Fragment **Base Color** is a Color property.
6. Create a material from the graph and assign it as the hull feature's override. The mask pass stays the HLSL shader: Shader Graph does not expose `ColorMask 0`.

## Screen-space edges

This pass outlines every depth or normal discontinuity, including the room. It is not a focus outline. Restricting it to one prop means a mask in front of it, which is the stencil path above, or a jump flood from that mask.

1. **Add Renderer Feature → Full Screen Pass Renderer Feature**.
2. Injection Point: **Before Rendering Transparents**, so transparent objects draw over the contour.
3. Requirements: **Depth** and **Normal**. If the field is a single choice, use **Everything**. That also builds colour and motion, which this shader does not read.
4. **Fetch Color Buffer** on, so the shader can blend over `_BlitTexture`. **Bind Depth-Stencil** off.
5. Pass Material: a material using the edge shader below.

Lit, Simple Lit, and URP Unlit already have a `DepthNormals` pass, so they show up in the normal buffer. A custom shader without that pass still has a depth edge and almost no normal edge.

## Jump flood

A jump flood starts from a binary silhouette, such as the stencil mask copied into a render target, and builds a distance field. Each pass samples neighbours at a power-of-two offset, so a radius of N pixels is about log2(N) full-screen passes, and a last pass keeps the texels inside the radius. The width is uniform in pixels, including across thin parts and concave corners, where an extruded hull self-intersects and breaks. URP does not ship this feature. It is the next step when the stroke has to be wide and even, and it is out of scope here.

## Rim highlight

A fresnel term is a glow that strengthens as the normal turns away from the camera. It is not a stroke of constant width, and it needs no renderer feature. The object's own shader adds it, and the component sets `_Highlight` to `1` while focused.

Assign the fresnel shader as the prop's material and set `Outline` **Mode** to **Fresnel**. The hull features can stay on the renderer; Fresnel mode does not move the layer, so they draw nothing extra.

The HLSL fresnel shader below is deliberately minimal: it is unlit, and it has no shadow-caster, depth, or depth-normals pass. A prop using it looks flat, casts no shadow, and is missing from the depth and normals textures that the edge pass and SSAO read. For a real prop, put the rim into a lit material instead: a **URP → Lit Shader Graph** with a **Fresnel Effect** node, multiplied by the highlight colour and a Float property named `_Highlight`, into **Emission**. That keeps lighting, shadows, and every pass URP needs, and the `Outline` component drives it unchanged.

## Parameters

| Field | Default | Effect |
| --- | --- | --- |
| Mode | Hull | Hull moves meshes onto the Outline layer. Fresnel sets `_Highlight` on a property block. |
| Outline Layer | `Outline` | GameObject layer the Render Objects features filter. Ignored in Fresnel mode. |
| Highlight Property | `_Highlight` | Float the fresnel shader multiplies by. `1` while focused. |
| Outline Width | `0.03` | Metres along the world normal. |
| Use Smoothed Normals | Off | Read the averaged normal from UV3. Leave off for skinned meshes. |
| Depth Threshold | `0.05` | Relative eye-depth change that counts as an edge in the full-screen pass. |
| Normal Threshold | `0.2` | Normal-dot change that counts as an edge. |

## Scripts

The mask, the hull, the edge, and the fresnel shader are each their own file. `Outline` is the component the interactable calls.

### Mask

```hlsl
Shader "Game/OutlineMask"
{
    SubShader
    {
        Tags
        {
            "RenderType" = "Opaque"
            "RenderPipeline" = "UniversalPipeline"
            "Queue" = "Geometry"
        }

        Pass
        {
            Name "OutlineMask"
            Tags { "LightMode" = "UniversalForward" }

            Cull Back
            ZWrite Off
            ZTest LEqual
            ColorMask 0

            HLSLPROGRAM
            #pragma vertex Vert
            #pragma fragment Frag
            #pragma multi_compile_instancing

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"

            struct Attributes
            {
                float4 positionOS : POSITION;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                UNITY_VERTEX_OUTPUT_STEREO
            };

            Varyings Vert(Attributes input)
            {
                Varyings output;
                UNITY_SETUP_INSTANCE_ID(input);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(output);
                output.positionCS = TransformObjectToHClip(input.positionOS.xyz);
                return output;
            }

            half4 Frag(Varyings input) : SV_Target
            {
                return 0;
            }
            ENDHLSL
        }
    }

    Fallback Off
}
```

### Hull

```hlsl
Shader "Game/OutlineHull"
{
    Properties
    {
        _OutlineColor ("Outline Colour", Color) = (1, 0.62, 0.15, 1)
        _OutlineWidth ("Outline Width", Float) = 0.03
        [Toggle] _UseSmoothedNormals ("Use Smoothed Normals", Float) = 0
    }

    SubShader
    {
        Tags
        {
            "RenderType" = "Opaque"
            "RenderPipeline" = "UniversalPipeline"
            "Queue" = "Geometry"
        }

        Pass
        {
            Name "OutlineHull"
            Tags { "LightMode" = "UniversalForward" }

            Cull Front
            ZWrite Off
            ZTest LEqual

            HLSLPROGRAM
            #pragma vertex Vert
            #pragma fragment Frag
            #pragma multi_compile_instancing

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"

            CBUFFER_START(UnityPerMaterial)
                half4 _OutlineColor;
                float _OutlineWidth;
                float _UseSmoothedNormals;
            CBUFFER_END

            struct Attributes
            {
                float4 positionOS : POSITION;
                float3 normalOS : NORMAL;
                float3 smoothNormalOS : TEXCOORD2;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                UNITY_VERTEX_OUTPUT_STEREO
            };

            Varyings Vert(Attributes input)
            {
                Varyings output;
                UNITY_SETUP_INSTANCE_ID(input);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(output);

                float3 normalOS = lerp(input.normalOS, input.smoothNormalOS, _UseSmoothedNormals);
                float3 positionWS = TransformObjectToWorld(input.positionOS.xyz);
                float3 normalWS = TransformObjectToWorldNormal(normalOS);
                positionWS += normalWS * _OutlineWidth;
                output.positionCS = TransformWorldToHClip(positionWS);
                return output;
            }

            half4 Frag(Varyings input) : SV_Target
            {
                return _OutlineColor;
            }
            ENDHLSL
        }
    }

    Fallback Off
}
```

### Edge

```hlsl
Shader "Game/OutlineEdge"
{
    Properties
    {
        _OutlineColor ("Outline Colour", Color) = (1, 0.62, 0.15, 1)
        _DepthThreshold ("Depth Threshold", Float) = 0.05
        _NormalThreshold ("Normal Threshold", Float) = 0.2
    }

    SubShader
    {
        Tags
        {
            "RenderPipeline" = "UniversalPipeline"
        }

        Pass
        {
            Name "OutlineEdge"
            ZWrite Off
            ZTest Always
            Cull Off

            HLSLPROGRAM
            #pragma vertex Vert
            #pragma fragment Frag

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
            #include "Packages/com.unity.render-pipelines.core/Runtime/Utilities/Blit.hlsl"
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/DeclareDepthTexture.hlsl"
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/DeclareNormalsTexture.hlsl"

            CBUFFER_START(UnityPerMaterial)
                half4 _OutlineColor;
                float _DepthThreshold;
                float _NormalThreshold;
            CBUFFER_END

            float EyeDepth(float2 uv)
            {
                return LinearEyeDepth(SampleSceneDepth(uv), _ZBufferParams);
            }

            half4 Frag(Varyings input) : SV_Target
            {
                UNITY_SETUP_STEREO_EYE_INDEX_POST_VERTEX(input);
                float2 uv = input.texcoord;
                // One pixel of the camera target. _ScreenSize is a URP global: xy is the size, zw is 1 / size.
                float2 texel = _ScreenSize.zw;

                float centre = EyeDepth(uv);
                float depthDelta = abs(EyeDepth(uv + float2(texel.x, 0)) - centre);
                depthDelta += abs(EyeDepth(uv + float2(0, texel.y)) - centre);
                depthDelta /= max(centre, 1e-3);

                float3 normal = SampleSceneNormals(uv);
                float3 normalX = SampleSceneNormals(uv + float2(texel.x, 0));
                float3 normalY = SampleSceneNormals(uv + float2(0, texel.y));
                float normalDelta = 1 - saturate(dot(normal, normalX));
                normalDelta = max(normalDelta, 1 - saturate(dot(normal, normalY)));

                float edge = depthDelta > _DepthThreshold ? 1 : 0;
                edge = max(edge, normalDelta > _NormalThreshold ? 1 : 0);

                half3 scene = SAMPLE_TEXTURE2D_X(_BlitTexture, sampler_LinearClamp, uv).rgb;
                half3 colour = lerp(scene, _OutlineColor.rgb, edge * _OutlineColor.a);
                return half4(colour, 1);
            }
            ENDHLSL
        }
    }

    Fallback Off
}
```

### Fresnel

```hlsl
Shader "Game/OutlineFresnel"
{
    Properties
    {
        _BaseColor ("Base Colour", Color) = (0.75, 0.75, 0.75, 1)
        _HighlightColor ("Highlight Colour", Color) = (1, 0.62, 0.15, 1)
        _FresnelPower ("Fresnel Power", Float) = 3
        _Highlight ("Highlight", Range(0, 1)) = 0
    }

    SubShader
    {
        Tags
        {
            "RenderType" = "Opaque"
            "RenderPipeline" = "UniversalPipeline"
            "Queue" = "Geometry"
        }

        Pass
        {
            Name "OutlineFresnel"
            Tags { "LightMode" = "UniversalForward" }

            Cull Back
            ZWrite On
            ZTest LEqual

            HLSLPROGRAM
            #pragma vertex Vert
            #pragma fragment Frag
            #pragma multi_compile_instancing

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"

            CBUFFER_START(UnityPerMaterial)
                half4 _BaseColor;
                half4 _HighlightColor;
                float _FresnelPower;
                float _Highlight;
            CBUFFER_END

            struct Attributes
            {
                float4 positionOS : POSITION;
                float3 normalOS : NORMAL;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float3 positionWS : TEXCOORD0;
                float3 normalWS : TEXCOORD1;
                UNITY_VERTEX_OUTPUT_STEREO
            };

            Varyings Vert(Attributes input)
            {
                Varyings output;
                UNITY_SETUP_INSTANCE_ID(input);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(output);
                output.positionWS = TransformObjectToWorld(input.positionOS.xyz);
                output.normalWS = TransformObjectToWorldNormal(input.normalOS);
                output.positionCS = TransformWorldToHClip(output.positionWS);
                return output;
            }

            half4 Frag(Varyings input) : SV_Target
            {
                float3 viewDir = normalize(GetCameraPositionWS() - input.positionWS);
                float facing = saturate(dot(normalize(input.normalWS), viewDir));
                float fresnel = pow(1 - facing, max(_FresnelPower, 0.001));
                half3 colour = _BaseColor.rgb + _HighlightColor.rgb * fresnel * _Highlight;
                return half4(colour, 1);
            }
            ENDHLSL
        }
    }

    Fallback Off
}
```

### Outline

Hull mode changes the GameObject layer on each mesh renderer. Fresnel mode sets a property block and leaves the layer alone. `OnFocusEnter` and `OnFocusExit` are not on this class; the interactable calls `SetFocused`.

```csharp
using System.Collections.Generic;
using UnityEngine;

/// <summary>
/// Toggles a hull outline or a fresnel highlight while an interactable is focused.
/// </summary>
/// <remarks>
/// Hull moves MeshRenderer and SkinnedMeshRenderer objects onto a GameObject layer
/// that the Render Objects features filter. It does not write renderingLayerMask.
/// Fresnel sets _Highlight on a property block. The material shader has to read it.
/// </remarks>
[DisallowMultipleComponent]
public class Outline : MonoBehaviour
{
    public enum Mode
    {
        Hull,
        Fresnel
    }

    [SerializeField] Mode mode = Mode.Hull;

    [Tooltip("GameObject layer the Render Objects features filter. Not a rendering layer.")]
    [SerializeField] string outlineLayer = "Outline";

    [SerializeField] string highlightProperty = "_Highlight";

    readonly List<Renderer> _renderers = new List<Renderer>();
    readonly List<int> _layers = new List<int>();
    MaterialPropertyBlock _block;
    int _outlineLayerId = -1;
    int _highlightId;
    bool _focused;
    bool _warned;

    public bool IsFocused => _focused;

    public void SetFocused(bool focused)
    {
        _focused = focused;
        Apply();
    }

    void OnEnable()
    {
        _highlightId = Shader.PropertyToID(highlightProperty);
        _outlineLayerId = LayerMask.NameToLayer(outlineLayer);
        CacheRenderers();
        Apply();
    }

    void OnDisable()
    {
        _focused = false;
        Apply();
    }

    void OnValidate()
    {
        if (!Application.isPlaying || !isActiveAndEnabled)
            return;

        _highlightId = Shader.PropertyToID(highlightProperty);
        _outlineLayerId = LayerMask.NameToLayer(outlineLayer);
        Apply();
    }

    void CacheRenderers()
    {
        _renderers.Clear();
        _layers.Clear();
        GetComponentsInChildren(false, _renderers);

        for (int i = _renderers.Count - 1; i >= 0; i--)
        {
            Renderer renderer = _renderers[i];
            if (renderer is MeshRenderer || renderer is SkinnedMeshRenderer)
                continue;
            _renderers.RemoveAt(i);
        }

        for (int i = 0; i < _renderers.Count; i++)
            _layers.Add(_renderers[i].gameObject.layer);
    }

    void Apply()
    {
        if (mode == Mode.Fresnel)
            ApplyFresnel();
        else
            ApplyHull();
    }

    void ApplyHull()
    {
        ClearPropertyBlocks();

        if (_outlineLayerId < 0)
        {
            if (!_warned && _focused)
            {
                _warned = true;
                Debug.LogWarning("Outline layer '" + outlineLayer + "' does not exist.", this);
            }

            return;
        }

        for (int i = 0; i < _renderers.Count; i++)
        {
            if (_renderers[i] == null)
                continue;
            _renderers[i].gameObject.layer = _focused ? _outlineLayerId : _layers[i];
        }
    }

    void ApplyFresnel()
    {
        RestoreLayers();

        if (_block == null)
            _block = new MaterialPropertyBlock();

        for (int i = 0; i < _renderers.Count; i++)
        {
            Renderer renderer = _renderers[i];
            if (renderer == null)
                continue;

            if (!_focused)
            {
                renderer.SetPropertyBlock(null);
                continue;
            }

            renderer.GetPropertyBlock(_block);
            _block.SetFloat(_highlightId, 1f);
            renderer.SetPropertyBlock(_block);
        }
    }

    void ClearPropertyBlocks()
    {
        for (int i = 0; i < _renderers.Count; i++)
        {
            if (_renderers[i] != null)
                _renderers[i].SetPropertyBlock(null);
        }
    }

    void RestoreLayers()
    {
        for (int i = 0; i < _renderers.Count; i++)
        {
            if (_renderers[i] != null)
                _renderers[i].gameObject.layer = _layers[i];
        }
    }
}
```

## Focus

The [interaction](../mechanics/interaction.md) contract already has the two callbacks. They fire when the focused instance changes, not every frame. A fade belongs in `Update` on this component, started from `SetFocused`, which is the same rule as the interaction page.

`DoorInteractable` and `PickupInteractable` do not reference `Outline`, so the interaction scripts still compile on their own. The field below is what you add to the interactable that should light up.

```csharp
[SerializeField] Outline outline;

public void OnFocusEnter(Interactor interactor)
{
    if (outline != null)
        outline.SetFocused(true);
}

public void OnFocusExit(Interactor interactor)
{
    if (outline != null)
        outline.SetFocused(false);
}
```

!!! warning "Common pitfalls"

    MSAA covers the hull, because it is ordinary geometry, and the stencil test runs per sample. The full-screen pass reads a resolved depth texture and a normal texture, not the multi-sample colour buffer, so its contour sits off the antialiased silhouette and shimmers. Turn MSAA off for that pass, or keep the hull.

    World-space extrusion is in metres, so a uniform parent scale does not change the width. Non-uniform scale still bends the normal. Object-space extrusion multiplies by the lossy scale. A negative scale flips winding, and **Cull Front** then discards the hull.

    URP skins `POSITION` and `NORMAL` before the vertex shader. A smoothed normal in UV3 is not skinned and stays in bind pose, so a posed character grows the outline from the bind shape. **Use Smoothed Normals** stays off on a skinned mesh. Hard edges on a static mesh still need that UV3 average, or the stroke gaps at the split.

    Both Render Objects features use **After Rendering Opaques**, with the mask above the hull. Earlier than that, the object has not written colour and depth yet. Later than transparents, the stroke draws over glass. **Write Depth** stays off so the stroke does not hide what draws after it. **Less Equal** keeps it behind walls. **Set As Input Attachment** ignores the stencil override.

    The hull and mask properties sit in `UnityPerMaterial`, and the materials are shared, so those draws stay on the SRP Batcher. **Override Mode: Shader** does not. Fresnel mode sets a `MaterialPropertyBlock` while the object is focused, and that renderer leaves the batch until the block is cleared. Setting `_Highlight` on the shared material lights up every object that uses it.

    Render Objects filters the GameObject layer. Writing `renderingLayerMask` does not select it. Moving the layer also moves any collider on that object: put the mesh on a child, or copy the collision-matrix row onto `Outline`. The renderer's **Opaque Layer Mask** has to include `Outline`, or the focused mesh vanishes apart from the stroke.

    Deferred stores material bits in the stencil during the G-buffer. These features run **after** opaques, once lighting has consumed that stencil. Do not move them earlier. Forward and Forward+ are the paths this was written for.

    The minimal fresnel shader is unlit and has only a forward pass. Objects using it cast no shadows and are absent from the depth and normals textures. Use the Lit Shader Graph version for anything in the level.

    The component caches renderers in `OnEnable`. A mesh added after that, or one that was inactive, is not moved. Hull mode clears property blocks on those renderers. The full-screen edge is the whole frame; it does not know which prop is focused.
