from __future__ import annotations

from base64 import b64decode
from typing import TYPE_CHECKING, cast
import json
import struct

from incoming_extractor.converters.state import cfg_to_json, lev_to_json, sav_to_json, xxx_to_json

if TYPE_CHECKING:
    from pathlib import Path


def _load(path: Path) -> dict[str, object]:
    return cast('dict[str, object]', json.loads(path.read_text('utf-8')))


def test_sav(tmp_path: Path) -> None:
    data = struct.pack('<3I', 605, 5, 1) + b'state-body'
    source = tmp_path / 'file0.sav'
    source.write_bytes(data)
    obj = _load(sav_to_json(source, tmp_path))
    assert obj['counts'] == [605, 5, 1]
    assert obj['size'] == len(data)
    assert b64decode(str(obj['data'])) == data


def test_sav_too_short_for_counts(tmp_path: Path) -> None:
    source = tmp_path / 's.sav'
    source.write_bytes(b'abcd')
    assert 'counts' not in _load(sav_to_json(source, tmp_path))


def test_xxx(tmp_path: Path) -> None:
    source = tmp_path / 't.xxx'
    source.write_bytes(struct.pack('<I', 0x69) + b'state')
    assert _load(xxx_to_json(source, tmp_path))['lead_count'] == 0x69


def test_xxx_too_short(tmp_path: Path) -> None:
    source = tmp_path / 't.xxx'
    source.write_bytes(b'ab')
    assert 'lead_count' not in _load(xxx_to_json(source, tmp_path))


def test_lev(tmp_path: Path) -> None:
    source = tmp_path / 'store.lev'
    source.write_bytes(b'flat-image')
    obj = _load(lev_to_json(source, tmp_path))
    assert obj['format'] == 'incoming-level-snapshot'
    assert b64decode(str(obj['data'])) == b'flat-image'


def test_cfg(tmp_path: Path) -> None:
    source = tmp_path / 'incoming.cfg'
    source.write_bytes(b'Wed Apr 15 16:24:58 1998\x00blocks')
    assert _load(cfg_to_json(source, tmp_path))['build_stamp'] == 'Wed Apr 15 16:24:58 1998'


def test_cfg_leading_nul(tmp_path: Path) -> None:
    source = tmp_path / 'c.cfg'
    source.write_bytes(b'\x00rest')
    assert 'build_stamp' not in _load(cfg_to_json(source, tmp_path))
