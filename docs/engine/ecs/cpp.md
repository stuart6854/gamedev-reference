# ECS in C++

The [entities](entities.md), [sparse-set storage](sparse-set-storage.md), and [archetype storage](archetype-storage.md) pages describe an ECS in pseudocode. This page is the same design in C++20: strong entity ids, component type ids, component masks, sparse-set pools with a world and views, type-erased archetype columns, and a command buffer. The code compiles as one file with GCC and Clang, and its tests pass under AddressSanitizer and UndefinedBehaviorSanitizer.

## Entity ids

```cpp
enum class Entity : std::uint32_t { null = 0 };

constexpr std::uint32_t INDEX_BITS = 24;
constexpr std::uint32_t INDEX_MASK = (1u << INDEX_BITS) - 1;
constexpr std::uint32_t GENERATION_MASK = 0xFFu;
constexpr std::uint32_t NO_INDEX = INDEX_MASK;          // "end of free list"

constexpr std::uint32_t index_of(Entity e) { return std::uint32_t(e) & INDEX_MASK; }
constexpr std::uint32_t generation_of(Entity e) { return std::uint32_t(e) >> INDEX_BITS; }
constexpr Entity make_entity(std::uint32_t index, std::uint32_t generation)
{
    return Entity((generation << INDEX_BITS) | (index & INDEX_MASK));
}

class EntityRegistry {
public:
    Entity create()
    {
        if (free_head_ != NO_INDEX) {
            std::uint32_t index = free_head_;
            Entity slot = slots_[index];               // free slot: next free index + current generation
            free_head_ = index_of(slot);
            Entity e = make_entity(index, generation_of(slot));
            slots_[index] = e;
            return e;
        }
        auto index = std::uint32_t(slots_.size());
        assert(index < NO_INDEX && "out of entity indices");
        Entity e = make_entity(index, 1);              // generations start at 1: Entity::null is never alive
        slots_.push_back(e);
        return e;
    }

    void destroy(Entity e)
    {
        assert(alive(e));
        std::uint32_t index = index_of(e);
        std::uint32_t generation = (generation_of(e) + 1) & GENERATION_MASK;
        if (generation == 0) generation = 1;           // skip 0 on wrap
        slots_[index] = make_entity(free_head_, generation);
        free_head_ = index;
    }

    bool alive(Entity e) const
    {
        std::uint32_t index = index_of(e);
        return e != Entity::null && index < slots_.size() && slots_[index] == e;
    }

    std::size_t capacity() const { return slots_.size(); }

private:
    std::vector<Entity> slots_;
    std::uint32_t free_head_ = NO_INDEX;
};
```

