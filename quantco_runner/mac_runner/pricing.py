"""FDN's Game 1 baseline. Inputs and outputs are internal, before serialization."""

import argparse
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


SAMPLE_COUNT = 100
CHARGE_RANK = 25
LIMIT_RANK = 33
DEFAULT_SPREAD_BPS = 500
ELIGIBILITY = {"yes", "no", "uncertain"}


def _decimal(value, field):
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"{field} must be a decimal number") from exc
    if not result.is_finite() or result < 0:
        raise ValueError(f"{field} must be finite and nonnegative")
    return result


def _samples_from_unit_band(item, coverage, relevance):
    """Build deterministic gross line samples from a manually supplied net band."""
    band = item["unit_price_band_net_cents"]
    if not isinstance(band, list) or len(band) != 3:
        raise ValueError("unit_price_band_net_cents must be [low, typical, high]")
    low, typical, high = (_decimal(price, "unit price") for price in band)
    if not low <= typical <= high:
        raise ValueError("unit price band must be ordered low to high")
    quantity = _decimal(item["quantity"], "quantity")
    vat = _decimal(item["vat_rate"], "vat_rate")
    if vat > 1:
        raise ValueError("vat_rate must be a fraction, e.g. 0.19")

    if "uncertain" in (coverage, relevance):
        eligible = item["eligible_samples"]
        if type(eligible) is not int or not 0 <= eligible <= SAMPLE_COUNT:
            raise ValueError("eligible_samples must be an integer from 0 to 100")
    else:
        eligible = SAMPLE_COUNT

    gross_factor = quantity * (1 + vat)
    samples = [0] * (SAMPLE_COUNT - eligible)
    for index in range(eligible):
        # Place the typical value at the median of the conditional price band.
        percentile = (Decimal(index) + Decimal("0.5")) / eligible
        if percentile < Decimal("0.5"):
            unit_price = low + 2 * percentile * (typical - low)
        else:
            unit_price = typical + (2 * percentile - 1) * (high - typical)
        gross = (unit_price * gross_factor).to_integral_value(rounding=ROUND_HALF_UP)
        samples.append(int(gross))
    return samples


def _price_item(item, spread_bps):
    coverage, relevance = item["coverage"], item["relevance"]
    if coverage not in ELIGIBILITY or relevance not in ELIGIBILITY:
        raise ValueError("coverage and relevance must be yes, no, or uncertain")
    if "no" in (coverage, relevance):
        return 0, 0

    if "threshold_samples_gross_cents" in item:
        samples = item["threshold_samples_gross_cents"]
    elif "unit_price_band_net_cents" in item:
        samples = _samples_from_unit_band(item, coverage, relevance)
    else:
        raise ValueError("provide threshold samples or a net unit price band")
    if (
        not isinstance(samples, list)
        or len(samples) != SAMPLE_COUNT
        or any(type(sample) is not int or sample < 0 for sample in samples)
        or any(a > b for a, b in zip(samples, samples[1:]))
    ):
        raise ValueError("expected 100 sorted, nonnegative integer gross-cent samples")

    # Keep the insurer's limit; use issuer headroom if the percentiles are close.
    limit = samples[LIMIT_RANK - 1]
    spread = (limit * spread_bps + 9999) // 10000
    charge = min(samples[CHARGE_RANK - 1], limit - spread)
    return charge, limit


def price_game(game, *, spread_bps=DEFAULT_SPREAD_BPS):
    """Return (item_id, charge_cents, limit_cents) in declared invoice order."""
    if type(spread_bps) is not int or not 1 <= spread_bps <= 10000:
        raise ValueError("spread_bps must be an integer from 1 to 10000")
    expected = game["expected_item_ids"]
    items = game["items"]
    if not isinstance(expected, list) or not isinstance(items, list):
        raise ValueError("expected_item_ids and items must be arrays")
    if not expected:
        raise ValueError("expected_item_ids must contain at least one invoice ID")
    if any(type(item_id) not in (str, int) or item_id == "" for item_id in expected):
        raise ValueError("invoice IDs must be nonempty strings or integers")
    if len(expected) != len(set(expected)):
        raise ValueError("duplicate expected invoice ID")

    by_id = {}
    expected_set = set(expected)
    for item in items:
        item_id = item["item_id"]
        if type(item_id) not in (str, int) or item_id not in expected_set:
            raise ValueError(f"unexpected invoice ID {item_id!r}")
        if item_id in by_id:
            raise ValueError(f"duplicate invoice ID {item_id!r}")
        by_id[item_id] = item

    missing = [item_id for item_id in expected if item_id not in by_id]
    if missing:
        raise ValueError(f"missing invoice IDs: {missing!r}")

    priced = []
    for item_id in expected:
        try:
            charge, limit = _price_item(by_id[item_id], spread_bps)
        except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
            raise ValueError(f"invoice ID {item_id!r}: {exc}") from exc
        priced.append((item_id, charge, limit))
    return priced


def price_payload(game, *, spread_bps=DEFAULT_SPREAD_BPS):
    """Build the internal runner payload, with prices in gross cents."""
    game_id = game["game_id"]
    if type(game_id) not in (str, int) or game_id == "":
        raise ValueError("game_id must be a nonempty string or integer")
    return {
        "game_id": game_id,
        "items": [
            {"item_id": item_id, "charge_cents": charge, "limit_cents": limit}
            for item_id, charge, limit in price_game(game, spread_bps=spread_bps)
        ],
    }


def main():
    parser = argparse.ArgumentParser(description="Price an FDN internal valuation JSON document.")
    parser.add_argument("input", nargs="?", default="-", help="input file, or - for stdin")
    parser.add_argument("--spread-bps", type=int, default=DEFAULT_SPREAD_BPS)
    args = parser.parse_args()
    try:
        if args.input == "-":
            game = json.load(sys.stdin, parse_float=Decimal)
        else:
            with open(args.input, encoding="utf-8") as source:
                game = json.load(source, parse_float=Decimal)
        result = price_payload(game, spread_bps=args.spread_bps)
    except (OSError, KeyError, TypeError, ValueError) as exc:
        parser.exit(2, f"pricing: {exc}\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
