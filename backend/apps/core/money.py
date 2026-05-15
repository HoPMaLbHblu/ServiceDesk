"""Decimal money arithmetic. Floats are never used for amounts."""

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def quantize(value: Decimal) -> Decimal:
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def line_total(quantity: Decimal, unit_price: Decimal) -> Decimal:
    return quantize(Decimal(quantity) * Decimal(unit_price))


@dataclass(frozen=True)
class Totals:
    subtotal: Decimal
    tax_total: Decimal
    total: Decimal


def compute_totals(lines: Iterable[tuple[Decimal, bool]], tax_rate_percent: Decimal) -> Totals:
    """``lines`` yields ``(line_total, taxable)``. Tax is rounded once, on the taxable sum."""
    subtotal = ZERO
    taxable = ZERO
    for amount, is_taxable in lines:
        subtotal += amount
        if is_taxable:
            taxable += amount
    tax = quantize(taxable * Decimal(tax_rate_percent) / Decimal(100))
    subtotal = quantize(subtotal)
    return Totals(subtotal=subtotal, tax_total=tax, total=subtotal + tax)
