---
package: Dear ImGui 1.92
---

# Dear ImGui

[Dear ImGui](https://github.com/ocornut/imgui) is an immediate-mode UI library for C++: the UI is rebuilt from code every frame, and widgets return whether they were used. It is the standard choice for engine tools, debug windows, and in-game editors, where writing a panel should take minutes. See [retained and immediate mode](index.md#retained-and-immediate-mode) for how it compares with the retained-mode UI the other pages build.

This page is a working reference: the begin and end rules, laying widgets out in rows, columns, and to the left, right, or centre, IDs, styling, and the common widgets.

```cpp
if (ImGui::Begin("Player"))
{
    ImGui::Text("Health: %d", player.health);
    ImGui::SliderFloat("Speed", &player.speed, 0.0f, 20.0f);
    if (ImGui::Button("Respawn"))
        respawn(player);
}
ImGui::End();
```

## Begin and End rules

The most common source of crashes and assertions is calling an `End` that should not be called, or missing one that should:

| Pair | Call the `End` |
| --- | --- |
| `Begin` / `End` | **Always**, whatever `Begin` returned |
| `BeginChild` / `EndChild` | **Always** |
| `BeginGroup` / `EndGroup` | Always (`BeginGroup` returns nothing) |
| `BeginTable` / `EndTable` | Only if `BeginTable` returned true |
| `BeginCombo` / `EndCombo` | Only if it returned true |
| `BeginPopup`, `BeginPopupModal`, `BeginPopupContextItem` / `EndPopup` | Only if it returned true |
| `BeginMenu`, `BeginMenuBar` / `EndMenu`, `EndMenuBar` | Only if it returned true |
| `BeginTabBar`, `BeginTabItem` / `EndTabBar`, `EndTabItem` | Only if it returned true |
| `TreeNode` / `TreePop` | Only if it returned true (open) |
| `BeginDragDropSource`, `BeginDragDropTarget` / `End...` | Only if it returned true |
| `BeginTooltip`, `BeginItemTooltip` / `EndTooltip` | Only if it returned true |
| `PushID`, `PushStyleVar`, `PushStyleColor`, `PushItemWidth` / `Pop...` | Always, the same number of times |

`Begin` and `BeginChild` are the odd ones out, for historical reasons. Everything else follows "only if true". Enable the debug log and keep `IM_ASSERT` active in development builds: Dear ImGui asserts on mismatched pairs at the end of the frame, naming the window.

## Layout basics

Dear ImGui places each item below the previous one, at the **cursor**. Everything else is moving the cursor.

| Call | Effect |
| --- | --- |
| `SameLine()` | Put the next item to the right of the previous one, with the default spacing |
| `SameLine(0, spacing)` | Same, with a chosen gap in pixels |
| `SameLine(x)` | Put the next item at `x` pixels from the start of the line |
| `Spacing()`, `Dummy(ImVec2(w, h))` | Vertical gap; empty space of a given size |
| `Separator()`, `SeparatorText("Physics")` | A horizontal line; a line with a heading |
| `Indent()` / `Unindent()` | Move the left edge in and back |
| `NewLine()` | End the current line, even if it is empty |
| `GetContentRegionAvail()` | Space left from the cursor to the edge of the window or cell. The main tool for layout |
| `GetCursorPosX()`, `SetCursorPosX(x)` | Read and set the cursor, in window coordinates |
| `SetNextItemWidth(w)` | Width of the next widget. `-FLT_MIN` fills to the right edge; a negative value leaves that much space |

Two values come up constantly:

```cpp
const ImGuiStyle& style = ImGui::GetStyle();

// Width of a button with this label.
float button_width(const char* label)
{
    return ImGui::CalcTextSize(label).x + ImGui::GetStyle().FramePadding.x * 2.0f;
}

// Height of one row of framed widgets (buttons, inputs), with and without the gap below.
float row = ImGui::GetFrameHeight();
float row_with_gap = ImGui::GetFrameHeightWithSpacing();
```

## Alignment: left, right, centre

Left is the default. For anything else, measure the item, then move the cursor.

### Right-aligned

```cpp
// One button against the right edge.
float w = button_width("Close");
ImGui::SetCursorPosX(ImGui::GetCursorPosX() + ImGui::GetContentRegionAvail().x - w);
if (ImGui::Button("Close")) close();

// Several buttons against the right edge, in order.
const char* labels[] = { "Apply", "Cancel" };
float total = button_width("Apply") + style.ItemSpacing.x + button_width("Cancel");
ImGui::SetCursorPosX(ImGui::GetCursorPosX() + ImGui::GetContentRegionAvail().x - total);
ImGui::Button("Apply");
ImGui::SameLine();
ImGui::Button("Cancel");

// Text on the left and a button on the right of the same line.
ImGui::AlignTextToFramePadding();
ImGui::Text("Entities: %d", count);
ImGui::SameLine(ImGui::GetCursorPosX() + ImGui::GetContentRegionAvail().x - button_width("Clear"));
ImGui::Button("Clear");
```

`AlignTextToFramePadding` moves plain text down to line up with the labels of framed widgets on the same line. Without it, text next to a button sits a few pixels too high.

The `SameLine(x)` form in the last example puts the button at `x` in window coordinates. Read just after the text, `GetCursorPosX()` is the start of a line and `GetContentRegionAvail().x` the width to the right edge, so their sum minus the button's width puts it flush right.

### Centred

```cpp
// Centre one item: half of the space left over.
void centre_next(float item_width)
{
    float avail = ImGui::GetContentRegionAvail().x;
    if (avail > item_width)
        ImGui::SetCursorPosX(ImGui::GetCursorPosX() + (avail - item_width) * 0.5f);
}

centre_next(ImGui::CalcTextSize("Game over").x);
ImGui::Text("Game over");

centre_next(button_width("Retry") + style.ItemSpacing.x + button_width("Quit"));
ImGui::Button("Retry");
ImGui::SameLine();
ImGui::Button("Quit");
```

When the width is not known in advance (a group of mixed widgets), measure it the previous frame. Wrap the items in `BeginGroup`/`EndGroup`, read `GetItemRectSize()` after `EndGroup`, store it, and centre with the stored width next frame. The first frame is off by a frame, which nobody sees.

### Vertically centred, or at the bottom

```cpp
// Content centred vertically in the window.
float content_height = 3 * ImGui::GetFrameHeightWithSpacing();
float avail_y = ImGui::GetContentRegionAvail().y;
if (avail_y > content_height)
    ImGui::SetCursorPosY(ImGui::GetCursorPosY() + (avail_y - content_height) * 0.5f);

// A scrolling area that fills the window except for a row of buttons at the bottom.
float footer = ImGui::GetFrameHeightWithSpacing();
if (ImGui::BeginChild("log", ImVec2(0, -footer)))
{
    for (const std::string& line : log_lines) ImGui::TextUnformatted(line.c_str());
}
ImGui::EndChild();
ImGui::Button("Clear");
```

A negative size for a child means "fill, minus this much". That one call gives a scrolling region with a fixed footer, the layout of most log and console windows.

### A centred window

```cpp
ImGuiViewport* vp = ImGui::GetMainViewport();
ImGui::SetNextWindowPos(vp->GetCenter(), ImGuiCond_Appearing, ImVec2(0.5f, 0.5f));   // pivot at the window's centre
ImGui::SetNextWindowSize(ImVec2(400, 0), ImGuiCond_Appearing);                         // 0 height: fit the contents
```

`ImGuiCond_Appearing` sets it each time the window appears, then lets the user move it. `ImGuiCond_Always` pins it.

## Columns with tables

Tables are the layout tool for anything in columns. The older `Columns()` API is legacy; use tables.

```cpp
// Three equal columns that share the width.
if (ImGui::BeginTable("stats", 3, ImGuiTableFlags_SizingStretchSame))
{
    ImGui::TableNextColumn(); ImGui::Text("Health");
    ImGui::TableNextColumn(); ImGui::Text("Stamina");
    ImGui::TableNextColumn(); ImGui::Text("Mana");
    ImGui::EndTable();
}
```

`TableNextColumn` moves to the next cell, wrapping to a new row after the last column. Each cell is its own small layout region: `GetContentRegionAvail().x` is the cell's width, so the alignment helpers above work inside cells.

### Column widths

```cpp
if (ImGui::BeginTable("inventory", 4,
        ImGuiTableFlags_Borders | ImGuiTableFlags_RowBg | ImGuiTableFlags_Resizable |
        ImGuiTableFlags_ScrollY, ImVec2(0, 300)))
{
    ImGui::TableSetupScrollFreeze(0, 1);                                     // keep the header visible
    ImGui::TableSetupColumn("Icon",  ImGuiTableColumnFlags_WidthFixed, 32.0f);
    ImGui::TableSetupColumn("Name",  ImGuiTableColumnFlags_WidthStretch);    // takes the rest
    ImGui::TableSetupColumn("Count", ImGuiTableColumnFlags_WidthFixed, 60.0f);
    ImGui::TableSetupColumn("Value", ImGuiTableColumnFlags_WidthFixed, 80.0f);
    ImGui::TableHeadersRow();

    for (const Item& item : items)
    {
        ImGui::TableNextRow();
        ImGui::TableNextColumn(); draw_icon(item.icon, 24);
        ImGui::TableNextColumn(); ImGui::TextUnformatted(item.name.c_str());
        ImGui::TableNextColumn(); right_aligned_text("%d", item.count);
        ImGui::TableNextColumn(); right_aligned_text("%.1f", item.value);
    }
    ImGui::EndTable();
}
```

- **Fixed** columns keep their width; **stretch** columns share what is left, by weight (`init_width_or_weight`).
- `ScrollY` needs a height in `outer_size`, and makes the table scroll inside that height. `TableSetupScrollFreeze(0, 1)` keeps the header row visible.
- `ImGuiTableFlags_Sortable` plus `TableGetSortSpecs()` gives clickable column sorting; sort your own data when `SpecsDirty` is set.
- For thousands of rows, wrap the row loop in `ImGuiListClipper`, which only submits the visible rows.

Right-aligned numbers make columns of values readable:

```cpp
void right_aligned_text(const char* fmt, ...)
{
    char buf[64];
    va_list args; va_start(args, fmt); vsnprintf(buf, sizeof(buf), fmt, args); va_end(args);
    float w = ImGui::CalcTextSize(buf).x;
    ImGui::SetCursorPosX(ImGui::GetCursorPosX() + ImGui::GetContentRegionAvail().x - w);
    ImGui::TextUnformatted(buf);
}
```

### Property grid: labels on the left

Dear ImGui puts widget labels on the **right** by default. Inspector-style panels look better with a column of labels on the left and widgets filling the right:

```cpp
bool begin_properties(const char* id)
{
    if (!ImGui::BeginTable(id, 2, ImGuiTableFlags_Resizable | ImGuiTableFlags_BordersInnerV))
        return false;
    ImGui::TableSetupColumn("Name",  ImGuiTableColumnFlags_WidthFixed, 120.0f);
    ImGui::TableSetupColumn("Value", ImGuiTableColumnFlags_WidthStretch);
    return true;
}

void property_label(const char* label)
{
    ImGui::TableNextRow();
    ImGui::TableNextColumn();
    ImGui::AlignTextToFramePadding();
    ImGui::TextUnformatted(label);
    ImGui::TableNextColumn();
    ImGui::SetNextItemWidth(-FLT_MIN);                   // fill the value column
}

if (begin_properties("transform"))
{
    property_label("Position"); ImGui::DragFloat3("##position", &t.position.x, 0.1f);
    property_label("Rotation"); ImGui::DragFloat3("##rotation", &t.rotation.x, 1.0f);
    property_label("Scale");    ImGui::DragFloat3("##scale", &t.scale.x, 0.01f);
    ImGui::EndTable();
}
```

The `##` labels hide the widget's own label while keeping its ID unique; see [IDs](#ids-and-state). Driving this from [reflection](../serialisation/reflection.md) data gives a generic inspector for every type.

### Toolbars and status bars

A one-row table is the easiest way to put groups of widgets at the left, centre, and right of a bar. The table measures each group, so there is no need to calculate widths by hand.

```cpp
// Toolbar: tools on the left, play controls in the middle, settings on the right.
if (ImGui::BeginTable("toolbar", 5, ImGuiTableFlags_SizingFixedFit))
{
    ImGui::TableSetupColumn("left",   ImGuiTableColumnFlags_WidthFixed);     // no width: fits its contents
    ImGui::TableSetupColumn("gap1",   ImGuiTableColumnFlags_WidthStretch);
    ImGui::TableSetupColumn("centre", ImGuiTableColumnFlags_WidthFixed);
    ImGui::TableSetupColumn("gap2",   ImGuiTableColumnFlags_WidthStretch);
    ImGui::TableSetupColumn("right",  ImGuiTableColumnFlags_WidthFixed);
    ImGui::TableNextRow();

    ImGui::TableNextColumn();
    ImGui::Button("Move"); ImGui::SameLine();
    ImGui::Button("Rotate"); ImGui::SameLine();
    ImGui::Button("Scale");

    ImGui::TableNextColumn();                                                // empty: takes spare space

    ImGui::TableNextColumn();
    ImGui::Button(playing ? "Pause" : "Play"); ImGui::SameLine();
    ImGui::Button("Step");

    ImGui::TableNextColumn();                                                // empty

    ImGui::TableNextColumn();
    ImGui::SetNextItemWidth(120);
    ImGui::Combo("##view", &view_mode, "Lit\0Unlit\0Wireframe\0");
    ImGui::EndTable();
}
```

- A **fixed** column with no width fits its contents, measured on the previous frame. A group that grows (a label that gets longer) resizes its column on the next frame.
- The two **stretch** gaps have equal weights, so they split the spare space evenly. The centre group sits halfway between the left and right groups, which is the centre of the bar only when those two groups are the same width.
- When the bar is too narrow, the gaps shrink to zero and the groups touch, instead of overlapping.

For a status bar whose middle must be exactly centred, use three **equal** stretch columns and align inside each cell:

```cpp
void centred_text(const char* text)
{
    centre_next(ImGui::CalcTextSize(text).x);
    ImGui::TextUnformatted(text);
}

// The main area fills the window except for one row at the bottom.
float status_height = ImGui::GetFrameHeightWithSpacing();
ImGui::BeginChild("main", ImVec2(0, -status_height));
draw_main_area();
ImGui::EndChild();

if (ImGui::BeginTable("status", 3, ImGuiTableFlags_SizingStretchSame | ImGuiTableFlags_BordersInnerV))
{
    ImGui::TableNextRow();
    ImGui::TableNextColumn(); ImGui::Text("%d entities", entity_count);
    ImGui::TableNextColumn(); centred_text(level_name);
    ImGui::TableNextColumn(); right_aligned_text("%.2f ms", frame_ms);
    ImGui::EndTable();
}
```

The equal columns put the middle cell's centre on the window's centre, whatever the other cells contain. Cells clip their contents, so text too long for its third of the bar is cut off instead of overlapping its neighbour. `BordersInnerV` draws dividers between the sections.

In a bar that mixes text with buttons or inputs, call `AlignTextToFramePadding()` before each piece of text, so it lines up with the widgets beside it.

## Panels: left, right, middle

Side-by-side regions are child windows on one line:

```cpp
// Left sidebar (fixed, resizable by dragging its edge), middle fills, right sidebar fixed.
const float right_width = 250.0f;

ImGui::BeginChild("left", ImVec2(200, 0), ImGuiChildFlags_Borders | ImGuiChildFlags_ResizeX);
draw_hierarchy();
ImGui::EndChild();

ImGui::SameLine();
float middle_width = ImGui::GetContentRegionAvail().x - right_width - style.ItemSpacing.x;
ImGui::BeginChild("middle", ImVec2(middle_width, 0), ImGuiChildFlags_Borders);
draw_viewport();
ImGui::EndChild();

ImGui::SameLine();
ImGui::BeginChild("right", ImVec2(0, 0), ImGuiChildFlags_Borders);   // 0 width: fill the rest
draw_inspector();
ImGui::EndChild();
```

- A size of `0` on an axis means "fill the remaining space"; a negative size means "fill, minus this much".
- `ImGuiChildFlags_ResizeX` lets the user drag the child's right edge, and remembers the width in the `.ini` file. `ImGuiChildFlags_ResizeY` does the same vertically.
- `ImGuiChildFlags_AutoResizeY` sizes a child to its contents' height, for framed sections that should not scroll.
- Each child scrolls on its own, which is what panels usually want.
- A top bar and bottom status bar are the same idea vertically: a child of fixed height, the main area with height `-status_height`, then the status bar.

For editor layouts the user can rearrange, use the **docking branch** of Dear ImGui, which adds dock spaces, tabs, and dragging windows into each other (and out of the main window, with multi-viewports). The retained-mode version of that is the [tabs, splits, and docking](docking.md) page.

## IDs and state

Dear ImGui keeps state (open trees, text being edited, scroll positions, which widget is active) keyed by an **ID**, a hash of the widget's label and the **ID stack** above it (the window, and anything pushed). Two widgets with the same label in the same scope share an ID, and the second one does not work properly: clicking it activates the first.

| Label | Shown | ID from |
| --- | --- | --- |
| `"Delete"` | Delete | "Delete" |
| `"Delete##enemy"` | Delete | "Delete##enemy" (the whole string) |
| `"##speed"` | (nothing) | "##speed" |
| `"Health: 50###health"` | Health: 50 | "###health" only, so the ID stays the same as the text changes |

```cpp
// Buttons in a loop all labelled "Delete": push something unique per item.
for (int i = 0; i < (int)enemies.size(); i++)
{
    ImGui::PushID(i);                        // or PushID(enemy.id), or PushID(&enemy)
    ImGui::Text("%s", enemies[i].name.c_str());
    ImGui::SameLine();
    if (ImGui::Button("Delete")) remove_index = i;
    ImGui::PopID();
}
```

- Push something **stable** per item: an entity id or a pointer, not the loop index, when items can be reordered or removed. Otherwise a tree node's open state moves to whichever item now has that index.
- Use `###` for labels that change every frame (a counter, a timer). Without it the ID changes with the text, and the widget loses its state every frame: a window titled `"Score: 10"` would turn into a new window as the score changes.
- When two widgets seem linked (editing one edits the other, or one cannot be clicked), it is an ID collision. The ID Stack Tool (`ShowIDStackToolWindow()`, also under Tools in the Metrics/Debugger window) shows the ID of whatever is under the mouse, and the debug log can report conflicting IDs.
- Do not **mutate a list while drawing it**. Record the change (`remove_index` above) and apply it after the loop.

## Styling

### Temporary changes

```cpp
ImGui::PushStyleColor(ImGuiCol_Button,        ImVec4(0.7f, 0.2f, 0.2f, 1.0f));
ImGui::PushStyleColor(ImGuiCol_ButtonHovered, ImVec4(0.8f, 0.3f, 0.3f, 1.0f));
ImGui::PushStyleColor(ImGuiCol_ButtonActive,  ImVec4(0.9f, 0.2f, 0.2f, 1.0f));
bool clicked = ImGui::Button("Delete all");
ImGui::PopStyleColor(3);

ImGui::PushStyleVar(ImGuiStyleVar_FramePadding, ImVec2(12, 8));     // a bigger button
ImGui::Button("Play");
ImGui::PopStyleVar();

ImGui::BeginDisabled(!can_save);                                    // greyed out, ignores input
ImGui::Button("Save");
ImGui::EndDisabled();
```

Pop counts must match the pushes. Wrap common combinations (a "danger" button, a "primary" button) in small helper functions, so the pushes and pops live in one place.

### Themes

```cpp
ImGui::StyleColorsDark();                     // a base theme
ImGuiStyle& s = ImGui::GetStyle();
s.WindowRounding = 4.0f;
s.FrameRounding  = 3.0f;
s.ItemSpacing    = ImVec2(8, 6);
s.Colors[ImGuiCol_Header] = ImVec4(0.20f, 0.45f, 0.45f, 1.0f);      // teal headers and selections
```

Set the theme once at start-up. The **Style Editor** in the demo window (`ShowStyleEditor()`) edits every value live and can export the code for the result.

### Fonts and DPI scaling

```cpp
ImGuiIO& io = ImGui::GetIO();
ImFont* ui   = io.Fonts->AddFontFromFileTTF("fonts/Inter-Regular.ttf", 16.0f);
ImFont* mono = io.Fonts->AddFontFromFileTTF("fonts/JetBrainsMono-Regular.ttf", 15.0f);

// Scale for high-DPI monitors (main_scale from the platform: e.g. GLFW's content scale).
ImGuiStyle& style = ImGui::GetStyle();
style.ScaleAllSizes(main_scale);              // padding, spacing, rounding; not fonts
style.FontScaleDpi = main_scale;              // fonts

// Later, for a section:
ImGui::PushFont(mono, 0.0f);                  // 0: keep the current size
draw_console();
ImGui::PopFont();
ImGui::PushFont(nullptr, style.FontSizeBase * 1.5f);   // nullptr: keep the font, change the size
ImGui::Text("Big heading");
ImGui::PopFont();
```

Since 1.92, fonts are rasterised on demand at whatever size is used, so any size stays sharp and there is no need to load a font several times at different sizes. Load a TrueType font for the UI; the built-in default font is designed for small sizes. Merge an icon font (Font Awesome, Material Symbols) into the main font with `ImFontConfig::MergeMode`, so icons can go inside labels: `ImGui::Button(ICON_FA_TRASH " Delete")`.

## Common widgets

### Combo box

```cpp
const char* names[] = { "Easy", "Normal", "Hard" };
if (ImGui::BeginCombo("Difficulty", names[difficulty]))
{
    for (int i = 0; i < IM_ARRAYSIZE(names); i++)
    {
        bool selected = (i == difficulty);
        if (ImGui::Selectable(names[i], selected)) difficulty = i;
        if (selected) ImGui::SetItemDefaultFocus();     // keyboard focus starts on the current one
    }
    ImGui::EndCombo();
}
```

`BeginCombo` takes any widgets, so a combo can hold a search box above a filtered list.

### Trees

```cpp
void draw_node(Node& node)
{
    ImGuiTreeNodeFlags flags = ImGuiTreeNodeFlags_OpenOnArrow | ImGuiTreeNodeFlags_SpanAvailWidth;
    if (node.children.empty()) flags |= ImGuiTreeNodeFlags_Leaf;
    if (&node == selected)     flags |= ImGuiTreeNodeFlags_Selected;

    bool open = ImGui::TreeNodeEx(&node, flags, "%s", node.name.c_str());   // pointer as the ID
    if (ImGui::IsItemClicked() && !ImGui::IsItemToggledOpen()) selected = &node;
    if (open)
    {
        for (Node& child : node.children) draw_node(child);
        ImGui::TreePop();
    }
}
```

`OpenOnArrow` makes clicking the label select the node and only the arrow open it, the way scene hierarchies behave. `CollapsingHeader` is a framed tree node that does not need `TreePop`, for sections of an inspector.

### Popups and modals

```cpp
if (ImGui::Button("Delete level"))
    ImGui::OpenPopup("Delete?");                 // once, on the click; never every frame

ImGui::SetNextWindowPos(ImGui::GetMainViewport()->GetCenter(), ImGuiCond_Appearing, ImVec2(0.5f, 0.5f));
if (ImGui::BeginPopupModal("Delete?", nullptr, ImGuiWindowFlags_AlwaysAutoResize))
{
    ImGui::Text("Delete '%s'? This cannot be undone.", level.name.c_str());
    ImGui::Separator();
    if (ImGui::Button("Delete", ImVec2(120, 0))) { delete_level(); ImGui::CloseCurrentPopup(); }
    ImGui::SameLine();
    if (ImGui::Button("Cancel", ImVec2(120, 0))) ImGui::CloseCurrentPopup();
    ImGui::EndPopup();
}

// Right-click menu on the last item.
ImGui::Text("%s", entity.name.c_str());
if (ImGui::BeginPopupContextItem("entity_menu"))
{
    if (ImGui::MenuItem("Duplicate")) duplicate(entity);
    if (ImGui::MenuItem("Delete"))    destroy(entity);
    ImGui::EndPopup();
}
```

`OpenPopup` and `BeginPopup` must be called with the same ID stack. Opening a popup from inside a menu or a loop that pushed an ID, and beginning it outside, is the usual reason a popup never appears.

### Drag and drop

```cpp
// Source: an asset in a list.
ImGui::Selectable(asset.name.c_str());
if (ImGui::BeginDragDropSource())
{
    ImGui::SetDragDropPayload("ASSET_ID", &asset.id, sizeof(asset.id));
    ImGui::Text("%s", asset.name.c_str());       // shown under the cursor while dragging
    ImGui::EndDragDropSource();
}

// Target: a slot in an inspector.
ImGui::Button(material.texture_name.c_str(), ImVec2(-FLT_MIN, 0));
if (ImGui::BeginDragDropTarget())
{
    if (const ImGuiPayload* p = ImGui::AcceptDragDropPayload("ASSET_ID"))
        material.texture = *static_cast<const AssetId*>(p->Data);
    ImGui::EndDragDropTarget();
}
```

The payload is copied, so send ids, not pointers to things that might move. The type string (up to 32 characters) decides which targets accept it.

### Tooltips, plots, and progress

```cpp
ImGui::Button("Bake");
ImGui::SetItemTooltip("Bakes lighting for the open level (about 2 minutes)");

// Frame times over the last 120 frames.
ImGui::PlotLines("##frametime", frame_ms, 120, frame_index, "Frame ms", 0.0f, 33.0f, ImVec2(-FLT_MIN, 60));

ImGui::ProgressBar(bake_progress, ImVec2(-FLT_MIN, 0));
```

For real charts (axes, zoom, several series), use the [ImPlot](https://github.com/epezent/implot) extension.

## Tips

- **Keep `ShowDemoWindow()` available** in development builds. Every feature is demonstrated there, and its source (`imgui_demo.cpp`) is the best documentation. The **Item Picker** in the Metrics window (`ShowMetricsWindow()`) breaks into the debugger in the code that submitted the widget you click.
- **Check `io.WantCaptureMouse` and `io.WantCaptureKeyboard`** before passing input to the game, so typing in a text field does not also move the player.
- **Draw only what is visible.** Immediate mode costs per submitted widget. `ImGuiListClipper` for long lists, and returning early when `Begin` returns false (the window is collapsed or hidden), keep big tools fast.
- **Hold no pointers** to data that may change during the frame in which you draw it; record actions and apply them after the UI code, the same as [deferred commands](../patterns/frame.md#deferred-commands).
- **Keep tools out of shipping builds**: compile the debug UI out, or at least do not create it, in shipping configurations.
