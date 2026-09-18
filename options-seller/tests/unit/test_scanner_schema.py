from __future__ import annotations

import json
from pathlib import Path

from options_seller.models.scanner import SCHEMA_ID, ScanEnvelope

FIXTURES = Path(__file__).parent.parent / "fixtures"
LIVE = Path("/workspace/stock-data-scanner/scan-latest.json")
EXAMPLE_LIVE = Path(__file__).parent.parent.parent / "examples" / "scan-latest.json"


def test_sample_fixture_is_v01():
    data = json.loads((FIXTURES / "sample_scan.json").read_text())
    env = ScanEnvelope.load(data)
    assert env.schema_ == SCHEMA_ID
    assert len(env.results) >= 1
    r = env.results[0]
    assert r.options.iv is None or isinstance(r.options.iv, float)
    # null suggested is fine
    assert r.options.suggested is None or r.options.suggested_legs()


def test_live_scan_parses():
    path = LIVE if LIVE.exists() else EXAMPLE_LIVE
    data = json.loads(path.read_text())
    env = ScanEnvelope.load(data)
    assert env.schema_ == SCHEMA_ID
    assert env.results
    for r in env.results:
        # Never invent — nulls stay null
        assert r.options.suggested is None or isinstance(r.options.suggested, (list, dict))


def test_bare_list_wraps():
    env = ScanEnvelope.load([{"symbol": "AAA", "price": 10.0}])
    assert env.schema_ == SCHEMA_ID
    assert env.results[0].symbol == "AAA"
