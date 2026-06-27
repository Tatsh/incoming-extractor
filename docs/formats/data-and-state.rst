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
     - Save game: header counts decoded, state as base64.
   * - ``.cfg``
     - PC
     - JSON
     - ✅
     - Config: build-stamp decoded, blocks as base64.
   * - ``.lev``
     - PC
     - JSON
     - ✅
     - Level snapshot: flat image as base64.
   * - ``.xxx``
     - PC
     - JSON
     - ✅
     - Debug snapshot: lead count decoded, state as base64.
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
``memcpy``-style images of build-specific RAM with no portable on-disk schema. Rather than invent a
schema for the opaque body, the JSON decodes the documented header fields (counts, build stamp, and
similar) and preserves the whole file losslessly as base64. This keeps the output both
human-inspectable and lossless.

Dreamcast ``.TXT`` text
-----------------------

Dreamcast ``.TXT`` files are re-encoded to UTF-8. The source encoding is detected in order: UTF-8,
then Shift-JIS (Japanese), then ISO-8859-15 (French, German, Spanish, and Italian). Pure-ASCII files
are already valid UTF-8 and pass through unchanged.
