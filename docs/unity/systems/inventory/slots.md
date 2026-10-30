---
engine: Unity
version: 6+
uses:
  - name: Shooters
    text: A hotbar that selects weapons with number keys.
  - name: Top-down survival
    text: Quick slots for consumables and tools.
---

# Slots and hotbar

A fixed array. Empty holes stay empty. `TryAdd` still merges fungible stacks, then uses the lowest free index, so a new pickup lands in the hotbar when those slots are free. `TrySwap`, `TryMerge`, and `TrySplit` are the player moves between two indices.

The hotbar is the first **Size** slots. Digit 1 selects slot 0. The wheel moves the selection when **Select On Scroll** is on. Copy one input listing. They are the same class.

When the hotbar order matches [`WeaponHolder.Weapons`](../../combat/weapons.md#holder), the bridge calls `Equip` with that index. The holder still owns firing. A binding list is for a bar whose order is not the holder's array. Leave the list empty to use the index.

The item types are on the [overview](index.md). The bag behind the bar can be this component, or a [list](list.md) you merge into by hand. Drag and drop is [still the UI topic](../../../roadmap.md#interface).

## Setup

1. Add `SlotInventory`. **Slot Count** is every cell, including the hotbar. Put starting gear on a slot index. A negative slot falls through to `TryAdd`.
2. Add `Hotbar` on the same actor. Assign the inventory. **Size** is how many of those slots the keys reach. It should be less than or equal to the slot count.
3. Copy the Input System `Hotbar` or the legacy one, not both. Active Input Handling has to include that backend.
4. Turn **Select On Scroll** off when the [orbit camera](../../cameras/third-person.md) already uses the wheel to zoom.
5. Add `HotbarWeaponBridge` only if this bar should draw the guns. Assign the holder from the weapons page. Leave **Bindings** empty when slot `i` is weapon `i`.
6. Add `HotbarLabel` to a uGUI `Text` if you want the selection on screen. Assign the hotbar and the same slot inventory, so a merge refreshes the name.

## Parameters

| Field | Default | Effect |
| --- | --- | --- |
| Slot Count | `24` | Fixed cells. At least 1. Read when the component awakes. |
| Size | `8` | How many leading slots the keys and the wheel select. |
| Select On Scroll | On | Wheel changes the selection. Off leaves the wheel to the camera. |
| Bindings | Empty | Item to holder index. Empty means the slot index is the holder index. |

## Scripts

Each block is its own file. The two hotbar listings both declare `Hotbar`.

### Slots

```csharp
using System;
using UnityEngine;

/// <summary>
/// Fixed slots. Holes are not closed up.
/// </summary>
[DisallowMultipleComponent]
public class SlotInventory : MonoBehaviour, IInventory
{
    [Serializable]
    public struct StartingStack
    {
        public int slot;
        public ItemDefinition definition;
        public int count;
    }

    [SerializeField] int slotCount = 24;
    [SerializeField] StartingStack[] starting = Array.Empty<StartingStack>();

    ItemInstance[] _slots = Array.Empty<ItemInstance>();
    bool _seeded;

    public event Action Changed;

    public int SlotCount => _slots.Length;

    void Awake()
    {
        _slots = new ItemInstance[Mathf.Max(1, slotCount)];
    }

    void Start()
    {
        if (_seeded || starting == null)
            return;
        _seeded = true;

        for (int i = 0; i < starting.Length; i++)
        {
            ItemDefinition definition = starting[i].definition;
            if (definition == null || starting[i].count <= 0)
                continue;

            ItemInstance created = ItemInstance.Create(definition, starting[i].count);
            int slot = starting[i].slot;
            if (created != null && created.Count == starting[i].count && Valid(slot) && _slots[slot] == null)
            {
                TryPlace(slot, created);
                continue;
            }

            ItemStack remainder;
            if (!TryAdd(new ItemStack(definition, starting[i].count), out remainder))
                Debug.LogWarning("Starting stack did not fit: " + definition.DisplayName, this);
        }
    }

    public ItemInstance Get(int index)
    {
        if (!Valid(index))
            return null;
        return _slots[index];
    }

    public bool TryPlace(int index, ItemInstance item)
    {
        if (!Valid(index) || item == null || item.Definition == null)
            return false;
        if (_slots[index] != null || ContainsInstance(item))
            return false;

        _slots[index] = item;
        Changed?.Invoke();
        return true;
    }

    public bool TrySwap(int a, int b)
    {
        if (!Valid(a) || !Valid(b))
            return false;
        if (a == b)
            return true;

        ItemInstance swap = _slots[a];
        _slots[a] = _slots[b];
        _slots[b] = swap;
        Changed?.Invoke();
        return true;
    }

    public bool TryMerge(int from, int into)
    {
        if (!Valid(from) || !Valid(into) || from == into)
            return false;

        ItemInstance source = _slots[from];
        if (source == null)
            return false;

        ItemInstance destination = _slots[into];
        if (destination == null)
        {
            _slots[into] = source;
            _slots[from] = null;
            Changed?.Invoke();
            return true;
        }

        if (!destination.CanMergeWith(source))
            return false;

        int moved = destination.Absorb(source.Count);
        if (moved <= 0)
            return false;

        source.Reduce(moved);
        if (source.Count <= 0)
            _slots[from] = null;
        Changed?.Invoke();
        return true;
    }

    public bool TrySplit(int from, int into, int amount)
    {
        if (!Valid(from) || !Valid(into) || from == into)
            return false;
        if (_slots[from] == null || _slots[into] != null)
            return false;

        ItemInstance split = _slots[from].Split(amount);
        if (split == null)
            return false;

        _slots[into] = split;
        Changed?.Invoke();
        return true;
    }

    public int Count(ItemDefinition definition)
    {
        if (definition == null)
            return 0;

        int total = 0;
        for (int i = 0; i < _slots.Length; i++)
        {
            if (_slots[i] != null && _slots[i].Definition == definition)
                total += _slots[i].Count;
        }

        return total;
    }

    public bool Contains(ItemDefinition definition, int count = 1)
    {
        if (count <= 0)
            return true;
        return Count(definition) >= count;
    }

    public bool ContainsInstance(ItemInstance instance)
    {
        if (instance == null)
            return false;
        for (int i = 0; i < _slots.Length; i++)
        {
            if (_slots[i] == instance)
                return true;
        }

        return false;
    }

    public bool CanAccept(ItemStack stack)
    {
        Ensure();
        if (!ItemStack.TryRead(stack, out ItemDefinition definition, out int count, out ItemInstance instance))
            return false;
        if (instance != null && ContainsInstance(instance))
            return true;
        if (instance != null)
        {
            int left = instance.Count;
            if (definition.MaxDurability <= 0f)
                left -= Mathf.Min(left, MergeRoom(definition, instance));
            if (left <= 0)
                return true;
            return EmptySlots() >= 1 && left <= definition.MaxStack;
        }

        if (definition.MaxDurability > 0f)
            return EmptySlots() >= count;
        return MergeRoom(definition, null) + EmptySlots() * definition.MaxStack >= count;
    }

    public bool TryAdd(ItemStack stack, out ItemStack remainder)
    {
        Ensure();
        remainder = default;
        if (!ItemStack.TryRead(stack, out ItemDefinition definition, out int count, out ItemInstance instance))
        {
            remainder = stack;
            return false;
        }

        if (instance != null && ContainsInstance(instance))
            return true;
        if (definition.MaxDurability > 0f)
            return AddDurable(definition, count, instance, out remainder);
        return AddFungible(definition, count, instance, out remainder);
    }

    public bool TryRemove(ItemDefinition definition, int count, out ItemStack removed)
    {
        removed = default;
        if (definition == null || count <= 0 || definition.MaxDurability > 0f)
            return false;
        if (Count(definition) < count)
            return false;

        int left = count;
        for (int i = _slots.Length - 1; i >= 0 && left > 0; i--)
        {
            ItemInstance item = _slots[i];
            if (item == null || item.Definition != definition)
                continue;
            left -= item.Reduce(left);
            if (item.Count <= 0)
                _slots[i] = null;
        }

        removed = new ItemStack(definition, count);
        Changed?.Invoke();
        return true;
    }

    public bool TryRemoveInstance(ItemInstance instance)
    {
        if (instance == null)
            return false;
        for (int i = 0; i < _slots.Length; i++)
        {
            if (_slots[i] != instance)
                continue;
            _slots[i] = null;
            Changed?.Invoke();
            return true;
        }

        return false;
    }

    bool AddFungible(ItemDefinition definition, int count, ItemInstance instance, out ItemStack remainder)
    {
        remainder = default;
        int left = count;
        bool changed = false;

        for (int i = 0; i < _slots.Length && left > 0; i++)
        {
            ItemInstance other = _slots[i];
            if (other == null || other == instance || !other.CanMergeWith(definition))
                continue;
            int taken = other.Absorb(left);
            if (taken <= 0)
                continue;
            if (instance != null)
                instance.Reduce(taken);
            left -= taken;
            changed = true;
        }

        if (left > 0 && instance != null)
        {
            int hole = FirstEmpty();
            if (hole >= 0 && instance.Count > 0 && instance.Count <= definition.MaxStack)
            {
                _slots[hole] = instance;
                left = 0;
                changed = true;
            }
        }
        else if (instance == null)
        {
            while (left > 0)
            {
                int hole = FirstEmpty();
                if (hole < 0)
                    break;
                ItemInstance created = ItemInstance.Create(definition, left);
                if (created == null)
                    break;
                _slots[hole] = created;
                left -= created.Count;
                changed = true;
            }
        }

        if (changed)
            Changed?.Invoke();
        if (left <= 0)
            return true;

        remainder = instance != null && instance.Count > 0
            ? new ItemStack(instance)
            : new ItemStack(definition, left);
        return false;
    }

    bool AddDurable(ItemDefinition definition, int count, ItemInstance instance, out ItemStack remainder)
    {
        remainder = default;
        if (instance != null)
        {
            int hole = FirstEmpty();
            if (hole < 0)
            {
                remainder = new ItemStack(instance);
                return false;
            }

            _slots[hole] = instance;
            Changed?.Invoke();
            return true;
        }

        int placed = 0;
        while (placed < count)
        {
            int hole = FirstEmpty();
            if (hole < 0)
                break;
            ItemInstance created = ItemInstance.Create(definition, 1);
            if (created == null)
                break;
            _slots[hole] = created;
            placed++;
        }

        if (placed > 0)
            Changed?.Invoke();
        if (placed == count)
            return true;

        remainder = new ItemStack(definition, count - placed);
        return false;
    }

    int MergeRoom(ItemDefinition definition, ItemInstance ignore)
    {
        if (definition == null || definition.MaxDurability > 0f)
            return 0;

        int room = 0;
        for (int i = 0; i < _slots.Length; i++)
        {
            ItemInstance other = _slots[i];
            if (other == null || other == ignore || !other.CanMergeWith(definition))
                continue;
            room += other.Room;
        }

        return room;
    }

    int EmptySlots()
    {
        int empty = 0;
        for (int i = 0; i < _slots.Length; i++)
        {
            if (_slots[i] == null)
                empty++;
        }

        return empty;
    }

    int FirstEmpty()
    {
        for (int i = 0; i < _slots.Length; i++)
        {
            if (_slots[i] == null)
                return i;
        }

        return -1;
    }

    bool Valid(int index)
    {
        return index >= 0 && index < _slots.Length;
    }

    void Ensure()
    {
        if (_slots == null || _slots.Length == 0)
            _slots = new ItemInstance[Mathf.Max(1, slotCount)];
    }

    void OnValidate()
    {
        if (slotCount < 1)
            slotCount = 1;
    }
}
```

### Hotbar

The wheel value is this frame's notch. Do not multiply it by `Time.deltaTime`.

=== "Input System"

    ```csharp
    using System;
    using UnityEngine;
    using UnityEngine.InputSystem;

    /// <summary>
    /// Selects the first slots of a SlotInventory.
    /// </summary>
    /// <remarks>
    /// Input System, the default backend in a new Unity 6 project.
    /// Requires the Input System package, and Active Input Handling set to
    /// "Input System Package (New)" or "Both". Digit 1 is slot 0.
    /// </remarks>
    [DisallowMultipleComponent]
    public class Hotbar : MonoBehaviour
    {
        static readonly Key[] NumberKeys =
        {
            Key.Digit1,
            Key.Digit2,
            Key.Digit3,
            Key.Digit4,
            Key.Digit5,
            Key.Digit6,
            Key.Digit7,
            Key.Digit8,
            Key.Digit9
        };

        [SerializeField] SlotInventory inventory;
        [SerializeField] int size = 8;

        [Tooltip("Turn off when an orbit camera already uses the scroll wheel to zoom.")]
        [SerializeField] bool selectOnScroll = true;

        int _selected;

        public event Action<int> SelectionChanged;

        public int Selected => _selected;

        public ItemInstance SelectedItem => inventory != null ? inventory.Get(_selected) : null;

        void Update()
        {
            if (inventory == null || size <= 0)
                return;

            ReadInput(out float scroll, out int number);
            if (number >= 0 && number < size)
                Select(number);
            else if (selectOnScroll && scroll > 0f)
                Select(Wrap(_selected + 1));
            else if (selectOnScroll && scroll < 0f)
                Select(Wrap(_selected - 1));
        }

        public void Select(int index)
        {
            int max = Mathf.Max(0, size - 1);
            int next = Mathf.Clamp(index, 0, max);
            if (next == _selected)
                return;
            _selected = next;
            SelectionChanged?.Invoke(_selected);
        }

        int Wrap(int index)
        {
            if (size <= 0)
                return 0;
            int wrapped = index % size;
            if (wrapped < 0)
                wrapped += size;
            return wrapped;
        }

        void ReadInput(out float scroll, out int number)
        {
            scroll = 0f;
            number = -1;

            Keyboard keyboard = Keyboard.current;
            if (keyboard != null)
            {
                for (int i = 0; i < NumberKeys.Length; i++)
                {
                    if (keyboard[NumberKeys[i]].wasPressedThisFrame)
                        number = i;
                }
            }

            Mouse mouse = Mouse.current;
            if (mouse != null)
            {
                float wheel = mouse.scroll.ReadValue().y;
                if (wheel > 0.01f)
                    scroll = 1f;
                else if (wheel < -0.01f)
                    scroll = -1f;
            }
        }

        void OnValidate()
        {
            if (size < 1)
                size = 1;
        }
    }
    ```

=== "Legacy Input Manager"

    `GetAxis("Mouse ScrollWheel")` is the default wheel axis, already this frame's notch. There is no gamepad on this listing.

    ```csharp
    using System;
    using UnityEngine;

    /// <summary>
    /// Selects the first slots of a SlotInventory.
    /// </summary>
    /// <remarks>
    /// Legacy Input Manager. Active Input Handling must be
    /// "Input Manager (Old)" or "Both". Digit 1 is slot 0.
    /// The wheel uses the default Mouse ScrollWheel axis.
    /// </remarks>
    [DisallowMultipleComponent]
    public class Hotbar : MonoBehaviour
    {
        [SerializeField] SlotInventory inventory;
        [SerializeField] int size = 8;

        [Tooltip("Turn off when an orbit camera already uses the scroll wheel to zoom.")]
        [SerializeField] bool selectOnScroll = true;

        int _selected;

        public event Action<int> SelectionChanged;

        public int Selected => _selected;

        public ItemInstance SelectedItem => inventory != null ? inventory.Get(_selected) : null;

        void Update()
        {
            if (inventory == null || size <= 0)
                return;

            ReadInput(out float scroll, out int number);
            if (number >= 0 && number < size)
                Select(number);
            else if (selectOnScroll && scroll > 0f)
                Select(Wrap(_selected + 1));
            else if (selectOnScroll && scroll < 0f)
                Select(Wrap(_selected - 1));
        }

        public void Select(int index)
        {
            int max = Mathf.Max(0, size - 1);
            int next = Mathf.Clamp(index, 0, max);
            if (next == _selected)
                return;
            _selected = next;
            SelectionChanged?.Invoke(_selected);
        }

        int Wrap(int index)
        {
            if (size <= 0)
                return 0;
            int wrapped = index % size;
            if (wrapped < 0)
                wrapped += size;
            return wrapped;
        }

        void ReadInput(out float scroll, out int number)
        {
            scroll = 0f;
            number = -1;

            float wheel = Input.GetAxis("Mouse ScrollWheel");
            if (wheel > 0.01f)
                scroll = 1f;
            else if (wheel < -0.01f)
                scroll = -1f;

            for (int i = 0; i < 9; i++)
            {
                if (Input.GetKeyDown(KeyCode.Alpha1 + i))
                    number = i;
            }
        }

        void OnValidate()
        {
            if (size < 1)
                size = 1;
        }
    }
    ```

### Holder link

`WeaponHolder` is the class on the [weapons](../../combat/weapons.md#holder) page. Copy it before this bridge. `Equip` is idempotent when that weapon is already the current one, so a bar and a holder that share an index agree. They fight when the binding says slot 2 is holder index 0 and the holder's own digit key also runs.

```csharp
using System;
using UnityEngine;

/// <summary>
/// Hotbar selection to WeaponHolder.Equip.
/// An empty binding list uses the slot index.
/// </summary>
[DisallowMultipleComponent]
public class HotbarWeaponBridge : MonoBehaviour
{
    [Serializable]
    public struct Binding
    {
        public ItemDefinition item;
        public int holderIndex;
    }

    [SerializeField] Hotbar hotbar;
    [SerializeField] WeaponHolder holder;
    [SerializeField] Binding[] bindings = Array.Empty<Binding>();

    void OnEnable()
    {
        if (hotbar != null)
            hotbar.SelectionChanged += OnSelected;
    }

    void OnDisable()
    {
        if (hotbar != null)
            hotbar.SelectionChanged -= OnSelected;
    }

    void OnSelected(int slot)
    {
        if (holder == null || hotbar == null)
            return;

        ItemInstance selected = hotbar.SelectedItem;
        if (selected == null || selected.Definition == null)
            return;

        if (bindings != null && bindings.Length > 0)
        {
            for (int i = 0; i < bindings.Length; i++)
            {
                if (bindings[i].item == selected.Definition)
                {
                    holder.Equip(bindings[i].holderIndex);
                    return;
                }
            }

            return;
        }

        holder.Equip(slot);
    }
}
```

### Label

```csharp
using UnityEngine;
using UnityEngine.UI;

/// <summary>
/// Selected slot and the item name. No icons and no drag.
/// </summary>
[DisallowMultipleComponent]
public class HotbarLabel : MonoBehaviour
{
    [SerializeField] Hotbar hotbar;
    [SerializeField] SlotInventory inventory;
    [SerializeField] Text label;

    void OnEnable()
    {
        if (hotbar != null)
            hotbar.SelectionChanged += OnSelected;
        if (inventory != null)
            inventory.Changed += OnBag;
        Refresh();
    }

    void OnDisable()
    {
        if (hotbar != null)
            hotbar.SelectionChanged -= OnSelected;
        if (inventory != null)
            inventory.Changed -= OnBag;
    }

    void OnSelected(int slot)
    {
        Refresh();
    }

    void OnBag()
    {
        Refresh();
    }

    void Refresh()
    {
        if (label == null)
            return;
        if (hotbar == null)
        {
            label.text = string.Empty;
            return;
        }

        ItemInstance item = hotbar.SelectedItem;
        string name = item != null && item.Definition != null ? item.Definition.DisplayName : "Empty";
        label.text = (hotbar.Selected + 1) + "  " + name;
    }
}
```

!!! warning "Common pitfalls"

    Digit 1 is slot 0. A bar of 4 ignores digits 5 to 9. The [holder](../../combat/weapons.md#holder) uses the same keys as weapon indices and has no flag to ignore them. Use the same order, or the two `Equip` calls will not match.

    `Select` does not raise when the index is already selected. The label reads the current slot from `OnEnable`, so the first frame is not a blank waiting for a key.

    `TryAdd` fills the lowest hole. That hole may be hotbar slot 0. A backpack that must not eat the bar is a separate `SlotInventory`, not the same array.

    `TryMerge` into a full stack moves nothing and returns false. `TrySplit` refuses a durability item and refuses a split that would empty the source. Swap is the exchange.

    `TryMerge` into an empty slot moves the whole stack. It does not leave a ghost behind.

    Scroll selection and orbit zoom read the same wheel. Turn one of them off.

    Slot count is captured in `Awake`. Changing it during Play Mode does not resize the array. Items already in the slots stay.

    The bridge does nothing for an empty selection, and nothing when a binding list is set but the selected item is not on it. It will not guess a weapon.
