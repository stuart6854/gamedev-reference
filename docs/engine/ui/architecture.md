---
uses:
  - name: RPGs
    text: Inventory, character, and quest screens that mirror large amounts of game state.
  - name: Strategy and tactics
    text: Many panels reading the same simulation, layered menus, and a HUD that must stay responsive.
  - name: Life and colony sims
    text: Needs bars, colonist panels, and notifications driven by a constantly changing simulation.
---

# Design and architecture

How UI fits around the rest of the game: where its data comes from, how screens are stacked, and how its look is defined and scaled. The [widget tree](widget-tree.md) and [layout](layout.md) pages cover the mechanics; this page covers the structure.

## The UI depends on the game, not the other way round

The game simulation should not know the UI exists. It exposes state (health, inventory, quest log) and actions (equip, drop, accept quest). The UI reads the state and calls the actions.

```text
game  <-- reads state, calls actions --  UI
```

When the dependency points this way:

- The game runs headless, for servers, tests, and replays.
- A screen can be rewritten without touching gameplay code.
- Two screens showing the same data (a HUD health bar and the character screen) cannot drift apart, because neither owns the value.

A UI action asks; it does not mutate. "Equip this sword" goes through the same function a controller or a script would call, so the rules (can this class use swords?) live in one place.

## Getting data into widgets

Three ways to keep a widget in step with the value it shows:

| | How | Good for | Watch out for |
| --- | --- | --- | --- |
| Polling | Read the value every frame, update the widget if it changed. | HUDs, timers, anything that changes most frames. | Cost scales with the number of bound values, visible or not. |
| Events | The game raises `HealthChanged`; the widget subscribes. | Rarely changing values with many readers. | Forgetting to unsubscribe, and handlers running at awkward times (mid-simulation). |
| Version numbers | The game increments a counter on every change; the widget compares it to the last one it saw. | Collections: inventories, lists, logs. | Nothing much. One integer compare per frame. |

Polling is the safest default. It cannot miss an update or leak a subscription, and comparing a few hundred values a frame costs nothing. Version numbers give the same safety for collections, where comparing the contents would be expensive:

```text
Inventory { items[], version }          // version += 1 on every change

InventoryView.update():
    if inventory.version == seen_version: return
    rebuild rows from inventory.items
    seen_version = inventory.version
```

### Bindings

A binding pairs a source with a widget, and only touches the widget when the value changed:

```text
Binding<T> {
    source: () -> T
    apply: (T) -> void
    last: T
}

update_bindings():
    for b in active bindings:          // bindings on attached widgets only
        v = b.source()
        if v != b.last:
            b.apply(v)
            b.last = v
```

Comparing before applying matters: setting a label's text, even to the same string, invalidates layout and re-shapes the text.

