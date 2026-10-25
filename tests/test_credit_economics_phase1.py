from decimal import Decimal

from core.credit_economics import (
    achieved_contribution_margin,
    maximum_credit_budget,
)


def test_budget_reserves_margin_variable_costs_and_extra_safety():
    budget = maximum_credit_budget(
        price_ttc="29",
        vat_rate="0.20",
        payment_variable_rate="0.022",
        payment_fixed_fee="0.25",
        target_margin_rate="0.70",
        other_variable_reserve_rate="0.05",
        additional_safety_rate="0.02",
        provider_cost_per_credit="0.05",
    )
    assert budget.max_credits == 93
    assert budget.provider_budget < Decimal("4.68")
    assert budget.provider_budget >= Decimal("4.65")


def test_international_payment_stress_reduces_the_funded_envelope():
    nominal = maximum_credit_budget(
        price_ttc="99",
        vat_rate="0.20",
        payment_variable_rate="0.022",
        payment_fixed_fee="0.25",
        target_margin_rate="0.70",
        other_variable_reserve_rate="0.05",
        additional_safety_rate="0.02",
        provider_cost_per_credit="0.05",
    )
    stressed = maximum_credit_budget(
        price_ttc="99",
        vat_rate="0.20",
        payment_variable_rate="0.0585",
        payment_fixed_fee="0.25",
        target_margin_rate="0.70",
        other_variable_reserve_rate="0.05",
        additional_safety_rate="0.02",
        provider_cost_per_credit="0.05",
    )
    assert nominal.max_credits == 330
    assert stressed.max_credits == 258


def test_margin_calculation_keeps_all_cost_buckets_explicit():
    margin = achieved_contribution_margin(
        revenue_ht="100",
        payment_fees="3",
        provider_cost="18",
        other_variable_cost="5",
        safety_reserve="2",
    )
    assert margin == Decimal("0.72")
