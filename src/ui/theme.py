from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AppTheme:
    """Paleta e tipografia — tuplas (claro, escuro) para CustomTkinter."""

  # Fundos
    bg: tuple[str, str] = ("#f1f5f9", "#0b1220")
    surface: tuple[str, str] = ("#ffffff", "#151d2e")
    surface_alt: tuple[str, str] = ("#f8fafc", "#1a2332")
    header: tuple[str, str] = ("#ffffff", "#111827")

  # Texto
    text: tuple[str, str] = ("#0f172a", "#f1f5f9")
    text_muted: tuple[str, str] = ("#64748b", "#94a3b8")
    text_soft: tuple[str, str] = ("#475569", "#cbd5e1")

  # Acentos
    primary: tuple[str, str] = ("#2563eb", "#3b82f6")
    primary_hover: tuple[str, str] = ("#1d4ed8", "#2563eb")
    primary_soft: tuple[str, str] = ("#dbeafe", "#1e3a5f")

    success: tuple[str, str] = ("#16a34a", "#22c55e")
    success_hover: tuple[str, str] = ("#15803d", "#16a34a")

    danger: tuple[str, str] = ("#dc2626", "#ef4444")
    danger_hover: tuple[str, str] = ("#b91c1c", "#dc2626")
    danger_soft: tuple[str, str] = ("#fee2e2", "#450a0a")

    warning: tuple[str, str] = ("#d97706", "#f59e0b")
    purple: tuple[str, str] = ("#7c3aed", "#8b5cf6")

    border: tuple[str, str] = ("#e2e8f0", "#334155")

  # Status
    status_idle: str = "#64748b"
    status_recording: str = "#dc2626"
    status_processing: str = "#2563eb"
    status_done: str = "#16a34a"
    status_ai: str = "#7c3aed"

    radius_sm: int = 8
    radius_md: int = 12
    radius_lg: int = 16
    radius_pill: int = 20

    def font_title(self) -> tuple[str, int, str]:
        return ("Segoe UI", 26, "bold")

    def font_subtitle(self) -> tuple[str, int]:
        return ("Segoe UI", 13)

    def font_section(self) -> tuple[str, int, str]:
        return ("Segoe UI", 13, "bold")

    def font_body(self) -> tuple[str, int]:
        return ("Segoe UI", 13)

    def font_small(self) -> tuple[str, int]:
        return ("Segoe UI", 11)

    def font_button(self) -> tuple[str, int, str]:
        return ("Segoe UI", 14, "bold")

    def ctk_font(self, spec: tuple) -> "ctk.CTkFont":
        import customtkinter as ctk

        if len(spec) == 2:
            return ctk.CTkFont(family=spec[0], size=spec[1])
        return ctk.CTkFont(family=spec[0], size=spec[1], weight=spec[2])


THEME = AppTheme()
