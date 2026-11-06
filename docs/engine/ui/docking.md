# Tabs, splits, and docking

The pieces of an editor-style layout. Tabs show one of several panels in the same space. Splits divide a space between two panels, with a draggable divider. Docking combines both into a tree the user rearranges by dragging tabs around.

## Tabs

```text
TabView {
    tabs[]              // { title, content }
    active              // index
    bar                 // a row of tab buttons
}

TabView.select(i):
    tabs[active].content.visibility = Collapsed
    tabs[i].content.visibility = Visible
    active = i
    on_changed(i)
```

All tab contents stay in the tree, and the inactive ones are Collapsed. Switching back keeps the scroll position, the half-typed text, and the expanded tree nodes. Building tab content on first selection, not when the tab view is created, keeps start-up cheap when most tabs are never opened.

**Reordering** by dragging a tab along the bar: the insert index is the number of other tabs whose midpoint is left of the pointer.

```text
insert_index(bar, pointer_x, dragged):
    i = 0
    for t in bar.tabs except dragged:
        if t.rect.x + t.rect.w / 2 < pointer_x: i += 1
    return i
```

Slide the other tabs towards their new places with a short animation as the index changes. Tabs that jump straight to their new places are hard to follow.

**Overflow**: when the tabs no longer fit, either shrink them down to a minimum width and then scroll the bar, or keep the full width and put the rest in a dropdown at the end. Always keep the active tab visible.

**Input**: Ctrl+Tab and Ctrl+Shift+Tab cycle tabs. On a gamepad, the shoulder buttons cycle the top-level tabs of a screen (a game menu's Inventory, Map, and Skills), wherever focus is.

## Splits

```text
Split {
    axis                // ROW: side by side; COLUMN: one above the other
    first, second
    ratio               // first's share of the space, 0..1
    min_first, min_second
    divider             // thickness, in units
}

Split.arrange_children(rect):
    space = rect.main - divider
    a = space * ratio
    if space >= min_first + min_second:
        a = clamp(a, min_first, space - min_second)
    else:
        a = space * min_first / (min_first + min_second)    // both under minimum: share by minimums
    arrange(first,  rect from rect.main_start with main size a)
    arrange(second, rect from rect.main_start + a + divider with main size space - a)
```

Dragging the divider sets the ratio from the pointer:

```text
on Drag(p):
    space = rect.main - divider
    a = (p.main - rect.main_start) - grab_offset
    ratio = clamp(a, min_first, space - min_second) / space
```

- Give the divider a hit area wider than it looks (a few units each side), and change the cursor while it is hovered.
- Storing a **ratio** keeps proportions when the window resizes. A sidebar should usually keep its width instead: store pixels for the side that should not change, and give the rest to the other.
- Double-clicking a divider is a common shortcut to reset it, or to collapse the smaller side.
- More than two panes in a row is a chain of nested splits. That keeps every split simple, and is exactly what the dock tree needs.

## Docking

### The dock tree

```text
DockNode =
    Split { axis, ratio, first, second }        // both are DockNodes
    TabStack { panels[], active }               // a leaf: a tab view

Panel { id, title, content }                    // id is stable across sessions

DockSpace {
    root                                        // DockNode filling the main window
    floating[]                                  // { rect, root } for each floating window
}
```

Every leaf is a tab stack, even one with a single panel. Then every operation is one of three: move a panel into a stack, split a stack, or remove a panel from a stack.

Each panel's `content` widget is created once and **reparented** as the panel moves: it is removed from one tab stack's content area and added to another. The panel keeps its state, and nothing is rebuilt.

### Removing a panel

When a stack is left empty, remove it and let its sibling take the parent split's place:

```text
remove_panel(stack, panel):
    stack.panels.remove(panel)
    if stack.panels not empty:
        stack.active = min(stack.active, len(stack.panels) - 1)
        return
    collapse(stack)

collapse(node):
    parent = node.parent
    if parent is null:
        if node is a floating window's root: close that window
        return                                  // the main window keeps an empty stack
    sibling = (parent.first == node) ? parent.second : parent.first
    replace parent with sibling in parent.parent (or as the tree root)
```

Collapsing keeps the tree free of splits with only one child, which would otherwise show as empty space with a divider beside it.

### Drop zones

While a tab is being dragged, find the tab stack under the pointer and which part of it the pointer is over:

```text
drop_zone(stack_rect, p):
    u = (p - stack_rect.pos) / stack_rect.size          // 0..1 inside the stack
    edge = min(u.x, 1 - u.x, u.y, 1 - u.y)
    if edge > 0.25: return CENTER
    if edge == u.x:      return LEFT
    if edge == 1 - u.x:  return RIGHT
    if edge == u.y:      return TOP
    return BOTTOM
```

Over the stack's tab bar, the drop is an insert at an index (see [reordering](#tabs)). Outside every stack, it is a new floating window. Show a translucent rectangle in the drag layer covering where the panel will end up: the whole stack for `CENTER`, half of it for an edge.

Dropping applies the change:

```text
drop(panel, stack, zone):
    if panel.stack == stack and len(stack.panels) == 1: return    // nothing would change
    remove_panel(panel.stack, panel)            // may collapse panel's old stack
    if zone == CENTER:
        stack.panels.append(panel)
        stack.active = last
        return
    new_stack = TabStack { panels: [panel] }
    axis = (zone in LEFT, RIGHT) ? ROW : COLUMN
    first, second = (zone in LEFT, TOP) ? (new_stack, stack) : (stack, new_stack)
    replace stack with Split { axis, ratio: 0.5, first, second }
```

The first line handles dragging a stack's only tab onto that same stack. Without it, removing the panel collapses the stack, and the split then replaces a node that is no longer in the tree.

Dropping on a **window edge**, not a stack, splits the root itself, giving a panel the full height or width of the window. Add four thin zones at the edges of the dock space for it.

### Saving the layout

Write the tree out with panel ids, not widgets:

```text
{ "split": "row", "ratio": 0.22,
  "first":  { "tabs": ["hierarchy"], "active": 0 },
  "second": { "split": "column", "ratio": 0.7,
              "first":  { "tabs": ["scene", "game"], "active": 0 },
              "second": { "tabs": ["console", "profiler"], "active": 1 } } }
```

When loading:

- Drop panel ids that no longer exist (a tool was removed), and collapse any stacks left empty.
- Put panels that are not in the saved layout (a tool was added) in a default place, such as a tab in the largest stack.
- If the saved layout is unreadable, use the built-in default. Keep the default as data in the same format, so "reset layout" is just loading it.
