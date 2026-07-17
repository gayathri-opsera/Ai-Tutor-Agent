"""Unit tests for the secrets provider."""
import os
import pytest
from src.provider import get_db_dsn, get_s3_access_key, get_s3_secret_key, is_production


def test_local_fallback_db_dsn(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("APP_ENV", "local")
    # Re-import to reset module-level _IS_PROD
    import importlib
    import src.provider as mod
    importlib.reload(mod)
    dsn = mod.get_db_dsn()
    assert "ai_tutor_local_password" in dsn


def test_prod_raises_without_db_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("APP_ENV", "production")
    import importlib
    import src.provider as mod
    importlib.reload(mod)
    with pytest.raises(EnvironmentError, match="DATABASE_URL"):
        mod.get_db_dsn()


def test_env_var_takes_precedence(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://custom:secret@db:5432/mydb")
    monkeypatch.setenv("APP_ENV", "local")
    import importlib
    import src.provider as mod
    importlib.reload(mod)
    dsn = mod.get_db_dsn()
    assert dsn == "postgresql://custom:secret@db:5432/mydb"


def test_s3_local_fallbacks(monkeypatch):
    monkeypatch.delenv("S3_ACCESS_KEY", raising=False)
    monkeypatch.delenv("S3_SECRET_KEY", raising=False)
    monkeypatch.setenv("APP_ENV", "local")
    import importlib
    import src.provider as mod
    importlib.reload(mod)
    assert mod.get_s3_access_key() == "minioadmin"
    assert mod.get_s3_secret_key() == "minioadmin"
