from __future__ import annotations

import customtkinter as ctk

from .theme import AppTheme, THEME


def section_header(
    parent: ctk.CTkBaseClass,
    title: str,
    subtitle: str | None = None,
    *,
    theme: AppTheme = THEME,
) -> ctk.CTkFrame:
    frame = ctk.CTkFrame(parent, fg_color="transparent")
    ctk.CTkLabel(
        frame,
        text=title,
        font=theme.ctk_font(theme.font_section()),
        text_color=theme.text,
    ).pack(anchor="w")
    if subtitle:
        ctk.CTkLabel(
            frame,
            text=subtitle,
            font=theme.ctk_font(theme.font_small()),
            text_color=theme.text_muted,
            justify="left",
        ).pack(anchor="w", pady=(2, 0))
    return frame


def card(
    parent: ctk.CTkBaseClass,
    *,
    theme: AppTheme = THEME,
    transparent: bool = False,
) -> ctk.CTkFrame:
    fg = "transparent" if transparent else theme.surface
    return ctk.CTkFrame(
        parent,
        fg_color=fg,
        corner_radius=theme.radius_md,
        border_width=0 if transparent else 1,
        border_color=theme.border,
    )


def hint_label(
    parent: ctk.CTkBaseClass,
    text: str,
    *,
    theme: AppTheme = THEME,
    danger: bool = False,
) -> ctk.CTkLabel:
    return ctk.CTkLabel(
        parent,
        text=text,
        font=theme.ctk_font(theme.font_small()),
        text_color=theme.danger if danger else theme.text_muted,
        justify="left",
        anchor="w",
    )


def field_label(parent: ctk.CTkBaseClass, text: str, *, theme: AppTheme = THEME) -> ctk.CTkLabel:
    return ctk.CTkLabel(
        parent,
        text=text,
        font=theme.ctk_font(theme.font_small()),
        text_color=theme.text_soft,
    )
