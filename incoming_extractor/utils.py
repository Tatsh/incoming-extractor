"""Small shared helpers."""
from __future__ import annotations

__all__ = ('pluralize',)


def pluralize(count: int, noun: str) -> str:
    """
    Format a count with a regularly pluralised noun.

    Parameters
    ----------
    count : int
        The quantity.
    noun : str
        The singular form of the noun; an ``s`` is appended when *count* is not 1.

    Returns
    -------
    str
        The count followed by the noun, pluralised when *count* is not 1.
    """
    return f'{count} {noun}' if count == 1 else f'{count} {noun}s'
