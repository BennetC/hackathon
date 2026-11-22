"""Read the QuantCo schedule and a released case key for offline use."""

import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener


BASE = "https://c2f.public.quantco.cloud"
TEAM_KEY_FILES = (
    Path.home() / ".config" / "fdn-quantco" / "team.key",
    Path(__file__).resolve().parent / ".cache" / "quantco" / "team.key",
)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _get(path, team_key):
    request = Request(BASE + path, method="GET",
                      headers={"X-API-Key": team_key, "Accept": "application/json"})
    try:
        with build_opener(NoRedirect()).open(request, timeout=10) as response:
            return json.load(response)
    except HTTPError as exc:
        raise ValueError(f"QuantCo GET {path} returned HTTP {exc.code}") from exc
    except URLError as exc:
        raise ValueError(f"QuantCo GET {path} failed to connect") from exc


def _private_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as temporary:
        temporary.write(text)
    Path(temporary.name).replace(path)


def load_team_key(key_file=None):
    if key_file is not None:
        key = key_file.read_text(encoding="utf-8").strip()
    else:
        key = os.getenv("TEAM_API_KEY", "").strip()
        if not key:
            for path in TEAM_KEY_FILES:
                try:
                    key = path.read_text(encoding="utf-8").strip()
                except FileNotFoundError:
                    continue
                if key:
                    break
    if not key:
        raise ValueError(f"missing TEAM_API_KEY and private team key file ({TEAM_KEY_FILES[0]})")
    if not key.isascii() or any(not 33 <= ord(char) <= 126 for char in key):
        raise ValueError("TEAM_API_KEY contains invalid header characters")
    return key


def schedule_starts(games):
    if not isinstance(games, list) or not games:
        raise ValueError("expected a nonempty QuantCo schedule")
    starts = {}
    for game in games:
        game_id = game["id"]
        value = game["start_time"]
        if type(game_id) is not int or game_id < 0 or game_id in starts or not isinstance(value, str):
            raise ValueError("invalid or duplicate QuantCo schedule entry")
        start = datetime.fromisoformat(value)
        if start.tzinfo is None:
            raise ValueError("the game's start time does not specify a timezone")
        starts[game_id] = start.astimezone(timezone.utc)
    return starts


def validate_key(response):
    key = response["decryption_key"]
    if not isinstance(key, str) or not key.strip() or "\n" in key or "\r" in key:
        raise ValueError("unexpected QuantCo decryption key format")
    return key


def fetch(team_key, output, game_id=None):
    games = _get("/api/games/list", team_key)
    starts = schedule_starts(games)
    _private_write(output / "games.json", json.dumps(games, indent=2) + "\n")
    count = len(games)
    if game_id is None:
        return count, False
    if game_id not in starts:
        raise ValueError(f"game {game_id} was not on the schedule")
    if starts[game_id] > datetime.now(timezone.utc):
        raise ValueError(f"game {game_id} has not started; key request skipped")
    key = validate_key(_get(f"/api/games/{game_id}/key", team_key))
    _private_write(output / f"game-{game_id}.password", key)
    return count, True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--key-file", type=Path, help="override TEAM_API_KEY or the private local team key file")
    parser.add_argument("--out", type=Path, default=Path(".cache/quantco"))
    parser.add_argument("--game", type=int, help="fetch a key only if this game already started")
    args = parser.parse_args()
    try:
        count, fetched = fetch(load_team_key(args.key_file), args.out, args.game)
        print(f"Saved {count} schedule entries in {args.out / 'games.json'}")
        if fetched:
            print(f"Saved the released key for game {args.game} in a private local file")
    except (KeyError, TypeError, ValueError, OSError) as exc:
        parser.exit(1, f"quantco fetch: {exc}\n")


if __name__ == "__main__":
    main()
