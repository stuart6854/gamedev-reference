# Layout

Layout turns the tree's sizing rules into a screen rect for every widget. It runs in two passes:

1. **Measure**, bottom-up: each widget reports the size it wants, given the space its parent can offer.
2. **Arrange**, top-down: each parent gives its children their final rects, using those desired sizes.

A widget only learns its final size in arrange. Measure is a question ("how big would you like to be?"); arrange is the answer.

## Sizing rules

Each axis has its own rule:

```text
Size =
    Fixed(px)           // exactly this many units
    Fit                 // the size of the content, plus padding
    Grow(weight)        // at least Fit, plus a share of the parent's spare space
    Percent(p)          // a fraction of the parent's inner size

Layout {
    width, height       // Size
    min_size, max_size  // clamps applied after the rule
    padding             // inside the widget, around its children
    margin              // outside the widget, kept clear by the parent
}
```

`Grow` is what makes a layout fill the screen: a sidebar with a fixed width and a content area that grows takes the rest. `Fit` is what makes it adapt to content: a button sized to its label. Most widgets use `Fit` on both axes; containers that fill a region use `Grow`.

## Measure

```text
measure(w, available):                   // available may be INFINITY on either axis
    inner = available - w.padding
    content = w.measure_content(inner)   // per widget type
    for each axis:
        desired[axis] = case w.layout.size[axis]:
            Fixed(px):   px
            Fit, Grow:   content[axis] + w.padding[axis]
            Percent(p):  if available[axis] is finite: available[axis] * p
                         else: content[axis] + w.padding[axis]
    w.desired_size = clamp(desired, w.min_size, w.max_size)
    return w.desired_size
```

`measure_content` is where widget types differ. A label returns its text's size. An image returns its texture's size. A container measures its children and combines their sizes.

`available` is infinite inside anything that scrolls on that axis: a scroll view offers unlimited height to its content, so the content reports its full height.

## Stacks

A stack places its children in a row or a column. It is the container behind most game UI: a menu is a column of buttons, a HUD bar is a row of icons.

```text
Stack {
    axis                // ROW or COLUMN; main is along it, cross is across it
    gap
    align_main          // START, CENTER, END, SPACE_BETWEEN; used when nothing grows
    align_cross         // START, CENTER, END, STRETCH
}

measure_content(stack, available):
    main = 0, cross = 0, count = 0
    for c in stack.children where c.visibility != Collapsed:
        s = measure(c, available) + c.margin
        main += s.main
        cross = max(cross, s.cross)
        count += 1
    if count > 0: main += stack.gap * (count - 1)
    return (main, cross)
```

Arranging hands out the spare space along the main axis to the children that grow, in proportion to their weights:

```text
arrange_children(stack, rect):
    inner = rect - stack.padding
    children = visible, non-collapsed children
    used = sum of (c.desired_size.main + c.margin.main) for c in children
         + stack.gap * (len(children) - 1)
    spare = max(0, inner.main - used)
    total_weight = sum of c.layout.main.weight for growing children

    pos = inner.main_start
    if total_weight == 0:
        pos += start_offset(stack.align_main, spare)      // 0, spare / 2, or spare
    for c in children:
        size_main = c.desired_size.main
        if c grows on the main axis:
            size_main += spare * c.layout.main.weight / total_weight
        size_main = clamp(size_main, c.min_size.main, c.max_size.main)

        size_cross = (stack.align_cross == STRETCH or c grows on the cross axis)
                     ? inner.cross - c.margin.cross
                     : c.desired_size.cross
        cross_pos = inner.cross_start + align(stack.align_cross, inner.cross, size_cross)

        arrange(c, rect from (pos + c.margin.main_start, cross_pos) with (size_main, size_cross))
        pos += size_main + c.margin.main + stack.gap
        // SPACE_BETWEEN adds spare / (len(children) - 1) here instead of using start_offset
```

`arrange(c, rect)` stores `rect` on the widget, calls its `arrange_children`, and clears its `LAYOUT` flag.

When the children do not fit, `spare` is 0 and the stack overflows its rect. That is a design decision, not a bug: decide per container whether to clip, scroll, or shrink. Shrinking needs a second rule, like CSS `flex-shrink`; most game UIs get by without it and put long content in a scroll view.

## Text that wraps

Wrapped text breaks the two-pass model. Its height depends on its width, and inside a row its width is not known until the row is arranged.

The fix is to lay out one axis at a time across the whole tree:

1. Measure and arrange **widths** for the whole tree. A wrapping label reports, as its desired width, its longest word (minimum) or its full unwrapped line (preferred).
2. **Wrap** every label at the width it was given.
3. Measure and arrange **heights** for the whole tree, now that every label knows its line count.

Clay and similar layout libraries work this way. The extra pass costs little, and it removes the "measure twice with a guessed width" workarounds.

## Overlays and anchors

An overlay places all its children on top of each other, each positioned within the overlay's rect by anchors. This is how HUD elements are pinned to corners, and how a panel is centred on screen.

```text
Anchored {
    anchor_min, anchor_max      // 0..1 on each axis, within the parent's rect
    offset_min, offset_max      // units added after anchoring; a pinned child uses only offset_min
    pivot                       // 0..1 point on the child that sits on the anchor
}

arrange_anchored(c, parent):
    for each axis:
        lo = parent.pos + parent.size * c.anchor_min
        hi = parent.pos + parent.size * c.anchor_max
        if c.anchor_min == c.anchor_max:            // pinned to a point
            size = c.desired_size
            pos = lo - size * c.pivot + c.offset_min
        else:                                       // stretched between two points
            pos = lo + c.offset_min
            size = (hi + c.offset_max) - pos
    arrange(c, rect(pos, size))
```

A health bar in the top-left corner has anchors `(0, 0)`, pivot `(0, 0)`, and offset_min `(16, 16)`. A dialog in the centre has anchors `(0.5, 0.5)` and pivot `(0.5, 0.5)`. A bottom bar that spans the screen has anchor_min `(0, 1)`, anchor_max `(1, 1)`, offset_min `(0, -64)`, and offset_max `(0, 0)`, which makes it 64 units tall. Here y points down, so 0 is the top edge.

Use anchors on the screen's top level and stacks inside each panel. Anchors everywhere means repositioning everything by hand whenever one element grows.

## Skipping work

Layout only descends into widgets flagged `LAYOUT` (see [invalidation](widget-tree.md#invalidation)), but a clean parent can still be given a different rect when a sibling grows. Cache on both passes:

- Measure: keep the last `available` and the result. If the widget is clean and `available` is unchanged, return the cached size.
- Arrange: if the widget is clean and its new rect has the same size as the old one, move the subtree by the position delta without re-running `arrange_children`.

## Snapping to pixels

Layout works in fractional units. The renderer should get whole pixels, or text and one-pixel borders go blurry.

Round each edge, not each size:

```text
x0 = round(rect.x * scale)
x1 = round((rect.x + rect.w) * scale)
pixel_rect.x = x0
pixel_rect.w = x1 - x0
```

Rounding sizes lets the error add up: ten 10.4-pixel columns rounded to 10 each leave a 4-pixel gap at the end. Rounding edges keeps neighbours touching. `scale` is the UI scale from [scaling](architecture.md#scaling-and-dpi).
