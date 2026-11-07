# Reflection

Every serialised type needs the same information: its fields, their names, their types, and where they are in memory. Written out by hand for each format (a binary writer, a text writer, an editor inspector, a network replicator), it is four copies that drift apart. **Reflection** describes each type once and drives all of them from that description.

C# has reflection built in. C++ does not, so engines build their own. This page shows two ways, in C++.

## A visitor per type

The smallest approach: each type has one function that visits its fields, and the visitor decides what to do with them.

```cpp
struct Player {
    std::string name;
    int health = 100;
    Vec3 position;
    std::vector<ItemId> inventory;
};

template <class Visitor>
void visit(Visitor& v, Player& p)
{
    v("name", p.name);
    v("health", p.health);
    v("position", p.position);
    v("inventory", p.inventory);
}
```

A binary writer, a binary reader, a JSON writer, and an editor inspector are all visitors:

```cpp
struct BinaryWriter {
    Stream& out;
    void operator()(const char*, int& value)          { out.write_i32(value); }
    void operator()(const char*, std::string& value)  { out.write_string(value); }
    template <class T> void operator()(const char*, std::vector<T>& values)
    {
        out.write_u32(uint32_t(values.size()));
        for (T& item : values) (*this)("", item);
    }
    template <class T> void operator()(const char*, T& value) { visit(*this, value); }   // nested types
};

struct BinaryReader { /* the same shape, reading instead of writing */ };
```

The same `visit` function both writes and reads, so the field order can never differ between the two. That alone prevents the most common serialisation bug.

The cost is that the description is code, not data: it is only available where the template is instantiated, and a tool cannot list a type's fields at run time.

## Type descriptions as data

For editors, scripting bindings, and generic tools, the description must be data that can be inspected at run time:

```cpp
enum class Kind { Int, Float, Bool, String, Vec3, Struct, Array, Handle };

struct FieldInfo {
    const char* name;
    const TypeInfo* type;
    size_t offset;              // offsetof(Owner, field)
    uint32_t flags;             // Transient, EditorOnly, ReadOnly, ...
};

struct TypeInfo {
    const char* name;
    size_t size;
    Kind kind;
    std::span<const FieldInfo> fields;          // for Struct
    const TypeInfo* element;                    // for Array
    // for Array: functions to get the count, resize, and get element i
};

#define FIELD(Owner, field, flags) \
    FieldInfo{ #field, type_of<decltype(Owner::field)>(), offsetof(Owner, field), flags }

template <> const TypeInfo* type_of<Player>()
{
    static const FieldInfo fields[] = {
        FIELD(Player, name, 0),
        FIELD(Player, health, 0),
        FIELD(Player, position, 0),
        FIELD(Player, inventory, 0),
    };
    static const TypeInfo info{ "Player", sizeof(Player), Kind::Struct, fields, nullptr };
    return &info;
}
```

A generic function walks any type from its description and a pointer:

```cpp
void write(BinaryWriter& w, const TypeInfo* type, const void* data)
{
    switch (type->kind) {
    case Kind::Int:    w.write_i32(*static_cast<const int*>(data)); break;
    case Kind::Struct:
        for (const FieldInfo& f : type->fields)
            if (!(f.flags & Transient))
                write(w, f.type, static_cast<const char*>(data) + f.offset);
        break;
    // ...
    }
}
```

`offsetof` is only well-defined for standard-layout types. Keep reflected types as plain structs (no virtual functions, no private fields), or generate accessor functions per field instead of offsets.

### Where the descriptions come from

| Approach | How | Trade-off |
| --- | --- | --- |
| Hand-written tables or macros | As above | Simple; easy to forget a field |
| Code generation from headers | A tool parses headers (libclang, or a custom parser like Unreal's UHT) for marked types and writes the tables | Nothing to forget; another build step |
| Generation from a schema | Types are written in a schema language (FlatBuffers, a custom IDL) and both the C++ structs and the tables are generated | The schema is the source of truth; C++ types are generated, not written |

With hand-written tables, put `static_assert(sizeof(Player) == 72, "update the reflection table");` next to each one. Adding a field changes the size and breaks the build until someone looks at the table.

## What reflection drives

| Use | What it reads from the description |
| --- | --- |
| Binary and text serialisation | Field names (text), types, order |
| Editor inspector | Field names, types, and flags such as `ReadOnly`, ranges, tooltips |
| Undo and redo | Copy, compare, and restore a field by path |
| Prefab overrides and diffs | Compare each field with the prefab's, and save only those that differ |
| Network replication | Which fields are replicated, and how to compare and pack them |
| Script bindings | Names and types to expose to Lua or C# |

Attach metadata to fields with flags or attributes (`Range(0, 100)`, `Tooltip("...")`, `Replicated`), stored in the field description. Each system reads only the metadata it understands.

### Diffing and overrides

A prefab instance saves only the fields it changed:

```text
diff(type, base, instance, path, out):
    for field in type.fields:
        a = base + field.offset
        b = instance + field.offset
        if field.type is Struct: diff(field.type, a, b, path + field.name, out)
        else if not equal(field.type, a, b): out.append({ path + field.name, value at b })
```

Applying the overrides is the reverse: copy the prefab, then set each saved path. A change to the prefab then reaches every instance, except for the fields an instance overrode. Undo works the same way, recording the path, the old value, and the new value.
