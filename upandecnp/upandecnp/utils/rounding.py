"""Round-half-up helper.

Python's builtin round() does round-half-to-even (banker's rounding), which
would turn 112.5 into 112. The agronomist's worked examples round halves up
(112.5 -> 113, 62.5 -> 63), so every intermediate rounding step in the
calculation engine must use this instead of round().
"""

from decimal import ROUND_HALF_UP, Decimal


def round_half_up(value, ndigits=0):
	q = Decimal(10) ** -ndigits
	return float(Decimal(str(value)).quantize(q, rounding=ROUND_HALF_UP))
