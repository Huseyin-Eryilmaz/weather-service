"""The mathematics of forecast accuracy, with no database in sight.

Everything here is a pure function over numbers, which is what lets the
statistics be tested exactly — feed in known pairs, assert the known
answer — the same way the game logic in earlier projects was testable
without a screen. The database layer next door does the fetching and
matching; this module only does the arithmetic.

Three error measures, because each answers a different question:

  - **MAE** (mean absolute error): the average miss, in the data's own
    units. "On average the forecast was off by 1.8 degrees." Easy to read,
    and it treats a 2-degree miss as exactly twice a 1-degree one.

  - **RMSE** (root mean square error): squares the errors before
    averaging, so a few large misses weigh far more than many small ones.
    Always at least as large as MAE; the gap between them is itself a
    signal, widening when the errors are uneven.

  - **bias** (mean signed error): the average *direction* of the miss.
    MAE and RMSE cannot tell "always 2 degrees too warm" from "randomly
    2 degrees out either way" — both look equally inaccurate. Bias
    separates them, and a persistent non-zero bias is the thing a
    forecaster could actually correct for.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class ErrorStats:
    """The accuracy of a set of forecast/observation pairs."""

    count: int
    mae: float
    rmse: float
    bias: float

    def rounded(self, digits: int = 3) -> ErrorStats:
        """A copy with the floats rounded — for stable API output."""
        return ErrorStats(
            count=self.count,
            mae=round(self.mae, digits),
            rmse=round(self.rmse, digits),
            bias=round(self.bias, digits),
        )


def absolute_error(forecast: float, observed: float) -> float:
    """How far one forecast missed, sign discarded."""
    return abs(forecast - observed)


def signed_error(forecast: float, observed: float) -> float:
    """The miss with its direction kept: positive means over-forecast."""
    return forecast - observed


def horizon_hours(issued_at_epoch: float, target_epoch: float) -> int:
    """How many whole hours before the target the forecast was issued.

    Negative differences (a forecast "issued" after its target, which
    should not happen but might through a data glitch) clamp to zero, so a
    bad row cannot produce a nonsensical negative horizon.
    """
    hours = (target_epoch - issued_at_epoch) / 3600
    return max(int(hours), 0)


def summarise(pairs: list[tuple[float, float]]) -> ErrorStats | None:
    """Reduces (forecast, observed) pairs to the three error measures.

    Returns None for an empty input rather than dividing by zero — the
    caller reads "no data to compare" from the None, not from a crash.
    """
    if not pairs:
        return None

    n = len(pairs)
    signed = [f - o for f, o in pairs]
    absolute = [abs(d) for d in signed]

    mae = sum(absolute) / n
    rmse = math.sqrt(sum(d * d for d in signed) / n)
    bias = sum(signed) / n

    return ErrorStats(count=n, mae=mae, rmse=rmse, bias=bias)
