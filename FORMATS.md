# Incoming asset formats

Status and notes for every asset format handled by `incoming-extract`. Platforms: **PC** (Windows,
`incoming.exe`) and **DC** (Dreamcast, `1ST_READ.BIN`). Many formats are shared between the builds.

Legend: ✅ converted · 📄 copied verbatim (already open, or no portable schema) · 🚧 being decoded.

## Container and media

| Format       | Platform | Output     | Status | Notes                                           |
| ------------ | -------- | ---------- | ------ | ----------------------------------------------- |
| `DATA1.CAB`  | PC       | files      | ✅     | InstallShield cabinet; unpacked with unshield.  |
| GDI + tracks | DC       | files      | ✅     | Extracted with gdiextract.                      |
| `.raw`       | DC       | WAV        | ✅     | Red Book CDDA wrapped in a RIFF header.         |
| `.PVR`       | DC       | PNG        | ✅     | Standard Dreamcast PVR via spvr2png.            |
| `*_T.PVR`    | DC       | PNG (many) | ✅     | Pack container; unpacked then spvr2png.         |
| `.PPM`       | PC       | PNG        | ✅     | Standard NetPBM `P6` via Pillow.                |
| `.wav`       | PC       | (copied)   | 📄     | Already standard RIFF/WAVE PCM.                 |
| `.OSB`       | DC       | WAV (many) | ✅     | Manatee voice bank; AICA ADPCM, one WAV/record. |
| `.MLT`       | DC       | JSON       | ✅     | Manatee `SMLT` multi-unit container table.      |

## Models and scenes

| Format     | Platform | Output    | Status | Notes                                                     |
| ---------- | -------- | --------- | ------ | --------------------------------------------------------- |
| `.IAN`     | PC       | OBJ + MTL | ✅     | LOD0 mesh; Y negated to +Y up, winding reversed.          |
| `*_M.BIN`  | DC       | OBJ + MTL | ✅     | Objects from the `_ML` index; materials by texture index. |
| `*_ML.BIN` | DC       | JSON      | ✅     | The model directory (offset table) into `_M.BIN`.         |
| `.MDL`     | PC, DC   | (copied)  | 📄     | Plain-text physics/config DSL.                            |
| `.ODL`     | PC, DC   | (copied)  | 📄     | Plain-text object definition DSL.                         |
| `.WDL`     | PC, DC   | (copied)  | 📄     | Plain-text world definition DSL.                          |

## Data and state

| Format | Platform | Output | Status | Notes                                                          |
| ------ | -------- | ------ | ------ | -------------------------------------------------------------- |
| `.bin` | PC, DC   | JSON   | ✅     | Terrain heightfield (513x513 s16) or tile flags (128x128 u16). |
| `.ctl` | PC, DC   | JSON   | ✅     | Demo/replay input recording (16-byte records).                 |
| `.sav` | PC       | JSON   | ✅     | Save game: header counts decoded, state as base64.             |
| `.cfg` | PC       | JSON   | ✅     | Config: build-stamp decoded, blocks as base64.                 |
| `.lev` | PC       | JSON   | ✅     | Level snapshot: flat image as base64.                          |
| `.xxx` | PC       | JSON   | ✅     | Debug snapshot: lead count decoded, state as base64.           |
| `.TXT` | DC       | UTF-8  | ✅     | Shift-JIS / ISO-8859-15 text re-encoded to UTF-8.              |

The save/config/level state files (`.sav`/`.cfg`/`.lev`/`.xxx`) are `memcpy`-style images of
build-specific RAM with no portable on-disk schema, so the JSON decodes the documented header fields
and preserves the whole file losslessly as base64 rather than inventing a schema for the opaque body.
Dreamcast `.TXT` files are re-encoded to UTF-8, detecting the source as UTF-8, Shift-JIS (Japanese),
or ISO-8859-15 (French, German, Spanish, Italian), in that order; ASCII files are unchanged.

## Detailed notes

### `.raw` (Dreamcast CDDA audio)

Red Book CDDA ripped verbatim: signed 16-bit, 44100 Hz, stereo, interleaved, whole 2352-byte
sectors, native little-endian. Conversion is a straight RIFF/WAVE header wrap with no byte-swap.

### `*_T.PVR` (Dreamcast level texture pack)

Table of contents of `(uint32 absolute offset, uint32 size)` pairs, zero-terminated; the table
length equals the first offset. Each entry points at a standard PVRT chunk. The last entry is short
by 8 bytes (the pixel data is still complete); the reader clamps it to the end of the file.

### `*_M.BIN` / `*_ML.BIN` (Dreamcast models)

`*_M.BIN` is a **pack of many independent objects** (a level's models: terrain patches, buildings,
props, vehicles), and `*_ML.BIN` is its directory: an array of `uint32` file offsets into `*_M.BIN`
terminated by `0xFFFFFFFF`. Each offset is a 144-byte object header; the active level-of-detail
record (at +0x10) gives a face count, a packed `(texture_index << 16) | vertex_count` word, and file
offsets to a 40-byte-stride vertex pool (position, normal, UV) and a 16-byte-stride triangle pool.
Non-mesh objects (sprites and placeholders) are detected by out-of-range pointers and skipped. Each
object is written as its own `<stem>_<NNN>.obj` + `.mtl` in a directory named after the source, and
its texture (the `texture_index` sub-texture of the level's `*_T.PVR` pack) is written as a PNG
beside the material.

### `.OSB` / `.MLT` (Dreamcast Manatee sound)

`.OSB` is a `SOSB` speech/SFX bank: a 16-byte header, an offset table of `SOSP` voice records, each
record holding packed AICA voice registers (sample start, length, 4-bit ADPCM codec, and pitch).
Every record is decoded with the Yamaha/AICA ADPCM algorithm to signed 16-bit mono PCM and written
as one WAV per record (22050 Hz in the shipped banks). `.MLT` is a Sega `SMLT` multi-unit container
whose 32-byte-per-unit table (type, bank, AICA address and size, file offset and size) is decoded to
JSON.

### `Manatee.drv` (Dreamcast)

Sega's Manatee AICA sound-driver program uploaded to the audio chip at runtime. Executable driver
code, not a convertible asset; copied verbatim and documented only.
