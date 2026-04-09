"""
Indian-style financial year: begins 1 April; Jan–Mar belong to FY starting previous calendar year.
Example: 15 Jan 2026 → FY 2025–26 (1 Apr 2025 – 31 Mar 2026).
"""
from __future__ import annotations

from datetime import date
from typing import Tuple


def financial_year_start(d: date) -> date:
    """First day of the financial year containing date ``d``."""
    if d.month >= 4:
        return date(d.year, 4, 1)
    return date(d.year - 1, 4, 1)


def financial_year_end(d: date) -> date:
    """Last day of the financial year containing date ``d`` (31 March)."""
    start = financial_year_start(d)
    return date(start.year + 1, 3, 31)


def financial_year_label(d: date) -> str:
    """Short label e.g. '2025-26' for the FY containing ``d``."""
    start = financial_year_start(d)
    y2 = start.year + 1
    return f"{start.year}-{str(y2)[-2:]}"


def financial_year_bounds(d: date) -> Tuple[date, date]:
    """Return (start, end) inclusive for the FY containing ``d``."""
    return financial_year_start(d), financial_year_end(d)
