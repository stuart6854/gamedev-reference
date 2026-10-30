---
engine: Unity
version: 6+
uses:
  - name: Companions and NPCs
    text: Survivors eat, sleep, scavenge, guard, or flee, chosen by hunger, fatigue, threat, and time of day.
  - name: Life and colony sims
    text: Many needs compete smoothly, without a hand-written rule for every combination.
  - name: Shooters
    text: Attack, take cover, reload, or retreat, scored by health, ammo, and distance.
  - name: Wildlife
    text: Graze, drink, rest, or flee, with a little randomness so a herd does not move in lockstep.
---

# Utility AI

Choosing what to do by scoring every option and taking the best. Each action has a few **considerations**, each a number from 0 to 1 that asks one question, such as "how hungry am I" or "how close is the threat", shaped by a response curve. Multiply them and the action's score falls out. Adding a new behaviour is adding one action with its considerations; no transition table grows.

A [state machine](../architecture/state-machines.md) is clearer when there are few states and the transitions are the design, as on the [enemy behaviour](enemy.md) page. Utility wins when many needs compete, and the right choice is "whichever matters most right now".

## Scoring

```text
score(action):
    s = 1
    for each consideration c:
        s *= curve_c(input_c)          // each in [0, 1]
        if s == 0: return 0            // one veto is enough
    s = compensate(s, count)
    return s * action.weight
```

Multiplying means any consideration at 0 vetoes the action: no food in reach makes "eat" score 0 however hungry the agent is.

### Compensation

Multiplying many numbers below 1 drags the result down: an action with five considerations at 0.9 scores 0.59, while one with a single consideration at 0.6 beats it. Compensate for the count, a correction from Dave Mark's Infinite Axis Utility System:

\[
m = 1 - \frac{1}{n}, \qquad s' = s + (1 - s)\,m\,s
\]

Five considerations at 0.9 now score about 0.78, while a single consideration is unchanged, since \(m = 0\).

### Response curves

The input is normalised to 0..1, such as hunger as a fraction or distance divided by a maximum. The curve says how much that matters:

| Shape | Curve | Use for |
| --- | --- | --- |
| Linear | \(y = x\) | Proportional: the more, the more. |
| Quadratic | \(y = x^2\) | Urgency: ignorable until it is high, then pressing. Hunger, fatigue. |
| Inverse | \(y = 1 - x\) | Less is better: distance to food, cost. |
| Logistic | an S-curve around a threshold | Nearly a switch, with a soft edge: low health, an enemy in range. |
| Constant | \(y = c\) | A baseline, such as idle at 0.1 so something always scores. |

In Unity, an `AnimationCurve` per consideration lets each be drawn in the inspector.

## Choosing

Score every action and take the highest. Two additions stop the agent dithering between two close options:

- **Momentum.** The current action's score is multiplied by **Momentum**, such as 1.2, so a challenger has to be clearly better to take over.
- **Commitment.** An action that has just started cannot be replaced for **Min Commitment** seconds, unless the challenger is an interrupt, such as flee.

For variety, pick at random among the actions within **Random Band** of the best, weighted by score. A herd then does not all start grazing on the same frame.

Re-score every **Think Interval**, a few times a second, not every frame. The current action still runs every frame.

## Setup

1. Make inputs: `ScriptableObject`s that read one number from the agent. The page has `NeedInput`, which reads a need from `Needs`. Write others the same way: health fraction, distance to the nearest threat, ammo fraction, time of day.
2. Write actions as components deriving from `UtilityAction`: `Enter`, `Tick`, `Exit`, and optionally `CanRun`. Put them all on the agent.
3. On each action, add **Considerations**: an input and a curve. Set the **Weight**: 1 for normal, higher for actions that should win ties, such as flee.
4. Put `UtilityBrain` on the agent. It finds the actions on the same object.
5. Watch `UtilityBrain.Current` and `Scores` in a debug view while tuning. Scores are where every utility bug shows.

## Scripts

### Inputs and considerations

