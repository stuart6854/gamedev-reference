---
engine: Unity
version: 6+
---

# Event systems

How a health pool tells a game-over screen that the player died, and how a gun tells a counter that the magazine changed, without either side polling. The [health](../systems/health.md#health) component already raises `Died`. The [weapon](../combat/weapons.md#weapon) already raises `AmmoChanged`. This page is the choice of pipe, and the rules for subscribing.

A channel asset carries a moment. A value you can read at any time is a different asset. That one is still [shared variables (`ScriptableObject`)](../../roadmap.md#architecture) on the roadmap. State machines and object pooling will join this Architecture group later.

## Which one to use

| Approach | Use it when | Do not use it when |
| --- | --- | --- |
| C# event, `event Action` or `event Action<T>` | The listener already has the component. The payload is typed. `Health.Died` and `Weapon.AmmoChanged` are this. | A designer must wire the response, or the listener should not keep that reference. |
| `UnityEvent` | The response is wired in the inspector, or on a button. One-off presentation. | The raise is on a hot path. Persistent calls go through reflection. A lambda passed to `AddListener` cannot be removed. |
| Static bus, `EventBus<T>` | Several systems share a signal and only the type connects them. The payload is a struct, so the raise does not box. | The signal belongs to one instance and the listener already holds it. A static list survives Play Mode when domain reload is off, unless you reset it. |
| ScriptableObject channel | The raiser and the listener both get the same asset. You want a **Raise** button while playing. | The signal is per instance. One asset is one listener list, shared by everyone who references it. |
| `SendMessage` and a hand-rolled observer | A hand-rolled observer is what the rows above already are. | `SendMessage`, `BroadcastMessage`, and `SendMessageUpwards` look a method up by string. A typo fails at runtime. |

`IDamageable` on the health page is the other shape: the hitter calls a method it already found. That is a direct call, not a list of listeners. Use it when there is one target. Use an event when the target does not know who is watching.

## C# events

`event` is a multicast delegate that only the declaring type can raise. Outsiders can `+=` and `-=`. They cannot clear the list or invoke it. A public `Action` field can be replaced or invoked by anyone. Prefer `event`.

The raise is synchronous and walks the invocation list in subscription order. `Died?.Invoke()` copies the current delegate and calls that. A listener that throws stops the rest of that raise. [`Health`](../systems/health.md#health) does this for `Died`, then invokes its inspector `UnityEvent` separately, so a throw on the C# event also skips the inspector hook.

The game-over screen below has the player's `Health`. It subscribes while it is enabled and shows a child panel. The panel starts inactive. The screen object stays active, or `OnEnable` never runs and the screen never hears death.

```csharp
using UnityEngine;

/// <summary>
/// Shows a panel when this player's health raises Died.
/// </summary>
[DisallowMultipleComponent]
public class GameOverScreen : MonoBehaviour
{
    [SerializeField] Health player;

    [Tooltip("Starts inactive. This object stays active so it can subscribe.")]
    [SerializeField] GameObject panel;

    void OnEnable()
    {
        if (player != null)
            player.Died += Show;
    }

    void OnDisable()
    {
        if (player != null)
            player.Died -= Show;
    }

    void Show()
    {
        if (panel != null)
            panel.SetActive(true);
    }
}
```

Ammo is the same shape with arguments. [`Weapon.AmmoChanged`](../combat/weapons.md#weapon) passes the magazine and the reserve. The counter on the weapons page is [`AmmoReadout`](../combat/weapons.md#readout-and-effects), which also rebinds when the holder swaps guns. The short form, when the counter already knows the weapon, is:

```csharp
using UnityEngine;
using UnityEngine.UI;

/// <summary>
/// Writes Weapon.AmmoChanged into a uGUI label.
/// </summary>
[DisallowMultipleComponent]
public class HudAmmoCounter : MonoBehaviour
{
    [SerializeField] Weapon weapon;
    [SerializeField] Text label;

    void OnEnable()
    {
        if (weapon == null)
            return;

        weapon.AmmoChanged += Refresh;
        Refresh(weapon.Magazine, weapon.Reserve);
    }

    void OnDisable()
    {
        if (weapon != null)
            weapon.AmmoChanged -= Refresh;
    }

    void Refresh(int magazine, int reserve)
    {
        if (label != null)
            label.text = magazine + " / " + reserve;
    }
}
```

Refresh once on enable. The weapon does not raise for the rounds it already holds unless its own `OnEnable` runs after the counter's. Reading `Magazine` and `Reserve` covers that order.

`Show` and `Refresh` are method groups. `player.Died += () => panel.SetActive(true)` allocates a closure every `OnEnable`, captures this screen, and `-=` cannot see that closure, so the health object keeps the screen alive. Do that and the pairing is theatre.

## UnityEvent

`UnityEvent` stores two lists. Persistent calls are the ones you pick in the inspector. They are serialised on the component and invoked by method name. Runtime calls are `AddListener`. Persistent calls run first.

A persistent call can carry a bool, int, float, string, or `UnityEngine.Object` that you type in the inspector. A struct or a second argument has to be a dynamic method, which receives the value from `Invoke`. `UnityEvent<T>` up to four type arguments works in Unity 6. `Health` already has `UnityEvent onDied` with no argument. `Weapon` has `UnityEvent<int, int> onAmmoChanged`. Those are the no-code hooks. They do not replace the C# events, which carry `DamageInfo` or stay easy to unsubscribe.

The cost is why they stay off the projectile path. Each persistent call looks the method up, and a `UnityEvent<T>` of a value type builds an invokable call that boxes more than `Action<T>`. A button press or a death screen can afford that. A hit scan that raises one per pellet should stay on a C# event.

`AddListener(Show)` and `RemoveListener(Show)` match, because delegate equality is the target and the method. `AddListener(() => Show())` is a new object every call, and `RemoveListener` will not find it. `RemoveAllListeners` removes runtime listeners only. Inspector wiring stays.

This component is the bridge when a designer wants a hook and the signal already exists as a C# event. `Health.onDied` is private. Subscribe to `Died`, then raise a `UnityEvent` you own.

```csharp
using UnityEngine;
using UnityEngine.Events;

/// <summary>
/// Designer hook for Health.Died. Wire Response in the inspector.
/// </summary>
[DisallowMultipleComponent]
public class DeathUnityEvent : MonoBehaviour
{
    [SerializeField] Health health;
    [SerializeField] UnityEvent response;

    void OnEnable()
    {
        if (health != null)
            health.Died += Raise;
    }

    void OnDisable()
    {
        if (health != null)
            health.Died -= Raise;
    }

    void Raise()
    {
        response?.Invoke();
    }
}
```

Wire **Response** to a method on an object that is active. Wiring it to `GameObject.SetActive(false)` on this same object unsubscribes inside the raise. A C# event finishes the list it already copied, so that is safe here. It is not the habit to copy onto a `UnityEvent`.

## Event bus

Use the bus when the screen should not hold a `Health` field. The signal is a struct. `Action<T>` then passes it without boxing. A class payload is a shared object: one listener can change a field and the next listener sees the change. A struct is a copy. A field that is itself a reference, such as `Health`, is still shared. The copy is the struct, not the component.

`where T : struct` also rejects an accidental `EventBus<object>`, which would box every raise.

The attribute that clears statics does not run on an open generic type. Unity never picks a `T`. The registry is a normal class. Each closed `EventBus<PlayerDied>` registers its own clear from the static constructor, which runs once per domain, the first time that `T` is used. The next enter-Play-Mode calls every registered clear. With domain reload left on, the domain is new anyway and the list is empty at startup. The clear matters when **Enter Play Mode Options** disables **Reload Domain**.

```csharp
using System;
using System.Collections.Generic;
using UnityEngine;

/// <summary>
/// Holds one reset per closed EventBus. The attribute is here because
/// RuntimeInitializeOnLoadMethod is ignored on a generic type.
/// </summary>
static class EventBusRegistry
{
    static readonly List<Action> Resets = new List<Action>();

    public static void Register(Action reset)
    {
        if (reset == null)
            return;

        for (int i = 0; i < Resets.Count; i++)
        {
            if (Resets[i] == reset)
                return;
        }

        Resets.Add(reset);
    }

    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
    static void ResetAll()
    {
        for (int i = 0; i < Resets.Count; i++)
            Resets[i]();
    }
}

/// <summary>
/// Static typed bus. T is a struct so Raise does not box the payload.
/// </summary>
public static class EventBus<T> where T : struct
{
    static Action<T> _listeners;
    static readonly List<T> _pending = new List<T>(8);
    static bool _raising;

    static EventBus()
    {
        EventBusRegistry.Register(Clear);
    }

    public static void Subscribe(Action<T> listener)
    {
        if (listener == null)
            return;
        _listeners += listener;
    }

    public static void Unsubscribe(Action<T> listener)
    {
        if (listener == null)
            return;
        _listeners -= listener;
    }

    public static void Raise(T payload)
    {
        if (_raising)
        {
            _pending.Add(payload);
            return;
        }

        _raising = true;
        try
        {
            Invoke(payload);
            for (int i = 0; i < _pending.Count; i++)
                Invoke(_pending[i]);
        }
        finally
        {
            _pending.Clear();
            _raising = false;
        }
    }

    public static void Clear()
    {
        _listeners = null;
        if (!_raising)
            _pending.Clear();
    }

    static void Invoke(T payload)
    {
        Action<T> listeners = _listeners;
        if (listeners != null)
            listeners.Invoke(payload);
    }
}
```

`Invoke` reads `_listeners` into a local first. `+=` and `-=` during the raise replace the field and leave that local alone, so the in-flight list is stable. A listener added during the raise runs on the next raise, not this one. A listener removed during the raise still runs if it was already on the list.

A raise from inside a listener is queued on `_pending` and runs after the current payload. The list keeps its spare capacity across raises, so a steady trickle does not allocate. A burst past eight nested signals allocates once, then the capacity stays.

One throw aborts the rest of that list and the queued payloads. The `finally` still clears the raising flag, so the next `Raise` works. Catching per listener means `GetInvocationList`, which allocates an array every raise. That belongs off the hot path:

```csharp
Delegate[] list = listeners.GetInvocationList();
for (int i = 0; i < list.Length; i++)
{
    try
    {
        ((Action<PlayerDied>)list[i]).Invoke(payload);
    }
    catch (Exception exception)
    {
        Debug.LogException(exception);
    }
}
```

The relay is what the health component does not know about. `Health` stays free of the bus, so the health scripts still compile on their own.

```csharp
using UnityEngine;

public struct PlayerDied
{
    public Health Player;
}

/// <summary>
/// Forwards Health.Died onto the bus. The screen does not reference Health.
/// </summary>
[DisallowMultipleComponent]
public class PlayerDeathRelay : MonoBehaviour
{
    [SerializeField] Health health;

    void OnEnable()
    {
        if (health != null)
            health.Died += OnDied;
    }

    void OnDisable()
    {
        if (health != null)
            health.Died -= OnDied;
    }

    void OnDied()
    {
        EventBus<PlayerDied>.Raise(new PlayerDied { Player = health });
    }
}
```

```csharp
using UnityEngine;

/// <summary>
/// Game-over panel for a PlayerDied signal. No Health field.
/// </summary>
[DisallowMultipleComponent]
public class PlayerDiedScreen : MonoBehaviour
{
    [Tooltip("Starts inactive. This object stays active so it can subscribe.")]
    [SerializeField] GameObject panel;

    void OnEnable()
    {
        EventBus<PlayerDied>.Subscribe(Show);
    }

    void OnDisable()
    {
        EventBus<PlayerDied>.Unsubscribe(Show);
    }

    void Show(PlayerDied died)
    {
        if (panel == null)
            return;
        if (died.Player != null && !died.Player.IsDead)
            return;
        panel.SetActive(true);
    }
}
```

Two players are two `PlayerDied` values. The screen uses `died.Player` if it has to tell them apart. If it only cares that the local player died, the relay should sit on that player alone. A static bus cannot filter for you.

Subscription order is call order. Script execution order only affects who subscribed first. Do not depend on it. If the HUD must update before the screen, do both from one listener.

## ScriptableObject channels

A channel is the bus stored on an asset, so a designer can assign it. Void is a signal with no payload. A typed channel is one argument. There is no `CreateAssetMenu` on an open generic, so each payload you want in the menu is a small subclass.

Listeners are not serialised. `[NonSerialized]` keeps them off the asset. With domain reload disabled the asset object is the same one next Play Mode, and that field would still hold last session's delegates. `OnEnable` and `OnDisable` on a `ScriptableObject` still run on those Play Mode transitions. Entering Play Mode runs the asset `OnEnable` before scene `OnEnable`, so the clear happens before listeners subscribe. Unity calls the `OnEnable` on the base. A subclass that declares its own `OnEnable` hides it, and the clear does not run unless that method calls `base.OnEnable()`. The channel `Raise` is a normal delegate invoke: a nested raise re-enters. It does not use the bus queue.

```csharp
using System;
using UnityEngine;

/// <summary>
/// Clears runtime listeners on Play Mode transitions, including when domain reload is off.
/// </summary>
public abstract class EventChannelBase : ScriptableObject
{
    // Protected so Unity still finds these when the asset's type is a subclass.
    // A subclass that declares its own OnEnable hides this one. Call base.OnEnable().
    protected void OnEnable()
    {
        ClearListeners();
    }

    protected void OnDisable()
    {
        ClearListeners();
    }

    protected abstract void ClearListeners();
}

public abstract class EventChannel<T> : EventChannelBase
{
    [NonSerialized] Action<T> _listeners;

    public void Subscribe(Action<T> listener)
    {
        if (listener == null)
            return;
        _listeners += listener;
    }

    public void Unsubscribe(Action<T> listener)
    {
        if (listener == null)
            return;
        _listeners -= listener;
    }

    public void Raise(T value)
    {
        Action<T> listeners = _listeners;
        if (listeners != null)
            listeners.Invoke(value);
    }

    protected override void ClearListeners()
    {
        _listeners = null;
    }
}
```

```csharp
using UnityEngine;

#if UNITY_EDITOR
using UnityEditor;
#endif

[CreateAssetMenu(fileName = "VoidEvent", menuName = "Game/Events/Void Event")]
public class VoidEventChannel : EventChannelBase
{
    [System.NonSerialized] System.Action _listeners;

    public void Subscribe(System.Action listener)
    {
        if (listener == null)
            return;
        _listeners += listener;
    }

    public void Unsubscribe(System.Action listener)
    {
        if (listener == null)
            return;
        _listeners -= listener;
    }

    public void Raise()
    {
        System.Action listeners = _listeners;
        if (listeners != null)
            listeners.Invoke();
    }

    protected override void ClearListeners()
    {
        _listeners = null;
    }
}

#if UNITY_EDITOR
[CustomEditor(typeof(VoidEventChannel))]
public class VoidEventChannelEditor : Editor
{
    public override void OnInspectorGUI()
    {
        DrawDefaultInspector();
        if (!Application.isPlaying)
        {
            EditorGUILayout.HelpBox("Enter Play Mode to raise this channel.", MessageType.Info);
            return;
        }

        if (GUILayout.Button("Raise"))
            ((VoidEventChannel)target).Raise();
    }
}
#endif
```

The editor class sits in this file under `UNITY_EDITOR`, so a player build does not reference `UnityEditor`. Split it into an Editor folder if the runtime assembly cannot see the editor. The button calls `Raise` on the same asset the listeners subscribed to. It does not `SetDirty` the asset. Outside Play Mode it does nothing useful: scene listeners are not subscribed.

Ammo is the typed channel. The payload matches `Weapon.AmmoChanged`: magazine, then reserve.

```csharp
using System;
using UnityEngine;

#if UNITY_EDITOR
using UnityEditor;
#endif

[Serializable]
public struct AmmoPayload
{
    public int magazine;
    public int reserve;
}

[CreateAssetMenu(fileName = "AmmoEvent", menuName = "Game/Events/Ammo Event")]
public class AmmoEventChannel : EventChannel<AmmoPayload>
{
}

#if UNITY_EDITOR
[CustomEditor(typeof(AmmoEventChannel))]
public class AmmoEventChannelEditor : Editor
{
    int _magazine = 30;
    int _reserve = 90;

    public override void OnInspectorGUI()
    {
        DrawDefaultInspector();
        if (!Application.isPlaying)
        {
            EditorGUILayout.HelpBox("Enter Play Mode to raise this channel.", MessageType.Info);
            return;
        }

        _magazine = EditorGUILayout.IntField("Magazine", _magazine);
        _reserve = EditorGUILayout.IntField("Reserve", _reserve);
        if (GUILayout.Button("Raise"))
        {
            ((AmmoEventChannel)target).Raise(new AmmoPayload
            {
                magazine = _magazine,
                reserve = _reserve
            });
        }
    }
}
#endif
```

The listener is a `UnityEvent` response on purpose. The designer wires the reaction. The script only subscribes. Put it on an active object. A listener on the inactive game-over panel never enables, so it never subscribes. Parent the panel under an active object and put the listener on the parent.

```csharp
using UnityEngine;
using UnityEngine.Events;

[DisallowMultipleComponent]
public class VoidEventListener : MonoBehaviour
{
    [SerializeField] VoidEventChannel channel;
    [SerializeField] UnityEvent response;

    void OnEnable()
    {
        if (channel != null)
            channel.Subscribe(OnRaised);
    }

    void OnDisable()
    {
        if (channel != null)
            channel.Unsubscribe(OnRaised);
    }

    void OnRaised()
    {
        response?.Invoke();
    }
}
```

```csharp
using UnityEngine;
using UnityEngine.Events;

[DisallowMultipleComponent]
public class AmmoEventListener : MonoBehaviour
{
    [SerializeField] AmmoEventChannel channel;
    [SerializeField] UnityEvent<AmmoPayload> response;

    void OnEnable()
    {
        if (channel != null)
            channel.Subscribe(OnRaised);
    }

    void OnDisable()
    {
        if (channel != null)
            channel.Unsubscribe(OnRaised);
    }

    void OnRaised(AmmoPayload ammo)
    {
        response?.Invoke(ammo);
    }
}
```

A persistent `UnityEvent<AmmoPayload>` call cannot type a struct into the inspector. The method has to be dynamic, `void Show(AmmoPayload ammo)`, so it receives the raised value. An `int` or a `bool` can be a constant in the inspector. That constant ignores the payload. For the HUD you want the dynamic method.

The relays keep `Health` and `Weapon` unaware of the assets.

```csharp
using UnityEngine;

[DisallowMultipleComponent]
public class HealthDeathChannel : MonoBehaviour
{
    [SerializeField] Health health;
    [SerializeField] VoidEventChannel died;

    void OnEnable()
    {
        if (health != null)
            health.Died += OnDied;
    }

    void OnDisable()
    {
        if (health != null)
            health.Died -= OnDied;
    }

    void OnDied()
    {
        if (died != null)
            died.Raise();
    }
}
```

```csharp
using UnityEngine;

[DisallowMultipleComponent]
public class WeaponAmmoChannel : MonoBehaviour
{
    [SerializeField] Weapon weapon;
    [SerializeField] AmmoEventChannel channel;

    void OnEnable()
    {
        if (weapon != null)
            weapon.AmmoChanged += OnAmmo;
    }

    void OnDisable()
    {
        if (weapon != null)
            weapon.AmmoChanged -= OnAmmo;
    }

    void OnAmmo(int magazine, int reserve)
    {
        if (channel == null)
            return;

        channel.Raise(new AmmoPayload
        {
            magazine = magazine,
            reserve = reserve
        });
    }
}
```

One void asset is one global "player died". Two characters that share it both open the same screen. Give them different assets, or use `Health.Died` / `PlayerDied.Player` when the instance matters.

### Setup

1. Create `Game/Events/Void Event` and name it Player Died. On the player, add `HealthDeathChannel` and assign `Health` and that asset.
2. On an object that stays active, add `VoidEventListener` and assign the asset. Wire **Response** to a child panel's `GameObject.SetActive` with the bool ticked. Leave the panel inactive.
3. Enter Play Mode, select the asset, and press **Raise**. The panel shows. Exit Play Mode and the button goes quiet.
4. For the counter, create `Game/Events/Ammo Event`. Add `WeaponAmmoChannel` on the weapon and `AmmoEventListener` on the HUD. Point the response at a method that takes `AmmoPayload`.
5. Prefer `GameOverScreen` or `HudAmmoCounter` when the listener already has the `Health` or the `Weapon`. The asset is the indirection, and it has a cost.

## Lifecycle

Subscribe in `OnEnable`. Unsubscribe in `OnDisable`. `Start` does not pair with anything. `OnDestroy` is late: a disabled listener is still on the list and still runs. `OnDisable` also runs when the object is destroyed, so you do not need both.

A destroyed `MonoBehaviour` compares equal to null with Unity's `==`, and it is not a C# null. `this?.gameObject` still throws. A delegate on a static bus still points at that object. The next raise calls into it. If the method touches a native object, Unity throws a missing-reference exception. `if (this == null) return;` at the top of the handler is a backstop. It uses the overloaded `==`. It is not a substitute for `-=`.

Unsubscribing from a publisher that is already destroyed is safe. The C# object is still there for the rest of the frame, and the event field is managed. The failure is the other way: the publisher lives, the listener does not.

**Reload Domain** off (**Project Settings → Editor → Enter Play Mode Options**) keeps static fields and the runtime fields of asset instances. Scene objects are destroyed and created again if **Reload Scene** is still on, and their `OnDisable` / `OnEnable` run. A static list that escaped `OnDisable` still holds the dead listener. `SubsystemRegistration` runs on the next enter Play Mode, before scene `OnEnable`, which is why the bus clears there and the channel clears in the asset `OnEnable`.

**Reload Scene** off as well means those scene objects stay enabled. `OnEnable` does not run again. Clearing the bus then drops live subscriptions and nobody puts them back. Reset statics when the domain survives. Do not clear a list that your listeners will not rebuild.

## Ordering and re-entrancy

C# invocation order is subscription order. `UnityEvent` runs inspector calls first, then `AddListener` order. Neither one is the script execution order, except that execution order changes who gets `OnEnable` first and therefore who subscribed first. Treat that as an accident.

`Health.Died` runs inside `ApplyDamage`, before `ApplyDamage` returns. A listener that calls `ApplyDamage` on another body nests that body's `Died` inside the first raise. The health page already says not to `Destroy` the body in a `Died` listener: later listeners on that same raise have not run, and `Destroy` defers `OnDisable` to the end of the frame, so they still run on a body that is about to go. `SetActive(false)` runs `OnDisable` immediately, during the raise.

The bus queues a nested `Raise` of the same `T` so a listener cannot re-enter the list. It does not queue a different type, and it does not queue `Health.Died`. Those stay nested. If a death handler must not see a half-finished kill, set a flag and do the work after `ApplyDamage` returns, or raise the bus from the relay and let the queue hold the second `PlayerDied`.

Changing the list during a C# raise does not skip or double-call inside that raise. The local copy is already taken. `UnityEvent.Invoke` has, across versions, skipped a call or invoked a listener twice when the list changes mid-invoke. Do not `AddListener` or `RemoveListener` from inside a `UnityEvent` response. Disable the object afterwards, or defer the unsubscribe.

## Allocation

A method-group subscribe allocates the delegate once, when the list has to grow. A closure allocates every time the line runs, and it boxes whatever it captures that the compiler cannot keep on the stack. Subscribe in `OnEnable`, not when the gun fires.

Boxing is a cast to `object` or to an interface. `EventBus<PlayerDied>.Raise(payload)` does not box `PlayerDied`. `EventBus<object>` is rejected by the struct constraint. `EventChannel<object>.Raise(someStruct)` boxes, because `T` is `object`. Keep `T` as the payload type.

`GetInvocationList` allocates. `UnityEvent`'s persistent call allocates more than a direct `Action`. String interpolation in a listener that runs per shot allocates. The ammo label should set `text` from the numbers it was given, not build a fresh string API around them beyond that assignment. `Text.text` itself allocates. That is the label, and it is still cheaper than subscribing a closure to do it.

The bus queue allocates when a nested burst exceeds the spare capacity. It does not allocate on a raise that nobody re-enters.

## Messages and observers

`SendMessage("Show")` walks the `GameObject` and calls a method by name. `BroadcastMessage` includes children. `SendMessageUpwards` includes parents. There is no payload type, the call allocates, and a missing method is silent unless you pass `SendMessageOptions.RequireReceiver`. None of that is worth it next to a typed event.

An observer, in the textbook sense, is a list of interested parties and a notify. `event`, the bus, and the channel are that list. Pick one of those. A second hand-rolled list on the same signal is how a project ends up with two death screens and one of them stale.

`IObservable<T>` is the same idea with a subscription object to dispose. It is a reasonable fit for streams of values over time. It is a heavy dependency for `Died` and `AmmoChanged`, which are already `event`.

!!! warning "Common pitfalls"

    `OnEnable` without `OnDisable` leaks. On a scene object the leak dies with the publisher. On a static bus or a channel asset it survives the listener, and the next raise calls a destroyed object. `this?.` does not catch that. Unity's overloaded `==` does, and only if the handler checks.

    A closure cannot be unpaired. `+= () => Show()` in `OnEnable` adds a new delegate every enable. `Reload Domain` off then keeps those delegates across Play Mode. Resetting the static list drops them. It also drops a listener that was still valid, if **Reload Scene** is off and `OnEnable` will not run again.

    `RuntimeInitializeOnLoadMethod` on `EventBus<T>` does not run. The attribute has to sit on a non-generic type. `SubsystemRegistration` is the one that runs before the scene loads. `BeforeSceneLoad` is already late enough for some assets to have subscribed.

    Raising `UnityEvent` from a projectile, or allocating `GetInvocationList` per hit, shows up as GC in the profiler long before the game-over screen does. Death and a button can use the inspector. The fire loop should use the C# event the weapon already raises.

    One channel asset is one list. Two players sharing Player Died both notify every listener. A listener on an inactive panel never subscribes. **Raise** in Edit Mode does not test the scene. Enter Play Mode first.

    Do not `Destroy` the publisher inside its own `Died` handler and assume later listeners have finished. They are still on this stack. The health page's latch means a second `ApplyDamage` from a listener does not raise `Died` again.
