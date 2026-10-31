---
engine: Unity
version: 6+
uses:
  - name: Base building
    text: Undo and redo for placing, rotating, and demolishing pieces.
  - name: Strategy and tactics
    text: Unit orders queued as commands, shown as waypoints, and cancelled one at a time.
  - name: Multiplayer
    text: Inputs sent as small command records instead of state.
---

# Command pattern

An action as an object: what to do, the data it needs, and how to undo it. Once actions are objects, they can be kept in a history for undo and redo, queued to run one after another, merged, recorded, or sent over the network. This page builds an undo history and uses it for [building](../systems/building.md), then covers queues.

For editor tools, use Unity's own `Undo` class instead. It already records changes to serialized objects and puts them in **Edit → Undo**. The [editor tooling](../tools/editor/index.md) pages use it.

## Command and history

```csharp
using System;
using System.Collections.Generic;

/// <summary>
/// One undoable action. Execute returns false when it could not run, and is then not recorded.
/// </summary>
public interface ICommand
{
    string Name { get; }
    bool Execute();
    void Undo();
}

/// <summary>Optional: a command that can absorb the next one, such as rotating the same piece again.</summary>
public interface IMergeable
{
    bool TryMerge(ICommand next);
}

/// <summary>
/// Undo and redo stacks with a size limit.
/// </summary>
public class CommandHistory
{
    readonly LinkedList<ICommand> _undo = new LinkedList<ICommand>();
    readonly Stack<ICommand> _redo = new Stack<ICommand>();
    readonly int _limit;

    public event Action Changed;

    public CommandHistory(int limit = 100) => _limit = Math.Max(1, limit);

    public bool CanUndo => _undo.Count > 0;
    public bool CanRedo => _redo.Count > 0;
    public string NextUndoName => CanUndo ? _undo.Last.Value.Name : null;
    public string NextRedoName => CanRedo ? _redo.Peek().Name : null;

    public bool Do(ICommand command)
    {
        if (command == null || !command.Execute())
            return false;

        // A new action makes the redo branch meaningless.
        _redo.Clear();

        if (_undo.Count > 0 && _undo.Last.Value is IMergeable last && last.TryMerge(command))
        {
            Changed?.Invoke();
            return true;
        }

        _undo.AddLast(command);
        if (_undo.Count > _limit)
            _undo.RemoveFirst();
        Changed?.Invoke();
        return true;
    }

    public bool Undo()
    {
        if (!CanUndo)
            return false;
        ICommand command = _undo.Last.Value;
        _undo.RemoveLast();
        command.Undo();
        _redo.Push(command);
        Changed?.Invoke();
        return true;
    }

    public bool Redo()
    {
        if (!CanRedo)
            return false;
        ICommand command = _redo.Pop();
        if (!command.Execute())
        {
            // The world changed since the undo, such as the spot now being taken. Drop the rest of the branch.
            _redo.Clear();
            Changed?.Invoke();
            return false;
        }
        _undo.AddLast(command);
        Changed?.Invoke();
        return true;
    }

    public void Clear()
    {
        _undo.Clear();
        _redo.Clear();
        Changed?.Invoke();
    }
}
```

- `Execute` is also the redo. A command stores enough to run again from scratch, not the result of its first run.
- `Execute` returning false keeps failed actions, such as a placement that is not valid, out of the history.
- `Changed` is for the UI: grey out the buttons, and show "Undo Place Wall".
- The limit bounds memory. A command holding a destroyed object's data is small; a command holding a mesh is not.

## Handles, not references

Undoing a placement destroys the piece. Redoing it instantiates a new one. A later command that refers to the first object, such as "rotate that wall", now points at a destroyed object. Commands that touch the same object share a handle, and whichever command recreates the object updates it.

```csharp
using UnityEngine;

/// <summary>Shared by every command about one object. Updated when the object is recreated.</summary>
public sealed class ObjectHandle
{
    public GameObject Current;
}
```

## Building commands

The build mode already knows how to place and demolish, including paying and refunding. Expose those two operations, and the commands only record what to call them with.

