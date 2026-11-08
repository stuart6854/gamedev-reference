# Mixer and voices

The mixer produces the samples the sound card plays. The device asks for a block of samples at a fixed rate, and the mixer must deliver it on time, every time: a late block is an audible click or gap, far more noticeable than a dropped video frame.

## The callback

```text
on_audio_callback(output, frame_count):            // called by the device on its own thread
    process commands from the game (non-blocking)
    clear the bus buffers
    for voice in active voices:
        render frame_count frames of the voice (decode, resample, gain, pan)
        add them into the voice's bus
    process buses from the leaves to the master (effects, then add into the parent)
    write the master bus to output (converted to the device's format)
```

- Block sizes are typically 256 to 1024 frames at 48 kHz: **5 to 21 milliseconds**. The whole mix must finish well inside that, every time, including the worst case.
- Mix in **32-bit float**. Summing many voices goes above 1.0 freely; a limiter on the master bus brings it back before converting to the device's format.
- Run the mixer on its own high-priority thread, either the device's callback thread or a mixer thread that fills a small ring of blocks ahead of the device.

## Rules for the audio thread

The audio thread has a hard deadline. Anything that can take an unbounded time is forbidden on it:

- **No locks** shared with other threads. If the game thread holds the lock when the callback runs, the callback waits, and the block is late. Communicate through lock-free queues.
- **No allocation or freeing.** General-purpose allocators can take locks or call the OS. Preallocate voices and buffers; free them on another thread.
- **No file I/O, no logging to files, no waiting on anything.**

The game sends commands through a single-producer, single-consumer [ring buffer](../../data-structures/ring-buffer.md):

```text
Command = Play { voice_id, sound, position, gain }
        | Stop { voice_id, fade_time }
        | SetParam { voice_id, param, value }
        | SetListener { position, orientation }

game thread:  queue.push(command)            // never blocks; if full, drop and log on the game thread
audio thread: while queue.pop(cmd): apply(cmd)  // at the start of each callback
```

Results travel back the same way, through a second queue: a voice finished, a stream ran dry.

## Voices

A **voice** is one sound playing: its source data, position in it, and its current settings.

```text
Voice {
    source              // decoded buffer or stream
    play_position       // in frames, fractional when resampling
    pitch               // playback rate: 1.0 normal
    gain                // after fades and attenuation
    pan or 3D position
    bus
    priority
    state               // Playing, Virtual, Stopping (fading out)
}
```

- **Resampling**: a sound at 44.1 kHz on a 48 kHz device, or played at a different pitch, advances `play_position` by `pitch × source_rate / device_rate` per output frame, interpolating between source frames. Linear interpolation is cheap and adequate for most effects; higher quality filters suit music.
- **Ramps**: changing gain from one block to the next in a single step makes a click. Interpolate gain (and pan) across the block from the old value to the new one. Start and stop voices with a short fade (a few milliseconds) for the same reason.

### Voice limits and priority

The mixer can only afford a certain number of voices (from 32 on low-end mobile to a few hundred on PC). When more sounds want to play, decide which ones are heard:

```text
audibility(voice) = priority * gain after attenuation

when a new sound starts and all voices are in use:
    lowest = the playing voice with the lowest audibility
    if new sound's audibility > lowest's: steal lowest (fade it out quickly), play the new one
    else: start the new one as virtual
```

### Virtual voices

A **virtual** voice is tracked but not mixed: its play position advances, its 3D position updates, but no samples are decoded or mixed. When a real voice frees up, or the virtual one becomes audible enough, it becomes real again at the right point in the sound.

A looping engine sound on a car out of earshot, ambient emitters across a level, the hundredth gunshot in a battle: all can be virtual most of the time, and come back without restarting when they matter. Stop one-shot sounds that would only be virtual for their whole short life, instead of virtualising them.

## Buses

Voices play into **buses**, which mix into other buses, ending at the master:

```text
Master
 ├── Music
 ├── SFX
 │    ├── Weapons
 │    ├── Footsteps
 │    └── UI
 ├── Dialogue
 └── Ambience
```

- **Volume per bus** gives the player's settings (music, effects, dialogue sliders) and designer control over whole categories.
- **Effects per bus**: EQ, compressors, and limiters on a bus process everything in it once, instead of per voice.
- **Sends**: a voice or bus can send a copy of its signal, at its own level, to an effect bus such as a reverb. Reverb is expensive, so a few shared reverb buses with per-voice send levels is the usual design; see [reverb](spatial.md#reverb).
- **Master limiter**: keeps the final mix below full scale, so loud moments are compressed instead of clipped.

### Ducking

When a character speaks, music and effects should dip so the line is heard. **Ducking** lowers one bus based on the level of another:

```text
duck(target_bus, trigger_bus, amount_db = -9, attack = 0.05 s, release = 0.5 s):
    level = trigger_bus's measured level this block (RMS or peak)
    wanted = level > threshold ? amount_db : 0
    current = move towards wanted with the attack time (going down) or release time (coming back)
    target_bus.gain_db += current
```

A short attack and a longer release make the dip fast and the recovery smooth. The same mechanism (sidechain compression) keeps big explosions from being buried under constant gunfire, by ducking the weapons bus when explosions play.