```csharp
using System;
using UnityEngine;

/// <summary>
/// Reads one number in 0..1 from an agent. Subclass per kind of input.
/// </summary>
public abstract class UtilityInput : ScriptableObject
{
    public abstract float Read(GameObject agent);
}

[Serializable]
public class Consideration
{
    public UtilityInput input;
    [Tooltip("x is the input in 0..1. y is how much this action wants it, in 0..1.")]
    public AnimationCurve curve = AnimationCurve.Linear(0f, 0f, 1f, 1f);

    public float Score(GameObject agent)
    {
        if (input == null)
            return 0f;
        return Mathf.Clamp01(curve.Evaluate(Mathf.Clamp01(input.Read(agent))));
    }
}
```

### Action

```csharp
using UnityEngine;

/// <summary>
/// One thing an agent can do. The brain scores it from its considerations and runs the best.
/// </summary>
public abstract class UtilityAction : MonoBehaviour
{
    [SerializeField] Consideration[] considerations = System.Array.Empty<Consideration>();
    [Min(0f)] [SerializeField] float weight = 1f;
    [Tooltip("May replace the current action during its commitment time. Flee, dodge.")]
    [SerializeField] bool interrupts;

    public bool Interrupts => interrupts;

    /// <summary>Hard requirements, checked before scoring. No food known: cannot eat.</summary>
    public virtual bool CanRun() => true;

    public virtual void Enter() { }
    public virtual void Tick(float dt) { }
    public virtual void Exit() { }

    /// <summary>True when the action has finished on its own and the brain should choose again now.</summary>
    public virtual bool IsDone => false;

    public float Score()
    {
        if (!CanRun() || considerations.Length == 0)
            return 0f;

        float score = 1f;
        for (int i = 0; i < considerations.Length; i++)
        {
            score *= considerations[i].Score(gameObject);
            if (score <= 0f)
                return 0f;
        }

        // Compensate for the number of considerations, so long lists are not penalised.
        float modification = 1f - 1f / considerations.Length;
        score += (1f - score) * modification * score;
        return score * weight;
    }
}
```

### Brain

```csharp
using System.Collections.Generic;
using UnityEngine;

/// <summary>
/// Scores the UtilityActions on this object on an interval and runs the best one every frame.
/// </summary>
public class UtilityBrain : MonoBehaviour
{
    [SerializeField] float thinkInterval = 0.25f;
    [Tooltip("Multiplier on the current action's score, so close challengers do not cause dithering.")]
    [SerializeField] float momentum = 1.2f;
    [SerializeField] float minCommitment = 1f;
    [Tooltip("Pick at random among actions within this fraction of the best. 0 always takes the best.")]
    [Range(0f, 0.5f)] [SerializeField] float randomBand;

    readonly List<UtilityAction> _actions = new List<UtilityAction>();
    readonly List<float> _scores = new List<float>();
    float _nextThink;
    float _startedAt;

    public UtilityAction Current { get; private set; }
    public IReadOnlyList<UtilityAction> Actions => _actions;
    public IReadOnlyList<float> Scores => _scores;

    void Awake()
    {
        GetComponents(_actions);
        for (int i = 0; i < _actions.Count; i++)
            _scores.Add(0f);
    }

    void OnEnable()
    {
        _nextThink = Time.time + Random.value * thinkInterval; // stagger agents
    }

    void OnDisable()
    {
        Switch(null);
    }

    void Update()
    {
        if (Time.time >= _nextThink || (Current != null && Current.IsDone))
        {
            _nextThink = Time.time + thinkInterval;
            Think();
        }

        if (Current != null)
            Current.Tick(Time.deltaTime);
    }

    void Think()
    {
        float best = 0f;
        int bestIndex = -1;
        bool committed = Current != null && !Current.IsDone && Time.time - _startedAt < minCommitment;

        for (int i = 0; i < _actions.Count; i++)
        {
            UtilityAction action = _actions[i];
            float score = action.enabled ? action.Score() : 0f;
            if (action == Current && !Current.IsDone)
                score *= momentum;
            if (committed && action != Current && !action.Interrupts)
                score = 0f;

            _scores[i] = score;
            if (score > best)
            {
                best = score;
                bestIndex = i;
            }
        }

        if (bestIndex >= 0 && randomBand > 0f)
            bestIndex = PickInBand(best);

        Switch(bestIndex >= 0 ? _actions[bestIndex] : null);
    }

    int PickInBand(float best)
    {
        float floor = best * (1f - randomBand);
        float total = 0f;
        for (int i = 0; i < _scores.Count; i++)
        {
            if (_scores[i] >= floor)
                total += _scores[i];
        }

        float roll = Random.value * total;
        int last = -1;
        for (int i = 0; i < _scores.Count; i++)
        {
            if (_scores[i] < floor)
                continue;
            if (roll < _scores[i])
                return i;
            roll -= _scores[i];
            last = i;
        }
        return last;
    }

    void Switch(UtilityAction next)
    {
        if (next == Current && (next == null || !next.IsDone))
            return;

        if (Current != null)
            Current.Exit();
        Current = next;
        _startedAt = Time.time;
        if (Current != null)
            Current.Enter();
    }
}
```

