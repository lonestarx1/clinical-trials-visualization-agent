"""Essie search expressions as a tree (design Q7, D7.1).

Queries are built from nodes and serialised by `to_essie`, never by string
concatenation. User text only ever enters through `Phrase`, which is always a
single quoted phrase, so it can't change the structure of the query.
"""

import re
import unicodedata
from dataclasses import dataclass

_FIELD = re.compile(r"[A-Za-z][A-Za-z0-9]*")
_CODE = re.compile(r"[A-Z][A-Z0-9_]*|true|false")
_BOUND = re.compile(r"MIN|MAX|\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])")
# Characters that could end the phrase or escape the next one; they have no meaning in names.
_UNSAFE = re.compile(r'["\\]|[\x00-\x1f\x7f]')


def clean_term(text: str) -> str:
    """Unicode-normalise, drop quote/backslash/control characters, collapse whitespace."""
    text = _UNSAFE.sub(" ", unicodedata.normalize("NFKC", text))
    return " ".join(text.split())


@dataclass(frozen=True)
class Phrase:
    """A user-supplied term, matched as one quoted phrase."""

    text: str

    def __post_init__(self) -> None:
        cleaned = clean_term(self.text)
        if not cleaned:
            raise ValueError("search term is empty after cleaning")
        object.__setattr__(self, "text", cleaned)


@dataclass(frozen=True)
class Code:
    """An enum code or boolean from our registry (never user text)."""

    value: str

    def __post_init__(self) -> None:
        if not _CODE.fullmatch(self.value):
            raise ValueError(f"not an enum code: {self.value!r}")


@dataclass(frozen=True)
class Range:
    lo: str
    hi: str

    def __post_init__(self) -> None:
        for bound in (self.lo, self.hi):
            if not _BOUND.fullmatch(bound):
                raise ValueError(f"range bound must be YYYY-MM-DD, MIN or MAX: {bound!r}")


@dataclass(frozen=True)
class Missing:
    pass


@dataclass(frozen=True)
class Area:
    field: str
    term: "Phrase | Code | Range | Missing"

    def __post_init__(self) -> None:
        if not _FIELD.fullmatch(self.field):
            raise ValueError(f"not a field name: {self.field!r}")


@dataclass(frozen=True)
class And:
    items: "list[Node]"

    def __post_init__(self) -> None:
        if not self.items:
            raise ValueError("AND needs at least one item")


@dataclass(frozen=True)
class Or:
    items: "list[Node]"

    def __post_init__(self) -> None:
        if not self.items:
            raise ValueError("OR needs at least one item")


@dataclass(frozen=True)
class Not:
    item: "Node"


Node = Phrase | Code | Range | Missing | Area | And | Or | Not


# Codes Essie reads as an operator unless quoted. Measured: AREA[Sex]ALL matched every trial,
# AREA[Sex]"ALL" the trials open to all sexes. NONE, NA and the booleans match as plain codes.
QUOTED_CODES = {"ALL"}


def to_essie(node: Node) -> str:
    match node:
        case Phrase(text):
            return f'"{text}"'
        case Code(value):
            return f'"{value}"' if value in QUOTED_CODES else value
        case Range(lo, hi):
            return f"RANGE[{lo},{hi}]"
        case Missing():
            return "MISSING"
        case Area(field, term):
            return f"AREA[{field}]{to_essie(term)}"
        case Not(item):
            return f"NOT {to_essie(item)}"
        case And(items) | Or(items):
            if len(items) == 1:
                return to_essie(items[0])
            op = " AND " if isinstance(node, And) else " OR "
            return "(" + op.join(to_essie(i) for i in items) + ")"
    raise TypeError(f"not an Essie node: {node!r}")
