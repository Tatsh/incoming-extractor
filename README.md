# incoming-extractor

<!-- WISWA-GENERATED-README:START -->

[![Python versions](https://img.shields.io/pypi/pyversions/incoming-extractor.svg?color=blue&logo=python&logoColor=white)](https://www.python.org/)
[![PyPI - Version](https://img.shields.io/pypi/v/incoming-extractor)](https://pypi.org/project/incoming-extractor/)
[![GitHub tag (with filter)](https://img.shields.io/github/v/tag/Tatsh/incoming-extractor)](https://github.com/Tatsh/incoming-extractor/tags)
[![License](https://img.shields.io/github/license/Tatsh/incoming-extractor)](https://github.com/Tatsh/incoming-extractor/blob/master/LICENSE.txt)
[![GitHub commits since latest release (by SemVer including pre-releases)](https://img.shields.io/github/commits-since/Tatsh/incoming-extractor/v0.0.0/master)](https://github.com/Tatsh/incoming-extractor/compare/v0.0.0...master)
[![CodeQL](https://github.com/Tatsh/incoming-extractor/actions/workflows/codeql.yml/badge.svg)](https://github.com/Tatsh/incoming-extractor/actions/workflows/codeql.yml)
[![QA](https://github.com/Tatsh/incoming-extractor/actions/workflows/qa.yml/badge.svg)](https://github.com/Tatsh/incoming-extractor/actions/workflows/qa.yml)
[![Tests](https://github.com/Tatsh/incoming-extractor/actions/workflows/tests.yml/badge.svg)](https://github.com/Tatsh/incoming-extractor/actions/workflows/tests.yml)
[![Coverage Status](https://coveralls.io/repos/github/Tatsh/incoming-extractor/badge.svg?branch=master)](https://coveralls.io/github/Tatsh/incoming-extractor?branch=master)
[![Dependabot](https://img.shields.io/badge/Dependabot-enabled-blue?logo=dependabot)](https://github.com/dependabot)
[![Documentation Status](https://readthedocs.org/projects/incoming-extractor/badge/?version=latest)](https://incoming-extractor.readthedocs.org/?badge=latest)
[![mypy](https://www.mypy-lang.org/static/mypy_badge.svg)](https://mypy-lang.org/)
[![uv](https://img.shields.io/badge/uv-261230?logo=astral)](https://docs.astral.sh/uv/)
[![pytest](https://img.shields.io/badge/pytest-zz?logo=Pytest&labelColor=black&color=black)](https://docs.pytest.org/en/stable/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Downloads](https://static.pepy.tech/badge/incoming-extractor/month)](https://pepy.tech/project/incoming-extractor)
[![Stargazers](https://img.shields.io/github/stars/Tatsh/incoming-extractor?logo=github&style=flat)](https://github.com/Tatsh/incoming-extractor/stargazers)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit)](https://github.com/pre-commit/pre-commit)
[![Prettier](https://img.shields.io/badge/Prettier-black?logo=prettier)](https://prettier.io/)

[![@Tatsh](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fpublic.api.bsky.app%2Fxrpc%2Fapp.bsky.actor.getProfile%2F%3Factor=did%3Aplc%3Auq42idtvuccnmtl57nsucz72&query=%24.followersCount&label=Follow+%40Tatsh&logo=bluesky&style=social)](https://bsky.app/profile/Tatsh.bsky.social)
[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-Tatsh-black?logo=buymeacoffee)](https://buymeacoffee.com/Tatsh)
[![Libera.Chat](https://img.shields.io/badge/Libera.Chat-Tatsh-black?logo=liberadotchat)](irc://irc.libera.chat/Tatsh)
[![Mastodon Follow](https://img.shields.io/mastodon/follow/109370961877277568?domain=hostux.social&style=social)](https://hostux.social/@Tatsh)
[![Patreon](https://img.shields.io/badge/Patreon-Tatsh2-F96854?logo=patreon)](https://www.patreon.com/Tatsh2)

<!-- WISWA-GENERATED-README:STOP -->

Extract and convert assets from the PC and Dreamcast versions of
[_Incoming_](https://www.gog.com/en/game/incoming_incoming_forces) (Rage Software, published by
Interplay, 1998-1999).

Given a PC disc (directory, ISO, or `DATA1.CAB`), a Dreamcast GDI, or a directory of already
extracted PC or GD-ROM content, this tool mirrors the source tree into an output directory,
converting the proprietary assets to open formats and copying everything else verbatim. The source
is never modified.

Full documentation, including a reverse-engineered reference for every asset format, is at
[incoming-extractor.readthedocs.org](https://incoming-extractor.readthedocs.org/).

## Usage

```shell
incoming-extractor --output OUTPUT_DIR SOURCE
```

`SOURCE` may be a PC disc directory or ISO containing `DATA1.CAB` (or the `DATA1.CAB` itself), a
Dreamcast `.gdi` file, or a directory of already extracted PC or GD-ROM content. Recognised assets
are converted (PVR and PPM to PNG, IAN and `*_M.BIN` to OBJ and MTL, terrain, saves, and `.ctl` to
JSON, CDDA `.raw` and `.OSB` to WAV, Shift-JIS or ISO-8859-15 `.TXT` to UTF-8) and every other file
is copied verbatim.

An installed copy works as the source too — point at the game's directory, such as the
`Incoming 3DFX` folder of the
[Zoom Platform _Incoming Trilogy_](https://www.zoom-platform.com/product/incoming-trilogy)
(`…/Incoming Trilogy/Incoming 3DFX`). The _Incoming 3DFX_, _Incoming USA_, and _Incoming Subversion_
(an expansion pack) titles share the original engine and are supported; _Incoming Forces_ is not
supported.

Pass `--gdiextract-path`, `--spvr2png-path`, or `--unshield-path` to point at the native tools when
they are not on `PATH`, `-j`/`--jobs` to set the number of concurrent conversion jobs (defaults to
the CPU count), and `--debug` for verbose logging.

## Utilities

Two standalone commands convert a single asset without mirroring a whole source tree:

- `ian2obj MODEL OUTDIR` — convert one model to Wavefront OBJ and MTL. Both the PC `.ian` mesh and
  the Dreamcast `*_M.BIN` model pack are accepted (the format is detected from the file name); a
  Dreamcast pack needs its matching `*_ML.BIN` index beside it and yields one OBJ and MTL per object.
  The texture is resolved from the game root, auto-detected from `MODEL` or set with `--game-root`,
  unless `--no-texture` is given.
- `extract-pvr-pack PACK OUTDIR` — unpack a Dreamcast `*_T.PVR` texture pack, writing each texture as
  a separate `.pvr` file, or as a PNG with `--png` (which requires `spvr2png`).

## Native tools

Some conversions shell out to native helpers, which must be on `PATH` or supplied with the matching
`--*-path` option:

- [spvr2png](https://github.com/nextgeniuspro/spvr2png) — converts Sega Dreamcast PVR images to PNG.
- [gdiextract](https://github.com/MachXNU/gdiextract) — extracts the ISO 9660 file system from a
  Dreamcast GDI.
- [unshield](https://github.com/twogood/unshield) — unpacks the InstallShield `DATA1.CAB` cabinet on
  the PC disc.

Extracting `DATA1.CAB` from a PC ISO additionally uses
[isodump](https://sourceforge.net/projects/cdrtools/) or [7z](https://www.7-zip.org/).

## Development

```shell
uv sync --all-groups --all-extras
yarn install
```

Run the formatters and checks:

```shell
yarn format
yarn qa
```
