# Input and focus

The UI turns raw device input into events, finds the widget each event is for, and delivers it along a path through the tree. Pointer events go to the widget under the pointer. Keyboard and gamepad events go to the widget with focus.

## Events

Translate device input into UI events at one boundary, so widgets never read devices directly:

```text
PointerMove(pos), PointerDown(pos, button), PointerUp(pos, button), Scroll(pos, delta)
KeyDown(key, mods), KeyUp(key, mods)
Text(characters)                    // typed text, from the OS
Navigate(UP | DOWN | LEFT | RIGHT)  // d-pad, stick, arrow keys
Submit, Cancel                      // A / B, Enter / Escape
```

`Navigate`, `Submit`, and `Cancel` are logical events. A button handles `Submit`, not "the A button or the Enter key", so a gamepad remap or a new device does not touch any widget.

`Text` comes from the OS's text input, not from key codes. Only the OS knows the keyboard layout, dead keys, and the IME (the input method used to compose Chinese, Japanese, and Korean text). Build characters from `KeyDown` and an AZERTY or Japanese keyboard types the wrong thing.

The UI also tells the game whether it used each event. A click on a button must not also fire the player's weapon:

```text
if not ui.handle(event):
    game.handle(event)
```

## Hit testing

```text
hit_test(w, p):
    if w.visibility != Visible: return null
    if w.clips and not w.rect.contains(p): return null
    for c in reverse(w.children):        // last painted is on top
        h = hit_test(c, p)
        if h: return h
    if w.hit_testable and w.rect.contains(p): return w
    return null
```

Test the layers from the top down: tooltips, then popups, then the main layer. Tooltips and drag images are not `hit_testable`, so the pointer passes through them.

A parent can only reject a point outside its rect if its children cannot draw outside it, which is true when it clips. Without clipping, a child moved by an animation or a negative margin can stick out, and must still be clickable.

Make decorative widgets (icons on a button, background images, text inside a button) not `hit_testable`. Otherwise the press lands on the icon, and the button never sees it unless the event bubbles.

## Routing

An event is delivered along the path from the root to the target, in three phases:

```text
dispatch(event, target):
    path = [target and its ancestors], root first     // built once, before any handler runs

    event.phase = CAPTURE
    for w in path except last:
        if w is attached: w.on_event(event)
        if event.handled: return true

    event.phase = TARGET
    if target is attached: target.on_event(event)
    if event.handled: return true

    event.phase = BUBBLE
    for w in reverse(path) except last:
        if w is attached: w.on_event(event)
        if event.handled: return true
    return false
```

- **Bubble** is where most handling happens. A click on a list row's label bubbles to the row, which selects itself. A scroll wheel event bubbles to the nearest scroll view.
- **Capture** lets an ancestor see an event first and stop it. A modal dialog, or a list that is being reordered by dragging, uses capture to stop its children reacting.

