# Flexbox layout

The CSS flexible box model, cut down to the subset that Yoga (the layout engine behind React Native) implements. It replaces the separate stack, wrap, and spacer widgets with one container: every widget can lay out its children as a flex container. Flexbox extends [stacks](layout.md#stacks) with shrinking, wrapping, and alignment rules, and the rest of the [layout](layout.md) page still applies.

## Properties

On the container:

| Property | Values | Default (CSS / Yoga) |
| --- | --- | --- |
| `flex-direction` | `row`, `column`, `row-reverse`, `column-reverse` | `row` / `column` |
| `flex-wrap` | `nowrap`, `wrap`, `wrap-reverse` | `nowrap` |
| `justify-content` | `flex-start`, `center`, `flex-end`, `space-between`, `space-around`, `space-evenly` | `flex-start` |
| `align-items` | `stretch`, `flex-start`, `center`, `flex-end` | `stretch` |
| `align-content` | as `justify-content`, plus `stretch` | `stretch` / `flex-start` |
| `row-gap`, `column-gap` | length | `0` |

On each item:

| Property | Values | Default (CSS / Yoga) |
| --- | --- | --- |
| `flex-grow` | number | `0` |
| `flex-shrink` | number | `1` / `0` |
| `flex-basis` | `auto`, length, percentage | `auto` |
| `align-self` | `auto`, or an `align-items` value | `auto` |
| `position` | `relative`, `absolute` | `relative` |
| `left`, `right`, `top`, `bottom` | length, percentage | unset |

Plus `width`, `height`, `min-*`, `max-*`, `margin`, and `padding` on everything. Percentages resolve against the parent's inner size on the same axis, and count as unset when that size is not known yet.

The **main axis** runs along `flex-direction` and the **cross axis** across it. Everything below is written in terms of main and cross, so one algorithm handles rows and columns.

Pick your own defaults and write them down. Yoga's column direction and zero shrink suit app-style UI, where content stacks down the screen and should not squash. CSS's defaults suit text flow.

## Measure modes

Each axis is given a size and a mode, which tells the widget how to treat that size:

```text
EXACTLY     // this is your size
AT_MOST     // be as big as your content, but no bigger than this
UNDEFINED   // be as big as your content
```

`layout(node, width, width_mode, height, height_mode)` sets the node's size and lays out its children. A leaf, such as a label, supplies a measure function that answers the same question for its content:

```text
measure_text(width, width_mode, height, height_mode):
    wrap_width = (width_mode == UNDEFINED) ? INFINITY : width
    size = shaped text size wrapped at wrap_width
    if width_mode == EXACTLY: size.w = width
    if height_mode == EXACTLY: size.h = height
    return size
```

## The algorithm

```text
flex_layout(node, avail, mode):             // avail and mode per axis, inner size (padding removed)
    items = children where position != absolute and visibility != Collapsed

    determine base sizes                    // step 1
    collect items into lines                // step 2
    resolve flexible lengths per line       // step 3
    find cross sizes                        // step 4
    align lines (align-content)             // step 5
    stretch items                           // step 6
    position items on the main axis        // step 7
    position items on the cross axis        // step 8
    size the container                      // step 9
    lay out absolute children               // step 10
```

### 1. Base sizes

The size an item would have before any growing or shrinking:

```text
for it in items:
    it.base = case:
        it.basis is a length or resolvable %:   resolve(it.basis, avail.main)
        it.size[main] is set:                   resolve(it.size[main], avail.main)
        else:                                   content size from layout(it, main: UNDEFINED,
                                                    cross: avail.cross with AT_MOST)
    it.hypo = clamp(it.base, it.min[main], it.max[main])
```

`flex-basis: 0` with `flex-grow: 1` on every item gives equal widths regardless of content: all bases are 0, so all the space is shared out evenly. `flex-basis: auto` gives each item its content size first and shares only the space left over.

### 2. Lines

Without wrapping, every item is on one line. With wrapping, start a new line when the next item would overflow:

```text
lines = [new line]
for it in items:
    outer = it.hypo + it.margin.main
    line = last(lines)
    if node.wrap and line.items not empty and line.used + gap.main + outer > avail.main:
        line = new line; lines.append(line)
    line.used += (line.items empty ? 0 : gap.main) + outer
    line.items.append(it)
```

If `avail.main` is undefined, everything fits on one line.

### 3. Flexible lengths

Within each line, grow items into spare space or shrink them out of missing space. Items that hit their min or max are frozen at it, and the rest of the space is shared again:

```text
resolve_flexible_lengths(line, space):
    if space is undefined:
        for it: it.main = it.hypo
        return
    growing = line.used < space
    for it in line.items:
        it.main = it.hypo
        it.frozen = growing ? it.grow == 0 : it.shrink == 0

    loop:
        unfrozen = items not frozen
        if unfrozen empty: break
        free = space - gaps
             - sum(it.main + it.margin.main for frozen items)
             - sum(it.base + it.margin.main for unfrozen items)
        if growing:
            weight(it) = it.grow
        else:
            weight(it) = it.shrink * it.base     // big items give up more
        total = sum(weight(it) for unfrozen)
        if total == 0: break

        any_clamped = false
        for it in unfrozen:
            target = it.base + free * weight(it) / total
            it.main = clamp(target, it.min[main], it.max[main])
            if it.main != target:
                it.frozen = true
                any_clamped = true
        if not any_clamped: break
```

- Shrink is weighted by base size, so a 400-unit item with `flex-shrink: 1` gives up four times as much as a 100-unit one. Weighting by `flex-shrink` alone would push small items to zero long before large ones noticed.
- The CSS spec freezes only the items clamped in the direction of the total violation. Freezing every clamped item, as here, is simpler and gives the same result in nearly every real layout.

**Minimum size.** In CSS, an item's `min-width: auto` means "no smaller than its content's minimum": the longest word, for text. Yoga uses 0. With 0, shrinking can squash a label to nothing; set `min-width` on items that must stay readable, or compute the min-content size and use it as the default minimum. On the other hand, a content pane that should shrink below its content needs `min-width: 0` in CSS, which is a common source of "why does this overflow?".

### 4. Cross sizes

Now each item's main size is known, and its cross size can be measured at that size. This is where wrapped text finds its height:

```text
for it in items:
    if it.size[cross] is set:
        it.cross = resolve(it.size[cross], avail.cross)
    else:
        it.cross = layout(it, main: it.main EXACTLY, cross: avail.cross AT_MOST).cross
    it.cross = clamp(it.cross, it.min[cross], it.max[cross])

for line in lines:
    line.cross = max(it.cross + it.margin.cross for it in line.items)

if lines has one entry and mode.cross == EXACTLY:
    lines[0].cross = avail.cross
```

### 5. Align lines

Only matters when the container wraps. Spare cross space is shared between lines exactly as `justify-content` shares main space between items (step 7), with one extra value: `stretch` adds an equal share to each line's cross size.

```text
free = avail.cross - sum(line.cross) - gap.cross * (len(lines) - 1)
if node.align_content == STRETCH and free > 0:
    for line: line.cross += free / len(lines)
else:
    lead, between = distribute(node.align_content, free, len(lines))
pos = lead
for line in lines:
    line.offset = pos
    pos += line.cross + gap.cross + between
```

### 6. Stretch

```text
for it in items:
    align = (it.align_self == AUTO) ? node.align_items : it.align_self
    if align == STRETCH and it.size[cross] is not set:
        it.cross = clamp(line.cross - it.margin.cross, it.min[cross], it.max[cross])
        layout(it, main: it.main EXACTLY, cross: it.cross EXACTLY)    // children see the new size
```

Stretching changes an item's size after it was measured, so its own children need laying out again. That repeated call is why layouts must be cached (see [caching](#caching)).

### 7. Main axis positions

```text
distribute(mode, free, n):                  // returns (leading space, extra space between)
    if free < 0:
        mode = (mode == SPACE_BETWEEN) ? FLEX_START
             : (mode in SPACE_AROUND, SPACE_EVENLY) ? CENTER
             : mode
    case mode:
        FLEX_START:    return (0, 0)
        CENTER:        return (free / 2, 0)
        FLEX_END:      return (free, 0)
        SPACE_BETWEEN: return (0, n > 1 ? free / (n - 1) : 0)
        SPACE_AROUND:  return (free / n / 2, free / n)
        SPACE_EVENLY:  return (free / (n + 1), free / (n + 1))

for line in lines:
    free = avail.main - sum(it.main + it.margin.main) - gap.main * (len(line.items) - 1)
    lead, between = distribute(node.justify_content, free, len(line.items))
    pos = lead
    for it in line.items:
        it.pos.main = pos + it.margin.main_start
        pos += it.main + it.margin.main + gap.main + between
```

When any item grows, `free` is 0 and `justify-content` has no effect. A spacer is just an empty item with `flex-grow: 1`.

Yoga also supports `auto` margins, which take the free space before `justify-content` sees it: `margin-left: auto` on the last item of a toolbar pushes it to the right edge.

### 8. Cross axis positions

```text
for it in line.items:
    outer = it.cross + it.margin.cross
    offset = case align:
        FLEX_START, STRETCH: 0
        CENTER:              (line.cross - outer) / 2
        FLEX_END:            line.cross - outer
    it.pos.cross = line.offset + offset + it.margin.cross_start
```

**Reversed directions** lay out as normal, then mirror: `pos.main = avail.main - pos.main - it.main` for `row-reverse` and `column-reverse`, and the same on the cross axis for line offsets with `wrap-reverse`. Mirror after positioning, so the rest of the algorithm never has to think about direction.

### 9. Container size

```text
content.main = max over lines of (sum(it.main + it.margin.main) + gaps)
content.cross = sum(line.cross) + gap.cross * (len(lines) - 1)
for each axis:
    size = case mode[axis]:
        EXACTLY:    avail[axis]
        AT_MOST:    min(content[axis], avail[axis])
        UNDEFINED:  content[axis]
node.size = clamp(size + padding, node.min, node.max)
```

### 10. Absolute children

An absolutely positioned child takes no space in the lines. It is placed against the container's padding box using its insets:

```text
for it in absolute children:
    for each axis (start = left or top, end = right or bottom):
        if it.size[axis] is set:                 w = resolve(it.size[axis])
        else if it.start and it.end are set:     w = parent_inner[axis] - it.start - it.end
        else:                                    w = measured content size
        if it.start is set:     pos = it.start
        else if it.end is set:  pos = parent_inner[axis] - it.end - w
        else:                   pos = aligned by justify-content or align-items, as a lone item
    layout(it, w EXACTLY, h EXACTLY); place at pos
```

Badges on icons, close buttons in panel corners, and overlays filling their parent (`left: 0; right: 0; top: 0; bottom: 0`) all use it. It replaces the separate overlay container from [anchors](layout.md#overlays-and-anchors) for most cases.

## Caching

One `flex_layout` lays out each child up to three times: for its base size (step 1), its cross size (step 4), and again if it stretches (step 6). Each of those lays out its own children several times, so without a cache the cost grows exponentially with tree depth.

Cache results per node, keyed by the arguments:

```text
key = (width, width_mode, height, height_mode)
if node is clean and node.cache has key: return node.cache[key]
```

Yoga keeps a handful of recent measurements per node plus the final layout. Also reuse a result across modes when the answer must be the same: an `AT_MOST 300` measurement that came back 200 wide answers an `AT_MOST 250` query too, because the content did not need more than 200. Clear the cache when the node is [invalidated](widget-tree.md#invalidation).

## Common layouts

```css
/* Toolbar: buttons on the left, a search box pushed to the right */
.toolbar  { flex-direction: row; align-items: center; column-gap: 8px; }
.spacer   { flex-grow: 1; }

/* Sidebar and content */
.split    { flex-direction: row; }
.sidebar  { flex-basis: 280px; flex-shrink: 0; }
.content  { flex-grow: 1; min-width: 0; }

/* Inventory grid: fixed slots that wrap */
.grid     { flex-direction: row; flex-wrap: wrap; gap: 4px; align-content: flex-start; }
.slot     { width: 64px; height: 64px; flex-shrink: 0; }

/* Dialog centred on screen */
.screen   { flex-grow: 1; justify-content: center; align-items: center; }

/* Count badge in an icon's corner */
.badge    { position: absolute; right: 2px; bottom: 2px; }

/* Three equal columns, whatever their content */
.col      { flex-grow: 1; flex-basis: 0; }
```

Flexbox cannot align items in two directions at once. A grid whose last row lines up with the rows above, or a form with aligned label columns, needs fixed item sizes (as in the inventory grid), or a grid layout model.
