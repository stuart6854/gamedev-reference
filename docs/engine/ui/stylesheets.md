# Style sheets

A subset of CSS for styling the widget tree: parsing a sheet, matching selectors against widgets, the cascade, inheritance and variables, and transitions. Unity's USS is an example of this kind of subset. The [styling](architecture.md#styling) section covers why styles live outside widget code; this page builds the system.

## The subset

```css
:root {
    --accent: #e0a030;
    --panel-bg: rgba(20, 24, 28, 0.9);
}

Panel {
    background-color: var(--panel-bg);
    padding: 12px;
    border-radius: 6px;
}

Button {
    color: #ddd;
    background-color: #333;
    transition: background-color 0.15s ease-out;
}

Button:hover          { background-color: #444; }
Button.primary        { background-color: var(--accent); color: #111; }
Button:disabled       { opacity: 0.5; }
.inventory > Slot     { width: 64px; height: 64px; }
#title                { font-size: 1.5em; }
```

| Feature | In | Out |
| --- | --- | --- |
| Selectors | type (`Button`), `.class`, `#id`, `*`, compounds (`Button.primary:hover`), descendant (`A B`), child (`A > B`), lists (`A, B`) | attribute selectors, sibling combinators, `:nth-child`, `:not`, `:has` |
| Pseudo-classes | `:hover`, `:active`, `:focus`, `:disabled`, `:checked`, `:root` | everything else |
| Values | lengths in `px`, `em`, `%`; numbers; colours (`#rgb`, `#rrggbb`, `#rrggbbaa`, `rgb()`, `rgba()`, a few names); keywords; times (`s`, `ms`); `var()` | `calc()`, other units, gradients |
| Properties | box and [flexbox](flexbox.md) properties, colours, borders, `border-radius`, `opacity`, font properties, `transition`; shorthands for `margin`, `padding`, `border`, `transition` | anything the engine does not draw |
| At-rules | none | `@media`, `@import`, `@keyframes` |

Each line in "Out" is a feature that makes matching or the cascade much more expensive, or one that game UI seldom needs. Leave them out until a screen needs one.

## Tokenizing

Split the source into tokens, dropping comments and keeping whitespace only where it matters (it is the descendant combinator):

```text
Token =
    IDENT(text)             // Button, color, ease-out, --accent
    HASH(text)              // #title, #e0a030 (an id or a colour, decided by context)
    NUMBER(value)
    DIMENSION(value, unit)  // 12px, 0.15s, 1.5em
    PERCENTAGE(value)
    STRING(text)
    FUNCTION(name)          // rgba( var(  — the name and the opening bracket
    COLON, SEMICOLON, COMMA, DOT, GREATER, STAR
    LBRACE, RBRACE, RPAREN
    WHITESPACE
    EOF

next_token():
    skip comments /* ... */
    c = peek()
    if c is whitespace: consume all whitespace; return WHITESPACE
    if c is digit, or (c in "+-." and a digit follows):
        n = consume number
        if an identifier starts here: return DIMENSION(n, consume ident)
        if peek() == '%': consume; return PERCENTAGE(n)
        return NUMBER(n)
    if c starts an identifier (letter, '_', '-', or "--"):
        name = consume ident
        if peek() == '(': consume; return FUNCTION(name)
        return IDENT(name)
    if c == '#': consume; return HASH(consume ident chars)
    if c in "\"'": return STRING(consume until matching quote)
    single-character tokens: { } ( ) : ; , . > *
```

Record the line and column on each token for error messages. A sheet with a typo should report "line 14: unknown property 'colr'" in the editor, not silently do nothing.

## Parsing

```text
stylesheet  := rule*
rule        := selector_list '{' declaration* '}'
declaration := IDENT ':' value_tokens ';'?

Rule {
    selectors[]
    declarations[]          // { property, value tokens, important: no }
    order                   // position in the sheet, for the cascade
}
```

Store each declaration's value as its raw tokens, and parse it per property afterwards. The grammar stays tiny, and properties containing `var()` cannot be parsed until the variable's value is known anyway.

