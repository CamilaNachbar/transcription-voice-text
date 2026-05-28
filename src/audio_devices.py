from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any, Literal

import soundcard as sc

DeviceKind = Literal["microphone", "loopback"]


@dataclass(frozen=True)
class AudioDeviceInfo:
    id: str
    name: str
    kind: DeviceKind
    is_default: bool = False


def _device_id(device: Any) -> str:
    return str(getattr(device, "id", device.name))


def list_microphones() -> list[AudioDeviceInfo]:
    default = sc.default_microphone()
    default_id = _device_id(default) if default else ""
    devices: list[AudioDeviceInfo] = []
    for mic in sc.all_microphones(include_loopback=False):
        dev_id = _device_id(mic)
        devices.append(
            AudioDeviceInfo(
                id=dev_id,
                name=mic.name,
                kind="microphone",
                is_default=dev_id == default_id,
            )
        )
    return devices


def list_loopback_devices() -> list[AudioDeviceInfo]:
    """Saídas de áudio graváveis (o que o Windows reproduz no dispositivo)."""
    default_speaker = sc.default_speaker()
    default_id = _device_id(default_speaker) if default_speaker else ""
    devices: list[AudioDeviceInfo] = []
    for mic in sc.all_microphones(include_loopback=True):
        if not getattr(mic, "isloopback", False):
            continue
        dev_id = _device_id(mic)
        devices.append(
            AudioDeviceInfo(
                id=dev_id,
                name=mic.name,
                kind="loopback",
                is_default=dev_id == default_id,
            )
        )
    return devices


def resolve_microphone(device_id: str | None) -> Any | None:
    if device_id:
        try:
            return sc.get_microphone(device_id, include_loopback=False)
        except Exception:
            pass
    return sc.default_microphone()


def resolve_loopback(device_id: str | None) -> Any | None:
    loopbacks = [
        m for m in sc.all_microphones(include_loopback=True) if getattr(m, "isloopback", False)
    ]
    if device_id:
        for mic in loopbacks:
            if _device_id(mic) == device_id:
                return mic
        try:
            return sc.get_microphone(device_id, include_loopback=True)
        except Exception:
            pass
    default_speaker = sc.default_speaker()
    if default_speaker:
        default_id = _device_id(default_speaker)
        for mic in loopbacks:
            if _device_id(mic) == default_id:
                return mic
    return loopbacks[0] if loopbacks else None


def platform_supports_loopback() -> bool:
    return sys.platform == "win32"
