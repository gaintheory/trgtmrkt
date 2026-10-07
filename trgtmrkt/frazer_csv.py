"""Read a Frazer export without silently misaligning columns.

Real exports differ from tidy CSV in ways pandas handles badly:
  * every data row carries one extra trailing field, so pandas quietly treats
    the first column as an index and shifts every value one column left;
  * a stray quote in a comment can tear one record into fragments;
  * the same header name appears more than once.

Rows are kept only when their width matches the header (after dropping the one
trailing empty field). Anything else is skipped and reported by line number,
never by content, so the report is safe to paste.
"""
from __future__ import annotations

import csv
import io
from pathlib import Path

import pandas as pd


def _dedupe(headers: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    out = []
    for h in headers:
        h = h.strip()
        n = seen.get(h, 0)
        seen[h] = n + 1
        out.append(h if n == 0 else f"{h}.{n}")  # leftmost keeps its own name
    return out


def read_frazer(source: str | Path | io.TextIOBase) -> tuple[pd.DataFrame, list[str]]:
    """Returns (rows as strings, issues). Never raises on a bad row."""
    if isinstance(source, (str, Path)):
        with open(source, newline="", encoding="utf-8-sig", errors="replace") as f:
            table = list(csv.reader(f))
    else:
        table = list(csv.reader(source))
    if not table:
        return pd.DataFrame(), ["The file is empty."]
    headers = _dedupe(table[0])
    width = len(headers)
    rows, issues = [], []
    for i, row in enumerate(table[1:], start=2):
        if not any(c.strip() for c in row):
            continue  # blank line
        while len(row) > width and row[-1].strip() == "":
            row = row[:-1]
        if len(row) != width:
            issues.append(f"row {i}: {len(row)} fields where the header has {width}; skipped")
            continue
        rows.append(row)
    return pd.DataFrame(rows, columns=headers, dtype=str), issues
