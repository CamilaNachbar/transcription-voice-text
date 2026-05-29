from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any, Literal

import soundcard as sc

from .mac_audio_guide import is_mac_virtual_capture_device

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


def _list_wasapi_loopback() -> list[AudioDeviceInfo]:
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


def _list_mac_participant_devices() -> list[AudioDeviceInfo]:
    """BlackHole / Loopback etc. aparecem como entrada de microfone no macOS."""
    devices: list[AudioDeviceInfo] = []
    seen: set[str] = set()

    for mic in sc.all_microphones(include_loopback=True):
        if not getattr(mic, "isloopback", False):
            continue
        dev_id = _device_id(mic)
        if dev_id not in seen:
            seen.add(dev_id)
            devices.append(
                AudioDeviceInfo(
                    id=dev_id,
                    name=mic.name,
                    kind="loopback",
                    is_default=False,
                )
            )

    for mic in sc.all_microphones(include_loopback=False):
        if not is_mac_virtual_capture_device(mic.name):
            continue
        dev_id = _device_id(mic)
        if dev_id in seen:
            continue
        seen.add(dev_id)
        devices.append(
            AudioDeviceInfo(
                id=dev_id,
                name=mic.name,
                kind="loopback",
                is_default="blackhole" in mic.name.lower(),
            )
        )

    devices.sort(key=lambda d: (not d.is_default, d.name.lower()))
    return devices


def list_loopback_devices() -> list[AudioDeviceInfo]:
    """Dispositivos para capturar áudio da reunião (sistema / participantes)."""
    if sys.platform == "win32":
        return _list_wasapi_loopback()
    if sys.platform == "darwin":
        return _list_mac_participant_devices()
    return []


def resolve_microphone(device_id: str | None) -> Any | None:
    if device_id:
        try:
            return sc.get_microphone(device_id, include_loopback=False)
        except Exception:
            pass
    return sc.default_microphone()


def _resolve_mac_participant_device(device_id: str | None) -> Any | None:
    virtual_mics = [
        m
        for m in sc.all_microphones(include_loopback=False)
        if is_mac_virtual_capture_device(m.name)
    ]
    loopbacks = [
        m for m in sc.all_microphones(include_loopback=True) if getattr(m, "isloopback", False)
    ]
    candidates = loopbacks + virtual_mics

    if device_id:
        for mic in candidates:
            if _device_id(mic) == device_id:
                return mic
        try:
            return sc.get_microphone(device_id, include_loopback=False)
        except Exception:
            pass

    for mic in virtual_mics:
        if "blackhole" in mic.name.lower():
            return mic
    return candidates[0] if candidates else None


def resolve_loopback(device_id: str | None) -> Any | None:
    if sys.platform == "darwin":
        return _resolve_mac_participant_device(device_id)

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
    return sys.platform in ("win32", "darwin")


def platform_loopback_kind() -> Literal["wasapi", "virtual", "none"]:
    if sys.platform == "win32":
        return "wasapi"
    if sys.platform == "darwin":
        return "virtual"
    return "none"
