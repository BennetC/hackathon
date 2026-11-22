"""Serialize prices and replay QuantCo payoffs locally with supplied scenarios."""

import argparse
import json
import os
from decimal import Decimal
from pathlib import Path


def _nonnegative_int(value, field):
    if type(value) is not int or value < 0:
        raise ValueError(f"{field} must be a nonnegative integer")
    return value


def wire_items(prices, *, expected_ids=None):
    """Use the handbook array format with the parsed invoice's actual indices."""
    indices, payload = set(), []
    for item in prices["items"]:
        index = _nonnegative_int(item["item_id"], "item_id")
        if index in indices:
            raise ValueError(f"duplicate invoice index {index}")
        indices.add(index)
        charge = _nonnegative_int(item["charge_cents"], "charge_cents")
        limit = _nonnegative_int(item["limit_cents"], "limit_cents")
        charge_price, acceptance_limit = charge / 100, limit / 100
        if (Decimal(str(charge_price)) * 100 != charge
                or Decimal(str(acceptance_limit)) * 100 != limit):
            raise ValueError("wire prices cannot represent the submitted cents exactly")
        payload.append({"index": index, "charge_price": charge_price, "acceptance_limit": acceptance_limit})
    if not payload:
        raise ValueError("cannot serialize an empty list of prices")
    if expected_ids is not None and [item["index"] for item in payload] != expected_ids:
        raise ValueError("wire payload must contain every invoice position in order")
    return payload


def payment_cents(charge, limit, threshold, cap):
    if charge <= limit:
        return min(charge, cap)
    if charge <= threshold:
        return Decimal(charge) * Decimal("1.5")
    return 0


def replay(prices, scenario):
    """Sum earnings and costs across independently specified counterparty quotes."""
    lines = {}
    for item in scenario["items"]:
        index = _nonnegative_int(item["index"], "scenario index")
        if index in lines:
            raise ValueError(f"duplicate scenario index {index}")
        lines[index] = item
    expected = {item["item_id"] for item in prices["items"]}
    if set(lines) != expected:
        raise ValueError("scenario indices must match the priced invoice exactly")
    earned = paid = 0
    for item in prices["items"]:
        line = lines[item["item_id"]]
        threshold = _nonnegative_int(line["threshold_cents"], "threshold_cents")
        cap = _nonnegative_int(line["cap_cents"], "cap_cents")
        if cap < 4 * threshold:
            raise ValueError("the scenario cap must be at least four times the threshold")
        for rival in line["opponents"]:
            rival_charge = _nonnegative_int(rival["charge_cents"], "opponent charge_cents")
            rival_limit = _nonnegative_int(rival["limit_cents"], "opponent limit_cents")
            earned += payment_cents(item["charge_cents"], rival_limit, threshold, cap)
            paid += payment_cents(rival_charge, item["limit_cents"], threshold, cap)
    return {"earned_cents": str(earned), "paid_cents": str(paid), "net_cents": str(earned - paid)}


def _private_file(path, flags):
    return os.open(path, flags, 0o600)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prices", type=Path)
    parser.add_argument("--scenario", type=Path, help="local thresholds, caps and opponent quotes")
    parser.add_argument("--schedule", type=Path, help="verify the game against a locally fetched schedule")
    parser.add_argument("--output", type=Path, help="save the preview/replay to a local file")
    args = parser.parse_args()
    try:
        prices = json.loads(args.prices.read_text())
        result = {"game_id": prices["game_id"], "submission_preview": wire_items(prices)}
        if args.schedule:
            games = json.loads(args.schedule.read_text())
            match = next((game for game in games if game["id"] == prices["game_id"]), None)
            if match is None:
                raise ValueError(f"game {prices['game_id']!r} was not on the saved schedule")
            result["scheduled_start"] = match["start_time"]
        if args.scenario:
            result["replay"] = replay(prices, json.loads(args.scenario.read_text()))
        encoded = json.dumps(result, indent=2, allow_nan=False)
        if args.output is None:
            print(encoded)
        else:
            with open(args.output, "x", encoding="utf-8", opener=_private_file) as stream:
                stream.write(encoded + "\n")
    except (KeyError, TypeError, ValueError, OSError, OverflowError) as exc:
        parser.exit(1, f"local simulation: {exc}\n")


if __name__ == "__main__":
    main()
