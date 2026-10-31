"""Settings, read from .env (or the real environment). No third-party dotenv: the file is KEY=VALUE lines."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_dotenv(path: Path = ROOT / ".env") -> None:
    """Put KEY=VALUE lines from .env into os.environ unless the variable is already set."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    telegram_chat_id: int
    anthropic_api_key: str
    llm_model: str
    check_interval_seconds: int
    rules_path: Path
    db_path: Path
    log_path: Path
    credentials_path: Path
    token_path: Path


def settings() -> Settings:
    load_dotenv()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    return Settings(
        telegram_bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", "").strip(),
        telegram_chat_id=int(chat_id) if chat_id.lstrip("-").isdigit() else 0,
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", "").strip(),
        llm_model=os.environ.get("LLM_MODEL", "claude-opus-5-5").strip(),
        check_interval_seconds=int(os.environ.get("CHECK_INTERVAL_SECONDS", "900")),
        rules_path=ROOT / os.environ.get("RULES_FILE", "rules.yaml"),
        db_path=ROOT / os.environ.get("STATE_DB", "state.db"),
        log_path=ROOT / os.environ.get("LOG_FILE", "decisions.log"),
        credentials_path=ROOT / "credentials.json",
        token_path=ROOT / "token.json",
    )


def require(s: Settings) -> list[str]:
    """Names of the settings that are missing. Empty list means the agent can start."""
    missing = []
    if not s.telegram_bot_token:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not s.telegram_chat_id:
        missing.append("TELEGRAM_CHAT_ID")
    if not s.anthropic_api_key:
        missing.append("ANTHROPIC_API_KEY")
    if not s.rules_path.exists():
        missing.append(f"{s.rules_path.name} (copy rules.example.yaml)")
    if not s.token_path.exists():
        missing.append("token.json (run: python -m agent.auth_gmail)")
    return missing
