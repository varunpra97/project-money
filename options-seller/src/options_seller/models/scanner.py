"""Scanner JSON schema locked to stock-data-scanner.scan/v0.1."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Optional, Union

from pydantic import BaseModel, Field, field_validator, model_validator


SCHEMA_ID = "stock-data-scanner.scan/v0.1"


class Bias(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class OptionRight(str, Enum):
    CALL = "call"
    PUT = "put"


class SideHint(str, Enum):
    BUY = "buy"
    SELL = "sell"


class TrendBlock(BaseModel):
    bias: Bias = Bias.NEUTRAL
    sma20: Optional[float] = None
    sma50: Optional[float] = None
    sma200: Optional[float] = None
    priceVsSma50Pct: Optional[float] = None


class LiquidityBlock(BaseModel):
    volume: Optional[float] = None
    avgVolume: Optional[float] = None
    volumeRatio: Optional[float] = None


class EarningsBlock(BaseModel):
    nextDate: Optional[date] = None
    daysToEarnings: Optional[int] = None

    @field_validator("nextDate", mode="before")
    @classmethod
    def parse_date(cls, v: Any) -> Any:
        if v is None or v == "":
            return None
        if isinstance(v, date) and not isinstance(v, datetime):
            return v
        if isinstance(v, datetime):
            return v.date()
        if isinstance(v, str):
            return date.fromisoformat(v[:10])
        return v


class SuggestedLeg(BaseModel):
    """Future options.suggested leg — never invent bid/ask/OI."""

    strike: float
    dte: int
    delta: Optional[float] = None
    premium: Optional[float] = None
    bid: Optional[float] = None
    ask: Optional[float] = None
    mid: Optional[float] = None
    openInterest: Optional[int] = None
    right: Optional[OptionRight] = None
    expiration: Optional[date] = None
    side: Optional[SideHint] = None
    strategyHint: Optional[str] = None

    @field_validator("expiration", mode="before")
    @classmethod
    def parse_exp(cls, v: Any) -> Any:
        if v is None or v == "":
            return None
        if isinstance(v, date) and not isinstance(v, datetime):
            return v
        if isinstance(v, str):
            return date.fromisoformat(v[:10])
        return v

    def resolved_mid(self) -> Optional[float]:
        if self.mid is not None:
            return self.mid
        if self.bid is not None and self.ask is not None:
            return (self.bid + self.ask) / 2.0
        if self.premium is not None:
            return abs(self.premium)
        return None

    def has_quotes(self) -> bool:
        return self.resolved_mid() is not None


class OptionsBlock(BaseModel):
    iv: Optional[float] = None
    ivRank: Optional[float] = None
    ivPercentile: Optional[float] = None
    impliedMovePct: Optional[float] = None
    # null, list of legs, or object with legs[]
    suggested: Optional[Union[list[SuggestedLeg], dict[str, Any]]] = None

    def suggested_legs(self) -> list[SuggestedLeg]:
        if self.suggested is None:
            return []
        if isinstance(self.suggested, list):
            return list(self.suggested)
        legs = self.suggested.get("legs") if isinstance(self.suggested, dict) else None
        if isinstance(legs, list):
            return [SuggestedLeg.model_validate(x) for x in legs]
        return []

    def suggested_strategy_name(self) -> Optional[str]:
        if isinstance(self.suggested, dict):
            return self.suggested.get("strategy") or self.suggested.get("name")
        return None


class MarkersBlock(BaseModel):
    available: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)


class ScanResult(BaseModel):
    """One row in stock-data-scanner.scan/v0.1 results[]."""

    symbol: str
    name: Optional[str] = None
    price: Optional[float] = None
    change: Optional[float] = None
    changePct: Optional[float] = None
    previousClose: Optional[float] = None
    open: Optional[float] = None
    dayHigh: Optional[float] = None
    dayLow: Optional[float] = None
    volume: Optional[float] = None
    avgVolume: Optional[float] = None
    marketCap: Optional[float] = None
    bid: Optional[float] = None
    ask: Optional[float] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    pe: Optional[float] = None
    eps: Optional[float] = None
    beta: Optional[float] = None
    dividendYield: Optional[float] = None
    fiftyTwoWeekHigh: Optional[float] = None
    fiftyTwoWeekLow: Optional[float] = None
    trend: TrendBlock = Field(default_factory=TrendBlock)
    liquidity: LiquidityBlock = Field(default_factory=LiquidityBlock)
    earnings: EarningsBlock = Field(default_factory=EarningsBlock)
    options: OptionsBlock = Field(default_factory=OptionsBlock)
    markers: MarkersBlock = Field(default_factory=MarkersBlock)

    @field_validator("symbol")
    @classmethod
    def upper_symbol(cls, v: str) -> str:
        return v.strip().upper()

    @property
    def bias(self) -> Bias:
        return self.trend.bias

    @property
    def iv_rank(self) -> Optional[float]:
        return self.options.ivRank

    @property
    def days_to_earnings(self) -> Optional[int]:
        return self.earnings.daysToEarnings


class ScanEnvelope(BaseModel):
    """Top-level stock-data-scanner.scan/v0.1 document."""

    schema_: str = Field(default=SCHEMA_ID, alias="schema")
    asOf: Optional[str] = None
    source: Optional[str] = None
    universe: list[str] = Field(default_factory=list)
    results: list[ScanResult] = Field(default_factory=list)

    model_config = {"populate_by_name": True}

    @model_validator(mode="before")
    @classmethod
    def accept_legacy_shapes(cls, data: Any) -> Any:
        """Also accept bare results list for tests (wrap into envelope)."""
        if isinstance(data, list):
            return {
                "schema": SCHEMA_ID,
                "asOf": None,
                "source": "fixture",
                "universe": [],
                "results": data,
            }
        return data

    @classmethod
    def load(cls, data: dict | list) -> "ScanEnvelope":
        return cls.model_validate(data)


# Portfolio / capital context (NOT part of scanner schema — separate input)
class PositionContext(BaseModel):
    symbol: str
    shares_owned: int = 0
    has_shares: bool = False
    cash_available: Optional[float] = None
    wheel_state: Optional[str] = None  # idle|csp_open|assigned|cc_open
    prefer_defined_risk: Optional[bool] = None

    @field_validator("symbol")
    @classmethod
    def upper_symbol(cls, v: str) -> str:
        return v.strip().upper()

    @model_validator(mode="after")
    def sync_has_shares(self) -> "PositionContext":
        if self.shares_owned >= 100:
            self.has_shares = True
        return self


class PortfolioContext(BaseModel):
    """Account capital / share inventory used by the selector."""

    cash_available: float = 50_000.0
    prefer_defined_risk: bool = False
    positions: list[PositionContext] = Field(default_factory=list)

    def for_symbol(self, symbol: str) -> PositionContext:
        sym = symbol.upper()
        for p in self.positions:
            if p.symbol == sym:
                cash = p.cash_available if p.cash_available is not None else self.cash_available
                prefer = (
                    p.prefer_defined_risk
                    if p.prefer_defined_risk is not None
                    else self.prefer_defined_risk
                )
                return PositionContext(
                    symbol=sym,
                    shares_owned=p.shares_owned,
                    has_shares=p.has_shares or p.shares_owned >= 100,
                    cash_available=cash,
                    wheel_state=p.wheel_state,
                    prefer_defined_risk=prefer,
                )
        return PositionContext(
            symbol=sym,
            cash_available=self.cash_available,
            prefer_defined_risk=self.prefer_defined_risk,
        )