An action that reports `IsDone` is re-entered if it still scores best: "eat" finishing one meal and starting another while still hungry is correct.

### Example: needs

A need is a number that grows over time, and actions reduce it.

```csharp
using UnityEngine;

public enum Need
{
    Hunger,
    Fatigue,
    Fear
}

/// <summary>
/// Needs in 0..1 that rise per second. Actions call Satisfy.
/// </summary>
public class Needs : MonoBehaviour
{
    [SerializeField] float hungerPerSecond = 0.005f;
    [SerializeField] float fatiguePerSecond = 0.003f;
    [SerializeField] float fearDecayPerSecond = 0.1f;

    float _hunger;
    float _fatigue;
    float _fear;

    public float Get(Need need) => need switch
    {
        Need.Hunger => _hunger,
        Need.Fatigue => _fatigue,
        _ => _fear
    };

    public void Satisfy(Need need, float amount) => Add(need, -amount);

    public void Add(Need need, float amount)
    {
        switch (need)
        {
            case Need.Hunger: _hunger = Mathf.Clamp01(_hunger + amount); break;
            case Need.Fatigue: _fatigue = Mathf.Clamp01(_fatigue + amount); break;
            default: _fear = Mathf.Clamp01(_fear + amount); break;
        }
    }

    void Update()
    {
        float dt = Time.deltaTime;
        Add(Need.Hunger, hungerPerSecond * dt);
        Add(Need.Fatigue, fatiguePerSecond * dt);
        Add(Need.Fear, -fearDecayPerSecond * dt);
    }
}

/// <summary>Reads one need from the agent's Needs.</summary>
[CreateAssetMenu(menuName = "Game/Utility/Need Input")]
public class NeedInput : UtilityInput
{
    public Need need;

    public override float Read(GameObject agent)
    {
        return agent.TryGetComponent(out Needs needs) ? needs.Get(need) : 0f;
    }
}

/// <summary>Stands still and recovers fatigue.</summary>
public class RestAction : UtilityAction
{
    [SerializeField] float recoveryPerSecond = 0.05f;
    Needs _needs;

    void Awake() => _needs = GetComponent<Needs>();

    public override void Tick(float dt) => _needs.Satisfy(Need.Fatigue, recoveryPerSecond * dt);

    public override bool IsDone => _needs.Get(Need.Fatigue) <= 0.05f;
}
```

Put `Needs`, `NeedInput`, and `RestAction` in separate files, each named after its class. Unity needs that to add a component or create an asset from a script.

A survivor might have:

| Action | Considerations | Weight |
| --- | --- | --- |
| Rest | Fatigue, quadratic. Fear, inverse. | 1 |
| Eat | Hunger, quadratic. Distance to food, inverse. `CanRun`: food known. | 1 |
| Scavenge | Hunger, linear. Daylight, logistic. Fear, inverse. | 0.8 |
| Flee | Fear, logistic around 0.6. **Interrupts**. | 2 |
| Idle | Constant 0.1. | 1 |

[Perception](perception.md) can feed fear: raise it on `Noticed`, and on loud `Heard` events.

!!! warning "Common pitfalls"

    An input outside 0..1 is clamped, so a raw distance of 25 reads as 1. Normalise inputs: divide by a maximum.

    Without a baseline action, there are moments where everything scores 0 and the agent freezes. Keep an idle action at a small constant score.

    Without momentum or commitment, two actions scoring 0.51 and 0.49 swap every think, and the agent walks back and forth.

    A weight above 1 lets an action win with weak considerations. Use weights for real priority, such as survival over comfort, not to fix a badly shaped curve.

    Scores nobody looks at are bugs nobody sees. Show `Current` and `Scores` over the agent's head while tuning.