**Recover the way browsers do.** A broken declaration is skipped up to the next `;` or `}`, and the rest of the rule still applies. A broken selector drops the whole rule, up to its matching `}`. One mistake costs one line, not the whole sheet.

### Selectors

```text
Compound {
    type                    // or null for any
    id                      // or null
    classes[]
    pseudo                  // bit flags: HOVER, ACTIVE, FOCUS, DISABLED, CHECKED, ROOT
}

Selector {
    compounds[]             // left to right
    combinators[]           // combinators[i] joins compounds[i - 1] and compounds[i]: DESCENDANT or CHILD
    specificity
}
```

Parse a compound from consecutive tokens with no whitespace between them. Whitespace followed by another compound is a descendant combinator; `>` (with or without spaces) is a child combinator. A comma starts the next selector in the list.

### Values

A property table drives value parsing:

```text
properties = {
    "width":            { type: LENGTH_OR_AUTO,  inherited: no,  initial: auto }
    "color":            { type: COLOR,           inherited: yes, initial: black }
    "font-size":        { type: LENGTH,          inherited: yes, initial: 16px }
    "flex-direction":   { type: KEYWORD(row, column, row-reverse, column-reverse),
                                                 inherited: no,  initial: column }
    "opacity":          { type: NUMBER,          inherited: no,  initial: 1 }
    ...
}
```

Unknown property: warn and skip. Shorthands expand when parsed: `padding: 4px 8px` becomes the four longhands (top and bottom 4, left and right 8), and from then on only longhands exist.

## Matching

Match each selector **right to left**: check the widget against the last compound, then walk up the tree for the rest. Most selectors fail on the last compound, before any walking.

```text
compound_matches(c, w):
    if c.type and c.type != w.type_name: return false
    if c.id and c.id != w.id: return false
    for cls in c.classes: if cls not in w.classes: return false
    if c.pseudo & ~w.state_flags: return false      // ROOT counts as a state flag on the root
    return true

matches(sel, i, w):                                 // call with i = last index
    if not compound_matches(sel.compounds[i], w): return false
    if i == 0: return true
    if sel.combinators[i] == CHILD:
        return w.parent and matches(sel, i - 1, w.parent)
    for a in ancestors(w):                          // DESCENDANT
        if matches(sel, i - 1, a): return true
    return false
```

Don't test every rule against every widget. Index rules by their rightmost compound: by id if it has one, else by its first class, else by type, else in a universal list. A widget only tests the rules in the buckets for its id, its classes, its type, and the universal list.

## The cascade

When several rules set the same property, the winner is the one with the highest specificity, and among equals, the one that comes last:

```text
specificity(sel) = (ids, classes + pseudo-classes, types)    // compared left to right
```

`#title` (1, 0, 0) beats `Button.primary:hover` (0, 2, 1), which beats `Panel Button` (0, 0, 2).

```text
cascade(w):
    matched = [(sel.specificity, rule.order, rule) for each rule and selector that matches w]
    sort matched by (specificity, order)
    declared = {}
    for (_, _, rule) in matched:            // lowest first, so later writes win
        for d in rule.declarations:
            declared[d.property] = d.value
    for d in w.inline_style:                // inline style beats every sheet
        declared[d.property] = d.value
    return declared
```

Several sheets (an engine default sheet, the game's theme, a screen's own sheet) are concatenated in that order, with `order` continuing across them, so later sheets win ties.

## Computed values

The cascade gives each property a declared value, or none. Turning that into the value layout and painting use:

```text
compute_style(w):
    declared = cascade(w)
    parent = w.parent ? w.parent.computed : initial values
    for each property p:
        v = declared[p]
        if v is absent:     v = properties[p].inherited ? parent[p] : INITIAL
        if v == INHERIT:    v = parent[p]
        if v == INITIAL:    v = properties[p].initial
        w.computed[p] = to_computed(p, substitute_vars(v, w), parent)
```

