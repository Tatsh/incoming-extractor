"""Command-line interface."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import logging

from bascom import setup_logging
import click

from . import __version__
from .context import using_tool_paths
from .dispatch import ConversionSummary, convert_file, convert_tree
from .sources import SourceError, prepare_source
from .tools import ToolNotFoundError
from .utils import pluralize

__all__ = ('main',)

log = logging.getLogger(__name__)


@click.command(context_settings={'help_option_names': ('-h', '--help')})
@click.version_option(__version__)
@click.option('-d', '--debug', is_flag=True, help='Enable debug output.')
@click.option('-o',
              '--output',
              required=True,
              type=click.Path(file_okay=False, path_type=Path),
              help='Output directory; the source tree is mirrored into it.')
@click.option('--gdiextract-path',
              type=click.Path(exists=True, dir_okay=False, path_type=Path),
              help='Path to the gdiextract binary.')
@click.option('--spvr2png-path',
              type=click.Path(exists=True, dir_okay=False, path_type=Path),
              help='Path to the spvr2png binary.')
@click.option('--unshield-path',
              type=click.Path(exists=True, dir_okay=False, path_type=Path),
              help='Path to the unshield binary.')
@click.argument('source', type=click.Path(exists=True, path_type=Path, resolve_path=True))
def main(source: Path,
         output: Path,
         *,
         debug: bool = False,
         gdiextract_path: Path | None = None,
         spvr2png_path: Path | None = None,
         unshield_path: Path | None = None) -> None:
    """
    Extract and convert Incoming assets from SOURCE into the output directory.

    SOURCE may be a PC disc directory or ISO containing DATA1.CAB (or the DATA1.CAB itself), a
    Dreamcast GDI file, or a directory of already extracted PC or GD-ROM content. The source tree is
    mirrored into the output directory: recognised assets are converted and every other file is
    copied verbatim. The source is never modified.
    """  # noqa: DOC501
    setup_logging(debug=debug, loggers={'incoming_extractor': {}})
    output.mkdir(parents=True, exist_ok=True)
    summary = ConversionSummary(0, 0, 0, 0, 0)
    warned: set[str] = set()
    tools = {'gdiextract': gdiextract_path, 'spvr2png': spvr2png_path, 'unshield': unshield_path}
    with using_tool_paths(tools), TemporaryDirectory() as work:
        try:
            prepared = prepare_source(source, Path(work))
        except (SourceError, ToolNotFoundError) as e:
            log.error('%s', e)  # noqa: TRY400
            raise click.Abort from e
        if prepared.root is not None:
            summary += convert_tree(prepared.root, output)
        for asset in prepared.files:
            summary += convert_file(asset, output, asset.parent, warned)
    click.echo(f'Converted {pluralize(summary.converted, "file")} into '
               f'{pluralize(summary.produced, "output")}; copied {summary.copied} '
               f'(skipped {summary.skipped}), failed {summary.failed}.')
    if summary.failed:
        raise click.exceptions.Exit(1)
