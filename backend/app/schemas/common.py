"""Field types shared by the request and the plan."""

import re
from datetime import date
from typing import Annotated, Any

from pydantic import AfterValidator, BeforeValidator, Field

from app.ctgov.essie import clean_term
from app.registry.enums import LabelledEnum

MAX_TERMS = 10
MAX_TERM_LENGTH = 200
MIN_YEAR = 1900


def _clean(value: str) -> str:
    cleaned = clean_term(value)
    if not cleaned:
        raise ValueError("must not be blank")
    if len(cleaned) > MAX_TERM_LENGTH:
        raise ValueError(f"must be at most {MAX_TERM_LENGTH} characters")
    return cleaned


def _as_list(value: Any) -> Any:
    return [value] if isinstance(value, str) else value


def _max_year(year: int) -> int:
    if year > date.today().year + 10:
        raise ValueError("must be at most 10 years from now")
    return year


Term = Annotated[str, AfterValidator(_clean)]
TermList = Annotated[list[Term], BeforeValidator(_as_list), Field(max_length=MAX_TERMS)]
Year = Annotated[int, Field(ge=MIN_YEAR), AfterValidator(_max_year)]


def _key(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def lenient(enum: type[LabelledEnum]) -> BeforeValidator:
    """Accept an enum code or its label, ignoring case, spaces and punctuation."""
    lookup = {_key(m.value): m for m in enum} | {_key(m.label): m for m in enum}

    def parse(value: Any) -> Any:
        return lookup.get(_key(value), value) if isinstance(value, str) else value

    return BeforeValidator(parse)