`to_computed` resolves what can be resolved without layout:

- `em` becomes `px`, multiplied by the font size. For `font-size` itself, `em` is relative to the **parent's** font size, so compute `font-size` first.
- Colours become RGBA floats.
- Percentages stay percentages; only layout knows what they are a percentage of.

Inherit only the properties that make sense to inherit, mostly text: `color`, `font-*`, `text-align`, and custom properties. Set `padding` on a panel and its children should not all get padding too.

Many widgets end up with identical computed styles: every slot in a grid, every row in a list. Intern computed styles by hash and share one copy, which saves memory and lets "did the style change?" be a pointer comparison.

## Variables

Custom properties (names starting `--`) are inherited properties whose values are token lists. `var(--name, fallback)` substitutes them into other values before those are parsed:

```text
substitute_vars(tokens, w, resolving = {}):
    out = []
    for t in tokens:
        if t is FUNCTION("var"):
            name, fallback = arguments of t
            if name in resolving: return INVALID              // a cycle: --a uses --b uses --a
            value = w.computed[name]                          // inherited, so set on :root reaches everything
            if value is absent: value = fallback
            if value is absent: return INVALID
            out += substitute_vars(value, w, resolving + {name})
        else:
            out.append(t)
    return out
```

Compute a widget's custom properties before its other properties, substituting any `var()` inside them, so the lookup above always finds a finished value.

If substitution or the following parse fails, the property behaves as if it was not declared: inherited properties inherit, others take their initial value. That is how CSS handles it; it cannot fall back to a lower-specificity rule, because the cascade has already finished.

Variables are what make themes cheap: a theme is a `:root` block of colours and sizes, and swapping it changes one rule.

## When to recompute

Styles depend on classes, ids, state flags, the tree position, and the parent's computed style. Mark a widget `STYLE` dirty when:

- its classes or id change,
- its state flags change (hovered, pressed, focused, disabled, checked),
- it moves to a different parent,
- its parent's computed style changes (only if an inherited property changed).

State changes are the most frequent, and descendant selectors make them spread: `Panel:hover Button` means hovering a panel can restyle every button inside it. While parsing, note whether any pseudo-class appears in a compound **other than the rightmost** one. If none does (the common case), a state change only dirties the widget itself.

Recompute dirty styles once per frame, top-down, before layout. If any property that affects layout changed, [invalidate layout](widget-tree.md#invalidation).

## Transitions

```css
Button { transition: background-color 0.15s ease-out, opacity 0.2s; }
```

When a computed value changes on a property that has a transition, animate from the value currently on screen to the new one, instead of jumping:

```text
Transition { property, from, to, start_time, duration, easing }

on_computed_change(w, p, old, new):
    spec = w.computed.transition entry for p
    if not spec or not interpolable(p): return            // just switch
    current = w.running[p] ? w.running[p].value_now() : old
    w.running[p] = Transition { p, from: current, to: new, now, spec.duration, spec.easing }

update_transitions(now):
    for each running transition t on w:
        u = clamp01((now - t.start_time) / t.duration)
        w.animated[p] = interpolate(t.from, t.to, t.easing(u))
        if u == 1: remove t
```

- Start from the **current displayed value**, not the old target. A pointer that leaves a button halfway through its hover fade should fade back from where it is, not snap to fully hovered first.
- Reversing halfway should take half the time. CSS shortens a reversed transition in proportion to how far the first one got; without that, quickly flicking over a button feels sluggish.
- **Interpolable** types: lengths in the same unit, numbers, and colours. Mix colours in linear space with premultiplied alpha, or a fade from transparent towards white passes through grey. Everything else (keywords, mixed units) switches at once.
- Painting reads `w.animated[p]` if present, else `w.computed[p]`. The computed value stays the target, so the next cascade compares against the target, not a midway value.
- Transitioning layout properties (`width`, `padding`, `margin`) relayouts every frame for the duration. Prefer `opacity`, colours, and render transforms (see [animation](architecture.md#animation)).
