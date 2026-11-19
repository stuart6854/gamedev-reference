# Shader compilation

D3D12 runs **DXIL** and Vulkan runs **SPIR-V**. Both are compiled from source ahead of time, and both can come from the same HLSL: Microsoft's **DXC** compiler outputs DXIL by default and SPIR-V with `-spirv`. One shader language, one compiler, two backends.

| | D3D12 | Vulkan |
| --- | --- | --- |
| Binary format | DXIL | SPIR-V |
| Compiler | DXC (`dxc`, or `dxcompiler.dll` as a library) | DXC with `-spirv`; glslang for GLSL; Slang |
| Profile | `vs_6_6`, `ps_6_6`, `cs_6_6`, `ms_6_5`, `as_6_5` | the same, plus `-fspv-target-env=vulkan1.3` |
| Resource binding | `register(t0, space1)` | `[[vk::binding(0, 0)]]`, or register shifts |
| Small constants | `ConstantBuffer<T>` bound as root constants | `[[vk::push_constant]]` |
| Reflection | `ID3D12ShaderReflection` | SPIRV-Reflect |
| Validation | DXC's built-in DXIL validator | `spirv-val` |

## Compiling

```bash
# D3D12: DXIL
dxc -T ps_6_6 -E PSMain -HV 2021 -Zi -Qembed_debug -Fo triangle.ps.dxil triangle.hlsl

# Vulkan: SPIR-V from the same file
dxc -spirv -fspv-target-env=vulkan1.3 -T ps_6_6 -E PSMain -HV 2021 -Fo triangle.ps.spv triangle.hlsl
```

- **`-T`** is the stage and shader model, **`-E`** the entry point. One file can hold several entry points (`VSMain`, `PSMain`), compiled one at a time.
- **`-HV 2021`** selects HLSL 2021: templates, operator overloading, logical operators that short-circuit. It is the default in current DXC; say it explicitly so older compilers agree.
- **`-Zi`** adds debug information for PIX and RenderDoc. Keep it in development builds; strip it (`-Qstrip_debug`, or write it to a separate file with `-Fd`) for shipping.
- **Shader model 6.6** is needed for `ResourceDescriptorHeap` and 64-bit atomics on D3D12; 6.5 for mesh shaders. Use the lowest model that has what you need, so older drivers can run it.

## One source for both APIs

