from __future__ import annotations

import json
from pathlib import Path

import pytest

from options_seller.config import load_defaults
from options_seller.models.scanner import PortfolioContext, ScanEnvelope, ScanResult

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def cfg():
    return load_defaults()


@pytest.fixture
def sample_envelope() -> ScanEnvelope:
    data = json.loads((FIXTURES / "sample_scan.json").read_text(encoding="utf-8"))
    return ScanEnvelope.load(data)


@pytest.fixture
def portfolio() -> PortfolioContext:
    data = json.loads((FIXTURES / "portfolio.json").read_text(encoding="utf-8"))
    return PortfolioContext.model_validate(data)


@pytest.fixture
def by_symbol(sample_envelope):
    return {r.symbol: r for r in sample_envelope.results}


@pytest.fixture
def minimal_scan() -> ScanResult:
    data = json.loads((FIXTURES / "minimal_null_options.json").read_text(encoding="utf-8"))
    return ScanEnvelope.load(data).results[0]
