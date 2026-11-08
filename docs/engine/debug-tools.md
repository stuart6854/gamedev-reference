# Console and debug tools

The tools that make an engine debuggable while it runs: console variables to change settings without rebuilding, commands to trigger actions, logging that can be filtered, assertions that stop at the right moment, and drawing lines and shapes from anywhere in the code. All of them are cheap to add early and expensive to retrofit.

## Console variables

A console variable (cvar) is a named, typed setting that can be read in code and changed at run time:

```cpp
CVar<float> r_shadow_distance("r.shadow_distance", 80.0f, "Maximum shadow distance in metres");
CVar<bool>  ai_debug_paths("ai.debug_paths", false, "Draw AI navigation paths");
CVar<int>   r_vsync("r.vsync", 1, "0 = off, 1 = on", CVarFlags::Saved);

float distance = r_shadow_distance.get();
```

```text
CVar registry:
    name -> { type, value, default, description, flags, on_change callbacks }
```

- **Register at start-up** with a static object per cvar (constructed into a registry created on first use, to avoid static order problems). The name is the address: `r.` for rendering, `ai.`, `phys.`, `net.`.
- **Flags**: `Saved` (written to the user's config file), `Cheat` (only in development builds, or only with cheats enabled), `ReadOnly` (shows a value, like a version), `RequiresRestart`.
- **On change**: some settings need work when they change (vsync recreates the swapchain). Register a callback rather than polling.
- **Load order**: defaults in code, then the config file, then command-line arguments (`+r.vsync 0`), then the console. Each later source overrides the earlier.
- **Reading is a plain load**, so cvars can be read in hot code. Copy the value into a local at the start of a loop rather than reading it per item.

## Commands

```cpp
ConsoleCommand god("god", "Toggle invulnerability", [](std::span<const std::string_view> args) {
    player().invulnerable = !player().invulnerable;
    log_info("god mode {}", player().invulnerable ? "on" : "off");
});

ConsoleCommand spawn("spawn", "spawn <prefab> [count]", [](auto args) { ... });
```

- Parse arguments with the same code that parses cvar values, and print the usage string on bad input.
- **Tab completion** of names (and of arguments such as prefab names, from a callback per command) makes the console usable. Show matching names with their descriptions as you type.
- **History** with up and down arrows, saved between sessions.
- **Bind** commands to keys (`bind F5 "save_quick"`) and run **scripts** of commands from a file (`exec benchmark.cfg`), so a test scenario is one command.
- Run commands on the **main thread**, at a known point in the frame, never from the input callback that received the keystroke.

## Logging

```cpp
log_info("Loaded level {} in {:.1f} ms", name, ms);
log_warn(LogCategory::Audio, "Sound {} not found", id);
log_error("Save failed: {}", reason);
```

- **Categories and levels** (`Audio: Warning`, `Render: Verbose`), each settable at run time with a cvar, so a noisy system can be silenced and a suspicious one turned up.
- **Several outputs**: the console window, a file, the debugger output, and the in-game console. Write the file in a background thread so logging does not stall the frame, and flush it on errors and crashes.
- **Format lazily**: check the level before formatting, so disabled verbose logs cost one comparison. With a macro, the arguments are not even evaluated.
- **Rate-limit** messages that can fire every frame (`log_warn_once`, or once per second), or one bad object fills the log with millions of lines.
- **Include the frame number** in each line. Lining up log lines with a profiler capture or a replay needs it.

## Assertions

```cpp
#define ENGINE_ASSERT(cond, ...)                                              \
    do {                                                                       \
        if (!(cond) && assert_failed(#cond, __FILE__, __LINE__, ##__VA_ARGS__)) \
            DEBUG_BREAK();                                                     \
    } while (0)

ENGINE_ASSERT(index < count, "index {} out of range ({})", index, count);
```

- **Break in the debugger** at the assertion itself (the `DEBUG_BREAK` is in the macro, so the debugger stops in the calling code, not inside a helper).
- **Ignore once, ignore always**: when not attached to a debugger, show a dialog that lets the developer continue, or silence that assertion for the session. An assertion that blocks a level designer's work every time gets deleted.
- **Levels**: `ASSERT` (development builds only), `VERIFY` (the expression always runs, only the check is removed), and `FATAL` (in every build; the state is unrecoverable, so crash with a report).
- Assertions are for **bugs**, not for expected failures. A missing save file is an error to handle; a negative array index is a bug to assert on.

## Debug drawing

Lines, boxes, spheres, arrows, and text drawn from anywhere in the code, for one frame or for a few seconds:

```cpp
debug::line(from, to, Color::Red);
debug::sphere(target, radius, Color::Yellow, /*seconds*/ 2.0f);
debug::box(bounds, Color::Green);
debug::text(position, "hp {}", health);         // text in the world, facing the camera
debug::text_2d(10, 10, "fps {}", fps);          // text on screen
```

```text
DebugDraw {
    lines[]         // { from, to, color, expire_time } per thread, merged before rendering
}

each frame: render all lines in one draw call, with depth test on (or off, for "through walls")
            then remove the expired ones
```

- **Callable from any thread.** Give each thread its own buffer and merge them, so AI and physics jobs can draw without locks.
- **Batch** everything into one line-list draw per frame. Spheres and boxes are expanded into lines when submitted.
- **Gate** each system's drawing behind a cvar (`ai.debug_paths`), so it is off unless asked for, and the call costs nothing when off.
- **Compile out** in shipping builds: the functions become empty inline functions, and the arguments are not evaluated.
- Persistent shapes (a raycast drawn for 2 seconds) let you see what happened on the frame of a bug, after it is gone.

## The in-game console and overlays

- A **drop-down console** (backquote key) for typing commands and reading the log, filterable by category and level. [Dear ImGui](ui/dear-imgui.md) makes it a short piece of code: a scrolling log with a fixed input line at the bottom.
- **Stat overlays**: frame time with a graph, CPU and GPU time, draw calls, memory, entity counts. A `stat` command toggles each group.
- **Debug menus** generated from cvars: every cvar under `ai.` becomes a checkbox or slider in an "AI" menu, with no extra code.
- **Pause and step**: freeze the game clock and advance one frame at a time, keeping the camera and UI live. Many bugs only make sense frame by frame.

## In shipping builds

Decide what ships:

- Debug drawing, the console, cheats, and verbose logging compile out of shipping builds.
- Logging of warnings and errors to a file usually stays, so player bug reports include a log.
- A **crash handler** that writes a minidump, the last few hundred log lines, and the cvar values that differ from defaults, then offers to send them, is the most useful debug tool a shipped game has.
