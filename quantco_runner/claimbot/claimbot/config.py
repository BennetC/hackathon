"""Settings loaded from environment variables (and a local .env file)."""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path


class ConfigError(RuntimeError):
    pass


def _float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    try:
        return float(raw) if raw else default
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number, got {raw!r}") from exc


def _int(name: str, default: int) -> int:
    return int(_float(name, default))


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise ConfigError(f"{name} must be a boolean (true/false/1/0), got {raw!r}")


@dataclass(frozen=True)
class Settings:
    api_key: str
    base_url: str = "https://c2f.public.quantco.cloud"
    cases_dir: Path = Path("data/cases")
    runs_dir: Path = Path("runs")
    case_file_template: str = "case_{game_id:03d}.zip"
    strategy: str = "council"
    team_name: str = "FDN"          # our name on the public leaderboard
    settle_delay_s: float = 20.0    # wait after a game window closes before fetching results
    game_window_s: float = 60.0
    submit_margin_s: float = 8.0
    key_retry_s: float = 15.0
    key_poll_s: float = 1.0
    key_early_s: float = 0.5
    wake_lead_s: float = 10.0
    schedule_refresh_s: float = 120.0
    http_timeout_s: float = 8.0
    fallback_charge: float = 0.0
    fallback_limit: float = 200.0
    fallback_line_count: int = 0
    bench_url: str = "https://bench.159-195-78-137.sslip.io"
    bench_token: str = ""
    bench_author: str = "fdn"
    bench_strategy_name: str = ""
    bench_upload: bool = False

    def with_overrides(self, **kwargs) -> "Settings":
        return replace(self, **{k: v for k, v in kwargs.items() if v is not None})


def load_settings(require_api_key: bool = True) -> Settings:
    api_key = os.environ.get("TEAM_API_KEY", "").strip()
    if require_api_key and not api_key:
        raise ConfigError("TEAM_API_KEY is not set (put it in .env or the environment)")
    bench_token = (
        os.environ.get("CLAIMBOT_BENCH_TOKEN") or os.environ.get("BENCH_TOKEN") or ""
    ).strip()
    return Settings(
        api_key=api_key,
        base_url=os.environ.get("CLAIMBOT_BASE_URL", Settings.base_url).rstrip("/"),
        cases_dir=Path(os.environ.get("CLAIMBOT_CASES_DIR", str(Settings.cases_dir))),
        runs_dir=Path(os.environ.get("CLAIMBOT_RUNS_DIR", str(Settings.runs_dir))),
        case_file_template=os.environ.get(
            "CLAIMBOT_CASE_FILE_TEMPLATE", Settings.case_file_template
        ),
        strategy=os.environ.get("CLAIMBOT_STRATEGY", Settings.strategy),
        team_name=os.environ.get("CLAIMBOT_TEAM", Settings.team_name).strip() or Settings.team_name,
        settle_delay_s=_float("CLAIMBOT_SETTLE_DELAY_S", Settings.settle_delay_s),
        game_window_s=_float("CLAIMBOT_GAME_WINDOW_S", Settings.game_window_s),
        submit_margin_s=_float("CLAIMBOT_SUBMIT_MARGIN_S", Settings.submit_margin_s),
        key_retry_s=_float("CLAIMBOT_KEY_RETRY_S", Settings.key_retry_s),
        key_poll_s=_float("CLAIMBOT_KEY_POLL_S", Settings.key_poll_s),
        key_early_s=_float("CLAIMBOT_KEY_EARLY_S", Settings.key_early_s),
        wake_lead_s=_float("CLAIMBOT_WAKE_LEAD_S", Settings.wake_lead_s),
        schedule_refresh_s=_float(
            "CLAIMBOT_SCHEDULE_REFRESH_S", Settings.schedule_refresh_s
        ),
        http_timeout_s=_float("CLAIMBOT_HTTP_TIMEOUT_S", Settings.http_timeout_s),
        fallback_charge=_float("CLAIMBOT_FALLBACK_CHARGE", Settings.fallback_charge),
        fallback_limit=_float("CLAIMBOT_FALLBACK_LIMIT", Settings.fallback_limit),
        fallback_line_count=_int(
            "CLAIMBOT_FALLBACK_LINE_COUNT", Settings.fallback_line_count
        ),
        bench_url=os.environ.get("CLAIMBOT_BENCH_URL", Settings.bench_url).strip().rstrip("/"),
        bench_token=bench_token,
        bench_author=os.environ.get("CLAIMBOT_BENCH_AUTHOR", Settings.bench_author).strip()
        or Settings.bench_author,
        bench_strategy_name=os.environ.get("CLAIMBOT_BENCH_STRATEGY_NAME", "").strip(),
        bench_upload=_bool("CLAIMBOT_BENCH_UPLOAD", bool(bench_token)),
    )
