Data and state
==============

See :ref:`the legend <formats-legend>` for the status symbols.

.. list-table::
   :header-rows: 1
   :widths: 12 12 12 8 56

   * - Format
     - Platform
     - Output
     - Status
     - Notes
   * - ``.bin``
     - PC, DC
     - JSON
     - ✅
     - Terrain heightfield (513×513 ``s16``) or tile flags (128×128 ``u16``).
   * - ``.ctl``
     - PC, DC
     - JSON
     - ✅
     - Demo/replay input recording (16-byte records).
   * - ``.sav``
     - PC
     - JSON
     - ✅
     - Mission-state snapshot: named fields decoded; gaps as base64.
   * - ``.cfg``
     - PC
     - JSON
     - ✅
     - Config: named blocks split; build stamp and verified checksum decoded.
   * - ``.lev``
     - PC
     - JSON
     - ✅
     - Level-state snapshot: shares the mission field table minus its prefix.
   * - ``.xxx``
     - PC
     - JSON
     - ✅
     - Debug snapshot: same format as ``.sav``.
   * - ``.TXT``
     - DC
     - UTF-8
     - ✅
     - Shift-JIS or ISO-8859-15 text re-encoded to UTF-8.

Terrain and replay
------------------

``.bin`` data files are either a terrain heightfield (a 513×513 grid of signed 16-bit samples) or a
tile-flag map (a 128×128 grid of unsigned 16-bit values); the shape is detected from the file size
and decoded to JSON. ``.ctl`` files are demo/replay input recordings of 16-byte records, decoded to
a JSON list.

Save and snapshot state
-----------------------

The save, config, level, and debug-snapshot files (``.sav``, ``.cfg``, ``.lev``, and ``.xxx``) are
``memcpy``-style images of game RAM. Their schemas were reverse-engineered from the PC executable
(``incoming.exe``), so the decoders map the real in-memory layout rather than treating the body as
opaque. Bytes that are not covered by a known field (gaps, large object pools, and run-time pointer
tables) are preserved losslessly as base64, so the output is both human-inspectable and lossless.

The configuration file (``.cfg``, written by ``SaveGameConfigFile``) is a concatenation of
fixed-size blocks described by the game's internal save-descriptor table, totalling 10980 bytes.
It is split into its 21 named blocks; the leading build-stamp string is decoded, and the high-score
checksum is decoded *and* recomputed (a signed-byte sum over the high-score-table block) and
reported as ``valid`` when the two agree.

The snapshot files share one field table derived from the contiguous run of game globals that the
engine serialises. ``.sav`` and ``.xxx`` (``SaveMissionStateSnapshot``) cover the whole region;
``.lev`` (``SaveLevelStateSnapshot``) is the same region without its 12-byte leading mission-id
prefix, so it reuses the same table shifted by that prefix. Each decoded field carries its game
variable name (mission and game-mode flags, camera and replay-camera state, the script runtime,
score statistics, frame and timer counters, lighting and fog state, the saved CD-audio track, and
more). Run-time pointer fields are decoded as unsigned 32-bit words; their saved values are not
meaningful across sessions.

Dreamcast ``.TXT`` text
-----------------------

Dreamcast ``.TXT`` files are re-encoded to UTF-8. The source encoding is detected in order: UTF-8,
then Shift-JIS (Japanese), then ISO-8859-15 (French, German, Spanish, and Italian). Pure-ASCII files
are already valid UTF-8 and pass through unchanged.
