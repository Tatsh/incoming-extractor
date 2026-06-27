"""
State converters: Incoming save, config, and snapshot files to JSON.

These files are images of build-specific in-memory state with no fully portable on-disk schema. The
documented header fields are decoded and the whole file is preserved losslessly as base64 so nothing
is lost.
"""
from __future__ import annotations

from base64 import b64encode
from typing import TYPE_CHECKING, Any
import json
import logging
import struct

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ('cfg_to_json', 'lev_to_json', 'sav_to_json', 'xxx_to_json')

log = logging.getLogger(__name__)

_U32 = struct.Struct('<I')


def _write_json(source: Path, dest_dir: Path, obj: dict[str, Any]) -> Path:
    destination = dest_dir / f'{source.stem}.json'
    destination.write_text(json.dumps(obj, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return destination


def _base(data: bytes, fmt: str) -> dict[str, Any]:
    return {'data': b64encode(data).decode('ascii'), 'format': fmt, 'size': len(data)}


def sav_to_json(source: Path, dest_dir: Path) -> Path:
    """
    Convert an Incoming ``.sav`` save game to JSON.

    The leading header counts are decoded; the serialized session state is preserved as base64.

    Parameters
    ----------
    source : Path
        The source ``.sav`` file.
    dest_dir : Path
        The directory the JSON is written to.

    Returns
    -------
    Path
        The written JSON path.
    """
    data = source.read_bytes()
    obj = _base(data, 'incoming-save')
    if len(data) >= 3 * _U32.size:
        obj['counts'] = [_U32.unpack_from(data, i * _U32.size)[0] for i in range(3)]
    return _write_json(source, dest_dir, obj)


def xxx_to_json(source: Path, dest_dir: Path) -> Path:
    """
    Convert an Incoming ``.xxx`` debug mission snapshot to JSON.

    The leading count is decoded; the serialized world state is preserved as base64.

    Parameters
    ----------
    source : Path
        The source ``.xxx`` file.
    dest_dir : Path
        The directory the JSON is written to.

    Returns
    -------
    Path
        The written JSON path.
    """
    data = source.read_bytes()
    obj = _base(data, 'incoming-debug-snapshot')
    if len(data) >= _U32.size:
        obj['lead_count'] = _U32.unpack_from(data, 0)[0]
    return _write_json(source, dest_dir, obj)


def lev_to_json(source: Path, dest_dir: Path) -> Path:
    """
    Convert an Incoming ``.lev`` level-state snapshot to JSON.

    The file is a flat image of the live mission/world-state region with no structured header, so it
    is preserved as base64.

    Parameters
    ----------
    source : Path
        The source ``.lev`` file.
    dest_dir : Path
        The directory the JSON is written to.

    Returns
    -------
    Path
        The written JSON path.
    """
    return _write_json(source, dest_dir, _base(source.read_bytes(), 'incoming-level-snapshot'))


def cfg_to_json(source: Path, dest_dir: Path) -> Path:
    """
    Convert an Incoming ``.cfg`` configuration file to JSON.

    The leading build-stamp string is decoded; the ordered configuration blocks are preserved as
    base64.

    Parameters
    ----------
    source : Path
        The source ``.cfg`` file.
    dest_dir : Path
        The directory the JSON is written to.

    Returns
    -------
    Path
        The written JSON path.
    """
    data = source.read_bytes()
    obj = _base(data, 'incoming-config')
    end = data.find(b'\x00')
    if end > 0:
        obj['build_stamp'] = data[:end].decode('latin-1')
    return _write_json(source, dest_dir, obj)
