from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from .config import AppConfig
from .transcriber import TranscriptLine


@dataclass
class SessionArtifacts:
    session_id: str
    folder: Path
    raw_path: Path
    formatted_path: Path
    summary_path: Path


class SessionStore:
    def __init__(self, config: AppConfig):
        self.root = config.session_root
        self.root.mkdir(parents=True, exist_ok=True)

    def new_session(self) -> SessionArtifacts:
        session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        folder = self.root / session_id
        folder.mkdir(parents=True, exist_ok=True)
        return SessionArtifacts(
            session_id=session_id,
            folder=folder,
            raw_path=folder / "transcricao_raw.txt",
            formatted_path=folder / "transcricao_formatada.txt",
            summary_path=folder / "resumo.txt",
        )

    def save(self, artifacts: SessionArtifacts, lines: list[TranscriptLine], formatted: str, summary: str) -> None:
        raw_text = "\n".join(
            f"[{line.when.strftime('%H:%M:%S')}] {line.speaker}: {line.text}" for line in lines
        )
        artifacts.raw_path.write_text(raw_text, encoding="utf-8")
        artifacts.formatted_path.write_text(formatted, encoding="utf-8")
        artifacts.summary_path.write_text(summary, encoding="utf-8")
        (artifacts.folder / "metadata.json").write_text(
            json.dumps(
                {
                    "session_id": artifacts.session_id,
                    "created_at": datetime.now().isoformat(),
                    "entries": [asdict(line) | {"when": line.when.isoformat()} for line in lines],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def list_sessions(self) -> list[Path]:
        return sorted([p for p in self.root.glob("*") if p.is_dir()], reverse=True)
