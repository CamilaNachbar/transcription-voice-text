from __future__ import annotations

import threading
from dataclasses import replace
from pathlib import Path

import customtkinter as ctk
from tkinter import messagebox

from .audio_capture import AudioCaptureService
from .claude_processor import ClaudePostProcessor
from .config import LLM_PROVIDER_LABELS, get_llm_status_detail, load_app_config
from .session_store import SessionStore
from .transcriber import TranscriptLine, WhisperTranscriber
from .ui.formatting import format_session_label
from .user_settings import load_appearance_mode, save_appearance_mode, save_llm_provider

WELCOME_TEXT = """Bem-vindo ao Transcritor de Reuniões

• Clique em "Iniciar reunião" para capturar microfone e áudio do sistema.
• A transcrição aparece aqui em tempo real.
• Pausas de fala são detectadas automaticamente.
• Ao parar, geramos transcrição formatada e resumo em .txt.

Selecione uma sessão à esquerda para revisar reuniões anteriores.
"""


class DesktopTranscriberApp:
  STATUS_IDLE = ("Parado", "#6c757d")
  STATUS_RECORDING = ("Gravando", "#dc3545")
  STATUS_PROCESSING = ("Processando", "#0d6efd")
  STATUS_DONE = ("Pronto", "#198754")

  def __init__(self) -> None:
    appearance = load_appearance_mode() or "system"
    ctk.set_appearance_mode(appearance)
    ctk.set_default_color_theme("blue")

    self.config = load_app_config()
    self.store = SessionStore(self.config)
    self.capture = AudioCaptureService(self.config)
    self.transcriber = WhisperTranscriber(self.config)
    self.processor = ClaudePostProcessor(self.config)

    self.root = ctk.CTk()
    self.root.title("Transcritor de Reuniões")
    self.root.geometry("1100x700")
    self.root.minsize(960, 620)

    self.running = False
    self.worker: threading.Thread | None = None
    self.lines: list[TranscriptLine] = []
    self.current_session = None
    self._selected_session: str | None = None
    self._session_buttons: dict[str, ctk.CTkButton] = {}

    self._build_ui()
    self._refresh_session_list()
    self._sync_llm_ui()
    self._set_status(self.STATUS_IDLE)
    self._show_welcome()

  def _build_ui(self) -> None:
    self.root.grid_columnconfigure(0, weight=1)
    self.root.grid_rowconfigure(2, weight=1)

    # --- Cabeçalho ---
    header = ctk.CTkFrame(self.root, fg_color="transparent")
    header.grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 8))

    title = ctk.CTkLabel(
      header,
      text="Transcritor de Reuniões",
      font=ctk.CTkFont(size=26, weight="bold"),
    )
    title.pack(anchor="w")
    ctk.CTkLabel(
      header,
      text="Captura local · Whisper · Resumo com Claude",
      font=ctk.CTkFont(size=13),
      text_color="gray55",
    ).pack(anchor="w", pady=(2, 0))

    # --- Barra de ações ---
    toolbar = ctk.CTkFrame(self.root, corner_radius=12)
    toolbar.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 12))

    actions = ctk.CTkFrame(toolbar, fg_color="transparent")
    actions.pack(side="left", fill="y", padx=16, pady=14)

    self.start_btn = ctk.CTkButton(
      actions,
      text="▶  Iniciar reunião",
      width=160,
      height=40,
      font=ctk.CTkFont(size=14, weight="bold"),
      fg_color="#198754",
      hover_color="#157347",
      command=self.start,
    )
    self.start_btn.pack(side="left", padx=(0, 10))

    self.stop_btn = ctk.CTkButton(
      actions,
      text="■  Parar e salvar",
      width=160,
      height=40,
      font=ctk.CTkFont(size=14, weight="bold"),
      fg_color="#dc3545",
      hover_color="#bb2d3b",
      command=self.stop,
      state="disabled",
    )
    self.stop_btn.pack(side="left")

    status_frame = ctk.CTkFrame(toolbar, fg_color="transparent")
    status_frame.pack(side="right", padx=20, pady=14)

    self.status_badge = ctk.CTkLabel(
      status_frame,
      text="Parado",
      width=120,
      height=32,
      corner_radius=16,
      font=ctk.CTkFont(size=13, weight="bold"),
      fg_color="#6c757d",
    )
    self.status_badge.pack(side="right")

    self.progress = ctk.CTkProgressBar(status_frame, width=140, mode="indeterminate")
    self.progress.pack(side="right", padx=(0, 12))
    self.progress.pack_forget()

    # --- Área principal ---
    main = ctk.CTkFrame(self.root, fg_color="transparent")
    main.grid(row=2, column=0, sticky="nsew", padx=20, pady=(0, 12))
    main.grid_columnconfigure(1, weight=1)
    main.grid_rowconfigure(0, weight=1)

    # Sidebar
    sidebar = ctk.CTkFrame(main, width=300, corner_radius=12)
    sidebar.grid(row=0, column=0, sticky="ns", padx=(0, 12))
    sidebar.grid_propagate(False)

    ctk.CTkLabel(
      sidebar,
      text="Histórico",
      font=ctk.CTkFont(size=15, weight="bold"),
    ).pack(anchor="w", padx=16, pady=(16, 4))

    ctk.CTkLabel(
      sidebar,
      text="Reuniões salvas por data e hora",
      font=ctk.CTkFont(size=11),
      text_color="gray55",
    ).pack(anchor="w", padx=16, pady=(0, 8))

    self.sessions_scroll = ctk.CTkScrollableFrame(sidebar, fg_color="transparent")
    self.sessions_scroll.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    self.empty_sessions_label = ctk.CTkLabel(
      self.sessions_scroll,
      text="Nenhuma sessão ainda.\nInicie uma reunião para começar.",
      font=ctk.CTkFont(size=12),
      text_color="gray55",
      justify="center",
    )

    refresh_btn = ctk.CTkButton(
      sidebar,
      text="Atualizar lista",
      height=32,
      fg_color="transparent",
      border_width=1,
      text_color=("gray20", "gray80"),
      command=self._refresh_session_list,
    )
    refresh_btn.pack(fill="x", padx=12, pady=(0, 12))

    # Painel de conteúdo
    content = ctk.CTkFrame(main, corner_radius=12)
    content.grid(row=0, column=1, sticky="nsew")
    content.grid_columnconfigure(0, weight=1)
    content.grid_rowconfigure(1, weight=1)

    content_header = ctk.CTkFrame(content, fg_color="transparent")
    content_header.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 8))

    self.content_title = ctk.CTkLabel(
      content_header,
      text="Transcrição",
      font=ctk.CTkFont(size=15, weight="bold"),
    )
    self.content_title.pack(side="left")

    self.line_count_label = ctk.CTkLabel(
      content_header,
      text="",
      font=ctk.CTkFont(size=12),
      text_color="gray55",
    )
    self.line_count_label.pack(side="right")

    self.live_text = ctk.CTkTextbox(
      content,
      font=ctk.CTkFont(size=14),
      wrap="word",
      corner_radius=8,
    )
    self.live_text.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 16))

    # --- Rodapé: LLM + tema ---
    footer = ctk.CTkFrame(self.root, corner_radius=12)
    footer.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 20))

    llm_left = ctk.CTkFrame(footer, fg_color="transparent")
    llm_left.pack(side="left", fill="x", expand=True, padx=16, pady=12)

    ctk.CTkLabel(
      llm_left,
      text="Provedor de IA",
      font=ctk.CTkFont(size=12, weight="bold"),
    ).pack(anchor="w")

    llm_row = ctk.CTkFrame(llm_left, fg_color="transparent")
    llm_row.pack(anchor="w", pady=(6, 0))

    self.llm_menu = ctk.CTkOptionMenu(
      llm_row,
      values=list(LLM_PROVIDER_LABELS.values()),
      width=220,
      command=self._on_llm_provider_changed,
    )
    self.llm_menu.pack(side="left")

    self.llm_status = ctk.CTkLabel(
      llm_row,
      text="",
      font=ctk.CTkFont(size=11),
      text_color="gray55",
      anchor="w",
    )
    self.llm_status.pack(side="left", padx=(16, 0))

    theme_right = ctk.CTkFrame(footer, fg_color="transparent")
    theme_right.pack(side="right", padx=16, pady=12)

    ctk.CTkLabel(
      theme_right,
      text="Aparência",
      font=ctk.CTkFont(size=12, weight="bold"),
    ).pack(anchor="e")

    self.theme_seg = ctk.CTkSegmentedButton(
      theme_right,
      values=["Sistema", "Claro", "Escuro"],
      command=self._on_theme_changed,
    )
    self.theme_seg.pack(pady=(6, 0))
    theme_labels = {"system": "Sistema", "light": "Claro", "dark": "Escuro"}
    self.theme_seg.set(theme_labels.get(load_appearance_mode() or "system", "Sistema"))

  def _show_welcome(self) -> None:
    self.content_title.configure(text="Transcrição")
    self.line_count_label.configure(text="")
    self.live_text.configure(state="normal")
    self.live_text.delete("1.0", "end")
    self.live_text.insert("1.0", WELCOME_TEXT)
    self.live_text.configure(state="disabled")

  def _set_text_content(self, title: str, body: str, subtitle: str = "") -> None:
    self.content_title.configure(text=title)
    self.line_count_label.configure(text=subtitle)
    self.live_text.configure(state="normal")
    self.live_text.delete("1.0", "end")
    self.live_text.insert("1.0", body)
    if self.running:
      self.live_text.configure(state="disabled")
    else:
      self.live_text.configure(state="normal")

  def _set_status(self, status: tuple[str, str]) -> None:
    text, color = status
    self.status_badge.configure(text=text, fg_color=color)

  def _sync_llm_ui(self) -> None:
    mode = self.config.llm_provider
    label = LLM_PROVIDER_LABELS.get(mode, mode)
    self.llm_menu.set(label)
    self.llm_status.configure(text=get_llm_status_detail(self.config))
    state = "disabled" if self.running else "normal"
    self.llm_menu.configure(state=state)

  def _on_llm_provider_changed(self, label: str) -> None:
    if self.running:
      return
    mode = next((k for k, v in LLM_PROVIDER_LABELS.items() if v == label), None)
    if mode is None:
      return
    save_llm_provider(mode)
    self.config = replace(self.config, llm_provider=mode)
    self.processor.reload(self.config)
    self._sync_llm_ui()

  def _on_theme_changed(self, choice: str) -> None:
    mapping = {"Sistema": "system", "Claro": "light", "Escuro": "dark"}
    mode = mapping.get(choice, "system")
    save_appearance_mode(mode)
    ctk.set_appearance_mode(mode)

  def start(self) -> None:
    if self.running:
      return
    self.running = True
    self.lines.clear()
    self._selected_session = None
    self._highlight_session(None)
    self.live_text.configure(state="normal")
    self.live_text.delete("1.0", "end")
    self.content_title.configure(text="Ao vivo")
    self.line_count_label.configure(text="0 falas")
    self.current_session = self.store.new_session()
    self.capture.start()
    self.worker = threading.Thread(target=self._worker_loop, daemon=True)
    self.worker.start()
    self._set_status(self.STATUS_RECORDING)
    self.start_btn.configure(state="disabled")
    self.stop_btn.configure(state="normal")
    self._sync_llm_ui()

  def stop(self) -> None:
    if not self.running:
      return
    self.running = False
    self.capture.stop()
    if self.worker:
      self.worker.join(timeout=2.0)
    self._set_status(self.STATUS_PROCESSING)
    self.progress.pack(side="right", padx=(0, 12), before=self.status_badge)
    self.progress.start()
    self.root.update_idletasks()

    raw = "\n".join(f"[{x.when.strftime('%H:%M:%S')}] {x.speaker}: {x.text}" for x in self.lines)
    formatted = self.processor.refine_transcript(raw)
    summary = self.processor.summarize(formatted)
    self.store.save(self.current_session, self.lines, formatted, summary)

    self.progress.stop()
    self.progress.pack_forget()
    self._set_status(self.STATUS_DONE)
    self.start_btn.configure(state="normal")
    self.stop_btn.configure(state="disabled")
    self._sync_llm_ui()
    self._refresh_session_list()

    body = (
      "━━━ TRANSCRIÇÃO FORMATADA ━━━\n\n"
      f"{formatted}\n\n"
      "━━━ RESUMO DA REUNIÃO ━━━\n\n"
      f"{summary}"
    )
    self._set_text_content("Resultado da reunião", body, f"{len(self.lines)} falas · arquivos salvos")
    messagebox.showinfo(
      "Reunião salva",
      f"Arquivos gerados em:\n{self.current_session.folder}",
    )

  def _worker_loop(self) -> None:
    while self.running:
      segment = self.capture.read_segment()
      if not segment:
        continue
      line = self.transcriber.transcribe_segment(segment)
      if not line:
        continue
      self.lines.append(line)
      self.root.after(0, self._append_live_line, line)

  def _append_live_line(self, line: TranscriptLine) -> None:
    self.live_text.configure(state="normal")
    self.live_text.insert(
      "end",
      f"[{line.when.strftime('%H:%M:%S')}] {line.speaker}\n{line.text}\n\n",
    )
    self.live_text.see("end")
    self.line_count_label.configure(text=f"{len(self.lines)} falas")

  def _refresh_session_list(self) -> None:
    for widget in self.sessions_scroll.winfo_children():
      widget.destroy()
    self._session_buttons.clear()

    folders = self.store.list_sessions()
    if not folders:
      self.empty_sessions_label = ctk.CTkLabel(
        self.sessions_scroll,
        text="Nenhuma sessão ainda.\nInicie uma reunião para começar.",
        font=ctk.CTkFont(size=12),
        text_color="gray55",
        justify="center",
      )
      self.empty_sessions_label.pack(pady=24)
      return

    for folder in folders:
      sid = folder.name
      btn = ctk.CTkButton(
        self.sessions_scroll,
        text=format_session_label(sid),
        anchor="w",
        height=36,
        fg_color="transparent",
        text_color=("gray10", "gray90"),
        hover_color=("gray88", "gray28"),
        command=lambda s=sid: self._open_session(s),
      )
      btn.pack(fill="x", pady=2, padx=4)
      self._session_buttons[sid] = btn

    if self._selected_session and self._selected_session in self._session_buttons:
      self._highlight_session(self._selected_session)

  def _highlight_session(self, session_id: str | None) -> None:
    for sid, btn in self._session_buttons.items():
      if sid == session_id:
        btn.configure(fg_color=("#dbeafe", "#1e3a5f"), hover_color=("#bfdbfe", "#1e40af"))
      else:
        btn.configure(fg_color="transparent", hover_color=("gray88", "gray28"))

  def _open_session(self, folder_name: str) -> None:
    if self.running:
      return
    self._selected_session = folder_name
    self._highlight_session(folder_name)
    folder = Path(self.config.session_root) / folder_name
    formatted = folder / "transcricao_formatada.txt"
    summary = folder / "resumo.txt"
    parts: list[str] = []
    if formatted.exists():
      parts.append("━━━ TRANSCRIÇÃO FORMATADA ━━━\n\n")
      parts.append(formatted.read_text(encoding="utf-8"))
    if summary.exists():
      parts.append("\n\n━━━ RESUMO DA REUNIÃO ━━━\n\n")
      parts.append(summary.read_text(encoding="utf-8"))
    if not parts:
      parts.append("Nenhum arquivo encontrado nesta sessão.")
    label = format_session_label(folder_name)
    self._set_text_content(f"Reunião · {label}", "".join(parts), str(folder))

  def run(self) -> None:
    self.root.mainloop()
