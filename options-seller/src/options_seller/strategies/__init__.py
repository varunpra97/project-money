"""Strategy builders."""

from options_seller.strategies.base import StrategyBuilder, StrategyResult
from options_seller.strategies.bear_call_credit_spread import BearCallCreditSpread
from options_seller.strategies.bull_put_credit_spread import BullPutCreditSpread
from options_seller.strategies.cash_secured_put import CashSecuredPut
from options_seller.strategies.covered_call import CoveredCall
from options_seller.strategies.iron_condor import IronCondor
from options_seller.strategies.wheel import WheelStrategy

STRATEGY_REGISTRY: dict[str, type[StrategyBuilder]] = {
    "cash_secured_put": CashSecuredPut,
    "covered_call": CoveredCall,
    "wheel": WheelStrategy,
    "bull_put_credit_spread": BullPutCreditSpread,
    "bear_call_credit_spread": BearCallCreditSpread,
    "iron_condor": IronCondor,
}

__all__ = [
    "STRATEGY_REGISTRY",
    "BearCallCreditSpread",
    "BullPutCreditSpread",
    "CashSecuredPut",
    "CoveredCall",
    "IronCondor",
    "StrategyBuilder",
    "StrategyResult",
    "WheelStrategy",
]