```csharp
using UnityEngine;

/// <summary>What the build mode offers commands. It pays on Place and refunds on Remove.</summary>
public interface IBuildActions
{
    GameObject Place(string pieceId, Vector3 position, Quaternion rotation);
    void Remove(GameObject piece);
}

public sealed class PlaceCommand : ICommand
{
    readonly IBuildActions _build;
    readonly string _pieceId;
    readonly Vector3 _position;
    readonly Quaternion _rotation;

    public ObjectHandle Handle { get; } = new ObjectHandle();
    public string Name => "Place " + _pieceId;

    public PlaceCommand(IBuildActions build, string pieceId, Vector3 position, Quaternion rotation)
    {
        _build = build;
        _pieceId = pieceId;
        _position = position;
        _rotation = rotation;
    }

    public bool Execute()
    {
        // Place checks validity and cost again. It returns null if either fails now.
        Handle.Current = _build.Place(_pieceId, _position, _rotation);
        return Handle.Current != null;
    }

    public void Undo()
    {
        if (Handle.Current != null)
            _build.Remove(Handle.Current);
        Handle.Current = null;
    }
}

public sealed class RotateCommand : ICommand, IMergeable
{
    readonly ObjectHandle _handle;
    Quaternion _from;
    Quaternion _to;

    public string Name => "Rotate";

    public RotateCommand(ObjectHandle handle, Quaternion to)
    {
        _handle = handle;
        _to = to;
    }

    public bool Execute()
    {
        if (_handle.Current == null)
            return false;
        _from = _handle.Current.transform.rotation;
        _handle.Current.transform.rotation = _to;
        return true;
    }

    public void Undo()
    {
        if (_handle.Current != null)
            _handle.Current.transform.rotation = _from;
    }

    // Ten presses of R on the same piece undo as one rotation.
    public bool TryMerge(ICommand next)
    {
        if (next is RotateCommand rotate && rotate._handle == _handle)
        {
            _to = rotate._to;
            return true;
        }
        return false;
    }
}
```

The build mode keeps a `CommandHistory` and, instead of placing directly, calls:

```csharp
var place = new PlaceCommand(this, piece.Id, ghostPosition, ghostRotation);
if (history.Do(place))
    _handles[place.Handle.Current] = place.Handle; // so later rotate and demolish commands find the handle
```

Ctrl+Z and Ctrl+Y, or the UI buttons, call `history.Undo()` and `history.Redo()`.

- `Place` checks again on redo. The spot may be blocked, or the materials spent since the undo. Redo then fails cleanly and the redo branch is dropped.
- A **Demolish** command is the mirror of place: `Execute` removes and records the piece id, position, and rotation; `Undo` places it again and updates the shared handle.
- Clear the history when leaving build mode, or a later undo removes a wall the player has long since forgotten about. Players expect undo for the last few actions, not the whole session.

## Composite commands

Placing a row of wall pieces in one drag is one action to the player. A composite runs several commands and undoes them in reverse:

```csharp
using System.Collections.Generic;

public sealed class CompositeCommand : ICommand
{
    readonly List<ICommand> _commands;
    readonly List<ICommand> _done = new List<ICommand>();

    public string Name { get; }

    public CompositeCommand(string name, List<ICommand> commands)
    {
        Name = name;
        _commands = commands;
    }

    public bool Execute()
    {
        _done.Clear();
        foreach (ICommand command in _commands)
        {
            if (command.Execute())
                _done.Add(command);
        }
        return _done.Count > 0; // a partial row still counts; undo removes what was placed
    }

    public void Undo()
    {
        for (int i = _done.Count - 1; i >= 0; i--)
            _done[i].Undo();
    }
}
```

## Queues

Without undo, commands are still useful as a queue. An RTS unit's orders, a turn-based character's planned moves, and a survivor's timed actions are each a list of commands run one at a time.

| Use | Shape |
| --- | --- |
| **Order queue** | Each command has `Start`, `Tick`, `IsDone`, and `Cancel`. The unit runs the head of the queue; Shift-click appends instead of replacing. |
| **Replay** | Record each frame's input commands with the frame number. Replaying them through the same deterministic simulation reproduces the session. |
| **Networking** | Send the command, "move to here", not the state. Small, and the server can validate it. |

Commands in a queue that runs over time are different from undoable ones. An undo command is instant and reversible; an order runs for seconds and can be cancelled half way. Keep the two interfaces separate.

!!! warning "Common pitfalls"

    A command that stores a reference to an object it may destroy and recreate breaks the next command after a redo. Share a handle.

    `Execute` that relies on state from its first run, such as an instance it created, fails on redo. Store the inputs and redo from them.

    Not clearing the redo stack on a new action lets redo replay actions on top of a different world.

    An undo history that also records costs must refund on undo and charge again on redo. Route both through the same place and remove code the game uses.

    Using a custom command history for edits made in the editor misses Unity's own Undo. Use `Undo.RecordObject` there.