The shared shader from [descriptors](descriptors.md#the-shader) shows the pattern: D3D12 reads the `register(...)` assignments, Vulkan reads the `[[vk::...]]` attributes, and each compiler ignores the other's.

```hlsl
[[vk::push_constant]] ConstantBuffer<PushConstants> pc : register(b0);
[[vk::binding(0, 0)]] Texture2D    textures[]    : register(t0, space1);
[[vk::binding(1, 0)]] SamplerState linearSampler : register(s0);
```

Instead of attributes on every declaration, DXC can derive Vulkan bindings from registers: `-fvk-t-shift 100 0`, `-fvk-s-shift 200 0`, `-fvk-u-shift 300 0` (and `-fvk-b-shift`) add an offset per register type, because HLSL's `t0`, `s0`, and `u0` would otherwise all map to binding 0. With a [bindless](descriptors.md#bindless-one-big-table) layout there are only a few declarations, and explicit attributes are clearer.

### Differences to handle

| Topic | What to do |
| --- | --- |
| Clip-space Y | flip the viewport on Vulkan (see [pipelines](pipelines.md#dynamic-rendering)), or compile with `-fvk-invert-y` |
| Matrix layout | HLSL packs matrices in constant buffers **column-major** by default. Match your C++ maths library: compile with `-Zpr` (row-major) or transpose on upload. The same flag applies to both outputs |
| Buffer layout | `ConstantBuffer` and push constants follow HLSL packing (16-byte rows) on D3D12; DXC follows Vulkan's std140/std430-style rules for SPIR-V unless you pass `-fvk-use-dx-layout`. Use it so one C++ struct matches both |
| 16-bit types | `-enable-16bit-types` for `half` and `int16_t` as true 16-bit values (shader model 6.2, plus Vulkan's `shaderFloat16` feature) |
| Wave operations | the same intrinsics (`WaveActiveSum`, `WaveReadLaneFirst`) on both, but wave size differs: 32 on NVIDIA, 32 or 64 on AMD, 8 to 32 on Intel. Never assume one (`WaveGetLaneCount()` tells the shader) |
| API-only features | wrap them in `#if defined(__spirv__)` or a define you pass per API; DXC defines `__spirv__` when compiling with `-spirv` |

### Use DXC for HLSL to SPIR-V

glslang also accepts HLSL (`glslangValidator -D`), but its HLSL support is incomplete. Compiling the shared shader above with glslang 15:

- rejects `NonUniformResourceIndex`;
- turns the unsized `Texture2D textures[]` into an array of **one** element, breaking bindless silently;
- gives `[[vk::push_constant]] ConstantBuffer<T> pc : register(b0)` a descriptor binding, which `spirv-val` rejects.

DXC handles all three. Use glslang for GLSL, and DXC for HLSL.

## DXC as a library

For hot reload in the editor, or a content pipeline written in the engine, link `dxcompiler` and compile in process:

```cpp
#include <dxcapi.h>

ComPtr<IDxcUtils> utils;
ComPtr<IDxcCompiler3> compiler;
HR_CHECK(DxcCreateInstance(CLSID_DxcUtils, IID_PPV_ARGS(&utils)));
HR_CHECK(DxcCreateInstance(CLSID_DxcCompiler, IID_PPV_ARGS(&compiler)));
ComPtr<IDxcIncludeHandler> includes;
HR_CHECK(utils->CreateDefaultIncludeHandler(&includes));       // resolves #include relative to the file

std::vector<LPCWSTR> args = { L"triangle.hlsl", L"-E", L"PSMain", L"-T", L"ps_6_6", L"-HV", L"2021", L"-Zpr" };
if (forVulkan) { args.push_back(L"-spirv"); args.push_back(L"-fspv-target-env=vulkan1.3"); args.push_back(L"-fvk-use-dx-layout"); }

DxcBuffer source{ .Ptr = text.data(), .Size = text.size(), .Encoding = DXC_CP_UTF8 };
ComPtr<IDxcResult> result;
HR_CHECK(compiler->Compile(&source, args.data(), UINT32(args.size()), includes.Get(), IID_PPV_ARGS(&result)));

ComPtr<IDxcBlobUtf8> errors;
result->GetOutput(DXC_OUT_ERRORS, IID_PPV_ARGS(&errors), nullptr);
if (errors && errors->GetStringLength() > 0)
    LogShaderMessages(errors->GetStringPointer());             // warnings too: show them to the author

HRESULT status;
result->GetStatus(&status);
if (FAILED(status)) return {};                                 // keep using the previous version
ComPtr<IDxcBlob> code;
HR_CHECK(result->GetOutput(DXC_OUT_OBJECT, IID_PPV_ARGS(&code), nullptr));   // DXIL or SPIR-V
```

- The first argument is the file name used in error messages and for resolving includes.
- `IDxcCompiler3` instances are not thread-safe: create one per worker thread.
- On hot reload, compile on a worker thread, and only replace the pipeline once compilation and pipeline creation have both succeeded, so a typo leaves the old shader running.

## Reflection

Reflection reads a compiled shader's inputs: which resources it binds, its constant buffer layout, its thread group size.

- **D3D12**: request `DXC_OUT_REFLECTION` from the result, then `utils->CreateReflection(&buffer, IID_PPV_ARGS(&reflection))` to get an `ID3D12ShaderReflection`.
- **Vulkan**: [SPIRV-Reflect](https://github.com/KhronosGroup/SPIRV-Reflect) parses the SPIR-V binary for the same information.

Reflection is useful for tools (material editors, validating that a shader matches its material's parameters). With a fixed **bindless** layout shared by every shader, the renderer needs little of it at run time: the layout is known in advance, and the shader only has to agree with it.

## Shaders in the content pipeline

Compile shaders at **cook time**, not on the player's machine, the same way as other [content](../../engine/content/import-cook.md):

- **Key the cache** by a hash of the source, every included file, the defines, the target (DXIL or SPIR-V and profile), and the compiler version.
- **Permutations multiply**: five boolean options make 32 variants of one shader. Prefer runtime branches on uniform values (cheap on modern GPUs) and specialisation constants (Vulkan) for options that rarely change, and compile only the combinations materials actually use.
- **Pipelines still compile on the device** from DXIL or SPIR-V. Shipping compiled shaders removes the HLSL step; [pipeline caches](pipelines.md#caching-and-hitching) remove most of the rest.

## Slang

[Slang](https://shader-slang.org/) is an HLSL-compatible shading language and compiler (originally from NVIDIA, now a Khronos project). It compiles to DXIL, SPIR-V, Metal, and CPU code, and adds modules (instead of `#include`), interfaces and generics, and automatic binding layout. Existing HLSL mostly compiles unchanged. It is worth a look for an engine that needs Metal too, or a large shader library; DXC is the simpler choice for D3D12 and Vulkan alone.

!!! warning "Common pitfalls"

    Matrices that look transposed on screen are almost always the column-major default. Pick `-Zpr` or transpose on upload, once, for every shader.

    Without `-fvk-use-dx-layout`, the same constant buffer struct can have different member offsets in DXIL and SPIR-V. Use the flag, or check offsets with reflection.

    Compiling HLSL for Vulkan with glslang silently breaks unbounded arrays. Use DXC.

    Compiling shaders while the game runs, on first use, hitches as badly as creating pipelines. Cook them ahead of time.

## C# tips

- `Vortice.Dxc` wraps the DXC library for C#. The arguments are the same strings as on the command line.
- A content pipeline written in C# can also run `dxc` as a process and read the output file; simpler, and fast enough for cooking.
