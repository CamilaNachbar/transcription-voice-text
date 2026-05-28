from __future__ import annotations

from datetime import datetime


def format_session_label(session_id: str) -> str:
    try:
        dt = datetime.strptime(session_id, "%Y%m%d_%H%M%S")
        return dt.strftime("%d/%m/%Y  ·  %H:%M")
    except ValueError:
        return session_id
