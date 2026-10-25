"""Pure financial helpers for credit-envelope validation.

No commercial plan quantities are defined here.  Prices, reserves and a
credit's provider-cost ceiling remain explicit inputs until the commercial
policy is approved.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_FLOOR


@dataclass(frozen=True)
class CreditBudget:
    price_ttc: Decimal
    revenue_ht: Decimal
    payment_fees: Decimal
    variable_reserve: Decimal
    safety_reserve: Decimal
    provider_budget: Decimal
    max_credits: int


def _decimal(value: Decimal | str | int | float) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def maximum_credit_budget(
    *,
    price_ttc: Decimal | str | int | float,
    vat_rate: Decimal | str | int | float,
    payment_variable_rate: Decimal | str | int | float,
    payment_fixed_fee: Decimal | str | int | float,
    target_margin_rate: Decimal | str | int | float,
    other_variable_reserve_rate: Decimal | str | int | float,
    additional_safety_rate: Decimal | str | int | float,
    provider_cost_per_credit: Decimal | str | int | float,
) -> CreditBudget:
    """Return the maximum funded credit envelope for explicit assumptions."""

    price = _decimal(price_ttc)
    vat = _decimal(vat_rate)
    payment_rate = _decimal(payment_variable_rate)
    fixed_fee = _decimal(payment_fixed_fee)
    target = _decimal(target_margin_rate)
    variable_rate = _decimal(other_variable_reserve_rate)
    safety_rate = _decimal(additional_safety_rate)
    unit_cost = _decimal(provider_cost_per_credit)
    rates = (vat, payment_rate, target, variable_rate, safety_rate)
    if price <= 0 or unit_cost <= 0 or any(rate < 0 for rate in rates):
        raise ValueError("prices and unit cost must be positive; rates non-negative")
    if target + variable_rate + safety_rate >= 1:
        raise ValueError("margin and reserves leave no provider budget")

    revenue_ht = price / (Decimal("1") + vat)
    payment_fees = price * payment_rate + fixed_fee
    variable_reserve = revenue_ht * variable_rate
    safety_reserve = revenue_ht * safety_rate
    provider_budget = (
        revenue_ht * (Decimal("1") - target)
        - payment_fees
        - variable_reserve
        - safety_reserve
    )
    funded = max(provider_budget, Decimal("0"))
    max_credits = int((funded / unit_cost).to_integral_value(rounding=ROUND_FLOOR))
    return CreditBudget(
        price_ttc=price,
        revenue_ht=revenue_ht,
        payment_fees=payment_fees,
        variable_reserve=variable_reserve,
        safety_reserve=safety_reserve,
        provider_budget=funded,
        max_credits=max_credits,
    )


def achieved_contribution_margin(
    *,
    revenue_ht: Decimal | str | int | float,
    payment_fees: Decimal | str | int | float,
    provider_cost: Decimal | str | int | float,
    other_variable_cost: Decimal | str | int | float,
    safety_reserve: Decimal | str | int | float = Decimal("0"),
) -> Decimal:
    revenue = _decimal(revenue_ht)
    if revenue <= 0:
        raise ValueError("revenue_ht must be positive")
    contribution = revenue - sum(
        _decimal(value)
        for value in (
            payment_fees,
            provider_cost,
            other_variable_cost,
            safety_reserve,
        )
    )
    return contribution / revenue
