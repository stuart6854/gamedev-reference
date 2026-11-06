---
uses:
  - name: Open worlds
    text: Hiding the draw distance, and height fog that pools in valleys.
  - name: Top-down survival
    text: Murky atmosphere that limits how far the player can read the map.
---

# Fog

Fog blends each surface towards a fog colour by how much air lies between it and the camera. It gives a sense of depth, and, when the fog colour matches the background, it hides where the scene stops. Shaders here are GLSL. The [ground grid](grid.md) page shows a typical surface to fog.

## The fog factor

Every fog model computes one number per pixel, the fog factor `f`: 0 means no fog and 1 means fully fogged. The colour is then:

```glsl
color = mix(surfaceColor, fogColor, f);
```

### Distance fog

```glsl
// Linear: no fog before fogStart, full fog at fogEnd.
float fogLinear(float d, float fogStart, float fogEnd) {
    return clamp((d - fogStart) / (fogEnd - fogStart), 0.0, 1.0);
}

// Exponential: what light passing through uniform fog actually does.
float fogExp(float d, float density) {
    return 1.0 - exp(-density * d);
}

// Squared exponential: clear near the camera, then thickens quickly.
float fogExp2(float d, float density) {
    float x = density * d;
    return 1.0 - exp(-x * x);
}
```

- **Linear** is the easiest to control, and the right choice for hiding a draw distance: set `fogEnd` just inside the far plane, and nothing ever pops in.
- **Exponential** is physically based: each unit of distance absorbs the same fraction of the remaining light. It never quite reaches 1, so it cannot hide a far plane by itself.
- **Exp2** keeps the foreground clear and thickens later, which often reads better for games.

To set the density from a visibility distance `v`, the distance at which the fog is 99 % opaque:

| Model | Density |
| --- | --- |
| Exp | \( \ln 100 / v \approx 4.6 / v \) |
| Exp2 | \( \sqrt{\ln 100} / v \approx 2.15 / v \) |

### Which distance

```glsl
float d = length(worldPos - cameraPosition);      // radial distance
// not: float d = -viewPos.z;                     // depth along the view axis
```

Fog from view depth is cheaper but wrong at the screen's edges: an object to the side is further away than its depth says, so it gets too little fog, and turning the camera on the spot changes how foggy it is. Radial distance does not depend on which way the camera is facing. Use it.

### Matching the background

A common setup makes the fog colour the same as the background (the clear colour), so objects fade into nothing as they recede. If they differ, distant objects show up as flat silhouettes in the fog colour against a different background.

With a gradient sky, there is no single background colour. Take the fog colour from the sky in the direction of the pixel:

```glsl
vec3 viewDir = normalize(worldPos - cameraPosition);
vec3 fogColor = skyColor(viewDir);                // the same function the sky shader uses
```

