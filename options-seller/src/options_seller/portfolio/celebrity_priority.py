"""Celebrity / priority watchlist overlay for the Command Center.

Paper-dashboard only — labels candidates and optional position badges.
Never invents share counts or disclosure details.
"""

from __future__ import annotations

from typing import Any, Optional

# Primary priority symbols (Candidates ⭐ badge)
PRIORITY_SYMBOLS: frozenset[str] = frozenset(
    {
        "SPCX",
        "AMZN",
        "GOOGL",
        "GOOG",
        "NFLX",
        "META",
        "CBRS",
        "HD",
        "INTC",
        "UBER",
        "VST",
        "TEM",
        "BE",
    }
)

# Honorable mentions — not full priority, but surface a caution when seen
HONORABLE_MENTIONS: frozenset[str] = frozenset({"FDXF"})

# Dual-class share pairs → preferred rollup key
DUAL_CLASS_NORMALIZE: dict[str, str] = {
    "GOOG": "GOOGL",
    "GOOGL": "GOOGL",
}

# Short caution captions keyed by symbol (shown under Candidates row)
CAUTION_NOTES: dict[str, str] = {
    "SPCX": "New listing — caution volume / lockup / options availability",
    "CBRS": "New listing — caution volume / lockup / options availability",
    "FDXF": "Spin-off / thin liquidity (honorable mention)",
    "GOOGL": "Dual class (GOOGL/GOOG) — don't double-count in rollups",
    "GOOG": "Dual class (GOOGL/GOOG) — don't double-count in rollups",
    "NFLX": "Prefer split-aware history if charting (N/A for paper marks)",
    "VST": "Prefer options / relative-volume columns when scan provides them",
    "BE": "Prefer options / relative-volume columns when scan provides them",
    "TEM": "Prefer options / relative-volume columns when scan provides them",
}

# Pelosi-linked names: disclosure lag only — never invent share counts
PELOSI_LINKED: frozenset[str] = frozenset({"INTC", "UBER", "VST", "TEM", "BE"})
PELOSI_DISCLOSURE_NOTE = (
    "Public-disclosure lag — do not invent share counts or timing"
)

# Columns to prefer highlighting when scan row has them
PREFERRED_SCAN_COLS: tuple[str, ...] = (
    "options_volume",
    "option_volume",
    "rel_volume",
    "relative_volume",
    "avg_volume",
    "iv_rank",
)


def normalize_symbol(symbol: str | None) -> str:
    if not symbol:
        return ""
    return str(symbol).strip().upper()


def is_priority(symbol: str | None) -> bool:
    return normalize_symbol(symbol) in PRIORITY_SYMBOLS


def is_honorable_mention(symbol: str | None) -> bool:
    return normalize_symbol(symbol) in HONORABLE_MENTIONS


def rollup_ticker(symbol: str | None) -> str:
    """Normalize dual-class tickers for performance rollups (GOOG→GOOGL)."""
    sym = normalize_symbol(symbol)
    return DUAL_CLASS_NORMALIZE.get(sym, sym or "?")


def caution_for(symbol: str | None) -> Optional[str]:
    """Short caution caption for Candidates / tooltips, or None."""
    sym = normalize_symbol(symbol)
    parts: list[str] = []
    note = CAUTION_NOTES.get(sym)
    if note:
        parts.append(note)
    if sym in PELOSI_LINKED:
        parts.append(PELOSI_DISCLOSURE_NOTE)
    if not parts and sym in HONORABLE_MENTIONS:
        parts.append(CAUTION_NOTES.get(sym) or "Honorable mention — thin liquidity")
    return " · ".join(parts) if parts else None


def priority_badge(symbol: str | None) -> Optional[str]:
    """Return badge text for UI, or None if not priority/honorable."""
    sym = normalize_symbol(symbol)
    if sym in PRIORITY_SYMBOLS:
        return "⭐ Priority"
    if sym in HONORABLE_MENTIONS:
        return "◇ Mention"
    return None


def celebrity_overlay(symbol: str | None) -> dict[str, Any]:
    """One-shot dict for dashboard rows."""
    sym = normalize_symbol(symbol)
    return {
        "symbol": sym,
        "is_priority": sym in PRIORITY_SYMBOLS,
        "is_honorable": sym in HONORABLE_MENTIONS,
        "badge": priority_badge(sym),
        "caution": caution_for(sym),
        "rollup_ticker": rollup_ticker(sym),
        "pelosi_linked": sym in PELOSI_LINKED,
        "prefer_volume_cols": sym in {"VST", "BE", "TEM", "SPCX", "CBRS"},
    }
