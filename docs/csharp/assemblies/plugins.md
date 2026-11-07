# Plugins

A .NET 8 application, such as a level editor or a game tool, that loads plugins from a folder: each plugin in its own load context, sharing only a contract assembly with the host, and unloadable while the application runs.

## The layout

```text
Editor/                       the host application
    Editor.exe
    Contracts.dll             interfaces shared with plugins
Plugins/
    Terrain/
        Terrain.dll           the plugin
        Terrain.deps.json     its dependency list, written by the build
        MathNet.Numerics.dll  a dependency only this plugin uses
```

## Shared contracts

The host and plugins talk through interfaces in a small assembly that both reference:

```csharp
// Contracts.dll
public interface IEditorPlugin
{
    string Name { get; }
    void Initialise(IEditorHost host);
    void Shutdown();
}

public interface IEditorHost
{
    void AddMenuItem(string path, Action onClick);
    void Log(string message);
}
```

Keep `Contracts.dll` small and stable. Every type in it is part of the plugin API, and changing it means rebuilding every plugin.

The plugin project references the contracts, but must not copy them to its output, so that only the host's copy is ever loaded:

```xml
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <EnableDynamicLoading>true</EnableDynamicLoading>
  </PropertyGroup>
  <ItemGroup>
    <ProjectReference Include="..\Contracts\Contracts.csproj">
      <Private>false</Private>
      <ExcludeAssets>runtime</ExcludeAssets>
    </ProjectReference>
    <PackageReference Include="MathNet.Numerics" Version="5.0.0" />
  </ItemGroup>
</Project>
```

- `EnableDynamicLoading` marks the project as a plugin: the build copies its NuGet dependencies to the output folder and writes a `.deps.json` describing them.
- `Private=false` and `ExcludeAssets=runtime` keep `Contracts.dll` out of the plugin's folder. If a copy is there, a careless `Load` picks it up, and casts to the host's interfaces fail with the confusing [type identity](index.md#type-identity) error.

## The load context

```csharp
using System.Reflection;
using System.Runtime.Loader;

sealed class PluginLoadContext : AssemblyLoadContext
{
    readonly AssemblyDependencyResolver _resolver;

    public PluginLoadContext(string pluginPath)
        : base(name: Path.GetFileNameWithoutExtension(pluginPath), isCollectible: true)
    {
        _resolver = new AssemblyDependencyResolver(pluginPath);
    }

    protected override Assembly? Load(AssemblyName name)
    {
        // Shared with the host: use the default context's copy.
        if (name.Name == "Contracts")
            return null;

        string? path = _resolver.ResolveAssemblyToPath(name);
        return path is null ? null : LoadFromAssemblyPath(path);
    }

    protected override IntPtr LoadUnmanagedDll(string unmanagedDllName)
    {
        string? path = _resolver.ResolveUnmanagedDllToPath(unmanagedDllName);
        return path is null ? IntPtr.Zero : LoadUnmanagedDllFromPath(path);
    }
}
```

`AssemblyDependencyResolver` reads the plugin's `.deps.json` and answers "where is this assembly for this plugin?", including NuGet dependencies, platform-specific native libraries, and satellite resource assemblies. Without it, a plugin with dependencies needs a hand-written search of its folder.

Anything the resolver does not find (the framework, `Contracts`) returns `null` and falls back to the default context.

## Loading and creating plugins

```csharp
sealed class LoadedPlugin
{
    public required PluginLoadContext Context;
    public required IEditorPlugin Instance;
}

static LoadedPlugin Load(string pluginPath, IEditorHost host)
{
    var context = new PluginLoadContext(pluginPath);
    Assembly assembly = context.LoadFromAssemblyPath(pluginPath);

    Type type = assembly.GetTypes()
        .Single(t => typeof(IEditorPlugin).IsAssignableFrom(t) && !t.IsAbstract);
    var instance = (IEditorPlugin)Activator.CreateInstance(type)!;
    instance.Initialise(host);

    return new LoadedPlugin { Context = context, Instance = instance };
}
```

`typeof(IEditorPlugin).IsAssignableFrom(t)` only finds the type if the plugin's `IEditorPlugin` is the host's. If it returns nothing for a plugin that clearly implements the interface, a second copy of `Contracts.dll` has been loaded.

## Unloading

```csharp
[MethodImpl(MethodImplOptions.NoInlining)]
static WeakReference Unload(LoadedPlugin plugin)
{
    plugin.Instance.Shutdown();          // the plugin removes its menu items and handlers
    var weak = new WeakReference(plugin.Context);
    plugin.Context.Unload();
    return weak;                          // drop every strong reference before returning
}

static bool WaitForUnload(WeakReference weak)
{
    for (int i = 0; weak.IsAlive && i < 10; i++)
    {
        GC.Collect();
        GC.WaitForPendingFinalizers();
    }
    return !weak.IsAlive;
}
```

The caller must also drop its own references (remove the `LoadedPlugin` from its list) before waiting. `NoInlining` keeps the JIT from extending a local's lifetime into the caller, which would keep the context alive during the wait.

If `WaitForUnload` returns false, something still references the plugin. The usual causes:

| Reference | Fix |
| --- | --- |
| Host events or callbacks holding plugin delegates (`AddMenuItem(..., plugin.OnClick)`) | Remove them in `Shutdown`, or have the host remove everything a plugin registered when it unloads |
| Host collections holding plugin objects or `Type`s | Clear them for that plugin |
| Static fields in the default context holding plugin data | Avoid; or clear on unload |
| Threads, timers, or tasks still running plugin code | Stop and wait for them in `Shutdown` |
| `GCHandle`s and function pointers handed to native code | Free them |
| Library caches keyed by type (serializer and reflection caches) | Use libraries that support unloading, or clear their caches |
| A `Resolving` event handler on the default context that the plugin added | Remove it |

To find the remaining root, take a memory dump and ask what keeps the context alive: `dotnet-dump collect -p <pid>`, then `dotnet-dump analyze` with `dumpheap -type PluginLoadContext` and `gcroot <address>`. The Visual Studio and Rider memory profilers show the same paths to roots.

Have the host own **every** registration a plugin makes, keyed by plugin, so unloading can remove them all whether or not the plugin's `Shutdown` is correct.

## Reloading a plugin

To reload after a rebuild: unload the old context, wait for it to go, then load the new build. On Windows, `LoadFromAssemblyPath` keeps the file open, so the build cannot overwrite it while it is loaded. Either copy the plugin folder to a temporary folder and load from there, or load from memory:

```csharp
using var dll = new MemoryStream(File.ReadAllBytes(dllPath));
using var pdb = File.Exists(pdbPath) ? new MemoryStream(File.ReadAllBytes(pdbPath)) : null;
Assembly assembly = context.LoadFromStream(dll, pdb);
```

Loading from a stream does not lock the file, and passing the PDB keeps line numbers in stack traces and lets the debugger work. The plugin's dependencies, loaded by `Load` through the resolver, still come from files; copy them too if they also change.
