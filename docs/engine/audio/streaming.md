# Streaming and formats

Uncompressed audio is large: one minute of 48 kHz stereo 16-bit PCM is about 11 MB. A game has hours of music, dialogue, and ambience, and thousands of effects. Choosing the right format for each sound, and streaming long ones from disk, keeps memory within budget without costing too much CPU.

## Formats

| Format | Ratio vs 16-bit PCM | Decode cost | Use for |
| --- | --- | --- | --- |
| PCM | 1:1 | None | Very short, very frequent sounds (UI clicks, footsteps) on platforms with memory to spare |
| ADPCM | About 4:1 | Very low | Short, frequent effects; sounds that many voices play at once |
| Vorbis | 8:1 to 15:1 | Moderate | Music, ambience, dialogue, long effects |
| Opus | 8:1 to 20:1 | Moderate | As Vorbis; better quality at low bit rates, especially for speech |
| Platform codecs (XMA, ATRAC9, and others) | As Vorbis | Hardware decoder, nearly free on the CPU | Everything on that platform that would otherwise be Vorbis |

- Pick the format **per sound** (or per category) in the import settings, with platform overrides, like [texture compression](../content/import-cook.md#per-asset-type).
- **Sample rate**: many effects lose nothing at 32 kHz or lower, and the saving is proportional. Music and dialogue usually stay at 44.1 or 48 kHz. Resampling happens in the mixer anyway.
- **Mono** for anything positioned in 3D. A stereo source played in 3D is panned as a whole, so its stereo width is wasted, and it is twice the size.

## Decompressed, compressed in memory, or streamed

| Mode | Memory | CPU | Start delay | Use for |
| --- | --- | --- | --- | --- |
| Decompress on load | Large (PCM) | Decode once when loaded | None | Short sounds played very often, by many voices |
| Compressed in memory | Small | Decode while playing, per voice | Small | Most effects |
| Streamed | A few buffers per voice | Decode while playing, plus disk reads | Needs a prefetched start | Music, ambience, dialogue: long sounds, few at a time |

The memory budget usually decides: a target such as "200 MB for all loaded audio" is met by streaming long sounds and compressing the rest, and only decompressing the hottest few.

## Streaming

A streaming voice reads its file in chunks, decodes them on a decoder thread, and hands decoded buffers to the mixer through a ring:

```text
StreamVoice {
    file, read_position
    decoded_ring[4]          // e.g. 4 buffers of ~100 ms each
    ring_read, ring_write
}

decoder thread, continuously:
    for stream with a free buffer in its ring:
        read the next compressed chunk (asynchronous I/O)
        decode into the free buffer
        publish it to the mixer (an atomic index update)

mixer, in the callback:
    take samples from the current buffer; move to the next when it is used up
    if the next buffer is not ready: output silence and report an underrun
```

- **Buffer enough** to cover the worst-case disk delay: on a busy drive with texture streaming, reads can take tens of milliseconds. Several hundred milliseconds of decoded audio per stream is common.
- **Prefetch the start**: keep the first buffer or two of each streamed sound decoded in memory, loaded with its level, so it starts instantly and streams the rest. Dialogue triggered by gameplay needs this, or every line starts late.
- **Limit concurrent streams** (for example 8 to 16). Each one is a continuous read; too many compete with asset streaming for the disk.
- Underruns are bugs. Log them with the stream's name, and treat them like dropped frames.

## Loops

- A looping sound must loop at the exact sample. Store loop start and end points in samples, and handle the wrap inside the mixer: copy the end of the loop, then the start, into the same output block.
- Compressed formats encode in blocks, and often add priming samples at the start. Loop points must account for them, and some encoders produce clicks at loop boundaries unless the loop is encoded specially. Test every looping asset.
- **Intro then loop**: music often has an introduction that plays once, followed by a looping section. Store both loop points; play from 0, then wrap from the loop end to the loop start.
- **Seamless transitions** between music tracks (or sections, for adaptive music) are scheduled on the audio thread to land on a beat or bar boundary, which is sample-accurate there and nowhere else.

## Seeking

Compressed streams can only start decoding at block or page boundaries. To seek (resuming music where it left off, or a virtual voice becoming real mid-sound), find the nearest seek point before the target, decode from there, and discard samples up to the target. Store a seek table with the file (time to byte offset every second or so) to avoid reading through the file from the start.
