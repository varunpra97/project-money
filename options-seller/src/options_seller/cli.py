"""CLI — paper / dry-run only; never places live broker orders."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from options_seller import __version__
from options_seller.config import load_defaults, merge_config
from options_seller.execution.paper import PaperExecutor
from options_seller.models.scanner import PortfolioContext, ScanEnvelope
from options_seller.selector import select_and_build
from options_seller.strategies import STRATEGY_REGISTRY

app = typer.Typer(
    name="options-seller",
    help="Paper options-selling strategies from stock-data-scanner.scan/v0.1 JSON. "
    "NOT FINANCIAL ADVICE. Never places live broker orders.",
    no_args_is_help=True,
)
strategies_app = typer.Typer(help="List available strategies")
scan_app = typer.Typer(help="Run selector against scanner JSON")
paper_app = typer.Typer(help="Paper portfolio status / close (dry-run only)")
risk_app = typer.Typer(help="Hard portfolio risk limits ($50k max open risk)")
app.add_typer(strategies_app, name="strategies")
app.add_typer(scan_app, name="scan")
app.add_typer(paper_app, name="paper")
app.add_typer(risk_app, name="risk")
console = Console()


@app.callback()
def main() -> None:
    """Options seller CLI (paper only)."""


@strategies_app.command("list")
def strategies_list() -> None:
    """List registered strategy modules."""
    table = Table(title="Strategies")
    table.add_column("Name")
    table.add_column("Class")
    for name, cls in STRATEGY_REGISTRY.items():
        table.add_row(name, cls.__name__)
    console.print(table)
    console.print(f"[dim]options-seller {__version__} — paper/dry-run only[/dim]")


def _load_portfolio(path: Optional[Path]) -> PortfolioContext:
    if path is None:
        return PortfolioContext()
    data = json.loads(path.read_text(encoding="utf-8"))
    return PortfolioContext.model_validate(data)


def _fmt_money(v: Optional[float]) -> str:
    if v is None:
        return "n/a (template)"
    return f"${v:,.2f}"


@scan_app.command("run")
def scan_run(
    input_path: Path = typer.Option(
        Path("/workspace/stock-data-scanner/scan-latest.json"),
        "--input",
        "-i",
        help="Path to scan JSON (stock-data-scanner.scan/v0.1). "
        "Default: /workspace/stock-data-scanner/scan-latest.json",
    ),
    portfolio_path: Optional[Path] = typer.Option(
        None, "--portfolio", "-p", help="Optional portfolio/capital context JSON"
    ),
    config_path: Optional[Path] = typer.Option(
        None, "--config", "-c", help="Optional YAML overrides"
    ),
    paper: bool = typer.Option(True, "--paper/--no-paper", help="Paper execute selected plans"),
    store: Path = typer.Option(
        Path("data/paper_portfolio.json"), "--store", help="Paper portfolio JSON path"
    ),
    slippage: float = typer.Option(0.02, "--slippage", help="Fractional slippage on credit"),
) -> None:
    """Select strategies from scanner output and optionally paper-fill."""
    raw = json.loads(input_path.read_text(encoding="utf-8"))
    envelope = ScanEnvelope.load(raw)
    cfg = load_defaults()
    if config_path:
        import yaml

        overrides = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        cfg = merge_config(cfg, overrides)

    portfolio = _load_portfolio(portfolio_path)
    executor = PaperExecutor(store_path=store, slippage=slippage) if paper else None

    console.print(
        f"[bold]Scan[/bold] schema={envelope.schema_!r} asOf={envelope.asOf} "
        f"results={len(envelope.results)}"
    )
    console.print("[yellow]DRY-RUN / PAPER ONLY — no live broker orders[/yellow]\n")

    any_hit = False
    for scan in envelope.results:
        sel = select_and_build(scan, cfg, portfolio)
        if sel is None:
            console.print(f"[dim]{scan.symbol}: skipped (earnings/filters/missing price)[/dim]")
            continue
        any_hit = True
        plan = sel.result.plan
        console.print(f"[bold cyan]{scan.symbol}[/bold cyan] → [green]{sel.strategy_name}[/green]")
        console.print(f"  reason: {sel.reason}")
        console.print(f"  bias={scan.bias.value} ivRank={scan.iv_rank} "
                      f"daysToEarnings={scan.days_to_earnings}")
        console.print(f"  template={plan.is_template} target_dte={plan.target_dte} "
                      f"target_delta={plan.target_delta}")
        for i, leg in enumerate(plan.legs, 1):
            console.print(
                f"  leg{i}: {leg.side.value} {leg.option_type} strike={leg.strike} "
                f"dte={leg.dte} delta={leg.delta} qty={leg.quantity} "
                f"{'(template)' if leg.template else ''}"
            )
        console.print(f"  max_profit={_fmt_money(plan.max_profit)}  "
                      f"max_loss={_fmt_money(plan.max_loss)}  "
                      f"capital={_fmt_money(plan.capital_required)}  "
                      f"net_premium={_fmt_money(plan.net_premium)}")
        console.print(f"  notes: {plan.notes}")

        if executor is not None:
            ticket = executor.execute(plan)
            console.print(
                f"  paper: status={ticket.status} fill_price={_fmt_money(ticket.fill_price)}"
            )
        console.print()

    if not any_hit:
        console.print("[yellow]No strategies selected for this scan.[/yellow]")
        raise typer.Exit(code=0)



@paper_app.command("status")
def paper_status(
    store: Path = typer.Option(
        Path("data/paper_portfolio.json"), "--store", help="Paper portfolio JSON path"
    ),
) -> None:
    """Show paper account summary and open positions."""
    from options_seller.portfolio.api import portfolio_greeks_est, summary_metrics

    executor = PaperExecutor(store_path=store)
    m = summary_metrics(executor)
    g = portfolio_greeks_est(executor)
    console.print("[yellow]PAPER / NOT LIVE[/yellow]")
    console.print(
        f"Net liq={_fmt_money(m['net_liquidation'])}  cash={_fmt_money(m['cash'])}  "
        f"day_pnl={_fmt_money(m['day_pnl'])}  unrealized={_fmt_money(m['unrealized_pnl'])}  "
        f"realized={_fmt_money(m['realized_pnl'])}"
    )
    console.print(
        f"Premium collected={_fmt_money(m['premium_collected'])}  "
        f"open={m['open_positions']}  capital_secured={_fmt_money(m['capital_secured'])}"
    )
    console.print(
        f"Greeks EST. Δ={g['delta']:+.1f} Θ={g['theta']:+.2f} "
        f"Γ={g['gamma']:+.2f} ν={g['vega']:+.2f}"
    )
    table = Table(title="Open positions")
    for col in ("id", "symbol", "strategy", "credit", "unrealized", "status", "dte"):
        table.add_column(col)
    for p in executor.list_open():
        table.add_row(
            (p.get("id") or "")[:8],
            str(p.get("underlying")),
            str(p.get("strategy")),
            _fmt_money(p.get("credit")),
            _fmt_money(p.get("unrealized_pnl")),
            str(p.get("status")),
            str(p.get("dte") if p.get("dte") is not None else "n/a"),
        )
    console.print(table)


@paper_app.command("close")
def paper_close(
    position_id: str = typer.Argument(..., help="Position id (full or unique prefix)"),
    price: Optional[float] = typer.Option(
        None, "--price", help="Debit to buy back; default = mark / EST"
    ),
    store: Path = typer.Option(
        Path("data/paper_portfolio.json"), "--store", help="Paper portfolio JSON path"
    ),
) -> None:
    """Close a paper position by id."""
    executor = PaperExecutor(store_path=store)
    match = None
    for p in executor.list_open():
        pid = p.get("id") or ""
        if pid == position_id or pid.startswith(position_id):
            match = p
            break
    if match is None:
        console.print(f"[red]No open position matching {position_id!r}[/red]")
        raise typer.Exit(code=1)
    closed = executor.close_position(match["id"], price=price)
    console.print(
        f"[green]Closed[/green] {closed.get('underlying')} {closed.get('strategy')} "
        f"realized={_fmt_money(closed.get('realized_pnl'))}"
    )


@paper_app.command("seed")
def paper_seed(
    store: Path = typer.Option(
        Path("data/paper_portfolio.json"), "--store", help="Paper portfolio JSON path"
    ),
) -> None:
    """Seed demo paper positions for the dashboard."""
    from options_seller.portfolio.api import seed_demo_book

    executor = PaperExecutor(store_path=store)
    seeded = seed_demo_book(executor, reset=True)
    console.print(f"[green]Seeded {len(seeded)} open demo positions (+1 closed).[/green] store={store}")



@risk_app.command("status")
def risk_status(
    store: Path = typer.Option(
        Path("data/paper_portfolio.json"), "--store", help="Paper portfolio JSON path"
    ),
) -> None:
    """Show aggregate open risk vs $50k hard cap (soft warn at 80%)."""
    from options_seller.risk.limits import evaluate_book, risk_limits_from_config

    cfg = load_defaults()
    limits = risk_limits_from_config(cfg)
    executor = PaperExecutor(store_path=store, risk_limits=limits)
    book = evaluate_book(executor.portfolio.get("positions", []), limits)
    console.print("[yellow]PAPER / NOT LIVE — risk status[/yellow]")
    color = {"ok": "green", "soft_warn": "yellow", "hard_breach": "red"}.get(
        book["status"], "white"
    )
    console.print(
        f"Status: [{color}]{book['status']}[/{color}]  "
        f"aggregate={_fmt_money(book['aggregate_open_risk'])} / "
        f"{_fmt_money(book['max_portfolio_risk_usd'])}  "
        f"({book['utilization_pct']}%)  headroom={_fmt_money(book['headroom'])}"
    )
    console.print(
        f"Soft warn @ {_fmt_money(book['soft_warn_usd'])} "
        f"({book['soft_warn_pct']*100:.0f}%)  open={book['open_count']}  "
        f"auto_trim={book['auto_trim']}"
    )
    if book["trim_targets"]:
        console.print(
            f"[red]Trim targets ({len(book['trim_targets'])}):[/red] "
            + ", ".join(t[:8] for t in book["trim_targets"])
        )
    table = Table(title="Open positions by risk")
    for col in ("id", "symbol", "strategy", "risk", "max_loss", "capital"):
        table.add_column(col)
    for p in book["positions_by_risk"]:
        table.add_row(
            (p.get("id") or "")[:8],
            str(p.get("underlying")),
            str(p.get("strategy")),
            _fmt_money(p.get("risk")),
            _fmt_money(p.get("max_loss")),
            _fmt_money(p.get("capital")),
        )
    console.print(table)


@risk_app.command("enforce")
def risk_enforce(
    store: Path = typer.Option(
        Path("data/paper_portfolio.json"), "--store", help="Paper portfolio JSON path"
    ),
) -> None:
    """Close highest-risk open positions until aggregate risk <= $50k hard cap."""
    from options_seller.risk.enforce import enforce_hard_limits
    from options_seller.risk.limits import risk_limits_from_config

    cfg = load_defaults()
    limits = risk_limits_from_config(cfg)
    executor = PaperExecutor(store_path=store, risk_limits=limits)
    result = enforce_hard_limits(executor, limits)
    console.print("[yellow]PAPER / NOT LIVE — risk enforce[/yellow]")
    console.print(result["message"])
    before = result["before"]
    after = result["after"]
    console.print(
        f"Before: {_fmt_money(before['aggregate_open_risk'])} "
        f"({before['status']}) → After: {_fmt_money(after['aggregate_open_risk'])} "
        f"({after['status']})  headroom={_fmt_money(after['headroom'])}"
    )
    for a in result["actions"]:
        console.print(
            f"  trimmed {a.get('underlying')} {a.get('strategy')} "
            f"freed={_fmt_money(a.get('risk_freed'))} "
            f"realized={_fmt_money(a.get('realized_pnl'))}"
        )



if __name__ == "__main__":
    app()
