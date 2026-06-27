from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from incoming_extractor.dispatch import ConversionSummary, convert_file, convert_tree
from incoming_extractor.test_utils import ctl_records, pvr_pack, pvrt_chunk
import pytest

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def test_summary_add() -> None:
    assert ConversionSummary(1, 2, 3, 4, 5) + ConversionSummary(1, 1, 1, 1, 1) == ConversionSummary(
        2, 3, 4, 5, 6)


def test_summary_add_not_implemented() -> None:
    with pytest.raises(TypeError):
        _ = ConversionSummary(0, 0, 0, 0, 0) + 5


def test_convert_file_no_rule(tmp_path: Path) -> None:
    source = tmp_path / 'a.mdl'
    source.write_text('text')
    dest = tmp_path / 'out'
    dest.mkdir()
    assert convert_file(source, dest, tmp_path, set()) == ConversionSummary(0, 0, 1, 0, 0)
    assert (dest / 'a.mdl').read_text() == 'text'


def test_convert_file_converted(tmp_path: Path) -> None:
    source = tmp_path / 'p.ctl'
    source.write_bytes(ctl_records(2))
    dest = tmp_path / 'out'
    dest.mkdir()
    summary = convert_file(source, dest, tmp_path, set())
    assert (summary.converted, summary.produced) == (1, 1)
    assert (dest / 'p.json').is_file()


def test_convert_file_skipped_warns_once(tmp_path: Path) -> None:
    source = tmp_path / 'x.bin'
    source.write_bytes(bytes(100))
    dest = tmp_path / 'out'
    dest.mkdir()
    warned: set[str] = set()
    first = convert_file(source, dest, tmp_path, warned)
    assert (first.copied, first.skipped) == (1, 1)
    assert 'terrain-bin' in warned
    assert (dest / 'x.bin').is_file()
    assert convert_file(source, dest, tmp_path, warned).skipped == 1


def test_convert_file_failed(tmp_path: Path) -> None:
    source = tmp_path / 'b.ctl'
    source.write_bytes(bytes(20))
    dest = tmp_path / 'out'
    dest.mkdir()
    summary = convert_file(source, dest, tmp_path, set())
    assert (summary.failed, summary.copied) == (1, 1)


def test_convert_file_name_matched_pack(tmp_path: Path, mocker: MockerFixture) -> None:
    source = tmp_path / 'AFRICA_T.PVR'  # matched by the _t.pvr name rule
    source.write_bytes(pvr_pack([pvrt_chunk(2, 2)]))
    mocker.patch('incoming_extractor.converters.images.find_spvr2png', return_value=Path('/spv'))

    def run(args: list[str], **_: object) -> object:
        raw_dir, dest = Path(args[2]), Path(args[4])
        for pvr in raw_dir.glob('*.pvr'):
            (dest / f'{pvr.stem}.png').write_bytes(b'PNG')
        return mocker.Mock()

    mocker.patch('incoming_extractor.converters.images.sp.run', side_effect=run)
    out = tmp_path / 'out'
    out.mkdir()
    assert convert_file(source, out, tmp_path, set()).converted == 1


def test_convert_tree(tmp_path: Path) -> None:
    root = tmp_path / 'in'
    (root / 'sub').mkdir(parents=True)
    (root / 'a.ctl').write_bytes(ctl_records(2))
    (root / 'sub' / 'b.mdl').write_text('x')
    out = tmp_path / 'out'
    summary = convert_tree(root, out)
    assert (out / 'a.json').is_file()
    assert (out / 'sub' / 'b.mdl').read_text() == 'x'
    assert (summary.converted, summary.copied) == (1, 1)
