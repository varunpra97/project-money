"""Celebrity portfolio priority rows for the Stock Data Scanner dashboard.

Encoded from celebrity-portfolio-scan-2026-09-18.md — do not invent moves.
"""

from __future__ import annotations

from pathlib import Path

SCAN_DATE = "2026-09-18"
SOURCE_REPORT = Path(__file__).resolve().parent / "celebrity-priority-2026-09-18.md"
SOURCE_REPORT_NOTE = (
    "Encoded from /workspace/celebrity-portfolio-scan-2026-09-18.md "
    "(copy: celebrity-priority-2026-09-18.md in this project)."
)

# Ranked top 12 + honorable mentions (FDXF, V, MA, SPGI, AVGO).
# Keys: rank, symbol, company, investor, what_changed, period, why, honorable
PRIORITY_ROWS: list[dict] = [
    {
        "rank": 1,
        "symbol": "SPCX",
        "company": "Space Exploration Technologies (SpaceX)",
        "investor": "Cathie Wood / ARK Invest (also NVIDIA, Coatue, Altimeter, Tiger, Appaloosa line items)",
        "what_changed": "NEW reportable public stake; ARK ~4.48M shares / ~$765M (~5% of ARK book)",
        "period": "IPO Nasdaq 2026-06-12; 13F as of 2026-06-30, filed 2026-08-14",
        "why": (
            "Largest IPO on record (~$1.75T); first retail-visible SpaceX tape; "
            "ARK made it a top-3 holding; mega-fund 13Fs suddenly show huge SPCX lines "
            "(many may be pre-IPO converts becoming reportable)"
        ),
        "honorable": False,
    },
    {
        "rank": 2,
        "symbol": "AMZN",
        "company": "Amazon.com",
        "investor": "Stanley Druckenmiller (Duquesne); Peter Thiel (Thiel Macro); David Tepper (Appaloosa); Bill Ackman (Pershing)",
        "what_changed": (
            "Druckenmiller +1,083% shares (45.8K → 541.6K, ~$129M); "
            "Thiel rebuilt book with AMZN as #1 (~$118M / 28%); "
            "Tepper top hold + add; Ackman trimmed ~25% but still top-5"
        ),
        "period": "Q2 2026 (filed mid-Aug); Motley Fool / Altcoinvest coverage 2026-09-17–18",
        "why": "Cross-celebrity consensus buy + Ackman trim = high dashboard attention; AWS/AI narrative",
        "honorable": False,
    },
    {
        "rank": 3,
        "symbol": "GOOGL",
        "company": "Alphabet (GOOGL / GOOG)",
        "investor": "Warren Buffett / Greg Abel (Berkshire); Bill Ackman; Stanley Druckenmiller; Tiger Global",
        "what_changed": (
            "Berkshire +~83% shares (~48M added) → ~$38B combined, #3 holding; "
            "Ackman full exit; Druckenmiller re-initiated after Q1 exit; Tiger cut ~45%"
        ),
        "period": "Q2 2026",
        "why": (
            "Sharpest “celebrity disagreement” name of the quarter — "
            "Buffett/Abel piled in while Ackman sold out"
        ),
        "honorable": False,
    },
    {
        "rank": 4,
        "symbol": "NFLX",
        "company": "Netflix",
        "investor": "Bill Ackman / Pershing Square",
        "what_changed": "NEW ~13.1M shares / ~$934M",
        "period": "Q2 2026",
        "why": "Rare large new position from a high-profile concentrated manager; Tiger fully exited same quarter",
        "honorable": False,
    },
    {
        "rank": 5,
        "symbol": "META",
        "company": "Meta Platforms",
        "investor": "Bill Ackman / Pershing Square",
        "what_changed": "ADD ~+20% shares (~$1.8B position)",
        "period": "Q2 2026",
        "why": "Contrarian add into lagging Mag-7 name; paired with NFLX initiation and GOOGL exit",
        "honorable": False,
    },
    {
        "rank": 6,
        "symbol": "CBRS",
        "company": "Cerebras Systems",
        "investor": "Brad Gerstner / Altimeter; Coatue; Tiger Global",
        "what_changed": "NEW large institutional stakes; Altimeter made CBRS #2 holding (~$1.60B); Coatue ~$1.55B new",
        "period": "IPO ~2026-05-14; 13F Q2 2026",
        "why": "Fresh AI-chip IPO absorbing celebrity-adjacent hedge-fund capital; high retail curiosity",
        "honorable": False,
    },
    {
        "rank": 7,
        "symbol": "HD",
        "company": "Home Depot",
        "investor": "Bill Gates / Cascade Investment",
        "what_changed": "NEW ~$353M (~1% of Cascade book)",
        "period": "Q2 2026 (filed 2026-08-14)",
        "why": (
            "First Cascade HD stake reported; funded alongside FDXF while trimming BRK/WM — "
            "Gates name moves retail flows"
        ),
        "honorable": False,
    },
    {
        "rank": 8,
        "symbol": "INTC",
        "company": "Intel",
        "investor": "Paul/Nancy Pelosi household; Coatue; Tiger; NVIDIA corporate book",
        "what_changed": (
            "Pelosi buys May 29 ($1–5M) and Jul 24 ($0.5–1M + $0.25–0.5M); "
            "Coatue NEW ~$1.69B; Tiger shares +160%"
        ),
        "period": "STOCK Act May–Jul 2026; 13F Q2",
        "why": "Dual celebrity + mega-fund tape; NVIDIA still holds huge INTC line",
        "honorable": False,
    },
    {
        "rank": 9,
        "symbol": "UBER",
        "company": "Uber Technologies",
        "investor": "Bill Ackman (largest Pershing position); Paul/Nancy Pelosi",
        "what_changed": (
            "Ackman +~15%, still #1 hold (~$2.48B / ~12.7%); "
            "Pelosi household buy $0.5–1M disclosed 2026-05-29"
        ),
        "period": "Q2 2026 + May 2026 disclosure",
        "why": (
            "Celebrity-investor + political-household overlap; "
            "long celebrity-VC history (Kutcher/Jay-Z era) keeps narrative sticky"
        ),
        "honorable": False,
    },
    {
        "rank": 10,
        "symbol": "VST",
        "company": "Vistra",
        "investor": "Peter Thiel / Thiel Macro; Paul/Nancy Pelosi",
        "what_changed": (
            "Thiel Macro new concentrated power book: VST ~$59.1M (~14%); "
            "Pelosi buy $100–250K (disclosed 2026-01-16)"
        ),
        "period": "Q2 2026 rebuild (after two empty quarters); Jan 2026 Pelosi",
        "why": (
            "Thiel’s sudden return to a power/nuclear-tilted book is attention-grabbing; "
            "VST is the liquid flagship of that theme"
        ),
        "honorable": False,
    },
    {
        "rank": 11,
        "symbol": "TEM",
        "company": "Tempus AI",
        "investor": "Cathie Wood / ARK; Paul/Nancy Pelosi",
        "what_changed": "ARK #4 hold ~$581M, +4.3% shares; Pelosi buy $50–100K (2026-01-16)",
        "period": "Q2 2026 / Jan 2026",
        "why": "ARK conviction name + political disclosure overlap; AI/health crossover retail interest",
        "honorable": False,
    },
    {
        "rank": 12,
        "symbol": "BE",
        "company": "Bloom Energy",
        "investor": "Paul/Nancy Pelosi household",
        "what_changed": (
            "Multiple buys late Jul 2026: Jul 24 ($1–5M ×2) and Jul 28 ($0.5–1M ×2) — "
            "most recent high-profile disclosure in this scan"
        ),
        "period": "Disclosed trade dates 2026-07-24 and 2026-07-28",
        "why": (
            "Freshest “celebrity/political portfolio” flow signal vs stale June 30 13Fs; "
            "clean-energy / power theme rhymes with Thiel’s VST book"
        ),
        "honorable": False,
    },
    # Honorable mentions (not in top 12)
    {
        "rank": None,
        "symbol": "FDXF",
        "company": "FedEx Freight Holding",
        "investor": "Bill Gates / Cascade Investment",
        "what_changed": "NEW ~$180M; newly spun off 2026-06-01, NYSE",
        "period": "Q2 2026; spin-off 2026-06-01",
        "why": "Cascade new stake in newly listed FedEx Freight spin-off — optional follow-on to HD",
        "honorable": True,
    },
    {
        "rank": None,
        "symbol": "V",
        "company": "Visa",
        "investor": "Bill Ackman / Pershing Square",
        "what_changed": "NEW ~$1.1B-class position",
        "period": "Q2 2026",
        "why": "Ackman payments/ratings overhaul — NEW large Visa stake",
        "honorable": True,
    },
    {
        "rank": None,
        "symbol": "MA",
        "company": "Mastercard",
        "investor": "Bill Ackman / Pershing Square",
        "what_changed": "NEW ~$1.1B-class position",
        "period": "Q2 2026",
        "why": "Ackman payments/ratings overhaul — NEW large Mastercard stake",
        "honorable": True,
    },
    {
        "rank": None,
        "symbol": "SPGI",
        "company": "S&P Global",
        "investor": "Bill Ackman / Pershing Square",
        "what_changed": "NEW ~$1.1B-class position",
        "period": "Q2 2026",
        "why": "Ackman payments/ratings overhaul — NEW large S&P Global stake",
        "honorable": True,
    },
    {
        "rank": None,
        "symbol": "AVGO",
        "company": "Broadcom",
        "investor": "Stanley Druckenmiller (Duquesne)",
        "what_changed": "Full exit (~196K shares) after short hold",
        "period": "Q2 2026; Motley Fool coverage 2026-09-17",
        "why": "Druckenmiller full exit after short hold — sell-side attention (paired with AMZN add)",
        "honorable": True,
    },
]


def priority_only() -> list[dict]:
    return [r for r in PRIORITY_ROWS if not r.get("honorable")]


def honorable_only() -> list[dict]:
    return [r for r in PRIORITY_ROWS if r.get("honorable")]


def symbols() -> list[str]:
    return [r["symbol"] for r in PRIORITY_ROWS]