The path is built before any handler runs and each widget is checked before it is called, because a handler may remove widgets from the tree (see [removing widgets during an event](widget-tree.md#removing-widgets-during-an-event)).

## Hover

Keep the widget under the pointer. When it changes, send leave and enter events to the widgets that left and joined its ancestor chain:

```text
on_pointer_move(p):
    new = hit_test_layers(p)
    old_chain = ancestors(hovered) including hovered
    new_chain = ancestors(new) including new
    for w in old_chain not in new_chain: clear w.HOVERED; send PointerLeave to w
    for w in new_chain not in old_chain: set w.HOVERED; send PointerEnter to w
    hovered = new
```

Every widget in the chain counts as hovered, so a panel can highlight while the pointer is over any of its children.

Run this on every frame, not only when the pointer moves. A list scrolling under a still pointer, or a panel animating in, changes what is under it.

## Press, click, and capture

```text
on_pointer_down(p, button):
    target = hit_test_layers(p)
    pressed = target
    press_pos = p
    captured = target                    // capture the pointer
    set target.PRESSED
    dispatch(PointerDown, target)

on_pointer_up(p, button):
    target = captured
    captured = null
    clear target.PRESSED
    dispatch(PointerUp, target)
    if target.rect.contains(p) and not dragging:
        dispatch(Click, target)
```

While the pointer is **captured**, every pointer event goes to the captured widget, wherever the pointer is. That is what lets a slider keep tracking after the pointer leaves the track, and stops a button from receiving an up event it never saw go down.

A click is a press and release on the same widget. Press a button, slide off, and release, and nothing happens. Players use this to back out of a mis-press.

Release capture when the window loses focus, when the captured widget is removed, or when a popup or screen is pushed on top. Otherwise the next press is sent to a widget the player cannot see.

## Dragging

A press only becomes a drag once the pointer has moved past a threshold. Without one, every slightly shaky click starts a drag.

```text
on_pointer_move(p):
    if pressed and not dragging and distance(p, press_pos) > DRAG_THRESHOLD:
        source = first of [pressed and its ancestors] that accepts drag
        if source:
            dragging = true
            captured = source
            dispatch(DragStart, source)
    if dragging:
        dispatch(Drag(p), captured)
```

A threshold of about 4 to 6 units, multiplied by the UI scale, works with a mouse. Touch needs about twice that.

Searching up from the pressed widget for one that accepts drag lets a scroll view hold buttons. The press lands on a button, the pointer moves, and the drag goes to the scroll view, which scrolls. The button never clicks, because the pointer was captured away from it.

For drag and drop between widgets, the drag source puts a payload and a drag image in the drag layer. On each move, hit test under the image (the drag image is not hit testable) and ask the widget there whether it accepts the payload, so it can highlight. On release, deliver the payload to it, or cancel and animate the image back to the source.

## Keyboard focus

One widget at a time has focus. Key, text, and navigation events go to it, with the same capture and bubble phases as pointer events:

```text
set_focus(w):
    if focused == w: return
    if focused: clear FOCUSED on focused; send FocusLost to focused
    focused = w
    if w: set FOCUSED on w; send FocusGained to w
```

- Pressing a focusable widget focuses it. Pressing anything else clears focus, so typing stops going to a text field the player clicked away from.
- A widget that is disabled, hidden, collapsed, or removed while it has focus loses focus. Move focus to the nearest focusable widget in its container, or to the screen's default, never to nothing while a gamepad is in use.
- Keep a `FOCUS_WITHIN` flag on the focused widget's ancestors, so a panel can show that something inside it is focused.

**Tab order** is the depth-first order of focusable, enabled, visible widgets in the focus scope, overridden by a `tab_index` where the tree order is wrong.

A **focus scope** is a subtree that focus cannot leave by navigation: the top screen, a modal dialog, or an open dropdown. See [the screen stack](architecture.md#the-screen-stack).

## Gamepad navigation

With a gamepad, `Navigate` moves focus to the nearest focusable widget in that direction:

```text
navigate(from, dir):
    if from.nav[dir]: return from.nav[dir]       // explicit override
    best = null, best_score = INFINITY
    a = from.rect
    for w in focusable widgets in the current scope:
        b = w.rect
        gap = edge_gap(a, b, dir)                // b's near edge minus a's far edge, along dir
        if gap < 0: continue                     // not in that direction
        overlap = overlap_on_perpendicular_axis(a, b, dir)
        off_axis = overlap > 0 ? 0 : distance between a and b across dir
        score = gap + off_axis * 2
        if score < best_score: best, best_score = w, score
    return best
```

Measuring from edges, not centres, handles widgets of different sizes: a small button right next to a tall panel's edge can be far from the panel's centre. Break ties (several widgets with the same score) by the distance between centres. Weighting the off-axis distance makes the cursor prefer moving in a straight line over jumping diagonally to something slightly closer.

The rules that make it feel right:

- **Explicit links** for the cases the geometry gets wrong, such as wrapping from the bottom of a list to the top, or jumping from a tab bar to its content.
- **Remember the last focus in each container.** Moving left out of a grid and back right should return to the same cell, not the cell nearest the panel edge.
- **Scroll to focus.** When focus moves to a widget inside a scroll view, scroll it into view (see [scroll views](elements.md#scroll-view)).
- **Hide the focus highlight when the mouse is used**, and show it again on the first gamepad or arrow key. When no widget has focus at that point, focus the screen's default widget instead of moving.
- **Repeat held directions**: a first delay of about 0.4 seconds, then about 0.1 seconds between moves.
