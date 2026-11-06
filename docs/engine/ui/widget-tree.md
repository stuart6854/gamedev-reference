# Widget tree

Every widget is a node with a parent and an ordered list of children. Layout, input, and painting are all walks over this tree.

## The widget

```text
Widget {
    parent
    children[]                  // paint order: later children draw on top
    rect                        // final screen rect, written by layout
    desired_size                // written by the measure pass
    layout                      // sizing rules: see the layout page
    style                       // resolved style: see the architecture page
    visibility                  // Visible, Hidden, or Collapsed
    enabled
    focusable
    hit_testable
    dirty                       // bit flags: LAYOUT, STYLE
    state                       // bit flags: HOVERED, PRESSED, FOCUSED, DISABLED

    // overridden per widget type
    measure_content(available) -> size
    arrange_children(rect)
    paint(draw_list)
    on_event(event)
}
```

A button, a label, and a stack are all widgets. They differ in the four overridable functions. Use composition for anything bigger: a slider is a widget with a track child and a thumb child, not a special case in the tree.

## Changing the tree

```text
add_child(parent, child, index = end):
    if child.parent: remove_child(child.parent, child)
    insert child into parent.children at index
    child.parent = parent
    invalidate_layout(parent)
    if parent is attached to the root: notify_attached(child)

remove_child(parent, child):
    remove child from parent.children
    child.parent = null
    invalidate_layout(parent)
    notify_detached(child)
```

`notify_attached` and `notify_detached` walk the subtree and call each widget's `on_attached` and `on_detached`. Those hooks are where a widget subscribes to data and starts animations, and where it unsubscribes. They run when the widget joins or leaves the live tree, not when it is created, so a widget built ahead of time and kept off-screen costs nothing until it is shown.

## Invalidation

A widget whose content changes (new text, a new child, a new padding) marks itself, and every ancestor, as needing layout:

```text
invalidate_layout(w):
    while w and not (w.dirty & LAYOUT):
        w.dirty |= LAYOUT
        w = w.parent
```

The loop stops at the first ancestor that is already dirty. That is safe because of an invariant: if a widget is dirty, so are all its ancestors. A frame with a thousand label changes walks each path once.

The layout pass then starts at the root and only descends into dirty children. A widget whose size cannot depend on its children, such as a fixed-size panel, is a **layout boundary**: invalidation can stop there and lay out only that subtree, because the rest of the tree cannot be affected.

```text
invalidate_layout(w):
    while w and not (w.dirty & LAYOUT):
        w.dirty |= LAYOUT
        if w.is_layout_boundary:
            add w to relayout_roots
            return
        w = w.parent
```

Each frame, after laying out the root if it is dirty, lay out each widget in `relayout_roots` inside the rect it already has.

For painting, the simplest approach is to repaint everything every frame. A game screen is a few thousand quads at most, and a full repaint is cheaper than tracking which parts changed. Cache the expensive inputs to painting instead: layout, resolved styles, and shaped text.

## Visibility

| | Takes layout space | Paints | Receives input |
| --- | --- | --- | --- |
| Visible | Yes | Yes | Yes, if `hit_testable` |
| Hidden | Yes | No | No |
| Collapsed | No | No | No |

Use Hidden when content must not move as something appears, such as an icon that blinks. Use Collapsed for content that is shown and removed, such as an optional row in a list. Changing to or from Collapsed invalidates layout. Changing between Visible and Hidden does not.

`enabled` is separate: a disabled button is still drawn and still takes space, but ignores input and is skipped by focus navigation. Disable a parent and every descendant is disabled with it.

## Layers

The root's children are full-screen layers, drawn in order:

```text
root
    main          // screens: see the architecture page
    popups        // dropdowns, context menus
    tooltips
    drag          // the image that follows the pointer while dragging
    debug
```

A dropdown opened inside a scroll view belongs to the popup layer, not the scroll view. As a child of the scroll view, it would be clipped by the scroll view's bounds and drawn under every widget after it in the tree. The popup keeps a reference to the widget it was opened from and positions itself against that widget's rect each frame.

## Removing widgets during an event

A button's click handler often closes the panel the button is in. If the panel is removed straight away, the input code is now walking a list that just changed, and is about to call into a widget that has gone.

Two rules make this safe:

1. **Removal is immediate, destruction is deferred.** `remove_child` detaches the widget at once, so it stops receiving input and stops painting. The widget's memory is freed at the end of the frame, from a `pending_destroy` list.
2. **Dispatch walks a copy.** The input code builds the list of widgets an event will visit before calling any of them, and skips any widget that has been detached since. See [routing](input.md#routing).

## Holding references to widgets

Game code that keeps a widget pointer will eventually use it after the widget is gone. Hand out [handles](../../data-structures/handle-table.md) instead: an index and a generation that fails to resolve once the widget is destroyed.

```text
label = ui.get(health_label_handle)
if label: label.set_text(...)
```

Widget lookup by name or id, `find(root, "health_label")`, is convenient for wiring up a screen when it is built. Avoid it every frame: it is a tree walk.
