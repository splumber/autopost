"""Config loading: config/default.yaml (+ optional config/local.yaml override)
for non-secret settings, .env / environment for secrets. Secrets never live in yaml.
"""
from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "default.yaml"
LOCAL_CONFIG_PATH = REPO_ROOT / "config" / "local.yaml"


class Secrets(BaseSettings):
    """Loaded strictly from environment / .env. Never persisted to yaml."""

    model_config = SettingsConfigDict(env_prefix="AUTOPOST_", env_file=".env", extra="ignore")

    llm_api_key: str = "unused"
    pexels_api_key: str | None = None
    pixabay_api_key: str | None = None
    tiktok_client_key: str | None = None
    tiktok_client_secret: str | None = None
    secret_key: str | None = None
    web_basic_auth_username: str | None = None
    web_basic_auth_password: str | None = None


class LLMConfig(BaseModel):
    base_url: str
    model: str
    temperature: float = 0.85
    max_tokens: int = 2000
    request_timeout_sec: int = 60
    max_retries: int = 3
    api_key: str = "unused"


class TTSConfig(BaseModel):
    voice: str = "en-US-GuyNeural"
    rate: str = "+0%"
    pitch: str = "+0Hz"


class StockConfig(BaseModel):
    provider_priority: list[str] = ["pexels", "pixabay"]
    orientation: str = "portrait"
    min_clip_duration_sec: int = 3
    max_results_per_query: int = 15
    pexels_api_key: str | None = None
    pixabay_api_key: str | None = None


class VideoConfig(BaseModel):
    width: int = 1080
    height: int = 1920
    fps: int = 30
    target_duration_min_sec: int = 60
    target_duration_max_sec: int = 90
    hook_duration_sec: int = 3
    caption_font_size: int = 64
    narration_volume_db: float = 0
    background_music_volume_db: float = -18


class NicheConfig(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    active_niche: str = "finance_education"
    disclaimer_text: str = "Educational content only. Not financial advice."
    topic_dedupe_window_days: int = 120


class TikTokConfig(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    client_key: str | None = None
    client_secret: str | None = None
    redirect_uri: str = "http://localhost:8787/oauth/callback"
    scopes: list[str] = ["user.info.basic", "video.publish"]
    privacy_level: str = "SELF_ONLY"
    audit_status: str = "unaudited"  # unaudited | approved
    disable_duet: bool = False
    disable_stitch: bool = False
    disable_comment: bool = False
    max_posts_per_day: int = 2
    absolute_daily_ceiling: int = 15
    min_hours_between_posts: int = 6
    posting_window_start_hour: int = 9
    posting_window_end_hour: int = 21
    timezone: str = "America/New_York"
    requests_per_minute_limit: int = 6
    api_base_url: str = "https://open.tiktokapis.com"

    @field_validator("max_posts_per_day")
    @classmethod
    def _clamp_daily(cls, v: int, info) -> int:
        ceiling = info.data.get("absolute_daily_ceiling", 15)
        return min(v, ceiling)

    @property
    def effective_privacy_level(self) -> str:
        """Hard clamp: never PUBLIC unless TikTok has approved the content audit."""
        if self.audit_status != "approved":
            return "SELF_ONLY"
        return self.privacy_level


class SchedulerConfig(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    pipeline_interval_minutes: int = 60
    analytics_poll_interval_minutes: int = 360
    human_approval_required: bool = False


class WebConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8080
    basic_auth_username: str | None = None
    basic_auth_password: str | None = None


class StorageConfig(BaseModel):
    data_dir: str = "/data"

    @property
    def db_path(self) -> str:
        return str(Path(self.data_dir) / "autopost.db")

    @property
    def video_output_dir(self) -> str:
        return str(Path(self.data_dir) / "videos")

    @property
    def cache_dir(self) -> str:
        return str(Path(self.data_dir) / "cache")


class LoggingConfig(BaseModel):
    level: str = "INFO"


class Settings(BaseModel):
    llm: LLMConfig
    tts: TTSConfig = TTSConfig()
    stock: StockConfig = StockConfig()
    video: VideoConfig = VideoConfig()
    niche: NicheConfig = NicheConfig()
    tiktok: TikTokConfig
    scheduler: SchedulerConfig = SchedulerConfig()
    web: WebConfig = WebConfig()
    storage: StorageConfig = StorageConfig()
    logging: LoggingConfig = LoggingConfig()
    secret_key: str | None = None

    def require_ready_for_publishing(self) -> None:
        missing = []
        if not self.tiktok.client_key or not self.tiktok.client_secret:
            missing.append("AUTOPOST_TIKTOK_CLIENT_KEY / AUTOPOST_TIKTOK_CLIENT_SECRET")
        if not self.secret_key:
            missing.append("AUTOPOST_SECRET_KEY")
        if missing:
            raise RuntimeError(
                "Cannot publish to TikTok yet, missing: " + ", ".join(missing)
                + ". See docs/SETUP_CHECKLIST.md."
            )

    def redacted(self) -> dict[str, Any]:
        """Config dump with secrets masked, safe to print/log/show in the dashboard."""
        data = self.model_dump()
        for path in (
            ("tiktok", "client_secret"),
            ("stock", "pexels_api_key"),
            ("stock", "pixabay_api_key"),
        ):
            section, key = path
            if data.get(section, {}).get(key):
                data[section][key] = "***"
        if data.get("secret_key"):
            data["secret_key"] = "***"
        return data


def _deep_merge(base: dict, override: dict) -> dict:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_config() -> Settings:
    raw = _deep_merge(_load_yaml(DEFAULT_CONFIG_PATH), _load_yaml(LOCAL_CONFIG_PATH))
    secrets = Secrets()

    raw.setdefault("llm", {})["api_key"] = secrets.llm_api_key
    raw.setdefault("tiktok", {})["client_key"] = secrets.tiktok_client_key
    raw["tiktok"]["client_secret"] = secrets.tiktok_client_secret
    raw.setdefault("stock", {})["pexels_api_key"] = secrets.pexels_api_key
    raw["stock"]["pixabay_api_key"] = secrets.pixabay_api_key
    raw.setdefault("web", {})["basic_auth_username"] = secrets.web_basic_auth_username
    raw["web"]["basic_auth_password"] = secrets.web_basic_auth_password
    raw["secret_key"] = secrets.secret_key

    if data_dir_env := os.environ.get("AUTOPOST_DATA_DIR"):
        raw.setdefault("storage", {})["data_dir"] = data_dir_env

    return Settings(**raw)


def save_local_override(patch: dict) -> None:
    """Deep-merge `patch` into config/local.yaml (used by the dashboard config editor)."""
    current = _load_yaml(LOCAL_CONFIG_PATH)
    merged = _deep_merge(current, patch)
    LOCAL_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOCAL_CONFIG_PATH.open("w", encoding="utf-8") as f:
        yaml.safe_dump(merged, f, sort_keys=False)
