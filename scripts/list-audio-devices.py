#!/usr/bin/env python3
"""Lista microfones e saídas de loopback (áudio do PC) disponíveis."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.audio_devices import list_loopback_devices, list_microphones  # noqa: E402


def main() -> int:
    print("=== Microfones ===\n")
    mics = list_microphones()
    if not mics:
        print("(nenhum)")
    for d in mics:
        mark = " [padrão]" if d.is_default else ""
        print(f"  {d.name}{mark}\n    id: {d.id}\n")

    print("=== Participantes — Teams, Meet, Zoom (loopback / WASAPI) ===\n")
    print(
        "Mesmo dispositivo em: Windows (Som → Saída), Teams (Configurações → Dispositivos "
        "→ Alto-falante) e no app em «Participantes».\n"
    )
    loops = list_loopback_devices()
    if not loops:
        print("(nenhum — loopback completo só no Windows)")
    for d in loops:
        mark = " [saída padrão do Windows]" if d.is_default else ""
        print(f"  {d.name}{mark}\n    id: {d.id}\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
