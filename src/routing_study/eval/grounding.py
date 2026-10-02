"""Deterministic anti-hallucination check (plan §4.4): every ID, amount and date in the final
answer must exist in the turn's structuredContent. Measures only; never rewrites the answer."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

# protocols (CAN-1A2B3C4D), tracking codes, boleto lines, order (O0001) and customer (C001)
# ids: an order id is supported only if the customer's profile, a tool result or the user's
# own words list it. Order/customer ids match case-insensitively (o0009 == O0009); the other
# codes stay upper-case so hyphenated words ("bem-vindo") are never read as protocols.
_ID = re.compile(r"\b(?:[A-Z]{2,5}-[0-9A-Z]{4,}|BR[0-9A-Z]{9}BR|\d{40,48})\b")
_PERSON_ID = re.compile(r"\b(?:O\d{4}|C\d{3})\b", re.IGNORECASE)
_MONEY = re.compile(r"R\$\s?(\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d+(?:[.,]\d{1,2})?)")
_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})")
_BR_DATE = re.compile(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{4}))?\b")
_THOUSANDS = re.compile(r"\d{1,3}(?:\.\d{3})+")
# installment fractions ("parcela 3/10", "3/10x", "3/10 parcelas") are not dates
_INSTALLMENT_BEFORE = re.compile(r"parcelas?\s*(?:n[º°o.]*\s*)?$")
_INSTALLMENT_AFTER = re.compile(r"\s*(?:x\b|parcelas?\b|pag[oa]s?\b)")  # "1/12 pago"


def _money(raw: str) -> float:
    if "," in raw or _THOUSANDS.fullmatch(raw):  # pt-BR: 1.299,90 / 1.299
        return round(float(raw.replace(".", "").replace(",", ".")), 2)
    return round(float(raw), 2)


def _br_dates(text: str) -> Iterable[tuple[str, str, str]]:
    for m in _BR_DATE.finditer(text):
        d, mo, y = m.groups()
        before = text[max(0, m.start() - 15) : m.start()].casefold()
        after = text[m.end() : m.end() + 10].casefold()
        if (
            _INSTALLMENT_BEFORE.search(before)
            or _INSTALLMENT_AFTER.match(after)
            or not (1 <= int(d) <= 31 and 1 <= int(mo) <= 12)
        ):
            continue
        yield d, mo, y or ""


def _ids(text: str) -> set[tuple[str, Any]]:
    return {("id", m) for m in _ID.findall(text)} | {
        ("id", m.upper()) for m in _PERSON_ID.findall(text)
    }


def answer_facts(text: str) -> set[tuple[str, Any]]:
    facts = _ids(text)
    facts |= {("money", _money(m)) for m in _MONEY.findall(text)}
    facts |= {("date", f"{y}-{mo}-{d}") for y, mo, d in _ISO.findall(text)}
    for d, mo, y in _br_dates(text):
        md = f"{int(mo):02d}-{int(d):02d}"
        facts.add(("date", f"{y}-{md}") if y else ("date_md", md))
    return facts


def _walk(value: Any) -> Iterable[Any]:
    if isinstance(value, dict):
        for v in value.values():
            yield from _walk(v)
    elif isinstance(value, list):
        for v in value:
            yield from _walk(v)
    else:
        yield value


def evidence_facts(structured: Iterable[Any]) -> set[tuple[str, Any]]:
    facts: set[tuple[str, Any]] = set()
    for doc in structured:
        for v in _walk(doc):
            if isinstance(v, bool) or v is None:
                continue
            if isinstance(v, int | float):
                facts.add(("money", round(float(v), 2)))
                continue
            s = str(v)
            facts |= _ids(s)
            for y, mo, d in _ISO.findall(s):
                facts |= {("date", f"{y}-{mo}-{d}"), ("date_md", f"{mo}-{d}")}
            facts |= {("money", _money(m)) for m in _MONEY.findall(s)}
    return facts


def grounded(answer: str, structured: Iterable[Any]) -> tuple[bool, list[str]]:
    """(ok, unsupported facts)."""
    missing = sorted(f"{k}:{v}" for k, v in answer_facts(answer) - evidence_facts(structured))
    return not missing, missing
