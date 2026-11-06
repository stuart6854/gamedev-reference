---
uses:
  - name: Base building
    text: A placement grid on the ground that shows where pieces will snap.
  - name: Strategy and tactics
    text: A map grid that stays crisp from close up to a zoomed-out overview.
---

# Ground grid

The reference grid an editor draws on the ground plane: thin minor lines, stronger major lines, coloured X and Z axes, and a fade into the distance. A mesh of lines is the obvious way to build one and shimmers badly. A fragment shader that computes the lines from the world position stays clean at every distance and angle. Shaders here are GLSL; the [fog](fog.md) page covers fading the grid and everything else into the background.

## A mesh of lines

```text
lines = []
for i in -n .. n:
    lines += [(i * spacing, 0, -n * spacing), (i * spacing, 0, n * spacing)]   // along Z
    lines += [(-n * spacing, 0, i * spacing), (n * spacing, 0, i * spacing)]   // along X
draw lines as a line list
```

Simple, and fine for a small, fixed grid seen from above. It goes wrong as soon as the camera moves around:

- **Shimmer and moiré.** Rasterised lines are one pixel wide and not anti-aliased. Far away, several lines land in one pixel or between pixels, and the pattern crawls as the camera moves.
- **No width control.** Most drivers, and every WebGL implementation, draw lines only one pixel wide. Thicker lines need quads.
- **A hard edge.** The grid stops at `n * spacing`, and an infinite-looking grid needs thousands of lines.
- **Fixed spacing.** Zoom out and the lines merge into a solid sheet. Zoom in and there are none in view.

## A shader grid

Draw one large quad on the ground and work out, per pixel, how close the pixel is to a grid line.

### The quad

Centre the quad under the camera every frame, so it always covers the view:

```glsl
// Vertex shader. position is a unit quad in XZ: (-1, 0, -1) to (1, 0, 1).
uniform mat4 viewProjection;
uniform vec3 cameraPosition;
uniform float extent;               // half-size in world units; no more than the far plane

in vec3 position;
out vec3 worldPos;

void main() {
    worldPos = vec3(cameraPosition.x + position.x * extent, 0.0,
                    cameraPosition.z + position.z * extent);
    gl_Position = viewProjection * vec4(worldPos, 1.0);
}
```

The lines come from `worldPos`, not from the quad's UVs, so moving the quad never moves the lines.

### Anti-aliased lines

`fwidth(x)` is how much `x` changes from one pixel to the next. Dividing a distance by it converts the distance into pixels, which is exactly what anti-aliasing needs:

```glsl
// 1 on a line, 0 between lines. Lines are about widthPx pixels wide at any distance.
float gridLines(vec2 p, float spacing, float widthPx) {
    vec2 coord = p / spacing;
    vec2 distPx = abs(fract(coord - 0.5) - 0.5) / fwidth(coord);   // distance to the nearest line, in pixels
    float d = min(distPx.x, distPx.y);
    return 1.0 - clamp(d - 0.5 * (widthPx - 1.0), 0.0, 1.0);
}
```

`abs(fract(c - 0.5) - 0.5)` is the distance from `c` to the nearest whole number: 0 on a line, 0.5 halfway between two. That is the core of every shader grid.

Constant-pixel-width lines look good near the camera, but in the distance the cells shrink and the lines do not. Past the point where cells are a few pixels across, the lines fill the whole cell and the grid turns into a solid grey sheet.

### Lines with a world width

The fix, from Ben Golus's "The Best Darn Grid Shader (Yet)", is to give lines a width in world units, a fraction of a cell. When a line becomes thinner than a pixel, draw it one pixel wide but fainter, in proportion. When a whole cell becomes smaller than a couple of pixels, fade to the cell's average coverage, which is what the grid would look like if it were perfectly filtered:

```glsl
// uv: position in cells. lineWidth: line width as a fraction of a cell, per axis.
float pristineGrid(vec2 uv, vec2 lineWidth) {
    vec2 deriv = vec2(length(vec2(dFdx(uv.x), dFdy(uv.x))),
                      length(vec2(dFdx(uv.y), dFdy(uv.y))));
    vec2 invert = step(0.5, lineWidth);                         // lines wider than half a cell: draw the gaps
    vec2 target = mix(lineWidth, 1.0 - lineWidth, invert);
    vec2 draw = clamp(target, deriv, vec2(0.5));                // never thinner than one pixel
    vec2 aa = deriv * 1.5;

    vec2 g = abs(fract(uv) * 2.0 - 1.0);                        // 1 on a line, 0 mid-cell
    g = mix(1.0 - g, g, invert);
    vec2 lines = smoothstep(draw + aa, draw - aa, g);
    lines *= clamp(target / draw, 0.0, 1.0);                    // fainter when drawn wider than it is
    lines = mix(lines, target, clamp(deriv * 2.0 - 1.0, 0.0, 1.0));    // tiny cells: average coverage
    lines = mix(lines, 1.0 - lines, invert);
    return mix(lines.x, 1.0, lines.y);                          // combine the two directions
}
```

The result fades smoothly into an even, faint tint in the distance, with no moiré at grazing angles. Use it in place of `gridLines` everywhere below.

### Minor lines, major lines, and axes

