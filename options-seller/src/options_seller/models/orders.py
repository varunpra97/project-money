"""Broker-agnostic order / trade ticket models."""

from __future__ import annotations

from enum import Enum
from datetime import date
from typing import Any, Optional

from pydantic import BaseModel, Field


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"


class Leg(BaseModel):
    symbol: str
    option_type: Optional[str] = None  # call|put|None for stock
    strike: Optional[float] = None
    dte: Optional[int] = None
    expiry: Optional[date] = None
    side: Side
    quantity: int = 1
    limit_price: Optional[float] = None
    delta: Optional[float] = None
    open_interest: Optional[int] = None
    template: bool = False  # True when built without live option quotes


class OrderPlan(BaseModel):
    """Multi-leg order plan (paper or live adapter)."""

    strategy: str
    underlying: str
    legs: list[Leg]
    credit_debit: str = "credit"
    net_premium: Optional[float] = None  # None when template / unknown
    max_profit: Optional[float] = None
    max_loss: Optional[float] = None
    capital_required: Optional[float] = None
    is_template: bool = False
    target_dte: Optional[int] = None
    target_delta: Optional[float] = None
    notes: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class TradeTicket(BaseModel):
    """Executable ticket derived from an OrderPlan."""

    plan: OrderPlan
    order_type: OrderType = OrderType.LIMIT
    slippage: float = 0.0
    paper: bool = True
    status: str = "pending"
    fill_price: Optional[float] = None
