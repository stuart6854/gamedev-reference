---
uses:
  - name: Base building
    text: Walls, floors, and pipes built at any size and subdivision, with colliders that match.
  - name: Strategy and tactics
    text: Range rings, selection discs, and area markers generated to the exact radius.
  - name: Roguelikes
    text: Procedural props and levels made from parts that are generated, not imported.
---

# Primitive generation

Building basic shapes in code: a plane, a cube, spheres, a cylinder and a cone, a capsule, a torus, and flat discs and rings. Each is a list of vertices, each with a position, a normal, and a UV, and a list of triangles that index them. The work is in three decisions: which vertices to share, which way round each triangle goes, and where the texture seams fall.

The code on this page is Python, written to read as pseudocode. It runs as written; every shape below was checked by script so that every triangle faces outward and agrees with its normals. A [Unity section](#unity) at the end ports the builder to C#.

## Conventions

- **Y is up.** Shapes sit centred on the origin.
- **Triangle order.** Every triangle `a, b, c` is ordered so that `cross(b - a, c - a)` points out of the front face. Seen from the front, that is **clockwise** in a left-handed system such as Unity or Direct3D, and **anticlockwise** in a right-handed one such as OpenGL. The same numbers render front-side-out in both; the right-handed view is a mirror image, which only shows in text on a texture.
- **`quad(a, b, c, d)`** takes four corners in order around the face and makes the triangles `a, b, c` and `a, c, d`.
- **UVs** run 0 to 1, with v up the texture.

```python
from math import sin, cos, pi, sqrt

def add(a, b): return (a[0]+b[0], a[1]+b[1], a[2]+b[2])
def sub(a, b): return (a[0]-b[0], a[1]-b[1], a[2]-b[2])
def scale(a, s): return (a[0]*s, a[1]*s, a[2]*s)
def dot(a, b): return a[0]*b[0] + a[1]*b[1] + a[2]*b[2]
def cross(a, b): return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
def normalize(a):
    l = sqrt(dot(a, a))
    return scale(a, 1/l) if l > 0 else a

class Mesh:
    def __init__(self):
        self.positions, self.normals, self.uvs, self.indices = [], [], [], []
    def vertex(self, p, n, uv):
        self.positions.append(p); self.normals.append(n); self.uvs.append(uv)
        return len(self.positions) - 1
    def tri(self, a, b, c):
        self.indices += [a, b, c]
    def quad(self, a, b, c, d):
        # a, b, c, d clockwise seen from the front
        self.tri(a, b, c); self.tri(a, c, d)
```

## Shared and split vertices

A vertex is one position *with* one normal and one UV. Two faces can share a vertex only if they want the same normal and the same UV there.

| Situation | Vertices at that point |
| --- | --- |
| Smooth surface, inside a texture | Shared. One vertex for every triangle around it. |
| Hard edge, such as a cube's corner | Split. One per face, each with that face's normal. A cube has 24 vertices, not 8. |
| Texture seam, such as a sphere's back | Split. Same position and normal, two UVs: u = 0 on one side, u = 1 on the other. |
| Pole of a UV sphere | Split. One per segment, each with its own u, so the texture does not twist. |

Sharing too much gives smeared lighting on hard edges and a texture that runs backwards across the seam. Sharing too little only costs memory.

## Plane and quad

A subdivided rectangle, used by every flat face on this page. `u_axis` and `v_axis` are the texture's right and up; their cross product, `v` then `u`, is the face's normal.

```python
def grid(m, center, u_axis, v_axis, normal, width, height, nu, nv):
    """A subdivided rectangle. cross(v_axis, u_axis) must equal normal."""
    start = len(m.positions)
    for j in range(nv + 1):
        for i in range(nu + 1):
            s, t = i / nu, j / nv
            p = add(center, add(scale(u_axis, (s - 0.5) * width), scale(v_axis, (t - 0.5) * height)))
            m.vertex(p, normal, (s, t))
    row = nu + 1
    for j in range(nv):
        for i in range(nu):
            a = start + j * row + i
            m.quad(a, a + row, a + row + 1, a + 1)

def plane(m, width, depth, nx, nz):
    grid(m, (0, 0, 0), (1, 0, 0), (0, 0, 1), (0, 1, 0), width, depth, nx, nz)
```

A quad is a plane with one subdivision each way. Subdivide for terrain, water that moves vertices, or anything lit per vertex. Vertex `(i, j)` is at index `j * (nu + 1) + i`.

## Cube

Six subdivided faces, each with its own vertices, so every edge is hard. The table gives each face's normal and texture axes, chosen so the texture is upright on the four sides when seen from outside.

```python
def cube(m, size, n=1):
    h = size / 2
    X, Y, Z = (1, 0, 0), (0, 1, 0), (0, 0, 1)
    neg = lambda a: scale(a, -1)
    faces = [  # normal, u (texture right), v (texture up)
        (X, Z, Y), (neg(X), neg(Z), Y),
        (Z, neg(X), Y), (neg(Z), X, Y),
        (Y, X, Z), (neg(Y), X, neg(Z)),
    ]
    for normal, u, v in faces:
        grid(m, scale(normal, h), u, v, normal, size, size, n, n)
```

A cube that should look rounded, such as a beveled box, needs bevel geometry, not shared normals: averaging the corner normals of a cube makes it look like a lumpy sphere.

## Disc and ring

Flat circles in the XZ plane, facing up, with planar UVs: the texture is laid flat over the shape, so no seam is needed and the ring of vertices closes with `% segments`.

```python
def disc(m, radius, segments):
    c = m.vertex((0, 0, 0), (0, 1, 0), (0.5, 0.5))
    for k in range(segments):
        a = 2 * pi * k / segments
        x, z = cos(a), sin(a)
        m.vertex((x * radius, 0, z * radius), (0, 1, 0), (0.5 + x / 2, 0.5 + z / 2))
    for k in range(segments):
        m.tri(c, c + 1 + (k + 1) % segments, c + 1 + k)

def ring(m, inner, outer, segments):
    start = len(m.positions)
    for k in range(segments):
        a = 2 * pi * k / segments
        x, z = cos(a), sin(a)
        for r in (inner, outer):
            t = r / outer
            m.vertex((x * r, 0, z * r), (0, 1, 0), (0.5 + x * t / 2, 0.5 + z * t / 2))
    for k in range(segments):
        i0 = start + 2 * k
        i1 = start + 2 * ((k + 1) % segments)
        m.quad(i0, i1, i1 + 1, i0 + 1)  # inner k, inner k+1, outer k+1, outer k
```

A disc is a fan around a centre vertex. A ring is a strip of quads between an inner and an outer circle: a selection marker or a range indicator. For a ring textured along its length instead, give u the angle and v the radius, and add a seam column as the sphere does.

## UV sphere

Rings of latitude from the top pole to the bottom, and segments of longitude around. It maps cleanly to an equirectangular texture, such as a planet or a sky.

```python
def uv_sphere(m, radius, segments, rings):
    start = len(m.positions)
    for i in range(rings + 1):
        theta = pi * i / rings            # 0 at the top
        for j in range(segments + 1):     # one extra column: the UV seam
            phi = 2 * pi * j / segments
            n = (sin(theta) * cos(phi), cos(theta), sin(theta) * sin(phi))
            m.vertex(scale(n, radius), n, (j / segments, 1 - i / rings))
    row = segments + 1
    for i in range(rings):
        for j in range(segments):
            a = start + i * row + j       # upper left
            b = a + 1                     # upper right
            c = a + row + 1               # lower right
            d = a + row                   # lower left
            if i != 0:
                m.tri(a, b, c)
            if i != rings - 1:
                m.tri(a, c, d)
```

- **The seam column.** There are `segments + 1` columns. The last has the same positions and normals as the first, with u = 1 instead of 0.
- **The poles.** The top row is `segments + 1` copies of the pole, each with its own u. The first band of quads collapses into triangles, so the degenerate half of each is skipped. The same at the bottom.
- **Uneven triangles.** Triangles are tall and thin near the poles and large at the equator. For even triangles, use an icosphere.

## Icosphere

An icosahedron, 20 equal triangles, with every triangle split into four, and every new point pushed out onto the sphere. Each subdivision quadruples the triangle count. The triangles stay close to equal in size, which suits physics, deformation, and planet terrain.

```python
def icosphere(m, radius, subdivisions):
    t = (1 + sqrt(5)) / 2
    corners = [(-1, t, 0), (1, t, 0), (-1, -t, 0), (1, -t, 0),
               (0, -1, t), (0, 1, t), (0, -1, -t), (0, 1, -t),
               (t, 0, -1), (t, 0, 1), (-t, 0, -1), (-t, 0, 1)]
    faces = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11),
             (1, 5, 9), (5, 11, 4), (11, 10, 2), (10, 7, 6), (7, 1, 8),
             (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9),
             (4, 9, 5), (2, 4, 11), (6, 2, 10), (8, 6, 7), (9, 8, 1)]
    points = [normalize(p) for p in corners]
    for _ in range(subdivisions):
        midpoint = {}
        def middle(a, b):
            key = (min(a, b), max(a, b))       # shared edges share one new point
            if key not in midpoint:
                points.append(normalize(scale(add(points[a], points[b]), 0.5)))
                midpoint[key] = len(points) - 1
            return midpoint[key]
        next_faces = []
        for a, b, c in faces:
            ab, bc, ca = middle(a, b), middle(b, c), middle(c, a)
            next_faces += [(a, ab, ca), (b, bc, ab), (c, ca, bc), (ab, bc, ca)]
        faces = next_faces
    start = len(m.positions)
    for p in points:
        m.vertex(scale(p, radius), p, (0, 0))   # UVs: see the notes
    for a, b, c in faces:
        m.tri(start + a, start + b, start + c)
```

- **Shared midpoints.** Two neighbouring triangles share an edge. The midpoint cache, keyed by the edge's two vertex indices in order, gives them the same new vertex, so the mesh has no cracks.
- **UVs.** There is no seam to cut along, so an icosphere is usually textured in the shader: triplanar mapping, a cube map, or a 3D noise. Spherical UVs computed from the normal need the triangles across the u = 0 line split with duplicated vertices, or the texture smears across the back.

## Cylinder and cone

A ring of quads between a bottom circle and a top circle, and a disc on each end with its own vertices, so the rim is a hard edge. With the top radius at 0, it is a cone.

```python
def cylinder(m, bottom_radius, top_radius, height, segments, caps=True):
    """A cone when top_radius is 0. Caps are separate vertices: a hard edge."""
    start = len(m.positions)
    slope = bottom_radius - top_radius
    for v, (r, y) in enumerate(((bottom_radius, -height / 2), (top_radius, height / 2))):
        # A cone's tip gets one vertex per side, turned half a side, so each face has its own tip normal.
        turn = 0.5 if (v == 1 and r == 0) else 0.0
        for j in range(segments + 1):
            phi = 2 * pi * (j + turn) / segments
            x, z = cos(phi), sin(phi)
            n = normalize((x * height, slope, z * height))
            m.vertex((x * r, y, z * r), n, (j / segments, v))
    row = segments + 1
    for j in range(segments):
        a = start + j          # bottom j
        b = a + 1              # bottom j+1
        c = a + row + 1        # top j+1
        d = a + row            # top j
        if top_radius > 0:
            m.quad(a, d, c, b)
        else:
            m.tri(a, d, b)     # d is the tip
    if caps:
        cap(m, bottom_radius, -height / 2, segments, down=True)
        if top_radius > 0:
            cap(m, top_radius, height / 2, segments, down=False)

def cap(m, radius, y, segments, down):
    n = (0, -1, 0) if down else (0, 1, 0)
    c = m.vertex((0, y, 0), n, (0.5, 0.5))
    for k in range(segments):
        a = 2 * pi * k / segments
        x, z = cos(a), sin(a)
        m.vertex((x * radius, y, z * radius), n, (0.5 + x / 2, 0.5 + z / 2))
    for k in range(segments):
        p, q = c + 1 + k, c + 1 + (k + 1) % segments
        if down:
            m.tri(c, p, q)
        else:
            m.tri(c, q, p)
```

- **Side normals** lean when the radii differ: `(x * height, bottom_radius - top_radius, z * height)`, normalised, is perpendicular to the sloped side.
- **A cone's tip** has one vertex per side, not one shared point. Each is turned half a side so its normal points out of the middle of its triangle. A single shared tip vertex has one normal, which no face agrees with, and the shading pinches.
- A pipe is a cylinder without caps. A frustum, such as a lampshade, is two non-zero radii.

## Capsule

Two hemispheres joined by a cylinder. The rows are the top half of a UV sphere, raised by half the straight length, then the bottom half, lowered by it. The two equator rows have the same normals and different heights, and the band between them is the cylinder.

```python
def capsule(m, radius, height, segments, rings):
    """height is the total, tip to tip. rings must be even: half for each end."""
    start = len(m.positions)
    half = max(0.0, height / 2 - radius)       # half the straight middle
    rows = []                                  # (theta, y offset)
    for i in range(rings // 2 + 1):
        rows.append((pi * i / rings, half))      # top hemisphere, down to the equator
    for i in range(rings // 2, rings + 1):
        rows.append((pi * i / rings, -half))     # bottom hemisphere, from the equator
    # v by distance along the profile, so the texture does not stretch on the middle
    total = pi * radius + 2 * half
    travelled = 0.0
    for k, (theta, y) in enumerate(rows):
        if k > 0:
            prev_theta, prev_y = rows[k - 1]
            travelled += radius * (theta - prev_theta) + abs(y - prev_y)
        for j in range(segments + 1):
            phi = 2 * pi * j / segments
            n = (sin(theta) * cos(phi), cos(theta), sin(theta) * sin(phi))
            m.vertex(add(scale(n, radius), (0, y, 0)), n, (j / segments, 1 - travelled / total))
    row = segments + 1
    last = len(rows) - 1
    for i in range(last):
        for j in range(segments):
            a = start + i * row + j
            b, c, d = a + 1, a + row + 1, a + row
            if i != 0:
                m.tri(a, b, c)
            if i != last - 1:
                m.tri(a, c, d)
```

- `height` is the full height, tip to tip, as a character controller's capsule is measured. With `height` at or below `2 * radius`, it is a sphere with an empty band at the equator; build a UV sphere instead.
- v is measured along the profile, so a texture is not squashed onto the caps and stretched along the middle.

## Torus

A circle swept round a larger circle. `major` is the distance from the centre to the middle of the tube, `minor` the tube's radius.

```python
def torus(m, major, minor, segments, sides):
    start = len(m.positions)
    for i in range(sides + 1):
        theta = 2 * pi * i / sides                 # around the tube
        for j in range(segments + 1):
            phi = 2 * pi * j / segments            # around the centre
            n = (cos(theta) * cos(phi), sin(theta), cos(theta) * sin(phi))
            centre = (major * cos(phi), 0, major * sin(phi))
            m.vertex(add(centre, scale(n, minor)), n, (j / segments, i / sides))
    row = segments + 1
    for i in range(sides):
        for j in range(segments):
            a = start + i * row + j
            m.quad(a, a + row, a + row + 1, a + 1)
```

Both directions wrap, so both need a seam: `segments + 1` columns and `sides + 1` rows, with the last of each repeating the first's position and normal and taking u or v = 1.

## Counts

| Shape | Vertices | Triangles |
| --- | --- | --- |
| Plane, `nx` by `nz` | (nx + 1)(nz + 1) | 2 nx nz |
| Cube, `n` per edge | 6 (n + 1)² | 12 n² |
| Disc, `s` segments | s + 1 | s |
| Ring, `s` segments | 2 s | 2 s |
| UV sphere, `s` segments, `r` rings | (s + 1)(r + 1) | 2 s (r − 1) |
| Icosphere, `k` subdivisions | 10 · 4ᵏ + 2 | 20 · 4ᵏ |
| Cylinder with caps, `s` | 4 (s + 1) | 4 s |
| Cone with base, `s` | 3 (s + 1) | 2 s |
| Capsule, `s` segments, `r` rings | (s + 1)(r + 2) | 2 s r |
| Torus, `s` segments, `t` sides | (s + 1)(t + 1) | 2 s t |

A UV sphere with 24 segments and 16 rings has 425 vertices and 720 triangles. An icosphere at 3 subdivisions has 642 and 1,280, more even, without UVs.

## Tangents and bounds

- **Tangents** are needed for normal maps. They follow the UV directions, and are best computed by the engine or with the MikkTSpace method, so the normal map baker and the renderer agree.
- **Bounds** are the box that contains every position. Engines use them for culling. Update them whenever positions change.
- **Index size.** 16-bit indices address 65,535 vertices. Past that, use 32-bit indices, or split the mesh.

## Unity

Unity's `GameObject.CreatePrimitive` makes a fixed cube, sphere, capsule, cylinder, plane, and quad. Generate your own for other sizes and subdivisions, a cone, a torus, a disc or a ring, shapes whose collider must match exactly, or geometry that changes at runtime.

The builder in C#. Unity is left-handed with clockwise front faces, so the windings above carry over unchanged.

```csharp
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;

/// <summary>
/// Collects vertices and triangles, then writes them to a Mesh.
/// </summary>
public class MeshBuilder
{
    public readonly List<Vector3> Positions = new List<Vector3>();
    public readonly List<Vector3> Normals = new List<Vector3>();
    public readonly List<Vector2> Uvs = new List<Vector2>();
    public readonly List<int> Indices = new List<int>();

    public int Vertex(Vector3 position, Vector3 normal, Vector2 uv)
    {
        Positions.Add(position);
        Normals.Add(normal);
        Uvs.Add(uv);
        return Positions.Count - 1;
    }

    public void Tri(int a, int b, int c)
    {
        Indices.Add(a);
        Indices.Add(b);
        Indices.Add(c);
    }

    public void Quad(int a, int b, int c, int d)
    {
        Tri(a, b, c);
        Tri(a, c, d);
    }

    public Mesh ToMesh(Mesh mesh = null)
    {
        if (mesh == null)
            mesh = new Mesh { name = "Generated" };
        mesh.Clear();
        mesh.indexFormat = Positions.Count > 65535 ? IndexFormat.UInt32 : IndexFormat.UInt16;
        mesh.SetVertices(Positions);
        mesh.SetNormals(Normals);
        mesh.SetUVs(0, Uvs);
        mesh.SetTriangles(Indices, 0); // also recalculates the bounds
        mesh.RecalculateTangents();
        return mesh;
    }
}
```

A shape ports line for line. The UV sphere:

```csharp
public static class Primitives
{
    public static void UvSphere(MeshBuilder m, float radius, int segments, int rings)
    {
        int start = m.Positions.Count;
        for (int i = 0; i <= rings; i++)
        {
            float theta = Mathf.PI * i / rings;
            for (int j = 0; j <= segments; j++)
            {
                float phi = 2f * Mathf.PI * j / segments;
                var n = new Vector3(Mathf.Sin(theta) * Mathf.Cos(phi), Mathf.Cos(theta), Mathf.Sin(theta) * Mathf.Sin(phi));
                m.Vertex(n * radius, n, new Vector2((float)j / segments, 1f - (float)i / rings));
            }
        }

        int row = segments + 1;
        for (int i = 0; i < rings; i++)
        {
            for (int j = 0; j < segments; j++)
            {
                int a = start + i * row + j;
                int b = a + 1, c = a + row + 1, d = a + row;
                if (i != 0)
                    m.Tri(a, b, c);
                if (i != rings - 1)
                    m.Tri(a, c, d);
            }
        }
    }
}
```

```csharp
using UnityEngine;

[RequireComponent(typeof(MeshFilter))]
public class GeneratedSphere : MonoBehaviour
{
    [SerializeField] float radius = 0.5f;
    [SerializeField, Min(3)] int segments = 24;
    [SerializeField, Min(2)] int rings = 16;

    Mesh _mesh;

    void Start() => Build();

    void Build()
    {
        var builder = new MeshBuilder();
        Primitives.UvSphere(builder, radius, segments, rings);
        _mesh = builder.ToMesh(_mesh);
        GetComponent<MeshFilter>().sharedMesh = _mesh;
        if (TryGetComponent(out MeshCollider meshCollider))
            meshCollider.sharedMesh = _mesh;
    }

    void OnDestroy()
    {
        // A mesh made in code is not an asset; destroy it with its owner.
        if (_mesh != null)
            Destroy(_mesh);
    }
}
```

- Reusing the `Mesh` in `ToMesh` avoids leaking a new one per rebuild.
- `MarkDynamic()` on a mesh rebuilt every frame tells the driver to expect frequent updates.
- To save a generated mesh as an asset, in editor code, `AssetDatabase.CreateAsset(mesh, "Assets/Meshes/Sphere.asset")`.
- For many meshes, or meshes built in jobs, the `Mesh.MeshData` API writes vertex buffers directly without the lists.
- **ProBuilder** is Unity's package for modelling and editing such shapes by hand in the editor.

!!! warning "Common pitfalls"

    A cube with 8 shared vertices has one averaged normal per corner and looks smooth and wrong. Split the vertices per face.

    A sphere with `segments` columns instead of `segments + 1` runs its texture backwards across one strip, from u near 1 back to 0.

    Triangles wound the wrong way are invisible from outside, because back faces are culled. Check `cross(b - a, c - a)` against the intended normal.

    More than 65,535 vertices with 16-bit indices wraps the indices and draws garbage. Switch to 32-bit indices.

    Moving vertices without updating the bounds culls the mesh while it is still on screen.
