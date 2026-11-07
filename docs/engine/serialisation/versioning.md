# Versioning

Data outlives the code that wrote it. A save from version 1.0 must load in 1.4, and a scene authored last year must open after its components gained new fields. Every format needs a plan for reading older data.

## Which data needs it

| Data | Old versions to read | Approach |
| --- | --- | --- |
| Cooked assets | None: they are rebuilt from source for each build | A version or layout hash, to reject stale data |
| Authoring files (scenes, prefabs) | Every version since the project started, until re-saved | Tagged fields, defaults, upgrade on load |
| Save games | Every version ever shipped, forever | Version numbers and migrations, and old files kept as tests |
| Network messages | Only the current version, if client and server must match | A protocol version checked on connect |

Cooked data is the easy case: put a version number (or a hash of the type layouts, from [reflection](reflection.md)) in the header, and rebuild when it does not match. Do not write migration code for data that can be rebuilt.

## Version numbers and migrations

The file records the version it was written with. The reader handles every older version:

```text
read_player(r, version):
    p = Player()
    p.name = r.read_string()
    p.health = r.read_i32()
    if version >= 3: p.stamina = r.read_i32()          // added in v3; older saves keep the default
    if version >= 5: p.position = r.read_vec3()
    else:            p.position = r.read_vec2() as vec3 with y = 0     // v5 went 3D
    return p
```

This gets hard to read after a dozen versions. The alternative is a chain of **migrations**, each turning version N data into version N + 1, with the reader only understanding the current version:

```text
migrations = {
    1: add_stamina_with_default,
    2: rename_hp_to_health,
    3: convert_positions_to_3d,
    4: split_inventory_into_bags,
}

load(file):
    data = parse into a generic tree (field names to values)
    for v in file.version .. CURRENT - 1:
        data = migrations[v](data)
    return read_current(data)
```

Migrations work on a **generic tree** (like a JSON document), not on the game's classes, because the classes only describe the current version. Each migration is small, written once when the format changes, and never edited again. The [save versioning](../../unity/systems/saving/versioning.md) page does this in Unity with frozen classes per version.

## Tagged fields

Instead of relying on field order, write each field with an id and a size:

```text
field:  id (varint)  wire_type (3 bits)  value
        wire types: varint, 32-bit, 64-bit, length-prefixed

read_struct(r):
    obj = default instance
    while not at end:
        id, wire = r.read_tag()
        if id is known: read the value into that field
        else: skip it by its wire type           // a field added by a newer version
    return obj
```

This is how Protocol Buffers works. Its rules for evolving a format apply to any tagged format:

- **Missing fields take their default.** Data from before a field existed loads with the default value.
- **Unknown fields are skipped.** An older reader can read newer data (forward compatibility), which matters for tools and servers that update at different times.
- **Never reuse a field id.** When a field is removed, reserve its id. A new field that reused it would be read from old data as the wrong thing.
- **Ids, not names, are the identity.** Renaming a field in the code is free.
- **Changing a field's type is a new field.** Add the new one with a new id, and convert from the old one in a migration if it is present.

Text formats get the same properties by keying on field names: missing names take defaults, unknown names are skipped (with a warning in development), and renames are handled by keeping a list of old names (an alias) per field.

## Renames and moves

| Change | Text format | Tagged binary |
| --- | --- | --- |
| Rename a field | Alias: also accept the old name when reading | Free: the id did not change |
| Rename a type | Alias for the type name | Type ids, not names, in the data |
| Move a field into a nested struct | Migration | Migration |
| Change units (degrees to radians) | Migration, with the version number | New field id, and a migration |

Write the old name or version in a comment next to the alias or migration, with the date or release. That is the only record of why it exists.

## Testing old data

Keep a file from every shipped version (and from interesting states: empty inventory, maximum level, every quest stage) in the repository, and load each one in a test:

```text
for file in test_data/saves/*.sav:
    test "loads " + file:
        game = load(file)
        check game is valid          // no errors, invariants hold, expected values present
```

Add a file to the set every time a version ships. A change that breaks an old save then fails a test, not a player's 80-hour game.
