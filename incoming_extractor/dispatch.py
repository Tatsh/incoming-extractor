"""Mirror a source tree into an output directory, converting or copying each file."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple
import logging
import shutil

from typing_extensions import override

from .context import using_input_root
from .converters import RULES, ConversionError, UnsupportedFormatError
from .utils import pluralize

if TYPE_CHECKING:
    from .converters import Rule

__all__ = ('ConversionSummary', 'convert_file', 'convert_tree')

log = logging.getLogger(__name__)


class ConversionSummary(NamedTuple):
    """Totals from mirroring a source tree into an output directory."""

    converted: int
    """Number of source files successfully converted."""
    produced: int
    """Number of converted output files written."""
    copied: int
    """Number of files copied verbatim (no converter, or not yet decoded)."""
    skipped: int
    """Number of matched files whose format is documented but not yet decoded."""
    failed: int
    """Number of matched files that errored during conversion (copied verbatim instead)."""
    @override
    def __add__(self, other: object) -> ConversionSummary:
        """
        Add two summaries field by field.

        Returns
        -------
        ConversionSummary
            The element-wise sum of the two summaries.
        """
        if not isinstance(other, ConversionSummary):
            return NotImplemented
        return ConversionSummary(*(a + b for a, b in zip(self, other, strict=True)))


def _match_rule(path: Path) -> Rule | None:
    return next((rule for rule in RULES if rule.match(path)), None)


def _copy(source: Path, dest_dir: Path) -> None:
    shutil.copy2(source, dest_dir / source.name)


def convert_file(source: Path, dest_dir: Path, input_root: Path,
                 warned: set[str]) -> ConversionSummary:
    """
    Convert or copy a single file into *dest_dir*.

    Parameters
    ----------
    source : Path
        The source file.
    dest_dir : Path
        The destination directory (already created).
    input_root : Path
        The root of the source tree, used to resolve sibling assets such as textures.
    warned : set[str]
        Format names already warned about, mutated to suppress duplicate warnings.

    Returns
    -------
    ConversionSummary
        The totals contributed by this file.
    """
    if (rule := _match_rule(source)) is None:
        _copy(source, dest_dir)
        return ConversionSummary(0, 0, 1, 0, 0)
    try:
        with using_input_root(input_root):
            result = rule.convert(source, dest_dir)
    except UnsupportedFormatError as e:
        if rule.name not in warned:
            warned.add(rule.name)
            log.warning('Copying %s files unconverted: %s', rule.name, e)
        _copy(source, dest_dir)
        return ConversionSummary(0, 0, 1, 1, 0)
    except ConversionError as e:
        log.error('%s', e)  # noqa: TRY400
        _copy(source, dest_dir)
        return ConversionSummary(0, 0, 1, 0, 1)
    produced = 1 if isinstance(result, Path) else len(result)
    log.debug('Converted `%s` to %s.', source, pluralize(produced, 'file'))
    return ConversionSummary(1, produced, 0, 0, 0)


def convert_tree(input_root: Path, output_root: Path) -> ConversionSummary:
    """
    Mirror *input_root* into *output_root*, converting recognised files and copying the rest.

    The output tree reproduces the input directory structure. Converted files are written at the
    mirrored location; every other file (including formats not yet decoded) is copied verbatim.

    Parameters
    ----------
    input_root : Path
        The directory to mirror.
    output_root : Path
        The directory to write the mirror into.

    Returns
    -------
    ConversionSummary
        The aggregate totals.
    """
    summary = ConversionSummary(0, 0, 0, 0, 0)
    warned: set[str] = set()
    for source in sorted(input_root.rglob('*')):
        if not source.is_file():
            continue
        dest_dir = output_root / source.relative_to(input_root).parent
        dest_dir.mkdir(parents=True, exist_ok=True)
        summary += convert_file(source, dest_dir, input_root, warned)
    return summary
