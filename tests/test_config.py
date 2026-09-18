import os

from autopost.config import load_config


def test_load_config_defaults(monkeypatch, tmp_path):
    monkeypatch.setenv("AUTOPOST_DATA_DIR", str(tmp_path))
    settings = load_config()
    assert settings.niche.active_niche == "finance_education"
    assert settings.tiktok.effective_privacy_level == "SELF_ONLY"


def test_privacy_level_clamped_until_audit_approved():
    from autopost.config import TikTokConfig

    cfg = TikTokConfig(privacy_level="PUBLIC_TO_EVERYONE", audit_status="unaudited")
    assert cfg.effective_privacy_level == "SELF_ONLY"

    cfg.audit_status = "approved"
    assert cfg.effective_privacy_level == "PUBLIC_TO_EVERYONE"


def test_max_posts_per_day_clamped_to_ceiling():
    from autopost.config import TikTokConfig

    cfg = TikTokConfig(max_posts_per_day=999, absolute_daily_ceiling=15)
    assert cfg.max_posts_per_day == 15


def test_redacted_masks_secrets():
    from autopost.config import Secrets, Settings, TikTokConfig, LLMConfig

    settings = Settings(
        llm=LLMConfig(base_url="http://x", model="m", api_key="secret-llm-key"),
        tiktok=TikTokConfig(client_key="ck", client_secret="super-secret"),
        secret_key="fernet-secret",
    )
    dumped = settings.redacted()
    assert dumped["tiktok"]["client_secret"] == "***"
    assert dumped["secret_key"] == "***"