Register bindings in `on_attached` and remove them in `on_detached` (see [changing the tree](widget-tree.md#changing-the-tree)). A screen that is closed then stops costing anything.

### View models

Between the game state and the widgets, keep a view model per screen: a plain object holding display-ready values.

```text
CharacterViewModel {
    name: string
    health_text: string             // "84 / 120"
    health_fraction: float          // 0.7, for the bar
    can_level_up: bool              // enables the button
    level_up()                      // calls the game action
}
```

Formatting, rounding, localisation, and "which button is enabled" live here, not scattered through widget code. The view model can be unit tested without building any UI, and the screen's widgets become simple bindings to its fields.

## The screen stack

A screen is a top-level panel in the main layer: the HUD, the pause menu, the inventory, a confirmation dialog. The game keeps them in a stack:

```text
Screen {
    root                    // widget
    blocks_input_below      // a menu does; a notification banner does not
    hides_below             // a full-screen menu can stop drawing what it covers
    default_focus
    saved_focus             // focus in the screen below, when this one was pushed
}

push(s):
    s.saved_focus = focused
    main_layer.add_child(s.root)
    stack.push(s)
    set_focus(s.default_focus)

pop():
    s = stack.pop()
    main_layer.remove_child(s.root)
    set_focus(s.saved_focus if still attached else top().default_focus)
```

- **Input** goes to the top screen, then down the stack until a screen with `blocks_input_below`. Pointer hit testing skips screens below that point. Gamepad focus scope is the top screen.
- **Cancel** pops the top screen, unless the screen handles it first, such as a text field clearing itself or a screen asking "discard changes?".
- **Transitions**: animate the outgoing screen before removing it, and block input to it while it animates. Push and pop logically straight away; only the visuals are delayed. Otherwise a fast double press of Cancel pops a screen that is already closing.
- **Game pause** is a separate decision from the stack. Opening the inventory may or may not pause the game; make it a screen flag, not a side effect of being on top.

## Styling

Keep visual values (colours, fonts, padding, sizes, sounds) out of widget code, in style rules:

```text
Style {
    background, border, corner_radius, padding
    font, font_size, text_color                 // inherited by children
    opacity
}

StyleRule {
    class                                       // "button", "button.primary", "panel.dark"
    state                                       // NONE, HOVERED, PRESSED, FOCUSED, DISABLED
    properties                                  // only the ones it sets
}
```

Resolve a widget's style when its classes, its state, or its parent's style change, not every frame:

```text
resolve_style(w):
    s = defaults
    s.text_properties = w.parent.resolved.text_properties   // inheritance
    for class in w.classes:
        s.apply(rules[class][NONE])
        for state in w.state flags, in a fixed order:
            s.apply(rules[class][state])
    s.apply(w.inline_style)
    if s.changes layout: invalidate_layout(w)
    w.resolved = s
```

- Only text properties inherit: a panel with dark text gives its labels dark text, but its padding does not leak into them.
- Apply states in a fixed order, so a disabled button that is also hovered shows as disabled.
- A theme is a different set of rules. Swapping themes re-resolves every widget once.

## Scaling and DPI

Design at a **reference resolution** (for example 1920 × 1080) in logical units, and scale to the screen at the end:

```text
scale = screen.height / reference.height             // match height
// or: min(screen.w / ref.w, screen.h / ref.h)       // fit inside, letterboxing the UI
scale *= user_ui_scale                               // accessibility setting

logical_screen = screen / scale                      // what layout sees
```

Layout runs in logical units against `logical_screen`, and the final rects are multiplied by `scale` and [snapped to pixels](layout.md#snapping-to-pixels).

- **Match height** suits most games: text stays the same size relative to the screen, and wider screens get more horizontal room, which anchored HUD corners use.
- **Ultrawide**: keep the main HUD and menus inside a centred 16:9 region, with only edge-anchored elements going wider.
- **User UI scale** (for example 75 % to 150 %) is an accessibility requirement on most platforms. Test the largest setting: it is where layouts overflow.
- **Safe area**: TVs crop the edges, and phones have notches. Apply the platform's safe area as padding on the root, so anchoring to a corner means the visible corner.
- Rasterise fonts at their final pixel size (`font_size * scale`), or use signed distance field fonts, which stay sharp at any scale. Scaling up a bitmap rasterised for 1080p blurs at 4K.

## Animation

Animate **render properties** (opacity, translation, scale, rotation, colour), applied when painting, not layout properties (width, padding, margin). A panel that slides in by animating its translation costs one transform per frame. Animating its margin re-runs layout for the panel and its siblings every frame, and moves its neighbours.

Hit testing should use the transformed rect, so a sliding button can be clicked where it is drawn.

## Localisation

- Translated text can be 30 to 40 % longer than English (German, Finnish) or much shorter (Chinese, Japanese). Size anything with text to `Fit`, and test with the longest language, or with a pseudo-localised build that pads every string.
- Never put text in textures. Build the label on top of the image.
- Use full sentences with placeholders (`"{player} found {item}"`), not concatenated fragments. Word order differs between languages.
- Right-to-left languages (Arabic, Hebrew) mirror the layout: rows run right to left and anchors flip horizontally. Supporting it later means changing every stack and anchor, so decide early whether you will.
