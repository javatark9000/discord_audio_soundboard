from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import os
from pathlib import Path
from uuid import uuid4


DEFAULT_VOLUME = 80.0
APP_DIRECTORY_NAME = "DiscordAudioSoundboard"
CONFIG_FILE_NAME = "config.json"


@dataclass
class SoundEntry:
    file_path: str
    display_name: str
    id: str = field(default_factory=lambda: uuid4().hex)


@dataclass
class AppConfig:
    sounds: list[SoundEntry] = field(default_factory=list)
    global_volume: float = DEFAULT_VOLUME


def get_config_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / APP_DIRECTORY_NAME / CONFIG_FILE_NAME
    return Path(__file__).resolve().parent / CONFIG_FILE_NAME


def load_config() -> AppConfig:
    config_path = get_config_path()
    if not config_path.exists():
        return AppConfig()

    try:
        raw_data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return AppConfig()

    sounds_data = raw_data.get("sounds", []) if isinstance(raw_data, dict) else []
    sounds: list[SoundEntry] = []
    if isinstance(sounds_data, list):
        for item in sounds_data:
            sound = _load_sound_entry(item)
            if sound is not None:
                sounds.append(sound)

    global_volume = _coerce_volume(
        raw_data.get("global_volume", DEFAULT_VOLUME) if isinstance(raw_data, dict) else DEFAULT_VOLUME
    )
    return AppConfig(sounds=sounds, global_volume=global_volume)


def save_config(config: AppConfig) -> None:
    config_path = get_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "global_volume": _coerce_volume(config.global_volume),
        "sounds": [asdict(sound) for sound in config.sounds],
    }
    config_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _load_sound_entry(item: object) -> SoundEntry | None:
    if not isinstance(item, dict):
        return None

    file_path = item.get("file_path")
    if not isinstance(file_path, str) or not file_path.strip():
        return None

    display_name = item.get("display_name")
    if not isinstance(display_name, str) or not display_name.strip():
        display_name = Path(file_path).stem

    sound_id = item.get("id")
    if not isinstance(sound_id, str) or not sound_id.strip():
        sound_id = uuid4().hex

    return SoundEntry(
        id=sound_id,
        file_path=file_path,
        display_name=display_name.strip(),
    )


def _coerce_volume(value: object) -> float:
    try:
        volume = float(value)
    except (TypeError, ValueError):
        return DEFAULT_VOLUME
    return max(0.0, min(100.0, volume))
