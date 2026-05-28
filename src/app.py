from __future__ import annotations

import queue
import threading
import time
from dataclasses import replace
from pathlib import Path

import customtkinter as ctk
from tkinter import messagebox

from .audio_capture import AudioCaptureService, AudioSegment, CaptureStatus
from .audio_devices import AudioDeviceInfo, list_loopback_devices, list_microphones
from .claude_processor import ClaudePostProcessor
from .config import LLM_PROVIDER_LABELS, get_llm_status_detail, load_app_config
from .llm_connection_test import format_connection_report, run_all_connection_tests
from .session_store import SessionStore
from .transcription_pipeline import TranscriptionPipeline
from .transcriber import TranscriptLine, WhisperTranscriber
from .wake_assistant import (
  WakeTriggerState,
  contains_wake_word,
  format_transcript,
)
from .ui.formatting import format_session_label
from .user_settings import (
  load_appearance_mode,
  load_capture_system_audio,
  load_loopback_device_id,
  load_microphone_device_id,
  load_wake_assistant_enabled,
  save_appearance_mode,
  save_capture_system_audio,
  save_llm_provider,
  save_loopback_device_id,
  save_microphone_device_id,
  save_wake_assistant_enabled,
)

WELCOME_TEXT = """Bem-vindo ao Transcritor de Reuniões

Reuniões online (Teams, Meet, Zoom, navegador):
• Microfone → «Você».
• Áudio da reunião → tenta separar Participante A, B, C… por timbre de voz.
• Use fone de ouvido para evitar eco (microfone pegando o mesmo som duas vezes).
• Em «Participantes», escolha o mesmo dispositivo de saída do Windows e do Teams.
• Com «Ativar IA ao ouvir CAMILA», a IA resume a reunião e sugere uma resposta quando alguém disser seu nome.

Clique em "Iniciar reunião" para começar. Ao parar, geramos transcrição e resumo em .txt.
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
    self.capture: AudioCaptureService | None = None
    self._mic_devices: list[AudioDeviceInfo] = []
    self._loopback_devices: list[AudioDeviceInfo] = []
    self.transcriber = WhisperTranscriber(self.config)
    self.pipeline = TranscriptionPipeline(self.config)
    self.processor = ClaudePostProcessor(self.config)

    self.root = ctk.CTk()
    self.root.title("Transcritor de Reuniões")
    self.root.geometry("1100x700")
    self.root.minsize(960, 620)

    self.running = False
    self.worker: threading.Thread | None = None
    self._transcriber_thread: threading.Thread | None = None
    self._segment_queue: queue.Queue[AudioSegment | None] = queue.Queue()
    self.lines: list[TranscriptLine] = []
    self.current_session = None
    self._selected_session: str | None = None
    self._session_buttons: dict[str, ctk.CTkButton] = {}
    self._wake_state = WakeTriggerState()
    self._llm_test_running = False
    wake_pref = load_wake_assistant_enabled()
    if wake_pref is not None:
      self.config = replace(self.config, wake_assistant_enabled=wake_pref)

    self._build_ui()
    self._refresh_session_list()
    self._sync_llm_ui()
    self._set_status(self.STATUS_IDLE)
    self._show_welcome()

  def _build_ui(self) -> None:
    self.root.grid_columnconfigure(0, weight=1)
    self.root.grid_rowconfigure(2, weight=1)
    self.root.grid_rowconfigure(3, weight=0)

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

    session_actions = ctk.CTkFrame(sidebar, fg_color="transparent")
    session_actions.pack(fill="x", padx=12, pady=(0, 8))

    refresh_btn = ctk.CTkButton(
      session_actions,
      text="Atualizar lista",
      height=32,
      fg_color="transparent",
      border_width=1,
      text_color=("gray20", "gray80"),
      command=self._refresh_session_list,
    )
    refresh_btn.pack(fill="x", pady=(0, 6))

    self.delete_session_btn = ctk.CTkButton(
      session_actions,
      text="Apagar selecionada",
      height=32,
      fg_color="#dc3545",
      hover_color="#bb2d3b",
      command=self._delete_selected_session,
    )
    self.delete_session_btn.pack(fill="x", pady=(0, 6))

    self.delete_all_btn = ctk.CTkButton(
      session_actions,
      text="Apagar todas",
      height=32,
      fg_color="transparent",
      border_width=1,
      border_color="#dc3545",
      text_color="#dc3545",
      hover_color=("gray90", "gray20"),
      command=self._delete_all_sessions,
    )
    self.delete_all_btn.pack(fill="x", pady=(0, 4))

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

    # --- Áudio: dispositivos ---
    audio_bar = ctk.CTkFrame(self.root, corner_radius=12)
    audio_bar.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 8))

    audio_inner = ctk.CTkFrame(audio_bar, fg_color="transparent")
    audio_inner.pack(fill="x", padx=16, pady=12)

    ctk.CTkLabel(
      audio_inner,
      text="Entrada de áudio",
      font=ctk.CTkFont(size=12, weight="bold"),
    ).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 8))

    ctk.CTkLabel(audio_inner, text="Microfone", font=ctk.CTkFont(size=11)).grid(
      row=1, column=0, sticky="w", padx=(0, 8),
    )
    self.mic_menu = ctk.CTkOptionMenu(
      audio_inner, width=320, command=self._on_mic_device_changed,
    )
    self.mic_menu.grid(row=1, column=1, sticky="w", padx=(0, 20))

    ctk.CTkLabel(
      audio_inner,
      text="Participantes (Teams, Meet…)",
      font=ctk.CTkFont(size=11),
    ).grid(row=1, column=2, sticky="w", padx=(0, 8))
    self.loopback_menu = ctk.CTkOptionMenu(
      audio_inner, width=320, command=self._on_loopback_device_changed,
    )
    self.loopback_menu.grid(row=1, column=3, sticky="w")

    self.system_audio_switch = ctk.CTkSwitch(
      audio_inner,
      text="Capturar voz dos participantes (áudio da reunião no PC)",
      command=self._on_system_audio_toggled,
    )
    self.system_audio_switch.grid(row=2, column=0, columnspan=2, sticky="w", pady=(10, 0))
    if load_capture_system_audio():
      self.system_audio_switch.select()
    else:
      self.system_audio_switch.deselect()

    self.audio_status = ctk.CTkLabel(
      audio_inner,
      text="",
      font=ctk.CTkFont(size=11),
      text_color="gray55",
      anchor="w",
      justify="left",
    )
    self.audio_status.grid(row=2, column=2, columnspan=2, sticky="w", padx=(8, 0), pady=(10, 0))

    refresh_audio_btn = ctk.CTkButton(
      audio_inner,
      text="Atualizar dispositivos",
      width=140,
      height=28,
      command=self._refresh_audio_devices,
    )
    refresh_audio_btn.grid(row=3, column=0, columnspan=2, sticky="w", pady=(10, 0))

    self._refresh_audio_devices()

    # --- Rodapé: LLM + tema ---
    footer = ctk.CTkFrame(self.root, corner_radius=12)
    footer.grid(row=4, column=0, sticky="ew", padx=20, pady=(0, 20))

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

    self.test_llm_btn = ctk.CTkButton(
      llm_row,
      text="Testar conexão IA",
      width=150,
      height=32,
      command=self._test_llm_connection,
    )
    self.test_llm_btn.pack(side="left", padx=(12, 0))

    wake_words_label = " / ".join(self.config.wake_words)
    self.wake_switch = ctk.CTkSwitch(
      llm_left,
      text=f"Ativar IA ao ouvir «{wake_words_label}» (resumo + sugestão de resposta)",
      command=self._on_wake_assistant_toggled,
    )
    self.wake_switch.pack(anchor="w", pady=(10, 0))
    if self.config.wake_assistant_enabled:
      self.wake_switch.select()
    else:
      self.wake_switch.deselect()

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

  def _device_label(self, device: AudioDeviceInfo) -> str:
    suffix = " ★ saída padrão do Windows" if device.is_default else ""
    return f"{device.name}{suffix}"

  def _refresh_audio_devices(self) -> None:
    self._mic_devices = list_microphones()
    self._loopback_devices = list_loopback_devices()

    mic_labels = [self._device_label(d) for d in self._mic_devices] or ["Nenhum microfone"]
    loop_labels = [self._device_label(d) for d in self._loopback_devices] or ["Nenhuma saída"]

    self.mic_menu.configure(values=mic_labels)
    self.loopback_menu.configure(values=loop_labels)

    saved_mic = load_microphone_device_id()
    saved_loop = load_loopback_device_id()

    mic_idx = next((i for i, d in enumerate(self._mic_devices) if d.id == saved_mic), None)
    loop_idx = next((i for i, d in enumerate(self._loopback_devices) if d.id == saved_loop), None)

    if mic_idx is None:
      mic_idx = next((i for i, d in enumerate(self._mic_devices) if d.is_default), 0)
    if loop_idx is None:
      loop_idx = next((i for i, d in enumerate(self._loopback_devices) if d.is_default), 0)

    if self._mic_devices:
      self.mic_menu.set(mic_labels[mic_idx])
    if self._loopback_devices:
      self.loopback_menu.set(loop_labels[loop_idx])

    self._update_audio_status_hint()

  def _selected_mic_id(self) -> str | None:
    label = self.mic_menu.get()
    for device in self._mic_devices:
      if self._device_label(device) == label:
        return device.id
    return None

  def _selected_loopback_id(self) -> str | None:
    label = self.loopback_menu.get()
    for device in self._loopback_devices:
      if self._device_label(device) == label:
        return device.id
    return None

  def _on_mic_device_changed(self, _label: str) -> None:
    if self.running:
      return
    save_microphone_device_id(self._selected_mic_id())

  def _on_loopback_device_changed(self, _label: str) -> None:
    if self.running:
      return
    save_loopback_device_id(self._selected_loopback_id())
    self._update_audio_status_hint()

  def _on_system_audio_toggled(self) -> None:
    if self.running:
      return
    save_capture_system_audio(bool(self.system_audio_switch.get()))
    self._update_audio_status_hint()

  def _update_audio_status_hint(self) -> None:
    if not self.system_audio_switch.get():
      self.audio_status.configure(
        text="Só a sua voz. Ative «participantes» para Teams, Meet, Zoom e navegador.",
        text_color="gray55",
      )
      return
    if not self._loopback_devices:
      self.audio_status.configure(
        text="Nenhuma saída de loopback encontrada (Windows WASAPI).",
        text_color="#dc3545",
      )
      return
    label = self.loopback_menu.get()
    self.audio_status.configure(
      text=(
        f"Selecionado: {label}. "
        "Teams/Meet/Zoom e o Windows devem usar essa mesma saída de som. Prefira fone."
      ),
      text_color="gray55",
    )

  def _build_capture(self) -> AudioCaptureService:
    return AudioCaptureService(
      self.config,
      microphone_device_id=self._selected_mic_id(),
      loopback_device_id=self._selected_loopback_id(),
      capture_system_audio=bool(self.system_audio_switch.get()),
    )

  def _format_capture_status(self, status: CaptureStatus) -> str:
    parts: list[str] = []
    for src in (status.microfone, status.sistema):
      if src.active:
        parts.append(f"{src.name}: ok")
      elif src.error:
        parts.append(f"{src.name}: {src.error}")
    return " · ".join(parts) if parts else ""

  def _sync_llm_ui(self) -> None:
    mode = self.config.llm_provider
    label = LLM_PROVIDER_LABELS.get(mode, mode)
    self.llm_menu.set(label)
    self.llm_status.configure(text=get_llm_status_detail(self.config))
    state = "disabled" if self.running else "normal"
    self.llm_menu.configure(state=state)
    self.mic_menu.configure(state=state)
    self.loopback_menu.configure(state=state)
    self.system_audio_switch.configure(state=state)
    self.wake_switch.configure(state=state)
    if self._llm_test_running:
      self.test_llm_btn.configure(state="disabled", text="Testando…")
    else:
      self.test_llm_btn.configure(state=state, text="Testar conexão IA")
    self._sync_delete_buttons()

  def _test_llm_connection(self) -> None:
    if self.running or self._llm_test_running:
      return
    self._llm_test_running = True
    self._sync_llm_ui()
    self.llm_status.configure(text="Testando conexão com agentes de IA…")
    threading.Thread(target=self._run_llm_connection_test, daemon=True).start()

  def _run_llm_connection_test(self) -> None:
    try:
      results = run_all_connection_tests(self.config)
      report, any_ok = format_connection_report(results)
      self.root.after(0, self._show_llm_test_results, report, any_ok)
    except Exception as exc:
      self.root.after(
        0,
        self._show_llm_test_results,
        f"Erro ao executar testes:\n{exc}",
        False,
      )
    finally:
      self.root.after(0, self._finish_llm_connection_test)

  def _finish_llm_connection_test(self) -> None:
    self._llm_test_running = False
    self._sync_llm_ui()

  def _show_llm_test_results(self, report: str, success: bool) -> None:
    dialog = ctk.CTkToplevel(self.root)
    dialog.title("Teste de conexão — IA")
    dialog.geometry("560x420")
    dialog.transient(self.root)
    dialog.grab_set()

    header = ctk.CTkLabel(
      dialog,
      text="Resultado do teste" if success else "Falha na conexão",
      font=ctk.CTkFont(size=16, weight="bold"),
      text_color=("#198754" if success else "#dc3545"),
    )
    header.pack(anchor="w", padx=20, pady=(16, 8))

    box = ctk.CTkTextbox(dialog, font=ctk.CTkFont(size=13), wrap="word")
    box.pack(fill="both", expand=True, padx=20, pady=(0, 12))
    box.insert("1.0", report)
    box.configure(state="disabled")

    ctk.CTkButton(dialog, text="Fechar", width=120, command=dialog.destroy).pack(pady=(0, 16))

  def _on_wake_assistant_toggled(self) -> None:
    if self.running:
      return
    enabled = bool(self.wake_switch.get())
    save_wake_assistant_enabled(enabled)
    self.config = replace(self.config, wake_assistant_enabled=enabled)

  def _sync_delete_buttons(self) -> None:
    if self.running:
      self.delete_session_btn.configure(state="disabled")
      self.delete_all_btn.configure(state="disabled")
      return
    has_sessions = bool(self.store.list_sessions())
    self.delete_all_btn.configure(state="normal" if has_sessions else "disabled")
    can_delete_selected = bool(self._selected_session) and (
      Path(self.config.session_root) / self._selected_session
    ).is_dir()
    self.delete_session_btn.configure(state="normal" if can_delete_selected else "disabled")

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
    save_microphone_device_id(self._selected_mic_id())
    save_loopback_device_id(self._selected_loopback_id())
    save_capture_system_audio(bool(self.system_audio_switch.get()))

    self.capture = self._build_capture()
    capture_status = self.capture.start()
    status_text = self._format_capture_status(capture_status)
    diar_hint = self.pipeline.diarization_status()
    if status_text:
      self.audio_status.configure(
        text=f"{status_text} · {diar_hint}", text_color="gray55",
      )
    else:
      self.audio_status.configure(text=diar_hint, text_color="gray55")

    if self.system_audio_switch.get() and not capture_status.sistema.active:
      messagebox.showwarning(
        "Áudio dos participantes indisponível",
        "Não foi possível capturar o áudio da reunião (Teams, Meet, etc.).\n\n"
        f"{capture_status.sistema.error or 'Erro desconhecido.'}\n\n"
        "No Teams: Configurações → Dispositivos → Alto-falante = mesmo item "
        "de «Participantes» no app.\n"
        "No Windows: Configurações → Som → Saída (ex.: fones «Game» vs «Chat»).",
      )

    self.pipeline.start_session()
    self._wake_state = WakeTriggerState()
    self._segment_queue = queue.Queue()
    self._transcriber_thread = threading.Thread(
      target=self._transcription_loop, name="transcriber", daemon=True,
    )
    self._transcriber_thread.start()
    self.worker = threading.Thread(target=self._capture_dispatch_loop, daemon=True)
    self.worker.start()
    self._set_status(self.STATUS_RECORDING)
    self.start_btn.configure(state="disabled")
    self.stop_btn.configure(state="normal")
    self._sync_llm_ui()

  def stop(self) -> None:
    if not self.running:
      return
    self.running = False
    if self.capture:
      self.capture.stop()
    if self.worker:
      self.worker.join(timeout=3.0)
    self._segment_queue.put(None)
    if self._transcriber_thread:
      self._transcriber_thread.join(timeout=120.0)
    self._set_status(self.STATUS_PROCESSING)
    self.progress.pack(side="right", padx=(0, 12), before=self.status_badge)
    self.progress.start()
    self.root.update_idletasks()

    raw = "\n".join(f"[{x.when.strftime('%H:%M:%S')}] {x.speaker}: {x.text}" for x in self.lines)
    formatted = self.processor.refine_transcript(raw)
    summary = self.processor.summarize(formatted)
    speakers = self.pipeline.registry.summary() if self.pipeline.registry else []
    self.store.save(
      self.current_session, self.lines, formatted, summary, speakers=speakers,
    )

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

  def _capture_dispatch_loop(self) -> None:
    """Encaminha segmentos de áudio para transcrição sem bloquear a captura."""
    while self.running:
      if not self.capture:
        time.sleep(0.05)
        continue
      segment = self.capture.read_segment(timeout=0.15)
      if segment:
        self._segment_queue.put(segment)
    if self.capture:
      while True:
        segment = self.capture.read_segment(timeout=0.05)
        if not segment:
          break
        self._segment_queue.put(segment)

  def _transcription_loop(self) -> None:
    while True:
      try:
        segment = self._segment_queue.get(timeout=0.25)
      except queue.Empty:
        if not self.running:
          continue
        continue
      if segment is None:
        break
      for line in self.pipeline.process_segment(segment, self.transcriber):
        self.lines.append(line)
        self.root.after(0, self._append_live_line, line)
        self.root.after(0, self._maybe_trigger_wake_assistant, line)

  def _wake_assistant_enabled_now(self) -> bool:
    return bool(self.wake_switch.get()) and self.config.wake_assistant_enabled

  def _maybe_trigger_wake_assistant(self, line: TranscriptLine) -> None:
    if not self.running or not self._wake_assistant_enabled_now():
      return
    if len(self.lines) < self.config.wake_min_lines:
      return
    detected = contains_wake_word(line.text, list(self.config.wake_words))
    if not detected:
      return
    if not self._wake_state.can_trigger(self.config.wake_cooldown_seconds):
      return

    self._wake_state.mark_started()
    self._set_status(("IA ativada…", "#6f42c1"))
    threading.Thread(
      target=self._run_wake_assistant,
      args=(detected, line),
      name="wake-assistant",
      daemon=True,
    ).start()

  def _run_wake_assistant(self, wake_name: str, trigger_line: TranscriptLine) -> None:
    try:
      transcript = format_transcript(self.lines)
      result = self.processor.assist_on_wake(transcript, wake_name)
      self.root.after(0, self._show_wake_assistant_result, wake_name, trigger_line, result)
    except Exception as exc:
      self.root.after(
        0,
        self._show_wake_assistant_result,
        wake_name,
        trigger_line,
        f"Erro ao consultar IA: {exc}",
      )
    finally:
      self._wake_state.mark_finished()
      if self.running:
        self.root.after(0, lambda: self._set_status(self.STATUS_RECORDING))

  def _show_wake_assistant_result(
    self, wake_name: str, trigger_line: TranscriptLine, result: str,
  ) -> None:
    when = trigger_line.when.strftime("%H:%M:%S")
    block = (
      f"\n{'═' * 52}\n"
      f"🎙 IA ativada — «{wake_name}» mencionado às {when}\n"
      f"{'═' * 52}\n\n"
      f"{result.strip()}\n\n"
    )
    self.live_text.configure(state="normal")
    self.live_text.insert("end", block)
    self.live_text.see("end")
    if self.running:
      self.live_text.configure(state="disabled")

    if self.current_session:
      path = self.current_session.folder / (
        f"assistente_{wake_name.lower()}_{trigger_line.when.strftime('%H%M%S')}.txt"
      )
      try:
        path.write_text(
          f"Gatilho: {wake_name} às {when}\n\n{result}",
          encoding="utf-8",
        )
      except OSError:
        pass

    messagebox.showinfo(
      f"Assistente — {wake_name}",
      "Resumo e sugestão de resposta adicionados à transcrição ao vivo.\n\n"
      "Role o painel central para ver o bloco destacado.",
    )

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
    self._sync_delete_buttons()

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
    self._sync_delete_buttons()

  def _delete_selected_session(self) -> None:
    if self.running or not self._selected_session:
      return
    sid = self._selected_session
    label = format_session_label(sid)
    if not messagebox.askyesno(
      "Apagar transcrição",
      f"Apagar permanentemente a reunião?\n\n{label}\n\nEsta ação não pode ser desfeita.",
      icon="warning",
    ):
      return
    if self.store.delete_session(sid):
      self._selected_session = None
      self._show_welcome()
      self._refresh_session_list()
      messagebox.showinfo("Apagado", "Transcrição removida.")
    else:
      messagebox.showerror("Erro", "Não foi possível apagar a sessão selecionada.")

  def _delete_all_sessions(self) -> None:
    if self.running:
      return
    folders = self.store.list_sessions()
    if not folders:
      return
    if not messagebox.askyesno(
      "Apagar todas as transcrições",
      f"Apagar permanentemente todas as {len(folders)} reuniões salvas?\n\n"
      "Esta ação não pode ser desfeita.",
      icon="warning",
    ):
      return
    removed = self.store.delete_all_sessions()
    self._selected_session = None
    self._show_welcome()
    self._refresh_session_list()
    messagebox.showinfo("Apagado", f"{removed} transcrição(ões) removida(s).")

  def run(self) -> None:
    self.root.mainloop()
