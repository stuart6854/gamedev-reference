---
uses:
  - name: RPGs
    text: Inventory grids, stat sliders, and long item lists that need virtualising.
  - name: Strategy and tactics
    text: Dense panels, tooltips on everything, and dropdowns for orders.
---

# Common elements

How the standard widgets are built from the [tree](widget-tree.md), [layout](layout.md), and [input](input.md) pieces. Each one is a small amount of state plus event handling. Anything more complex is composed from these.

## Label and image

A label holds a string and a text style. `measure_content` returns the size of the shaped text, wrapped to the available width if wrapping is on. Shaping text (turning a string into positioned glyphs) is expensive, so cache the result and redo it only when the text, font, size, or wrap width changes.

An image holds a texture region and a scale mode: stretch, fit inside, fill and crop, or **nine-slice**. A nine-slice image is cut into a 3 × 3 grid. The corners stay their original size, the edges stretch along one axis, and the centre stretches along both, so one small texture makes a panel border of any size.

## Button

```text
Button : Widget {
    on_click            // callback
}

Button.on_event(e):
    case e:
        Click:  if enabled: on_click(); e.handled = true
        Submit: if enabled: on_click(); e.handled = true
```

Hover, pressed, focused, and disabled are state flags maintained by the input code (see [hover](input.md#hover) and [press, click, and capture](input.md#press-click-and-capture)). The button only uses them to pick a style. It contains a label or an image as a child, so an icon button and a text button are the same widget.

Give a button's visuals a short response even when its action is slow: a pressed state, a sound, then the action. A button that does nothing for a frame or two reads as broken.

## Toggle and radio group

A toggle is a button that flips a boolean on click and shows a checkmark or a switch. A radio group is a container that owns the selected index, and its children are toggles that ask the group to select them:

```text
RadioGroup.select(i):
    if i == selected: return
    children[selected].checked = false
    children[i].checked = true
    selected = i
    on_changed(i)
```

For gamepad use, a horizontal "selector" (`< Medium >`, cycled with left and right) usually works better than a radio group: one focus stop instead of three.

## Slider

A track and a thumb. The value comes from the pointer's position along the track:

```text
Slider { min, max, step, value }

value_from_pointer(s, x):
    t = clamp01((x - s.track.x - s.grab_offset) / s.track.w)
    v = lerp(s.min, s.max, t)
    if s.step > 0:
        v = s.min + round((v - s.min) / s.step) * s.step
    return v

Slider.on_event(e):
    case e:
        PointerDown(p):
            grab_offset = (p is on the thumb) ? p.x - thumb_centre.x : 0
            set_value(value_from_pointer(self, p.x))
            e.handled = true
        Drag(p):        set_value(value_from_pointer(self, p.x))
        Navigate(LEFT): set_value(value - keyboard_step)
        Navigate(RIGHT): set_value(value + keyboard_step)
```

`grab_offset` stops the thumb jumping when the player grabs it off-centre. Pressing the track (not the thumb) jumps the value to that point.

Separate **changing** from **committed**: a volume slider can update the volume on every move, but a slider that triggers something expensive (a graphics setting, a server call) should act on release.

## Text field

```text
TextField {
    text
    caret               // index into text
    anchor              // other end of the selection; == caret when nothing is selected
    scroll_x            // keeps the caret visible in a field narrower than the text
}
```

- `Text` events insert at the caret, replacing the selection. `KeyDown` handles editing: Backspace, Delete, arrows (with Shift to extend the selection), Home and End, Ctrl+A, and the clipboard keys.
- Move the caret by **grapheme**, not by byte or code point. "é" can be two code points and an emoji can be several; Backspace must delete what the player sees as one character.
- Hit test a click against the glyph positions from the shaped text, and put the caret on whichever side of the glyph is nearer.
- While focused, tell the OS where the caret is, so the IME's candidate window opens next to it, and show the IME's in-progress (composition) text inline without committing it.
- On consoles, focus opens the platform's on-screen keyboard instead; the field receives the finished string.

## Scroll view

A viewport that clips, and one content child that is measured with unlimited space along the scroll axis:

```text
ScrollView {
    content
    offset              // how far the content is scrolled
}

ScrollView.measure_content(available):
    measure(content, (available.w, INFINITY))       // vertical scrolling
    return content.desired_size

ScrollView.arrange_children(rect):
    max_offset = max(0, content.desired_size.h - rect.h)
    offset = clamp(offset, 0, max_offset)
    arrange(content, rect(rect.x, rect.y - offset, rect.w, content.desired_size.h))
```

- Paint pushes a clip rect the size of the viewport, paints the content, and pops it. Hit testing must respect the same clip (see [hit testing](input.md#hit-testing)).
- `Scroll` events bubble up to the nearest scroll view that can still move in that direction, so an inner list scrolls first and the outer page scrolls once the list reaches its end.
- Dragging the content (touch) moves `offset` with the pointer. On release, keep the release velocity and decay it each frame for inertia.
- Changing `offset` only moves the content. Don't invalidate layout for it; offset the existing rects.

When focus moves to a widget inside the view, bring it into view:

```text
scroll_into_view(view, r, margin):
    if r.top - margin < view.rect.top:       view.offset -= view.rect.top - (r.top - margin)
    if r.bottom + margin > view.rect.bottom: view.offset += (r.bottom + margin) - view.rect.bottom
```

Scroll only as far as needed. Snapping the focused item to the top of the view on every move makes gamepad scrolling jumpy.

## Virtualised list

A list of 10,000 items cannot have 10,000 widgets. Build only the rows that are visible, and reuse them as the list scrolls:

```text
VirtualList {
    count               // number of items in the data
    row_height          // fixed
    bind(row_widget, index)     // fills a row with item index's data
    rows[]              // pooled row widgets
}

VirtualList.arrange_children(rect):
    first = floor(offset / row_height)
    visible = ceil(rect.h / row_height) + 1
    last = min(count, first + visible)
    ensure len(rows) >= last - first
    for i in first .. last - 1:
        row = rows[i mod len(rows)]
        if row.index != i:
            row.index = i
            bind(row, i)
        arrange(row, rect(rect.x, rect.y + i * row_height - offset, rect.w, row_height))
    collapse the rows not used this frame
```

The list's content height is `count * row_height`, so the scrollbar is right without building anything. Indexing pooled rows by `i mod len(rows)` means a row only rebinds when it scrolls off one end and reappears at the other.

A row that holds focus must keep it when it is rebound to a different item. Store focus as the item index, and refocus whichever row is showing that index. Rows with different heights need a prefix sum of the heights to find `first`, and a binary search over it.

## Dropdown and popups

A dropdown is a button that opens a list in the [popup layer](widget-tree.md#layers):

```text
open_popup(content, anchor_widget):
    popup = Popup(content)
    popup_layer.add_child(popup)
    place below anchor_widget; if it would go off the bottom of the screen, place above
    clamp horizontally to the screen
    push focus scope(popup)
```

Close it on Cancel, on a selection, on a click outside it, or when its anchor widget is removed or scrolled off screen. For "click outside", put an invisible full-screen widget under the popup in the popup layer: it catches the press, closes the popup, and handles the event, so the press does not also click whatever was behind it.

Context menus are the same, anchored to the pointer instead of a widget. A submenu opens a second popup beside its item, and closing a menu closes its submenus.

## Tooltip

```text
on hover change:
    tooltip_timer = 0
    hide tooltip

each frame:
    if hovered has tooltip text and pointer is still:
        tooltip_timer += dt
        if tooltip_timer > 0.5 and tooltip hidden: show(hovered.tooltip)
```

- Put the tooltip in the tooltip layer, not hit-testable, offset below and right of the pointer, and clamped inside the screen.
- Once one tooltip is showing, show the next one immediately when the pointer moves to another widget with a tooltip. Waiting again makes scanning a row of icons slow.
- For gamepad, show the focused widget's tooltip after the same delay, positioned beside the widget instead of the pointer.
- Tooltips that the player needs to read slowly (item stats) can be pinned with a button press, so they become a popup that can itself have tooltips.
