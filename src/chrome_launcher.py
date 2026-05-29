"""Abrir Google Chrome para reuniões no navegador."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def find_chrome_executable() -> Path | None:
    if sys.platform != "win32":
        return None
    candidates = [
        Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
        / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
        / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("LOCALAPPDATA", ""))
        / "Google/Chrome/Application/chrome.exe",
    ]
    for path in candidates:
        if path.is_file():
            return path
    found = shutil.which("chrome") or shutil.which("google-chrome")
    return Path(found) if found else None


def open_chrome(url: str) -> tuple[bool, str]:
    """Abre uma URL no Chrome. Retorna (sucesso, mensagem)."""
    target = (url or "https://meet.google.com/new").strip()
    if not target.startswith(("http://", "https://")):
        target = f"https://{target}"

    if sys.platform == "darwin":
        try:
            subprocess.Popen(
                ["open", "-a", "Google Chrome", target],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True, f"Chrome aberto: {target}"
        except OSError:
            try:
                subprocess.Popen(["open", target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True, f"Navegador aberto: {target}"
            except OSError as exc:
                return False, f"Não foi possível abrir o Chrome: {exc}"

    chrome = find_chrome_executable()
    if chrome is None:
        return False, (
            "Google Chrome não encontrado neste PC.\n"
            "Instale o Chrome ou use «Iniciar reunião» com outro navegador."
        )

    try:
        subprocess.Popen(
            [str(chrome), target],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
        return True, f"Chrome aberto: {target}"
    except OSError as exc:
        return False, f"Não foi possível abrir o Chrome: {exc}"
