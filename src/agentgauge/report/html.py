"""Build HTML safely: every dynamic value is escaped by one function, here.

Model output, case ids and error messages are untrusted. Code that builds the report never
concatenates them into markup; it passes them to :func:`tag` or :func:`text`, which escape
them. The only way to get unescaped text through is to wrap it in :class:`Markup`, which is
what :func:`tag` itself returns.
"""

from __future__ import annotations

import html
import re
from collections.abc import Iterable

_ATTRIBUTE_NAME = re.compile(r"^[a-zA-Z][a-zA-Z0-9-]*$")


class Markup(str):
    """HTML that is already safe: built by :func:`tag`, :func:`text` or :func:`join`."""

    __slots__ = ()


def esc(value: object) -> str:
    """Escape ``value`` for use as element text or inside a double-quoted attribute."""
    return html.escape(str(value), quote=True)


def text(value: object) -> Markup:
    """``value`` as safe HTML text. A :class:`Markup` is returned unchanged."""
    return value if isinstance(value, Markup) else Markup(esc(value))


def join(items: Iterable[object], separator: str = "") -> Markup:
    """Concatenate items, escaping any that are not already :class:`Markup`."""
    return Markup(separator.join(text(item) for item in items))


def tag(name: str, *children: object, **attributes: object) -> Markup:
    """An element with escaped children and attributes.

    An attribute named ``class_`` or ``for_`` is written without the underscore; other
    underscores become hyphens (``aria_label`` is ``aria-label``). ``True`` writes a bare
    attribute, ``False`` and ``None`` leave it out.
    """
    if not re.fullmatch(r"[a-z][a-z0-9]*", name):
        raise ValueError(f"not a valid element name: {name!r}")
    parts = [name]
    for key, value in attributes.items():
        attribute = key.rstrip("_").replace("_", "-")
        if not _ATTRIBUTE_NAME.match(attribute):
            raise ValueError(f"not a valid attribute name: {key!r}")
        if value is None or value is False:
            continue
        parts.append(attribute if value is True else f'{attribute}="{esc(value)}"')
    return Markup(f"<{' '.join(parts)}>{join(children)}</{name}>")