Then a distant hill fades into exactly the sky behind it. The sky shader itself is not fogged (see [sky](#a-sky-to-match)).

### Per pixel, in linear space

- Compute fog per pixel, not per vertex. Distance interpolated across a large triangle, such as a ground plane, is wrong in the middle: a quad with every corner far from the camera fogs its middle heavily, even when the camera is standing on it.
- Mix in linear colour space, before tone mapping, with the fog colour also in linear. Mixing gamma-encoded colours makes the fade look uneven, darkening in the middle of the transition.

## Height fog

Real fog sits low: in valleys and over water, thinning with height. Model its density as falling off exponentially with height:

\[
\rho(y) = a\, e^{-b\,(y - h_0)}
\]

`a` is the density at height \(h_0\), and `b` is how quickly it thins with height. The amount of fog along the ray from the camera \(c\) to the point \(p\) (the **optical depth**) is the integral of the density along the ray, which has a closed form because the ray's height changes linearly:

\[
\tau = \int_0^L \rho(c_y + t\,\tfrac{\Delta y}{L})\, dt = L\, \frac{\rho(c_y) - \rho(p_y)}{b\, \Delta y}, \qquad \Delta y = p_y - c_y
\]

and the fog factor is \(f = 1 - e^{-\tau}\).

```glsl
uniform float heightFogDensity;     // a
uniform float heightFogFalloff;     // b
uniform float heightFogBase;        // h0

float density(float y) {
    return heightFogDensity * exp(-heightFogFalloff * (y - heightFogBase));
}

float heightFogDepth(vec3 cam, vec3 p) {
    vec3 ray = p - cam;
    float L = length(ray);
    float dy = ray.y;
    if (abs(heightFogFalloff * dy) < 1e-4)
        return L * density(cam.y);                // level ray: constant density
    return L * (density(cam.y) - density(p.y)) / (heightFogFalloff * dy);
}
```

The difference form avoids the overflow in the textbook version, \(L\,\rho(c_y)\,(1 - e^{-b\Delta y})/(b\Delta y)\), whose \(e^{-b\Delta y}\) becomes huge when a high camera looks down a long way.

- The density grows without limit below \(h_0\). Clamp the heights passed to `density` to a floor (`max(y, heightFogBase - 50.0)`), or a deep pit fills with solid fog.
- Height fog uses the real height of the surface, so it fogs a valley floor more than the hilltop beside it, at the same distance. That is the whole effect, and distance fog cannot do it.

### Combining fogs

Two fogs combine by **adding optical depths**, not by mixing their factors:

```glsl
float tau = globalDensity * d + heightFogDepth(cameraPosition, worldPos);
float f = 1.0 - exp(-tau);
```

The exponential form of distance fog is already an optical depth (`density * d`), so it adds directly. Linear fog does not fit this model; to combine it, use `max` of the two factors.

To keep fog off the area right around the camera, start the ray at a distance `s`: multiply the optical depth by `max(0.0, d - s) / d`.

## Fog in custom shaders

Fog only works if every surface gets the same fog. A grid, particles, or a custom material that skips it shows up as a bright cut-out against foggy surroundings. Put fog in one shared include and call it at the end of every fragment shader:

```glsl
// fog.glsl
uniform vec3 cameraPosition;
uniform float fogDensity;
uniform vec3 fogBaseColor;
// ... height fog and scattering uniforms

float fogFactor(vec3 worldPos) {
    float d = length(worldPos - cameraPosition);
    float tau = fogDensity * d + heightFogDepth(cameraPosition, worldPos);
    return 1.0 - exp(-tau);
}

vec3 fogColorFor(vec3 worldPos) { /* fogBaseColor, or sky colour, plus scattering below */ }

vec3 applyFog(vec3 color, vec3 worldPos) {
    return mix(color, fogColorFor(worldPos), fogFactor(worldPos));
}
```

Each shader passes its world position from the vertex shader. Then the cases that need something other than `applyFog`:

| Surface | Fog it as | Why |
| --- | --- | --- |
| Opaque, lit or unlit | `applyFog(color, worldPos)` | |
| Emissive and glowing | `applyFog` as well | A bright lamp should fade into fog too, or it reads as being in front of it. |
| Alpha blended | `rgb = applyFog(rgb, worldPos)`, alpha unchanged | Blending over an already fogged background then gives the right result. |
| Premultiplied alpha | `rgb = mix(rgb, fogColor * a, f)` | The fog colour must be scaled by the pixel's own alpha. |
| Additive (sparks, glows) | `rgb *= 1.0 - f` | It adds onto a background that is already fogged, so it should fade to black (adds nothing), not towards the fog colour. |
| Sky | not fogged | It is infinitely far away, so it would be pure fog colour. See [sky](#a-sky-to-match). |

### Grids and other transparent surfaces

A ground grid, decals, and selection rings are drawn over a surface that is already fogged. Fading their alpha is all they need: `alpha *= 1.0 - fogFactor(worldPos)`. With the background the same colour as the fog, this is how the grid dissolves into the distance.

### Fog as a full-screen pass

Instead of in every material, fog can be applied in one post-processing pass: read the depth buffer, reconstruct each pixel's world position, and apply the same functions.

- One place to change, and opaque materials need no fog code.
- Transparent surfaces do not write depth, so the pass fogs whatever is behind them, not the transparent surface itself. They still need fog in their own shaders.
- The sky must be skipped (depth at the far plane).

Engines often do both: a pass for opaque geometry, and the include for transparents.

## Scattering colour

Real fog is brighter towards the sun: light scattered towards the camera by the fog. Tint the fog colour by how closely the view direction lines up with the sun:

```glsl
uniform vec3 sunDirection;          // towards the sun, normalised
uniform vec3 sunFogColor;
uniform float sunFogExponent;       // e.g. 8.0: higher is a tighter glow

vec3 fogColorFor(vec3 worldPos) {
    vec3 viewDir = normalize(worldPos - cameraPosition);
    float sun = pow(max(dot(viewDir, sunDirection), 0.0), sunFogExponent);
    return mix(fogBaseColor, sunFogColor, sun);
}
```

Looking towards a low sun, the fog glows warm. Looking away, it stays the base colour.

Fog can also absorb colours unequally. Use a density per channel, slightly higher for blue than red, and distant objects take on a blue-grey haze:

```glsl
uniform vec3 fogDensityRGB;         // e.g. vec3(0.010, 0.012, 0.016)

vec3 extinction = exp(-fogDensityRGB * d);           // light left per channel
color = color * extinction + fogColor * (1.0 - extinction);
```

This is aerial perspective in its simplest form. The full version, with Rayleigh and Mie scattering, is an atmosphere model; this approximation covers most game scenes.

## A sky to match

The sky and the fog must meet at the horizon, or geometry fading into the fog leaves a visible band against the sky. Build the sky from the same colours:

```glsl
vec3 skyColor(vec3 dir) {
    float up = clamp(dir.y, 0.0, 1.0);
    vec3 sky = mix(horizonColor, zenithColor, pow(up, 0.5));
    float sun = pow(max(dot(dir, sunDirection), 0.0), sunFogExponent);
    return mix(sky, sunFogColor, sun);
}
```

Use `skyColor(viewDir)` as the fog colour, with `horizonColor` also the fog's base colour. Then fully fogged geometry is exactly the colour of the sky behind it, at any height and towards or away from the sun. Below the horizon (`dir.y < 0`) keep the horizon colour, so the ground fades into it too.

For a flat, single-colour background, all of this reduces to one colour: clear the screen with `fogBaseColor` and the fog takes care of the rest.
