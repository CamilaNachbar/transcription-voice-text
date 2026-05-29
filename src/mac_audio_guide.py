"""Orientações para capturar áudio de reunião no macOS."""

from __future__ import annotations

import sys

MAC_VIRTUAL_DEVICE_KEYWORDS: tuple[str, ...] = (
    "blackhole",
    "loopback audio",
    "soundflower",
    "aggregate",
    "multi-output",
    "vb-cable",
)


def is_mac_virtual_capture_device(name: str) -> bool:
    lowered = name.lower()
    return any(keyword in lowered for keyword in MAC_VIRTUAL_DEVICE_KEYWORDS)


MAC_PARTICIPANT_SETUP = """Áudio dos participantes no macOS

O Mac não tem loopback nativo como o Windows. Use um dispositivo virtual:

1) BlackHole (grátis)
   • Instale: https://existential.audio/blackhole/
   • Abra «Configuração de Áudio MIDI» (Audio MIDI Setup)
   • Crie «Dispositivo com saída múltipla»: marque BlackHole 2ch + seus fones
   • Defina esse dispositivo como saída padrão do Mac
   • No app, em «Participantes», escolha BlackHole 2ch

2) Loopback (Rogue Amoeba, pago)
   • Mais estável que BlackHole em alguns Macs
   • Crie rota: saída do Meet/Teams → dispositivo virtual → selecione no app

3) Só microfone (sem participantes)
   • Desative «Capturar voz dos participantes»
   • Transcreve apenas o que você fala no microfone

Permissões: Ajustes do Sistema → Privacidade → Microfone → permita Terminal ou o app Python.

Se BlackHole não aparecer na lista, reinicie o Mac após instalar e clique em «Atualizar dispositivos».
"""