- `enum class Entity` is a distinct type: it does not convert to or from `int`, so an entity cannot be passed where an index or a count is expected. `Entity::null` is value 0.
- 24 bits of index and 8 of generation, as on the [handle table](../../data-structures/handle-table.md#packing-the-handle) page. More entities need a 64-bit id (32 + 32).
- The free list is threaded through `slots_` itself: a free slot stores the next free index in its index bits, and the generation the slot will have when reused. `alive` is one comparison, because a free slot can never equal a live id.

## Component type ids

Each component type needs a small integer, to index arrays of pools and bits in masks.

```cpp
using ComponentId = std::uint32_t;

inline ComponentId next_component_id()
{
    static std::atomic<ComponentId> next{ 0 };
    return next.fetch_add(1, std::memory_order_relaxed);
}

template <class T>
ComponentId component_id()
{
    static const ComponentId id = next_component_id();     // assigned on first use, once per T
    return id;
}
```

- A function-local `static` in a template is initialised once per `T`, thread-safely, on first call. Ids are dense (0, 1, 2…), so they index arrays directly.
- The id **depends on the order** types are first used, so it differs between runs that touch components in a different order. Never save it to disk or send it over the network; save a stable name or hash instead.
- **Across DLLs**, each module gets its own copy of the template's static, and so its own ids. If plugins add components, register every component type in the main module at start-up (giving out ids there), or key components by a hash of the type name:

```cpp
constexpr std::uint64_t fnv1a(std::string_view s)
{
    std::uint64_t h = 14695981039346656037ull;
    for (char c : s) { h ^= std::uint8_t(c); h *= 1099511628211ull; }
    return h;
}

template <class T>
constexpr std::uint64_t type_hash()
{
    // The function name contains T, e.g. "constexpr uint64_t type_hash() [with T = Position]".
    return fnv1a(std::source_location::current().function_name());
}
```

`std::source_location::current().function_name()` includes the template argument, and the string is the same everywhere for one compiler, so the hash is stable across modules. It is not the same between compilers, and the exact text is implementation-defined, so use it for run-time lookup, not as a file format. Ship a table of explicit names for save files.

## Component masks

One bit per component type, as on the [entities](entities.md#component-masks) page and the [bitsets](../../data-structures/bits.md#component-masks) section of the bit manipulation page.

```cpp
constexpr std::size_t MAX_COMPONENTS = 256;

struct ComponentMask {
    std::array<std::uint64_t, MAX_COMPONENTS / 64> words{};

    void set(ComponentId id)        { words[id >> 6] |=  (std::uint64_t(1) << (id & 63)); }
    void reset(ComponentId id)      { words[id >> 6] &= ~(std::uint64_t(1) << (id & 63)); }
    bool test(ComponentId id) const { return (words[id >> 6] >> (id & 63)) & 1; }

    bool contains_all(const ComponentMask& required) const
    {
        for (std::size_t i = 0; i < words.size(); i++)
            if ((words[i] & required.words[i]) != required.words[i]) return false;
        return true;
    }

    bool intersects(const ComponentMask& other) const
    {
        for (std::size_t i = 0; i < words.size(); i++)
            if (words[i] & other.words[i]) return true;
        return false;
    }

    template <class F>
    void for_each(F&& f) const                         // calls f(id) for every set bit
    {
        for (std::size_t i = 0; i < words.size(); i++) {
            std::uint64_t w = words[i];
            while (w) {
                f(ComponentId(i * 64 + std::countr_zero(w)));
                w &= w - 1;
            }
        }
    }

    bool operator==(const ComponentMask&) const = default;
};

struct ComponentMaskHash {
    std::size_t operator()(const ComponentMask& m) const
    {
        std::uint64_t h = 14695981039346656037ull;
        for (std::uint64_t w : m.words) { h ^= w; h *= 1099511628211ull; }
        return std::size_t(h);
    }
};

template <class... Ts>
ComponentMask mask_of()
{
    ComponentMask m;
    (m.set(component_id<Ts>()), ...);
    return m;
}

inline bool matches(const ComponentMask& entity, const ComponentMask& with, const ComponentMask& without)
{
    return entity.contains_all(with) && !entity.intersects(without);
}
```

- **Fixed size.** `MAX_COMPONENTS` is a compile-time limit (256 here: four 64-bit words). Most games have tens to low hundreds of component types. A fixed array makes masks plain values: copyable, comparable, hashable, and stored inline in other structures with no allocation.
- **`std::bitset<N>`** works too, and has `set`, `reset`, `test`, `&`, and `|`. It does not expose its words, so "contains all" becomes `(a & b) == b`, which builds a temporary, and visiting set bits needs `_Find_first` and `_Find_next` (a GCC extension) or a loop over every bit. The hand-written version above uses `std::countr_zero` to jump straight to each set bit.
- **`contains_all` and `intersects`** are a query's whole test: `matches(entity_mask, with, without)`. Build the `with` and `without` masks once when the query is created, not per entity.
- **`for_each`** visits only the set bits, which is how `World::destroy` (below) finds the pools an entity is in without checking every pool.
- **Archetypes** use the mask as their identity: `ComponentMaskHash` lets an `std::unordered_map<ComponentMask, Archetype>` find the archetype for a set of components.

## Sparse-set pools

```cpp
class PoolBase {
public:
    virtual ~PoolBase() = default;
    virtual void remove(Entity e) = 0;
    virtual bool contains(Entity e) const = 0;
    virtual void emplace_bytes(Entity e, const void* bytes) = 0;    // for command buffers
    std::span<const Entity> entities() const { return dense_; }
    std::size_t size() const { return dense_.size(); }

protected:
    static constexpr std::uint32_t ABSENT = ~0u;
    std::vector<std::uint32_t> sparse_;                 // entity index -> position in dense_
    std::vector<Entity> dense_;                         // packed entities

    std::uint32_t position_of(Entity e) const
    {
        std::uint32_t i = index_of(e);
        if (i >= sparse_.size()) return ABSENT;
        std::uint32_t p = sparse_[i];
        return (p != ABSENT && dense_[p] == e) ? p : ABSENT;
    }
};

template <class T>
class Pool final : public PoolBase {
public:
    template <class... Args>
    T& emplace(Entity e, Args&&... args)
    {
        assert(!contains(e));
        std::uint32_t i = index_of(e);
        if (i >= sparse_.size()) sparse_.resize(i + 1, ABSENT);
        sparse_[i] = std::uint32_t(dense_.size());
        dense_.push_back(e);
        return values_.emplace_back(std::forward<Args>(args)...);
    }

    void remove(Entity e) override
    {
        std::uint32_t p = position_of(e);
        if (p == ABSENT) return;
        std::uint32_t last = std::uint32_t(dense_.size() - 1);
        if (p != last) {                                // swap the last element into the hole
            dense_[p] = dense_[last];
            values_[p] = std::move(values_[last]);
            sparse_[index_of(dense_[p])] = p;
        }
        dense_.pop_back();
        values_.pop_back();
        sparse_[index_of(e)] = ABSENT;
    }

    bool contains(Entity e) const override { return position_of(e) != ABSENT; }

    T* try_get(Entity e)
    {
        std::uint32_t p = position_of(e);
        return p == ABSENT ? nullptr : &values_[p];
    }

    T& get(Entity e) { return values_[position_of(e)]; }    // caller guarantees contains(e)

    std::span<T> values() { return values_; }

    void emplace_bytes(Entity e, const void* bytes) override
    {
        if constexpr (std::is_trivially_copyable_v<T> && std::is_default_constructible_v<T>) {
            T value;
            std::memcpy(&value, bytes, sizeof(T));      // memcpy: the bytes may be unaligned
            emplace(e, value);
        } else {
            assert(false && "only trivially copyable components go through byte command buffers");
        }
    }

private:
    std::vector<T> values_;                             // parallel to dense_
};
```

- `PoolBase` holds everything that does not depend on `T` (the sparse and dense arrays, the entity list), so the world can call `remove` and `contains` on any pool through a base pointer. Only `values_` is typed.
- `remove` moves the last element into the hole, and updates the moved entity's `sparse_` entry. Every reference into `values()` and every `T&` from `get` may now point at a different entity's component.
- `sparse_` grows to the highest entity index that has the component. With hundreds of thousands of entities and a component only a few have, that wastes memory: page it (an array of 4,096-entry pages, allocated on first use), as EnTT does.
- `emplace_bytes` lets a [command buffer](#command-buffer) add a component it only knows as bytes and an id.

## The world

```cpp
class World {
public:
    Entity create()
    {
        Entity e = entities_.create();
        std::uint32_t i = index_of(e);
        if (i >= masks_.size()) masks_.resize(i + 1);
        masks_[i] = {};
        return e;
    }

    void destroy(Entity e)
    {
        if (!entities_.alive(e)) return;
        masks_[index_of(e)].for_each([&](ComponentId id) { pools_[id]->remove(e); });
        masks_[index_of(e)] = {};
        entities_.destroy(e);
    }

    bool alive(Entity e) const { return entities_.alive(e); }

    template <class T, class... Args>
    T& add(Entity e, Args&&... args)
    {
        assert(alive(e));
        masks_[index_of(e)].set(component_id<T>());
        return pool<T>().emplace(e, std::forward<Args>(args)...);
    }

    template <class T>
    void remove(Entity e)
    {
        masks_[index_of(e)].reset(component_id<T>());
        pool<T>().remove(e);
    }

    template <class... Ts>
    bool has(Entity e) const
    {
        return alive(e) && masks_[index_of(e)].contains_all(mask_of<Ts...>());
    }

    template <class T>
    T* try_get(Entity e) { return alive(e) ? pool<T>().try_get(e) : nullptr; }

    template <class T>
    Pool<T>& pool()
    {
        ComponentId id = component_id<T>();
        assert(id < MAX_COMPONENTS);
        if (id >= pools_.size()) pools_.resize(id + 1);
        if (!pools_[id]) pools_[id] = std::make_unique<Pool<T>>();
        return static_cast<Pool<T>&>(*pools_[id]);
    }

    PoolBase* pool_by_id(ComponentId id) { return id < pools_.size() ? pools_[id].get() : nullptr; }

    void add_bytes(Entity e, ComponentId id, const void* bytes)
    {
        masks_[index_of(e)].set(id);
        pools_[id]->emplace_bytes(e, bytes);
    }

    template <class... Ts>
    auto view();

private:
    EntityRegistry entities_;
    std::vector<std::unique_ptr<PoolBase>> pools_;      // indexed by ComponentId
    std::vector<ComponentMask> masks_;                  // indexed by entity index
};
```

- `add` sets the mask bit and emplaces into the pool; `remove` clears and removes; `destroy` walks the mask's bits and removes from exactly those pools.
- `has<Position, Velocity>(e)` is one `contains_all` on the entity's mask, rather than a lookup in each pool.
- `pool<T>()` creates pools on first use. Calling it from several threads at once is a data race on `pools_`: create every pool at start-up (registering each component type) if systems run in parallel.

## Views

```cpp
template <class... Ts>
class View {
public:
    explicit View(Pool<Ts>&... pools) : pools_(&pools...) {}

    template <class F>
    void each(F&& f)
    {
        // Lead with the smallest pool: it bounds the number of candidates.
        const PoolBase* lead = nullptr;
        std::apply([&](auto*... p) { ((lead = (!lead || p->size() < lead->size()) ? p : lead), ...); }, pools_);

        for (Entity e : lead->entities()) {
            bool all = std::apply([&](auto*... p) { return (p->contains(e) && ...); }, pools_);
            if (all)
                std::apply([&](auto*... p) { f(e, p->get(e)...); }, pools_);
        }
    }

private:
    std::tuple<Pool<Ts>*...> pools_;
};

template <class... Ts>
auto World::view() { return View<Ts...>(pool<Ts>()...); }
```

```cpp
world.view<Position, Velocity>().each([&](Entity e, Position& p, Velocity& v) {
    p.x += v.x * dt;
    p.y += v.y * dt;
});
```

- The view walks the **smallest** pool's entities and checks the others, as described under [views](sparse-set-storage.md#views). The fold expressions `(p->contains(e) && ...)` and `f(e, p->get(e)...)` expand once per component type at compile time, so there is no loop over pools at run time.
- **Do not add or remove components or destroy entities inside `each`.** The lead pool's `entities()` span is invalidated by any change to that pool. Record changes in a command buffer and play it back after the loop.
- `get` is called after `contains`, so it does the sparse lookup twice. A production version has each pool return a pointer from one lookup (`try_get`), and skips the check for the lead pool, which contains every entity it yields.

## Archetype columns

An archetype table stores each component type as a column of raw bytes, because one archetype class must hold any set of types. Each column needs to know how to move and destroy its elements:

```cpp
struct ComponentInfo {
    std::size_t size;
    std::size_t align;
    void (*move_construct)(void* dst, void* src);       // construct at dst from src, leaving src destructible
    void (*destroy)(void* p);
    bool trivial;                                       // trivially copyable: memcpy and no destructor
};

template <class T>
const ComponentInfo& info_of()
{
    static const ComponentInfo info{
        sizeof(T),
        alignof(T),
        [](void* dst, void* src) { ::new (dst) T(std::move(*static_cast<T*>(src))); },
        [](void* p) { static_cast<T*>(p)->~T(); },
        std::is_trivially_copyable_v<T>,
    };
    return info;
}
```

```cpp
class Column {
public:
    explicit Column(const ComponentInfo& info) : info_(&info) {}
    Column(const Column&) = delete;
    Column& operator=(const Column&) = delete;
    ~Column()
    {
        clear();
        ::operator delete(data_, std::align_val_t(info_->align));
    }

    void* at(std::size_t row) { return data_ + row * info_->size; }   // sizeof is a multiple of alignof
    std::size_t size() const { return count_; }

    template <class T> T* as() { return std::launder(reinterpret_cast<T*>(data_)); }

    // Move-construct a new last row from src (which the caller then destroys or drops).
    void push_from(void* src)
    {
        if (count_ == capacity_) grow();
        relocate(at(count_), src);
        ++count_;
    }

    // Remove a row by moving the last row into it.
    void swap_remove(std::size_t row)
    {
        std::size_t last = count_ - 1;
        info_->destroy(at(row));
        if (row != last) {
            relocate(at(row), at(last));
            info_->destroy(at(last));
        }
        --count_;
    }

    void clear()
    {
        if (!info_->trivial)
            for (std::size_t i = 0; i < count_; i++) info_->destroy(at(i));
        count_ = 0;
    }

private:
    void relocate(void* dst, void* src)
    {
        if (info_->trivial) std::memcpy(dst, src, info_->size);
        else info_->move_construct(dst, src);
    }

    void grow()
    {
        std::size_t new_capacity = capacity_ ? capacity_ * 2 : 16;
        auto* fresh = static_cast<std::byte*>(
            ::operator new(new_capacity * info_->size, std::align_val_t(info_->align)));
        for (std::size_t i = 0; i < count_; i++) {
            relocate(fresh + i * info_->size, at(i));
            info_->destroy(at(i));
        }
        ::operator delete(data_, std::align_val_t(info_->align));
        data_ = fresh;
        capacity_ = new_capacity;
    }

    const ComponentInfo* info_;
    std::byte* data_ = nullptr;
    std::size_t count_ = 0;
    std::size_t capacity_ = 0;
};
```

- **Trivially copyable** components (plain data, the common case) are moved with `memcpy` and never destroyed: the `trivial` flag skips the function pointers.
- **Non-trivial** components (holding a `std::vector` or `std::string`) are move-constructed into their new place and the old object destroyed, so they work too, at the cost of an indirect call per move.
- **Alignment**: `operator new` with `std::align_val_t` gives storage aligned for the type. `sizeof(T)` is always a multiple of `alignof(T)`, so every element at `row * size` is aligned.
- `as<T>()` reinterprets the buffer as a `T*` for iteration. `std::launder` tells the compiler the objects were created in that storage by placement new.

Iterating archetypes that match a query fetches each column pointer once per archetype, so the inner loop is plain array access:

```cpp
struct Archetype {
    ComponentMask mask;
    std::vector<ComponentId> types;                     // sorted ids, same order as columns
    std::vector<std::unique_ptr<Column>> columns;
    std::vector<Entity> entities;

    int column_index(ComponentId id) const              // -1 if absent
    {
        for (std::size_t i = 0; i < types.size(); i++)
            if (types[i] == id) return int(i);
        return -1;
    }

    template <class T> T* column() { return columns[column_index(component_id<T>())]->template as<T>(); }
    std::size_t size() const { return entities.size(); }
};

// Archetypes are found by their mask.
using ArchetypeMap = std::unordered_map<ComponentMask, std::unique_ptr<Archetype>, ComponentMaskHash>;

template <class... Ts, class F>
void for_each(std::vector<Archetype*>& matching, F&& f)
{
    for (Archetype* a : matching) {
        std::size_t n = a->size();
        if (n == 0) continue;
        auto columns = std::make_tuple(a->template column<Ts>()...);    // fetched once per archetype
        for (std::size_t row = 0; row < n; row++)
            f(std::get<Ts*>(columns)[row]...);
    }
}
```

```cpp
// matching: the query's cached list of archetypes whose masks match (see queries on the archetype page)
for_each<Position, Velocity>(matching, [&](Position& p, Velocity& v) { p.x += v.x * dt; });
```

Moving an entity between archetypes (adding or removing a component) is `push_from` on each column of the destination for the types both share, then `swap_remove` on the source row, in the order the [archetype page](archetype-storage.md#adding-and-removing-a-component) describes.

## Command buffer

Changes recorded during iteration and applied at a sync point, as a flat byte buffer rather than a list of `std::function` (which allocates per command):

```cpp
class CommandBuffer {
public:
    void destroy(Entity e) { write(Header{ Op::Destroy, 0, e, 0 }); }

    template <class T>
    void add(Entity e, const T& value)
    {
        static_assert(std::is_trivially_copyable_v<T>, "byte commands need trivially copyable components");
        write(Header{ Op::Add, component_id<T>(), e, std::uint32_t(sizeof(T)) });
        append(&value, sizeof(T));
    }

    template <class T>
    void remove(Entity e) { write(Header{ Op::Remove, component_id<T>(), e, 0 }); }

    void playback(World& world)
    {
        std::size_t pos = 0;
        while (pos < bytes_.size()) {
            Header h;
            std::memcpy(&h, bytes_.data() + pos, sizeof(h));       // memcpy: no alignment assumptions
            pos += sizeof(h);
            const std::byte* payload = bytes_.data() + pos;
            pos += h.size;

            if (!world.alive(h.entity)) continue;                    // destroyed earlier: skip
            switch (h.op) {
            case Op::Destroy: world.destroy(h.entity); break;
            case Op::Add:     world.add_bytes(h.entity, h.component, payload); break;
            case Op::Remove:
                if (PoolBase* p = world.pool_by_id(h.component)) p->remove(h.entity);
                break;
            }
        }
        bytes_.clear();                                              // keeps capacity
    }

private:
    enum class Op : std::uint8_t { Destroy, Add, Remove };
    struct Header { Op op; ComponentId component; Entity entity; std::uint32_t size; };

    void write(const Header& h) { append(&h, sizeof(h)); }
    void append(const void* p, std::size_t n)
    {
        auto* b = static_cast<const std::byte*>(p);
        bytes_.insert(bytes_.end(), b, b + n);
    }

    std::vector<std::byte> bytes_;
};
```

- Each command is a fixed header followed by the component's bytes. Reading uses `memcpy` into a local, because headers and payloads are packed back to back and are not aligned.
- Only **trivially copyable** components can go through bytes (enforced by `static_assert`). Others need a typed command list per component type, or a `std::vector<std::function<void(World&)>>` for rare cases.
- Playback **skips commands for dead entities**, so a destroy followed by an add for the same entity does not resurrect a reused index.
- Give each worker thread its own buffer, and play them back in a fixed order (by thread index), as described under [deferred commands](../patterns/frame.md#deferred-commands).
