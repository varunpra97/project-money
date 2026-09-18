"""Broker adapter stub — intentionally unimplemented for live trading."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from options_seller.models.orders import OrderPlan, TradeTicket


class BrokerAdapter(ABC):
    """Broker-agnostic interface. Live implementations are out of scope."""

    @abstractmethod
    def place_order(self, ticket: TradeTicket) -> dict[str, Any]:
        raise NotImplementedError("Live broker orders are not implemented")

    @abstractmethod
    def cancel_order(self, order_id: str) -> dict[str, Any]:
        raise NotImplementedError("Live broker cancel is not implemented")

    @abstractmethod
    def get_positions(self) -> list[dict[str, Any]]:
        raise NotImplementedError("Live broker positions are not implemented")


class StubBrokerAdapter(BrokerAdapter):
    """Marked unimplemented — CLI must never route here for live orders."""

    def place_order(self, ticket: TradeTicket) -> dict[str, Any]:
        raise NotImplementedError(
            "StubBrokerAdapter.place_order is unimplemented. "
            "Use PaperExecutor for dry-run / paper fills only."
        )

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        raise NotImplementedError("StubBrokerAdapter.cancel_order is unimplemented")

    def get_positions(self) -> list[dict[str, Any]]:
        raise NotImplementedError("StubBrokerAdapter.get_positions is unimplemented")


def plan_to_ticket(plan: OrderPlan, *, slippage: float = 0.0) -> TradeTicket:
    return TradeTicket(plan=plan, slippage=slippage, paper=True, status="pending")
