from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import LLMProviderMode

SETTINGS_FILE = Path("data") / "user_settings.json"


def _read() -> dict[str, Any]:
    if not SETTINGS_FILE.exists():
        return {}
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _write(data: dict[str, Any]) -> None:
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_llm_provider() -> LLMProviderMode | None:
    value = (_read().get("llm_provider") or "").strip().lower()
    if value in ("auto", "anthropic", "cursor"):
        return value  # type: ignore[return-value]
    return None


def save_llm_provider(mode: LLMProviderMode) -> None:
    data = _read()
    data["llm_provider"] = mode
    _write(data)


def load_appearance_mode() -> str | None:
    value = (_read().get("appearance_mode") or "").strip().lower()
    if value in ("system", "light", "dark"):
        return value
    return None


def save_appearance_mode(mode: str) -> None:
    data = _read()
    data["appearance_mode"] = mode
    _write(data)


def load_loopback_device_id() -> str | None:
    value = (_read().get("loopback_device_id") or "").strip()
    return value or None


def save_loopback_device_id(device_id: str | None) -> None:
    data = _read()
    if device_id:
        data["loopback_device_id"] = device_id
    else:
        data.pop("loopback_device_id", None)
    _write(data)


def load_microphone_device_id() -> str | None:
    value = (_read().get("microphone_device_id") or "").strip()
    return value or None


def save_microphone_device_id(device_id: str | None) -> None:
    data = _read()
    if device_id:
        data["microphone_device_id"] = device_id
    else:
        data.pop("microphone_device_id", None)
    _write(data)


def load_capture_system_audio() -> bool:
    value = _read().get("capture_system_audio")
    if value is None:
        return True
    return bool(value)


def save_capture_system_audio(enabled: bool) -> None:
    data = _read()
    data["capture_system_audio"] = enabled
    _write(data)


def load_wake_assistant_enabled() -> bool | None:
    value = _read().get("wake_assistant_enabled")
    if value is None:
        return None
    return bool(value)


def save_wake_assistant_enabled(enabled: bool) -> None:
    data = _read()
    data["wake_assistant_enabled"] = enabled
    _write(data)
