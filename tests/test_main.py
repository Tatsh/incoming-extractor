from __future__ import annotations

from typing import TYPE_CHECKING

from incoming_extractor.dispatch import ConversionSummary
from incoming_extractor.main import main
from incoming_extractor.sources import PreparedSource, SourceError

if TYPE_CHECKING:
    from pathlib import Path

    from click.testing import CliRunner
    from pytest_mock import MockerFixture


def test_main_success(runner: CliRunner, mocker: MockerFixture, tmp_path: Path) -> None:
    source = tmp_path / 'in'
    source.mkdir()
    mocker.patch('incoming_extractor.main.prepare_source', return_value=PreparedSource(source, ()))
    mocker.patch('incoming_extractor.main.convert_tree',
                 return_value=ConversionSummary(2, 3, 0, 0, 0))
    result = runner.invoke(main, ['-o', str(tmp_path / 'out'), str(source)])
    assert result.exit_code == 0
    assert 'Converted 2' in result.output


def test_main_loose_files(runner: CliRunner, mocker: MockerFixture, tmp_path: Path) -> None:
    asset = tmp_path / 't.raw'
    asset.write_text('x')
    mocker.patch('incoming_extractor.main.prepare_source',
                 return_value=PreparedSource(None, (asset,)))
    convert_file = mocker.patch('incoming_extractor.main.convert_file',
                                return_value=ConversionSummary(1, 1, 0, 0, 0))
    result = runner.invoke(main, ['-o', str(tmp_path / 'out'), str(asset)])
    assert result.exit_code == 0
    convert_file.assert_called_once()


def test_main_source_error(runner: CliRunner, mocker: MockerFixture, tmp_path: Path) -> None:
    source = tmp_path / 'in'
    source.mkdir()
    mocker.patch('incoming_extractor.main.prepare_source', side_effect=SourceError('bad source'))
    result = runner.invoke(main, ['-o', str(tmp_path / 'out'), str(source)])
    assert result.exit_code == 1


def test_main_reports_failures(runner: CliRunner, mocker: MockerFixture, tmp_path: Path) -> None:
    source = tmp_path / 'in'
    source.mkdir()
    mocker.patch('incoming_extractor.main.prepare_source', return_value=PreparedSource(source, ()))
    mocker.patch('incoming_extractor.main.convert_tree',
                 return_value=ConversionSummary(0, 0, 0, 0, 1))
    result = runner.invoke(main, ['-o', str(tmp_path / 'out'), str(source)])
    assert result.exit_code == 1