```glsl
uniform float minorSpacing;         // 1.0
uniform float majorSpacing;         // 10.0
uniform float lineWidth;            // world units, e.g. 0.02
uniform vec3 minorColor, majorColor, xAxisColor, zAxisColor;

in vec3 worldPos;
out vec4 fragColor;

// 1 within halfWidth of the line coord == 0, at least one pixel wide.
float axisLine(float coord, float halfWidth) {
    float px = fwidth(coord);
    float w = max(halfWidth, px * 0.5);
    float line = 1.0 - smoothstep(w - px, w + px, abs(coord));
    return line * clamp(halfWidth / w, 0.0, 1.0);
}

void main() {
    vec2 p = worldPos.xz;
    float minor = pristineGrid(p / minorSpacing, vec2(lineWidth / minorSpacing));
    float major = pristineGrid(p / majorSpacing, vec2(2.0 * lineWidth / majorSpacing));

    vec3 color = mix(minorColor, majorColor, major);
    float alpha = max(minor * 0.4, major * 0.8);

    float xAxis = axisLine(p.y, lineWidth * 1.5);       // the X axis is the line z == 0
    float zAxis = axisLine(p.x, lineWidth * 1.5);       // the Z axis is the line x == 0
    color = mix(color, xAxisColor, xAxis);
    color = mix(color, zAxisColor, zAxis);
    alpha = max(alpha, max(xAxis, zAxis));

    if (alpha < 0.001) discard;
    fragColor = vec4(color, alpha);
}
```

Dividing the world width by each spacing keeps minor and major lines the same thickness in world units; the major lines here are twice as thick. Editors usually colour the X axis red and the Z axis blue, matching the gizmo.

### Drawing it

- Draw the grid after opaque geometry, with blending on, the depth test on, and depth writes off. Objects in front hide it, and it does not hide anything drawn after it.
- If there is a real floor at `y = 0`, the two z-fight. Lift the grid slightly, or use a depth offset (`glPolygonOffset`).
- Draw it from below too (turn off back-face culling), but at lower alpha, so the camera's side of the ground is obvious.

### A full-screen version

Instead of a quad, draw a full-screen triangle and intersect each pixel's view ray with the ground plane. There is no extent to choose, and the grid reaches the horizon.

```glsl
// Vertex: unproject each corner to the near and far planes.
uniform mat4 inverseViewProjection;
out vec3 nearPoint, farPoint;

vec3 unproject(vec2 ndc, float z) {
    vec4 p = inverseViewProjection * vec4(ndc, z, 1.0);
    return p.xyz / p.w;
}
// in main(): nearPoint = unproject(ndc, -1.0); farPoint = unproject(ndc, 1.0);

// Fragment: find where the ray crosses y = 0, and write that point's depth.
uniform mat4 viewProjection;

void main() {
    float t = -nearPoint.y / (farPoint.y - nearPoint.y);
    if (t <= 0.0 || t >= 1.0) discard;                  // ray misses the ground before the far plane
    vec3 worldPos = nearPoint + t * (farPoint - nearPoint);
    vec4 clip = viewProjection * vec4(worldPos, 1.0);
    gl_FragDepth = 0.5 * (clip.z / clip.w) + 0.5;       // so objects still hide the grid
    // ... grid colour as above
}
```

Writing `gl_FragDepth` turns off early depth testing for the draw, so every pixel runs the shader even where an object covers it. The quad version avoids that, and is easier to fit into an engine's material system. Use the full-screen version when the grid must run to the horizon.

## Fading and level of detail

### Fade with distance

```glsl
uniform vec3 cameraPosition;
uniform float fadeStart, fadeEnd;

float dist = length(worldPos - cameraPosition);
alpha *= 1.0 - smoothstep(fadeStart, fadeEnd, dist);
```

Link `fadeEnd` to how high the camera is (for example `fadeEnd = max(50.0, cameraHeight * 20.0)`), so zooming out shows more grid, not the same small patch. If the scene uses [fog](fog.md#grids-and-other-transparent-surfaces), apply the fog to the grid's alpha as well, so the grid disappears into the background at the same rate as everything else.

### Fade at grazing angles

Looking along the ground, even a perfectly filtered grid becomes a band of grey near the horizon. Fade it out by how flat the view is:

```glsl
vec3 viewDir = normalize(worldPos - cameraPosition);
alpha *= smoothstep(0.0, 0.15, abs(viewDir.y));
```

### Changing spacing with zoom

Zoomed out, 1-unit cells are a few pixels across and only add noise. Pick the spacing per pixel from how much world the pixel covers, and cross-fade between powers of ten:

```glsl
uniform float baseSpacing;          // smallest spacing, e.g. 1.0
uniform float minCellPx;            // e.g. 8.0: thinner cells than this give way to the next level

vec2 p = worldPos.xz;
float worldPerPx = length(fwidth(p));
float level = max(0.0, log(worldPerPx * minCellPx / baseSpacing) / log(10.0));
float lod = floor(level);
float blend = fract(level);

float s0 = baseSpacing * pow(10.0, lod);        // fine level, fading out
float s1 = s0 * 10.0;                           // coarse level, full strength
float w = lineWidth * s0 / baseSpacing;         // line width grows with the level
float fine   = pristineGrid(p / s0, vec2(w / s0));
float coarse = pristineGrid(p / s1, vec2(w / s1));
float grid = max(fine * (1.0 - blend), coarse);
```

Line width is scaled with the level (`w`), so they stay a similar number of pixels thick. Because `worldPerPx` is per pixel, the level changes across the screen: nearby ground shows 1-unit cells while the distance shows 10-unit and 100-unit cells, joined by the cross-fade. For one spacing across the whole screen, compute `level` once on the CPU from the camera's height instead, and pass `lod` and `blend` as uniforms.
