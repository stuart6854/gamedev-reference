# UI

How a retained-mode UI system works: a tree of widgets that lives between frames, with layout, input, and drawing run over it. Everything is pseudocode; no particular library is assumed.

## Retained and immediate mode

| | Retained mode | Immediate mode |
| --- | --- | --- |
| The tree | Built once, then changed by code. | Rebuilt from code every frame. |
| Widget state (hover, scroll offset, text being edited) | Stored on the widget. | Stored in a side table, keyed by an id the code supplies. |
| Layout | Cached. Redone only for parts that changed. | Redone each frame, or one frame late. |
| Styling, animation, data binding, visual editors | Natural fit: each has a widget to attach to. | Possible, but needs work. |
| Keeping UI in sync with game state | Your job. See [design and architecture](architecture.md). | Free: the code reads the state as it draws. |
| Examples | HTML, Qt, Unity UI Toolkit and uGUI | Dear ImGui, Clay, Unity IMGUI |

Retained mode suits player-facing game UI, where art direction, animation, and gamepad navigation matter. Immediate mode suits debug tools, where every panel is quick to write and throwaway.

## The UI frame

```text
ui_frame(dt):
    dispatch queued input events            // input page
    update bindings and animations          // architecture page
    layout_dirty_widgets()                  // layout page
    paint(root, draw_list)                  // quads, text, and clip rects for the renderer
    destroy widgets queued for removal      // widget tree page
```

Input is dispatched against last frame's layout, which is what the player was looking at when they clicked. Layout runs after bindings, so a label whose text changed this frame is measured with its new text before it is drawn.

## Pages

- [Widget tree](widget-tree.md) — the widget record, invalidation, visibility, layers, and changing the tree while it is being walked.
- [Layout](layout.md) — measure and arrange, sizing rules, stacks, wrapping text, anchors, and pixel snapping.
- [Flexbox layout](flexbox.md) — the Yoga subset of CSS flexbox: base sizes, lines, growing and shrinking, alignment, absolute children, and caching.
- [Input and focus](input.md) — hit testing, event routing, hover and press, pointer capture, dragging, keyboard focus, and gamepad navigation.
- [Common elements](elements.md) — buttons, toggles, sliders, text fields, scroll views, virtualised lists, popups, and tooltips.
- [Tabs, splits, and docking](docking.md) — tab views, split panes, and a dock tree with drop zones and saved layouts.
- [Design and architecture](architecture.md) — keeping UI apart from game state, view models and bindings, the screen stack, styling, scaling, and animation.
- [Style sheets](stylesheets.md) — a CSS subset: tokenizing and parsing, selector matching, the cascade, computed values, variables, and transitions.
