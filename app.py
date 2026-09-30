import json
import random
import string
import subprocess
import sys
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox

try:
    import ttkbootstrap as ttk
    from ttkbootstrap.constants import BOTH, END, EW, LEFT, NSEW, NS, RIGHT, VERTICAL, W, WORD, X

    TTKBOOTSTRAP = True
except ImportError:
    from tkinter import ttk

    TTKBOOTSTRAP = False
    BOTH = tk.BOTH
    END = tk.END
    EW = tk.EW
    LEFT = tk.LEFT
    NSEW = tk.NSEW
    NS = tk.NS
    RIGHT = tk.RIGHT
    VERTICAL = tk.VERTICAL
    W = tk.W
    WORD = tk.WORD
    X = tk.X

try:
    import paho.mqtt.client as mqtt
except ImportError as exc:
    raise SystemExit(
        "Fehlende Abhaengigkeit: paho-mqtt. Bitte mit 'pip install paho-mqtt' installieren."
    ) from exc


INTERVAL_OPTIONS = {
    "nie": 0,
    "10 s": 10,
    "30 s": 30,
    "1 min": 60,
    "5 min": 300,
    "10 min": 600,
    "15 min": 900,
}

PAYLOAD_CHANGE_OPTIONS = {
    "10 s": 10,
    "30 s": 30,
    "1 min": 60,
    "5 min": 300,
    "10 min": 600,
    "15 min": 900,
    "30 min": 1800,
    "60 min": 3600,
}
DEFAULT_PAYLOAD_CHANGE_INTERVAL = "10 s"

TEMPLATES_FILENAME = "MQTT-Tool-Vorlagen.json"
LEGACY_PREFERENCES_FILENAME = "preferences.json"
PAYLOAD_CHANGE_CHECKED = "☑"
PAYLOAD_CHANGE_UNCHECKED = "☐"
THEME_LIGHT = "litera"
THEME_DARK = "darkly"
EXPLORER_MAGENTA = "#d946ef"


def _app_data_dir() -> Path:
    path = Path.home() / "Documents" / "MQTT-Tool"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _templates_path() -> Path:
    return _app_data_dir() / TEMPLATES_FILENAME


def _frozen_app_dir() -> Path | None:
    if not getattr(sys, "frozen", False):
        return None
    executable = Path(sys.executable).resolve()
    if executable.parent.name == "MacOS":
        return executable.parents[2].parent
    return executable.parent


def _legacy_template_paths() -> list[Path]:
    paths: list[Path] = []
    candidates = [
        Path(__file__).resolve().parent / TEMPLATES_FILENAME,
        Path(__file__).resolve().parent / LEGACY_PREFERENCES_FILENAME,
        Path(__file__).resolve().parent / "dist" / TEMPLATES_FILENAME,
        Path(__file__).resolve().parent / "dist" / LEGACY_PREFERENCES_FILENAME,
    ]
    frozen_dir = _frozen_app_dir()
    if frozen_dir is not None:
        candidates.extend(
            [
                frozen_dir / TEMPLATES_FILENAME,
                frozen_dir / LEGACY_PREFERENCES_FILENAME,
            ]
        )
    for candidate in candidates:
        if candidate not in paths:
            paths.append(candidate)
    return paths


UI_SETTINGS_PATH = _app_data_dir() / "ui-settings.json"
LOG_CATEGORIES = ("System", "Verbindung", "Senden", "Payload", "Topic", "Explorer", "Vorlage", "Fehler")


class MQTTToolApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("MQTT-Tool")
        self.root.geometry("780x800")

        self.client: mqtt.Client | None = None
        self.connected = False
        self._want_connected = False
        self._active_connection: tuple[str, str, str, str] | None = None
        self._suppress_disconnect_reconnect = False
        self.heartbeat_job: str | None = None
        self.payload_change_job: str | None = None
        self.reconnect_job: str | None = None
        self.watchdog_job: str | None = None
        self._reconnect_attempts = 0
        self._last_watchdog_wall: float | None = None
        self._button_flash_jobs: dict[str, str | None] = {}
        self.preferences: dict[str, dict[str, object]] = {}
        self.templates_path = _templates_path()
        self.explorer_window: tk.Toplevel | None = None
        self._explorer_counts: dict[str, int] = {}
        self._explorer_payloads: dict[str, str] = {}
        self._explorer_suppressed_topics: set[str] = set()
        self._explorer_sort_column = "topic"
        self._explorer_sort_reverse = False
        self.payload_change_column_width = 78
        self.topic_column_width = 300
        self.payload_column_width = 130
        self.payload_type_width = 90
        self.range_column_width = 110
        self.string_length_width = 110
        self.log_entries: list[tuple[str, str, str]] = []
        self.mono_font = ("Menlo", 11)
        self.ui_font = ("Helvetica Neue", 11)
        self.dark_mode = tk.BooleanVar(value=False)
        self.auto_reconnect = tk.BooleanVar(value=True)
        self._themed_buttons: list[tuple[ttk.Button, str]] = []
        self._load_ui_settings()

        self._build_ui()
        self._apply_theme(initial=True)
        self._load_preferences_file()
        self._refresh_preferences_dropdown()
        self._ensure_explorer_window(show=True)
        self._start_connection_watchdog()
        self._log("Applikation gestartet")
        self._log(f"Vorlagen-Datei: {self.templates_path}", category="Vorlage")

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=10)
        outer.pack(fill=BOTH, expand=True)

        self.preference_name = tk.StringVar(value="default")
        self.selected_preference = tk.StringVar()
        self.server_ip = tk.StringVar(value="127.0.0.1")
        self.server_port = tk.StringVar(value="1883")
        self.username = tk.StringVar()
        self.password = tk.StringVar()
        self.retain = tk.BooleanVar(value=False)
        self.qos = tk.StringVar(value="0")
        self.heartbeat = tk.StringVar(value="nie")
        self.payload_change_enabled = tk.BooleanVar(value=False)
        self.payload_change_interval = tk.StringVar(value=DEFAULT_PAYLOAD_CHANGE_INTERVAL)
        self.status_text = tk.StringVar(value="Nicht verbunden")
        self.selected_log_filter = tk.StringVar(value="Alle")
        self.explorer_status = tk.StringVar(
            value="Nicht verbunden – Explorer startet nach dem Verbinden"
        )
        self.explorer_include_sys = tk.BooleanVar(value=False)

        header = ttk.Frame(outer)
        header.pack(fill=X, pady=(0, 8))
        ttk.Label(header, text="MQTT-Tool", font=("Helvetica Neue", 18, "bold")).pack(side=LEFT)
        theme_frame = ttk.Frame(header)
        theme_frame.pack(side=RIGHT)
        if TTKBOOTSTRAP:
            ttk.Checkbutton(
                theme_frame,
                text="Dark Mode",
                variable=self.dark_mode,
                command=self._toggle_theme,
                bootstyle="round-toggle",
            ).pack(side=RIGHT)
        else:
            ttk.Checkbutton(
                theme_frame,
                text="Dark Mode",
                variable=self.dark_mode,
                command=self._toggle_theme,
            ).pack(side=RIGHT)

        paned = ttk.Panedwindow(outer, orient=tk.VERTICAL)
        paned.pack(fill=BOTH, expand=True)

        upper_container = ttk.Frame(paned)
        log_section = ttk.Labelframe(paned, text="Log", padding=8)
        paned.add(upper_container, weight=3)
        paned.add(log_section, weight=1)

        upper_container.columnconfigure(0, weight=1)
        upper_container.rowconfigure(0, weight=1)
        self._upper_canvas = tk.Canvas(upper_container, highlightthickness=0, borderwidth=0)
        upper_scroll = ttk.Scrollbar(upper_container, orient=VERTICAL, command=self._upper_canvas.yview)
        self._upper_canvas.grid(row=0, column=0, sticky=NSEW)
        upper_scroll.grid(row=0, column=1, sticky=NS)
        self._upper_canvas.configure(yscrollcommand=upper_scroll.set)

        upper = ttk.Frame(self._upper_canvas)
        self._upper_canvas_window = self._upper_canvas.create_window((0, 0), window=upper, anchor="nw")

        def _sync_upper_scroll_region(_event=None) -> None:
            self._upper_canvas.configure(scrollregion=self._upper_canvas.bbox("all"))

        def _sync_upper_canvas_width(event) -> None:
            self._upper_canvas.itemconfigure(self._upper_canvas_window, width=event.width)

        upper.bind("<Configure>", _sync_upper_scroll_region)
        self._upper_canvas.bind("<Configure>", _sync_upper_canvas_width)

        def _on_upper_mousewheel(event) -> str | None:
            if event.delta:
                self._upper_canvas.yview_scroll(int(-1 * event.delta), "units")
            return "break"

        def _bind_upper_wheel(_event=None) -> None:
            self._upper_canvas.bind_all("<MouseWheel>", _on_upper_mousewheel)

        def _unbind_upper_wheel(_event=None) -> None:
            self._upper_canvas.unbind_all("<MouseWheel>")

        self._upper_canvas.bind("<Enter>", _bind_upper_wheel)
        self._upper_canvas.bind("<Leave>", _unbind_upper_wheel)
        upper.bind("<Enter>", _bind_upper_wheel)
        upper.bind("<Leave>", _unbind_upper_wheel)

        templates_frame = ttk.Labelframe(upper, text="Vorlagen", padding=10)
        templates_frame.pack(fill=X, pady=(0, 8))
        templates_frame.columnconfigure(1, weight=1)
        ttk.Label(templates_frame, text="Name").grid(row=0, column=0, sticky=W, padx=(0, 8), pady=2)
        ttk.Entry(templates_frame, textvariable=self.preference_name).grid(row=0, column=1, sticky=EW, pady=2)
        pref_btns = ttk.Frame(templates_frame)
        pref_btns.grid(row=0, column=2, padx=(8, 0), pady=2)
        self._style_button(pref_btns, "Speichern", self.save_preference, "info-outline").pack(side=LEFT, padx=2)
        ttk.Label(templates_frame, text="Auswahl").grid(row=1, column=0, sticky=W, padx=(0, 8), pady=2)
        self.preferences_box = ttk.Combobox(
            templates_frame,
            textvariable=self.selected_preference,
            state="readonly",
        )
        self.preferences_box.grid(row=1, column=1, sticky=EW, pady=2)
        self.preferences_box.bind("<<ComboboxSelected>>", lambda _event: self.load_selected_preference())
        pref_actions = ttk.Frame(templates_frame)
        pref_actions.grid(row=1, column=2, padx=(8, 0), pady=2)
        self._style_button(pref_actions, "Laden", self.load_selected_preference, "secondary-outline").pack(
            side=LEFT, padx=2
        )
        self._style_button(pref_actions, "Löschen", self.delete_selected_preference, "danger-outline").pack(
            side=LEFT, padx=2
        )
        self._style_button(pref_actions, "Datei zeigen", self.reveal_templates_file, "secondary-outline").pack(
            side=LEFT, padx=2
        )
        self._style_button(pref_actions, "Importieren", self.import_templates_file, "secondary-outline").pack(
            side=LEFT, padx=2
        )

        conn_frame = ttk.Labelframe(upper, text="Verbindung", padding=10)
        conn_frame.pack(fill=X, pady=(0, 8))
        conn_frame.columnconfigure(1, weight=1)
        conn_frame.columnconfigure(3, weight=1)

        status_bar = ttk.Frame(conn_frame)
        status_bar.grid(row=0, column=0, columnspan=4, sticky=EW, pady=(0, 8))
        self.status_indicator = ttk.Label(status_bar, text="●", font=("Helvetica Neue", 18))
        self.status_indicator.pack(side=LEFT)
        ttk.Label(status_bar, textvariable=self.status_text, font=("Helvetica Neue", 11, "bold")).pack(
            side=LEFT, padx=(8, 0)
        )

        ttk.Label(conn_frame, text="Server-IP").grid(row=1, column=0, sticky=W, padx=(0, 8), pady=2)
        ttk.Entry(conn_frame, textvariable=self.server_ip).grid(row=1, column=1, sticky=EW, pady=2)
        ttk.Label(conn_frame, text="Port").grid(row=1, column=2, sticky=W, padx=(12, 8), pady=2)
        ttk.Entry(conn_frame, textvariable=self.server_port, width=8).grid(row=1, column=3, sticky=W, pady=2)

        ttk.Label(conn_frame, text="Benutzer").grid(row=2, column=0, sticky=W, padx=(0, 8), pady=2)
        ttk.Entry(conn_frame, textvariable=self.username).grid(row=2, column=1, sticky=EW, pady=2)
        ttk.Label(conn_frame, text="Passwort").grid(row=2, column=2, sticky=W, padx=(12, 8), pady=2)
        ttk.Entry(conn_frame, textvariable=self.password, show="*").grid(row=2, column=3, sticky=EW, pady=2)

        opts = ttk.Frame(conn_frame)
        opts.grid(row=3, column=0, columnspan=4, sticky=W, pady=(6, 0))
        ttk.Checkbutton(opts, text="Retain", variable=self.retain).pack(side=LEFT, padx=(0, 12))
        ttk.Label(opts, text="QoS").pack(side=LEFT)
        ttk.Combobox(opts, textvariable=self.qos, values=["0", "1", "2"], state="readonly", width=4).pack(
            side=LEFT, padx=(4, 12)
        )
        ttk.Label(opts, text="Heartbeat").pack(side=LEFT)
        heartbeat_box = ttk.Combobox(
            opts,
            textvariable=self.heartbeat,
            values=list(INTERVAL_OPTIONS.keys()),
            state="readonly",
            width=10,
        )
        heartbeat_box.pack(side=LEFT, padx=(4, 0))
        heartbeat_box.bind("<<ComboboxSelected>>", lambda _event: self._restart_heartbeat())

        action_row = ttk.Frame(conn_frame)
        action_row.grid(row=4, column=0, columnspan=4, sticky=W, pady=(10, 0))
        self.connect_btn = self._style_button(
            action_row, "Verbinden", self.connect, "success-outline", tracked=False
        )
        self.connect_btn.pack(side=LEFT, padx=(0, 6))
        self.disconnect_btn = self._style_button(
            action_row, "Trennen", self.disconnect, "danger", tracked=False
        )
        self.disconnect_btn.pack(side=LEFT, padx=(0, 6))
        self.publish_btn = self._style_button(
            action_row, "Jetzt senden", self._on_publish_clicked, "info-outline", tracked=False
        )
        self.publish_btn.pack(side=LEFT, padx=(0, 6))
        self._style_button(action_row, "Explorer", self.show_explorer_window, "secondary-outline").pack(side=LEFT)
        ttk.Checkbutton(
            action_row,
            text="Auto-Reconnect",
            variable=self.auto_reconnect,
            command=self._on_auto_reconnect_toggle,
        ).pack(side=LEFT, padx=(12, 0))

        topics_frame = ttk.Labelframe(upper, text="Topics", padding=10)
        topics_frame.pack(fill=BOTH, expand=True, pady=(0, 8))
        topics_frame.columnconfigure(0, weight=1)
        topics_frame.rowconfigure(0, weight=1)

        self.topic_tree = ttk.Treeview(
            topics_frame,
            columns=("payload_change", "topic", "payload", "payload_type", "range_low", "range_high", "string_length"),
            show="headings",
            height=6,
        )
        self.topic_tree.grid(row=0, column=0, sticky=NSEW)
        self.topic_tree.heading("payload_change", text="Änderung", anchor="center")
        self.topic_tree.heading("topic", text="Topic", anchor="w")
        self.topic_tree.heading("payload", text="Payload", anchor="center")
        self.topic_tree.heading("payload_type", text="Typ", anchor="center")
        self.topic_tree.heading("range_low", text="Range von", anchor="center")
        self.topic_tree.heading("range_high", text="Range bis", anchor="center")
        self.topic_tree.heading("string_length", text="Stringlänge", anchor="center")
        self.topic_tree.column("payload_change", width=self.payload_change_column_width, minwidth=50, anchor="center", stretch=False)
        self.topic_tree.column("topic", width=self.topic_column_width, minwidth=80, anchor="w", stretch=True)
        self.topic_tree.column("payload", width=self.payload_column_width, minwidth=60, anchor="center", stretch=True)
        self.topic_tree.column("payload_type", width=self.payload_type_width, minwidth=50, anchor="center", stretch=False)
        self.topic_tree.column("range_low", width=self.range_column_width, minwidth=60, anchor="center", stretch=False)
        self.topic_tree.column("range_high", width=self.range_column_width, minwidth=60, anchor="center", stretch=False)
        self.topic_tree.column("string_length", width=self.string_length_width, minwidth=60, anchor="center", stretch=False)
        self.topic_tree.bind("<Button-1>", self._on_topic_tree_click)
        self.topic_tree.bind("<Double-1>", self._on_topic_tree_double_click)

        topic_button_row = ttk.Frame(topics_frame)
        topic_button_row.grid(row=1, column=0, sticky=W, pady=(8, 0))
        self._style_button(topic_button_row, "Hinzufügen", self.add_topic_row, "info-outline").pack(side=LEFT, padx=(0, 4))
        self._style_button(topic_button_row, "Bearbeiten", self.edit_selected_topic_row, "info-outline").pack(
            side=LEFT, padx=4
        )
        self._style_button(topic_button_row, "Löschen", self.remove_selected_topic_row, "danger-outline").pack(
            side=LEFT, padx=4
        )

        payload_frame = ttk.Labelframe(upper, text="Payload-Änderung", padding=10)
        payload_frame.pack(fill=X)
        ttk.Checkbutton(
            payload_frame,
            text="Payload-Änderung aktivieren",
            variable=self.payload_change_enabled,
            command=self._on_payload_change_toggle,
        ).pack(side=LEFT, padx=(0, 16))
        ttk.Label(payload_frame, text="Intervall").pack(side=LEFT)
        payload_change_box = ttk.Combobox(
            payload_frame,
            textvariable=self.payload_change_interval,
            values=list(PAYLOAD_CHANGE_OPTIONS.keys()),
            state="readonly",
            width=12,
        )
        payload_change_box.pack(side=LEFT, padx=(6, 0))
        payload_change_box.bind("<<ComboboxSelected>>", lambda _event: self._restart_payload_change())

        log_header = ttk.Frame(log_section)
        log_header.pack(fill=X, pady=(0, 6))
        ttk.Label(log_header, text="Filter").pack(side=LEFT)
        log_filter_box = ttk.Combobox(
            log_header,
            textvariable=self.selected_log_filter,
            values=["Alle", *LOG_CATEGORIES],
            state="readonly",
            width=12,
        )
        log_filter_box.pack(side=LEFT, padx=(6, 0))
        log_filter_box.bind("<<ComboboxSelected>>", lambda _event: self._refresh_log_view())
        self._style_button(log_header, "Exportieren", self._export_log, "secondary-outline").pack(side=RIGHT, padx=(4, 0))
        self._style_button(log_header, "Leeren", self._clear_log, "secondary-outline").pack(side=RIGHT, padx=(4, 0))

        log_container = ttk.Frame(log_section)
        log_container.pack(fill=BOTH, expand=True)
        log_container.columnconfigure(0, weight=1)
        log_container.rowconfigure(0, weight=1)
        self.log_text = tk.Text(log_container, height=8, state=tk.DISABLED, wrap=WORD, font=self.mono_font, borderwidth=0)
        self.log_text.grid(row=0, column=0, sticky=NSEW)
        log_scrollbar = ttk.Scrollbar(log_container, orient=VERTICAL, command=self.log_text.yview)
        log_scrollbar.grid(row=0, column=1, sticky=NS)
        self.log_text.configure(yscrollcommand=log_scrollbar.set)

        self._update_range_visibility()
        self._update_connection_status()

    def _resolve_bootstyle(self, bootstyle: str) -> str:
        if not self.dark_mode.get():
            return bootstyle
        dark_styles = {
            "primary-outline": "info-outline",
            "secondary-outline": "info-outline",
            "secondary": "light-outline",
        }
        return dark_styles.get(bootstyle, bootstyle)

    def _style_button(
        self, parent, text: str, command, bootstyle: str = "", *, tracked: bool = True
    ) -> ttk.Button:
        if TTKBOOTSTRAP and bootstyle:
            button = ttk.Button(
                parent,
                text=text,
                command=command,
                bootstyle=self._resolve_bootstyle(bootstyle),
            )
            if tracked:
                self._themed_buttons.append((button, bootstyle))
            return button
        return ttk.Button(parent, text=text, command=command)

    def _refresh_button_styles(self) -> None:
        if not TTKBOOTSTRAP:
            return
        for button, bootstyle in self._themed_buttons:
            if button.winfo_exists():
                button.configure(bootstyle=self._resolve_bootstyle(bootstyle))

    def _load_ui_settings(self) -> None:
        if not UI_SETTINGS_PATH.exists():
            return
        try:
            data = json.loads(UI_SETTINGS_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        if isinstance(data, dict):
            self.dark_mode.set(bool(data.get("dark_mode", False)))
            if "auto_reconnect" in data:
                self.auto_reconnect.set(bool(data.get("auto_reconnect")))

    def _save_ui_settings(self) -> None:
        try:
            UI_SETTINGS_PATH.write_text(
                json.dumps(
                    {
                        "dark_mode": self.dark_mode.get(),
                        "auto_reconnect": self.auto_reconnect.get(),
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        except OSError:
            pass

    def _on_auto_reconnect_toggle(self) -> None:
        self._save_ui_settings()
        if not self.auto_reconnect.get():
            self._cancel_reconnect()
        elif self._want_connected and not self.connected:
            self._schedule_auto_reconnect(delay_ms=500, reason="Auto-Reconnect aktiviert")

    def _toggle_theme(self) -> None:
        self._apply_theme()
        self._save_ui_settings()

    def _apply_theme(self, initial: bool = False) -> None:
        theme = THEME_DARK if self.dark_mode.get() else THEME_LIGHT
        if TTKBOOTSTRAP and hasattr(self.root, "style"):
            self.root.style.theme_use(theme)
        self._configure_tree_separators()
        self._configure_log_tags()
        self._apply_text_themes()
        self._update_connection_status()
        self._refresh_button_styles()
        if not initial:
            self._refresh_log_view()
            if getattr(self, "explorer_payload_text", None) is not None and self.explorer_payload_text.winfo_exists():
                self._on_explorer_select()

    def _configure_tree_separators(self) -> None:
        """Macht Spaltentrenner in Treeview-Überschriften sichtbar (Drag-Griff)."""
        if TTKBOOTSTRAP and hasattr(self.root, "style"):
            style = self.root.style
        else:
            style = ttk.Style()

        if self.dark_mode.get():
            border = "#6a6a6a"
            heading_bg = "#2f2f2f"
            heading_fg = "#e8e8e8"
        else:
            border = "#9a9a9a"
            heading_bg = "#ececec"
            heading_fg = "#1a1a1a"

        style.configure(
            "Treeview.Heading",
            relief="solid",
            borderwidth=1,
            bordercolor=border,
            background=heading_bg,
            foreground=heading_fg,
            padding=(6, 4),
        )
        # Fallback für Themes, die bordercolor ignorieren
        try:
            style.map(
                "Treeview.Heading",
                relief=[("active", "solid"), ("!active", "solid")],
                bordercolor=[("active", border), ("!active", border)],
            )
        except tk.TclError:
            pass

    def _log_colors(self) -> dict[str, str]:
        if self.dark_mode.get():
            return {
                "muted": "#888888",
                "System": "#aaaaaa",
                "Verbindung": "#5cb85c",
                "Senden": "#5bc0de",
                "Payload": "#f0ad4e",
                "Topic": "#b48ead",
                "Explorer": "#8fbc8f",
                "Vorlage": "#9cdcfe",
                "Fehler": "#ff6b6b",
            }
        return {
            "muted": "#666666",
            "System": "#555555",
            "Verbindung": "#198754",
            "Senden": "#0d6efd",
            "Payload": "#fd7e14",
            "Topic": "#6f42c1",
            "Explorer": "#2e8b57",
            "Vorlage": "#0dcaf0",
            "Fehler": "#dc3545",
        }

    def _configure_log_tags(self) -> None:
        if not hasattr(self, "log_text"):
            return
        colors = self._log_colors()
        for tag, color in colors.items():
            self.log_text.tag_configure(tag, foreground=color)

    def _apply_text_themes(self) -> None:
        if self.dark_mode.get():
            bg, fg, insert = "#1e1e1e", "#e8e8e8", "#e8e8e8"
            canvas_bg = "#222222"
        else:
            bg, fg, insert = "#fafafa", "#1a1a1a", "#1a1a1a"
            canvas_bg = "#ffffff"
        for widget in (getattr(self, "log_text", None), getattr(self, "explorer_payload_text", None)):
            if widget is not None and widget.winfo_exists():
                widget.configure(bg=bg, fg=fg, insertbackground=insert, highlightthickness=0)
        canvas = getattr(self, "_upper_canvas", None)
        if canvas is not None and canvas.winfo_exists():
            canvas.configure(bg=canvas_bg, highlightthickness=0)

    def _update_connection_status(self) -> None:
        if not hasattr(self, "status_indicator"):
            return
        if self.connected:
            if TTKBOOTSTRAP:
                self.status_indicator.configure(bootstyle="success")
            else:
                self.status_indicator.configure(foreground="#198754")
        else:
            if TTKBOOTSTRAP:
                self.status_indicator.configure(bootstyle="danger")
            else:
                self.status_indicator.configure(foreground="#dc3545")
        self._update_connection_button_styles()

    def _update_connection_button_styles(self) -> None:
        if not TTKBOOTSTRAP:
            return
        if self.connected:
            connect_style = "success"
            disconnect_style = "danger-outline"
        else:
            connect_style = "success-outline"
            disconnect_style = "danger"
        if hasattr(self, "connect_btn") and self.connect_btn.winfo_exists():
            self.connect_btn.configure(bootstyle=connect_style)
        if hasattr(self, "disconnect_btn") and self.disconnect_btn.winfo_exists():
            self.disconnect_btn.configure(bootstyle=disconnect_style)

    def _flash_button(
        self,
        button: ttk.Button,
        *,
        outline: str = "info-outline",
        filled: str = "info",
        duration_ms: int = 250,
    ) -> None:
        if not TTKBOOTSTRAP:
            return
        btn_id = str(button)
        pending = self._button_flash_jobs.get(btn_id)
        if pending:
            self.root.after_cancel(pending)
        button.configure(bootstyle=filled)

        def reset() -> None:
            self._button_flash_jobs[btn_id] = None
            if button.winfo_exists():
                button.configure(bootstyle=outline)

        self._button_flash_jobs[btn_id] = self.root.after(duration_ms, reset)

    def _on_publish_clicked(self) -> None:
        self._flash_button(self.publish_btn)
        self.publish_once()

    def connect(self, *, silent: bool = False) -> bool:
        if self.connected:
            return True

        host = self.server_ip.get().strip()
        if not host:
            if not silent:
                messagebox.showerror("Fehler", "Bitte eine Server-IP eintragen.")
            self._log("Verbindung fehlgeschlagen: Server-IP fehlt", category="Fehler")
            return False

        try:
            port = int(self.server_port.get().strip())
        except ValueError:
            if not silent:
                messagebox.showerror("Fehler", "Port muss eine gueltige Zahl sein.")
            self._log("Verbindung fehlgeschlagen: Ungültiger Port", category="Fehler")
            return False

        self._cleanup_client(keep_want_connected=True)

        self.client = mqtt.Client(protocol=mqtt.MQTTv311)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

        username = self.username.get().strip()
        if username:
            self.client.username_pw_set(username, self.password.get())

        try:
            if not silent:
                self._clear_explorer(log_message=False)
            self.client.connect(host, port, keepalive=60)
            self.client.loop_start()
        except Exception as err:
            self.client = None
            if not silent:
                messagebox.showerror("Verbindungsfehler", str(err))
            self._log(f"Verbindungsfehler: {err}", category="Fehler")
            return False

        self._want_connected = True
        self._reconnect_attempts = 0
        self._cancel_reconnect()
        self.connected = True
        self._active_connection = (host, str(port), username, self.password.get())
        self.status_text.set(f"Verbunden mit {host}:{port}")
        self._update_connection_status()
        self._log(
            f"{'Wiederverbunden' if silent else 'Verbunden'} mit {host}:{port}",
            category="Verbindung",
        )
        self._update_explorer_status()
        self._restart_heartbeat()
        self._restart_payload_change()
        return True

    def disconnect(self, reason: str | None = None) -> None:
        was_connected = self.connected or self.client is not None
        self._want_connected = False
        self._cancel_reconnect()
        self._cleanup_client(keep_want_connected=False)

        self.status_text.set("Nicht verbunden")
        self._update_connection_status()
        self._update_explorer_status()
        if was_connected or reason:
            self._log(reason or "Verbindung getrennt", category="Verbindung")

    def _cleanup_client(self, *, keep_want_connected: bool) -> None:
        self._cancel_timers()
        self._suppress_disconnect_reconnect = True
        try:
            if self.client is not None:
                try:
                    self.client.loop_stop()
                except Exception:
                    pass
                try:
                    self.client.disconnect()
                except Exception:
                    pass
                self.client = None
        finally:
            self._suppress_disconnect_reconnect = False
        self.connected = False
        self._active_connection = None
        if not keep_want_connected:
            self._want_connected = False

    def _cancel_reconnect(self) -> None:
        if self.reconnect_job is not None:
            self.root.after_cancel(self.reconnect_job)
            self.reconnect_job = None

    def _schedule_auto_reconnect(self, delay_ms: int = 1500, reason: str | None = None) -> None:
        if not self.auto_reconnect.get() or not self._want_connected:
            return
        if self.connected:
            return
        self._cancel_reconnect()
        if reason:
            self.status_text.set(reason)
            self._log(reason, category="Verbindung")
        self.reconnect_job = self.root.after(delay_ms, self._attempt_auto_reconnect)

    def _attempt_auto_reconnect(self) -> None:
        self.reconnect_job = None
        if not self.auto_reconnect.get() or not self._want_connected or self.connected:
            return

        self._reconnect_attempts += 1
        attempt = self._reconnect_attempts
        self.status_text.set(f"Auto-Reconnect… (Versuch {attempt})")
        self._log(f"Auto-Reconnect Versuch {attempt}", category="Verbindung")

        if self.connect(silent=True):
            return

        # Exponentielles Backoff, max. 60 s zwischen Versuchen
        delay_ms = min(60_000, 1500 * (2 ** min(attempt - 1, 5)))
        self._schedule_auto_reconnect(delay_ms=delay_ms)

    def _start_connection_watchdog(self) -> None:
        self._last_watchdog_wall = time.time()
        self._watchdog_tick()

    def _watchdog_tick(self) -> None:
        now = time.time()
        last = self._last_watchdog_wall
        self._last_watchdog_wall = now

        # Großer Zeitsprung (z. B. Mac-Ruhezustand) → Verbindung oft tot
        if last is not None and (now - last) >= 12:
            if self.auto_reconnect.get() and self._want_connected:
                self.root.after(
                    0,
                    lambda: self._handle_wake_from_sleep(gap_seconds=now - last),
                )

        self.watchdog_job = self.root.after(2000, self._watchdog_tick)

    def _handle_wake_from_sleep(self, gap_seconds: float) -> None:
        if not self.auto_reconnect.get() or not self._want_connected:
            return
        self._log(
            f"Aufwachen erkannt (Pause {gap_seconds:.0f} s) – stelle Verbindung wieder her",
            category="Verbindung",
        )
        self._cleanup_client(keep_want_connected=True)
        self._update_connection_status()
        self._update_explorer_status()
        self._reconnect_attempts = 0
        self._schedule_auto_reconnect(delay_ms=800, reason="Verbinde nach Aufwachen…")

    def publish_once(self) -> None:
        if not self.connected or self.client is None:
            messagebox.showwarning("Hinweis", "Nicht verbunden. Bitte zuerst verbinden.")
            self._log("Senden abgebrochen: Nicht verbunden", category="Fehler")
            return

        topic_payloads = self._get_topic_payloads()
        qos = int(self.qos.get())
        retain = self.retain.get()

        if not topic_payloads:
            messagebox.showerror("Fehler", "Es ist kein gueltiges Topic eingetragen.")
            self._log("Senden abgebrochen: Kein gültiges Topic", category="Fehler")
            return

        sent = 0
        failed_topics: list[str] = []
        for topic, payload, _payload_type, _row_low, _row_high, _string_length, _payload_change in topic_payloads:
            result = self.client.publish(topic, payload, qos=qos, retain=retain)
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                sent += 1
            else:
                failed_topics.append(topic)

        if failed_topics:
            self.status_text.set(
                f"Teilweise gesendet ({sent}/{len(topic_payloads)}). Fehler bei: {', '.join(failed_topics)}"
            )
            self._log(
                f"Teilweise gesendet ({sent}/{len(topic_payloads)}), Fehler: {', '.join(failed_topics)}"
                ,
                category="Senden",
            )
            return
        self.status_text.set(f"Gesendet an {sent} Topic(s)")
        self._log(f"Gesendet an {sent} Topic(s)", category="Senden")

    def _publish_single_topic(self, topic: str, payload: str) -> None:
        """Sendet ein einzelnes Topic sofort, falls verbunden."""
        topic = topic.strip()
        if not topic:
            return
        if not self.connected or self.client is None:
            self._log(f"Sofort-Senden übersprungen (nicht verbunden): {topic}", category="Senden")
            return

        qos = int(self.qos.get())
        retain = self.retain.get()
        result = self.client.publish(topic, payload, qos=qos, retain=retain)
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            self.status_text.set(f"Gesendet: {topic}")
            self._log(f"Sofort gesendet: {topic} = {payload}", category="Senden")
        else:
            self.status_text.set(f"Senden fehlgeschlagen: {topic}")
            self._log(f"Sofort-Senden fehlgeschlagen: {topic}", category="Fehler")

    def _publish_heartbeat(self) -> None:
        if self._get_topic_payloads():
            self.publish_once()
        self._schedule_heartbeat()

    def _restart_heartbeat(self) -> None:
        if self.heartbeat_job is not None:
            self.root.after_cancel(self.heartbeat_job)
            self.heartbeat_job = None

        if self.connected:
            self._schedule_heartbeat()

    def _schedule_heartbeat(self) -> None:
        interval = INTERVAL_OPTIONS.get(self.heartbeat.get(), 0)
        if interval <= 0:
            return
        self.heartbeat_job = self.root.after(interval * 1000, self._publish_heartbeat)

    def _restart_payload_change(self) -> None:
        if self.payload_change_job is not None:
            self.root.after_cancel(self.payload_change_job)
            self.payload_change_job = None

        if self.connected:
            self._schedule_payload_change()

    def _any_topic_payload_change_enabled(self) -> bool:
        for item_id in self.topic_tree.get_children():
            payload_change, *_rest = self._unpack_topic_values(self.topic_tree.item(item_id, "values"))
            if payload_change:
                return True
        return False

    def _payload_change_timer_needed(self) -> bool:
        # Timer läuft, wenn global aktiv ODER mindestens ein Topic die Änderung aktiviert hat
        # (Topic-Checkbox overrulled die globale Einstellung).
        return self.payload_change_enabled.get() or self._any_topic_payload_change_enabled()

    def _schedule_payload_change(self) -> None:
        if not self._payload_change_timer_needed():
            return
        interval = PAYLOAD_CHANGE_OPTIONS.get(self.payload_change_interval.get(), 0)
        if interval <= 0:
            return
        self.payload_change_job = self.root.after(interval * 1000, self._apply_payload_change)

    def _normalize_payload_change_interval(self, value: object) -> str:
        text = str(value).strip() if value is not None else ""
        if text in PAYLOAD_CHANGE_OPTIONS:
            return text
        return DEFAULT_PAYLOAD_CHANGE_INTERVAL

    def _apply_payload_change(self) -> None:
        if not self._payload_change_timer_needed():
            return

        children = self.topic_tree.get_children()
        if not children:
            self.status_text.set("Keine Topic-Eintraege vorhanden.")
            self._log("Payload-Änderung übersprungen: Keine Topic-Einträge", category="Payload")
            self._schedule_payload_change()
            return

        updated_count = 0
        for item_id in children:
            payload_change, topic, payload, payload_type, row_low, row_high, str_length = self._unpack_topic_values(
                self.topic_tree.item(item_id, "values")
            )
            # Pro-Topic-Checkbox entscheidet (overrulled globale Checkbox)
            if not payload_change or not topic:
                continue

            new_payload = self._generate_updated_payload(payload, payload_type, row_low, row_high, str_length)
            if new_payload == payload:
                continue

            self.topic_tree.item(
                item_id,
                values=self._topic_values_tuple(
                    payload_change, topic, new_payload, payload_type, row_low, row_high, str_length
                ),
            )
            updated_count += 1

        if updated_count == 0:
            self._log(
                "Payload-Änderung übersprungen: Keine aktivierten Topics oder keine gültige Range/Länge",
                category="Payload",
            )
        else:
            self._log(f"Payload-Änderung angewendet auf {updated_count} Topic(s)", category="Payload")
            if self.connected:
                self.publish_once()

        self._schedule_payload_change()

    def _cancel_timers(self) -> None:
        if self.heartbeat_job is not None:
            self.root.after_cancel(self.heartbeat_job)
            self.heartbeat_job = None
        if self.payload_change_job is not None:
            self.root.after_cancel(self.payload_change_job)
            self.payload_change_job = None

    def _on_connect(self, client, _userdata, _flags, rc):
        if rc == 0:
            self.connected = True
            self._reconnect_attempts = 0
            self._cancel_reconnect()
            self.status_text.set("MQTT verbunden")
            self._update_connection_status()
            self._log("MQTT-Session aktiv", category="Verbindung")
            self._subscribe_explorer(client)
        else:
            self.status_text.set(f"MQTT Verbindungsfehler: {rc}")
            self._log(f"MQTT Verbindungsfehler: {rc}", category="Fehler")
            if self.auto_reconnect.get() and self._want_connected:
                self.root.after(
                    0,
                    lambda: self._schedule_auto_reconnect(
                        delay_ms=2000, reason="Verbindungsfehler – versuche erneut…"
                    ),
                )

    def _on_disconnect(self, _client, _userdata, rc):
        if self._suppress_disconnect_reconnect:
            self.root.after(0, self._update_explorer_status)
            return
        if rc != 0:
            self.connected = False
            self.status_text.set("Verbindung unerwartet getrennt.")
            self._update_connection_status()
            self._log(f"Verbindung unerwartet getrennt (Code {rc})", category="Fehler")
            if self.auto_reconnect.get() and self._want_connected:
                self.root.after(
                    0,
                    lambda: self._schedule_auto_reconnect(
                        delay_ms=1500, reason="Verbindung verloren – Auto-Reconnect…"
                    ),
                )
        self.root.after(0, self._update_explorer_status)

    def _on_message(self, _client, _userdata, msg) -> None:
        topic = str(getattr(msg, "topic", "") or "")
        payload = self._decode_mqtt_payload(getattr(msg, "payload", b""))
        retain = bool(getattr(msg, "retain", False))
        self.root.after(0, lambda t=topic, p=payload, r=retain: self._explorer_upsert(t, p, r))

    def show_explorer_window(self) -> None:
        self._ensure_explorer_window(show=True)

    def _hide_explorer_window(self) -> None:
        if self.explorer_window is not None and self.explorer_window.winfo_exists():
            self.explorer_window.withdraw()

    def _place_explorer_window(self) -> None:
        if self.explorer_window is None or not self.explorer_window.winfo_exists():
            return
        self.root.update_idletasks()
        x = self.root.winfo_rootx()
        y = self.root.winfo_rooty()
        width = self.root.winfo_width()
        self.explorer_window.geometry(f"860x780+{max(0, x + width + 16)}+{max(0, y)}")
        self.explorer_window.deiconify()
        self.explorer_window.lift()

    def _ensure_explorer_window(self, show: bool = True) -> None:
        created = False
        if self.explorer_window is None or not self.explorer_window.winfo_exists():
            window = tk.Toplevel(self.root)
            window.title("MQTT Explorer")
            window.minsize(640, 480)
            window.geometry("860x780")
            window.protocol("WM_DELETE_WINDOW", self._hide_explorer_window)
            frame = ttk.Frame(window, padding=12)
            frame.pack(fill=tk.BOTH, expand=True)
            self._build_explorer_ui(frame)
            self.explorer_window = window
            created = True

        if not show:
            self.explorer_window.withdraw()
            return
        self.explorer_window.deiconify()
        self.explorer_window.lift()
        if created:
            self.root.after_idle(self._place_explorer_window)

    def _build_explorer_ui(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(2, weight=3)
        parent.rowconfigure(4, weight=1)

        header = ttk.Frame(parent)
        header.grid(row=0, column=0, sticky=EW, pady=(0, 8))
        ttk.Label(header, text="MQTT Explorer", font=("Helvetica Neue", 14, "bold")).pack(side=LEFT)
        ttk.Label(header, textvariable=self.explorer_status).pack(side=LEFT, padx=(12, 0))

        toolbar = ttk.Labelframe(parent, text="Aktionen", padding=6)
        toolbar.grid(row=1, column=0, sticky=EW, pady=(0, 8))

        view_grp = ttk.Frame(toolbar)
        view_grp.pack(side=LEFT, padx=(0, 12))
        self._style_button(view_grp, "Aufklappen", self._explorer_expand_all, "secondary-outline").pack(
            side=LEFT, padx=2
        )
        self._style_button(view_grp, "Zuklappen", self._explorer_collapse_all, "secondary-outline").pack(
            side=LEFT, padx=2
        )

        del_grp = ttk.Frame(toolbar)
        del_grp.pack(side=LEFT, padx=(0, 12))
        self.explorer_delete_payload_btn = self._style_button(
            del_grp,
            "Payload löschen",
            self._on_explorer_delete_payload_clicked,
            "warning-outline",
            tracked=False,
        )
        self.explorer_delete_payload_btn.pack(side=LEFT, padx=2)
        self.explorer_delete_topic_btn = self._style_button(
            del_grp,
            "Topic löschen",
            self._on_explorer_delete_topic_clicked,
            f"{EXPLORER_MAGENTA}-outline",
            tracked=False,
        )
        self.explorer_delete_topic_btn.pack(side=LEFT, padx=2)
        self.explorer_delete_tree_btn = self._style_button(
            del_grp,
            "Baum löschen",
            self._on_explorer_delete_tree_clicked,
            "danger-outline",
            tracked=False,
        )
        self.explorer_delete_tree_btn.pack(side=LEFT, padx=2)
        self._style_button(del_grp, "Leeren", self._clear_explorer, "secondary").pack(side=LEFT, padx=2)

        ttk.Checkbutton(
            toolbar,
            text="System-Topics ($SYS)",
            variable=self.explorer_include_sys,
            command=self._on_explorer_sys_toggle,
        ).pack(side=RIGHT)

        tree_container = ttk.Frame(parent)
        tree_container.grid(row=2, column=0, sticky=NSEW)
        tree_container.columnconfigure(0, weight=1)
        tree_container.rowconfigure(0, weight=1)

        self.explorer_tree = ttk.Treeview(
            tree_container,
            columns=("payload", "time", "count"),
            show="tree headings",
            height=16,
        )
        self.explorer_tree.heading("#0", text="Topic", command=lambda: self._explorer_sort_by("topic"))
        self.explorer_tree.heading("payload", text="Payload")
        self.explorer_tree.heading("time", text="Zeit", command=lambda: self._explorer_sort_by("time"))
        self.explorer_tree.heading("count", text="Anzahl")
        self.explorer_tree.column("#0", width=260, stretch=True)
        self.explorer_tree.column("payload", width=360, anchor="w", stretch=True)
        self.explorer_tree.column("time", width=80, anchor="center", stretch=False)
        self.explorer_tree.column("count", width=70, anchor="e", stretch=False)

        tree_scroll_y = ttk.Scrollbar(tree_container, orient=tk.VERTICAL, command=self.explorer_tree.yview)
        tree_scroll_x = ttk.Scrollbar(tree_container, orient=tk.HORIZONTAL, command=self.explorer_tree.xview)
        self.explorer_tree.configure(yscrollcommand=tree_scroll_y.set, xscrollcommand=tree_scroll_x.set)
        self.explorer_tree.grid(row=0, column=0, sticky=NSEW)
        tree_scroll_y.grid(row=0, column=1, sticky=NS)
        tree_scroll_x.grid(row=1, column=0, sticky=EW)
        self.explorer_tree.bind("<<TreeviewSelect>>", self._on_explorer_select)

        ttk.Label(parent, text="Payload der Auswahl").grid(row=3, column=0, sticky=W, pady=(8, 4))
        payload_container = ttk.Frame(parent)
        payload_container.grid(row=4, column=0, sticky=NSEW)
        payload_container.columnconfigure(0, weight=1)
        payload_container.rowconfigure(0, weight=1)

        self.explorer_payload_text = tk.Text(
            payload_container,
            height=7,
            state=tk.DISABLED,
            wrap=WORD,
            font=self.mono_font,
            borderwidth=0,
        )
        self.explorer_payload_text.grid(row=0, column=0, sticky=NSEW)
        payload_scroll = ttk.Scrollbar(
            payload_container, orient=VERTICAL, command=self.explorer_payload_text.yview
        )
        payload_scroll.grid(row=0, column=1, sticky=NS)
        self.explorer_payload_text.configure(yscrollcommand=payload_scroll.set)
        self._explorer_update_sort_headings()
        self._apply_text_themes()

    def _explorer_parse_time(self, time_str: str) -> tuple[int, int, int]:
        if not time_str:
            return (0, 0, 0)
        parts = time_str.strip().split(":")
        try:
            numbers = [int(part) for part in parts[:3]]
        except ValueError:
            return (0, 0, 0)
        while len(numbers) < 3:
            numbers.append(0)
        return numbers[0], numbers[1], numbers[2]

    def _explorer_latest_time(self, item_id: str) -> str:
        values = self.explorer_tree.item(item_id, "values")
        time_str = str(values[1]) if len(values) > 1 else ""
        if time_str:
            return time_str
        latest = (0, 0, 0)
        latest_str = ""
        for child in self.explorer_tree.get_children(item_id):
            child_time = self._explorer_latest_time(child)
            parsed = self._explorer_parse_time(child_time)
            if parsed >= latest:
                latest = parsed
                latest_str = child_time
        return latest_str

    def _explorer_sort_key(self, item_id: str) -> object:
        if self._explorer_sort_column == "time":
            return self._explorer_parse_time(self._explorer_latest_time(item_id))
        return self.explorer_tree.item(item_id, "text").lower()

    def _explorer_apply_sort(self, parent: str = "") -> None:
        if getattr(self, "explorer_tree", None) is None or not self.explorer_tree.winfo_exists():
            return
        children = list(self.explorer_tree.get_children(parent))
        children.sort(key=self._explorer_sort_key, reverse=self._explorer_sort_reverse)
        for index, child in enumerate(children):
            self.explorer_tree.move(child, parent, index)
            self._explorer_apply_sort(child)

    def _explorer_update_sort_headings(self) -> None:
        if getattr(self, "explorer_tree", None) is None or not self.explorer_tree.winfo_exists():
            return
        topic_text = "Topic"
        time_text = "Zeit"
        arrow = " ▼" if self._explorer_sort_reverse else " ▲"
        if self._explorer_sort_column == "topic":
            topic_text += arrow
        elif self._explorer_sort_column == "time":
            time_text += arrow
        self.explorer_tree.heading("#0", text=topic_text)
        self.explorer_tree.heading("time", text=time_text)

    def _explorer_sort_by(self, column: str) -> None:
        if self._explorer_sort_column == column:
            self._explorer_sort_reverse = not self._explorer_sort_reverse
        else:
            self._explorer_sort_column = column
            self._explorer_sort_reverse = False
        self._explorer_apply_sort()
        self._explorer_update_sort_headings()
        direction = "absteigend" if self._explorer_sort_reverse else "aufsteigend"
        label = "Topic" if column == "topic" else "Zeit"
        self._log(f"Explorer sortiert nach {label} ({direction})", category="Explorer")

    def _explorer_selected_iid(self) -> str | None:
        if getattr(self, "explorer_tree", None) is None or not self.explorer_tree.winfo_exists():
            return None
        selected = self.explorer_tree.selection()
        return selected[0] if selected else None

    def _explorer_topics_under(self, prefix: str) -> list[str]:
        topics: list[str] = []
        if prefix in self._explorer_payloads:
            topics.append(prefix)
        prefix_with_slash = f"{prefix}/"
        for topic in self._explorer_payloads:
            if topic.startswith(prefix_with_slash):
                topics.append(topic)
        return sorted(set(topics))

    def _explorer_remove_topic_leaf(self, topic: str) -> None:
        self._explorer_counts.pop(topic, None)
        self._explorer_payloads.pop(topic, None)
        if getattr(self, "explorer_tree", None) is None or not self.explorer_tree.winfo_exists():
            return
        if not self.explorer_tree.exists(topic):
            return
        parent = self.explorer_tree.parent(topic)
        self.explorer_tree.delete(topic)
        self._explorer_prune_empty_ancestors(parent)

    def _explorer_suppress_topics(self, topics: list[str]) -> None:
        self._explorer_suppressed_topics.update(topics)

    def _explorer_remove_topic_prefix(self, prefix: str) -> None:
        topics = self._explorer_topics_under(prefix)
        self._explorer_suppress_topics(topics)
        prefix_with_slash = f"{prefix}/"
        for topic in list(self._explorer_payloads):
            if topic == prefix or topic.startswith(prefix_with_slash):
                self._explorer_payloads.pop(topic, None)
                self._explorer_counts.pop(topic, None)
        if self.explorer_tree.exists(prefix):
            parent = self.explorer_tree.parent(prefix)
            self.explorer_tree.delete(prefix)
            self._explorer_prune_empty_ancestors(parent)

    def _mqtt_clear_retain(self, topic: str) -> bool:
        if not self.connected or self.client is None:
            return False
        try:
            result = self.client.publish(topic, "", qos=0, retain=True)
        except Exception as err:
            self._log(f"Retain löschen fehlgeschlagen ({topic}): {err}", category="Fehler")
            return False
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            self._log(f"Retain löschen fehlgeschlagen ({topic}, Code {result.rc})", category="Fehler")
            return False
        return True

    def _explorer_prune_empty_ancestors(self, item_id: str) -> None:
        while item_id:
            if item_id in self._explorer_payloads:
                return
            if self.explorer_tree.get_children(item_id):
                return
            parent = self.explorer_tree.parent(item_id)
            self.explorer_tree.delete(item_id)
            item_id = parent

    def _explorer_remove_topics(
        self,
        topics: list[str],
        *,
        clear_retain: bool,
        log_message: str,
    ) -> None:
        if not topics:
            return
        self._explorer_suppress_topics(topics)
        for topic in topics:
            self._explorer_remove_topic_leaf(topic)
        cleared = 0
        if clear_retain and self.connected:
            for topic in topics:
                if self._mqtt_clear_retain(topic):
                    cleared += 1
        self._on_explorer_select()
        self._update_explorer_status()
        if clear_retain and self.connected:
            suffix = f", Retain auf {cleared} Topic(s) gelöscht"
        elif clear_retain:
            suffix = ", nur lokal entfernt (nicht verbunden)"
        else:
            suffix = ""
        self._log(f"{log_message}{suffix}", category="Explorer")

    def _on_explorer_delete_payload_clicked(self) -> None:
        self._flash_button(
            self.explorer_delete_payload_btn, outline="warning-outline", filled="warning"
        )
        self._explorer_delete_selected_payload()

    def _on_explorer_delete_topic_clicked(self) -> None:
        self._flash_button(
            self.explorer_delete_topic_btn,
            outline=f"{EXPLORER_MAGENTA}-outline",
            filled=EXPLORER_MAGENTA,
        )
        self._explorer_delete_selected_topic()

    def _on_explorer_delete_tree_clicked(self) -> None:
        self._flash_button(self.explorer_delete_tree_btn, outline="danger-outline", filled="danger")
        self._explorer_delete_selected_tree()

    def _explorer_delete_selected_payload(self) -> None:
        topic = self._explorer_selected_iid()
        if not topic:
            messagebox.showinfo("Hinweis", "Bitte zuerst ein Topic auswählen.")
            return
        if topic not in self._explorer_payloads:
            messagebox.showinfo("Hinweis", "Die Auswahl hat kein eigenes Payload.")
            return
        if not messagebox.askyesno(
            "Payload löschen",
            f"Payload von '{topic}' löschen?\n\n"
            "Bei verbundener Session wird auch die Retain-Nachricht auf dem Broker entfernt.",
            parent=self.explorer_window,
        ):
            return
        if self.connected:
            self._mqtt_clear_retain(topic)
        self._explorer_counts.pop(topic, None)
        self._explorer_payloads.pop(topic, None)
        if self.explorer_tree.exists(topic):
            self.explorer_tree.item(topic, values=("", "", ""))
        self._on_explorer_select()
        self._update_explorer_status()
        if self.connected:
            self._log(f"Payload gelöscht: {topic}", category="Explorer")
        else:
            self._log(f"Payload lokal gelöscht: {topic}", category="Explorer")

    def _explorer_delete_selected_topic(self) -> None:
        topic = self._explorer_selected_iid()
        if not topic:
            messagebox.showinfo("Hinweis", "Bitte zuerst ein Topic auswählen.", parent=self.explorer_window)
            return
        has_payload = topic in self._explorer_payloads
        is_empty_leaf = (
            self.explorer_tree.exists(topic)
            and not self.explorer_tree.get_children(topic)
            and not has_payload
        )
        if not has_payload and not is_empty_leaf:
            messagebox.showinfo(
                "Hinweis",
                "Die Auswahl ist eine Zwischenebene. Für Untertopics bitte 'Baum löschen' verwenden.",
                parent=self.explorer_window,
            )
            return
        if not messagebox.askyesno(
            "Topic löschen",
            f"Topic '{topic}' aus dem Explorer entfernen?\n\n"
            "Bei verbundener Session wird auch die Retain-Nachricht auf dem Broker entfernt.",
            parent=self.explorer_window,
        ):
            return
        self._explorer_remove_topics([topic], clear_retain=True, log_message=f"Topic gelöscht: {topic}")

    def _explorer_delete_selected_tree(self) -> None:
        prefix = self._explorer_selected_iid()
        if not prefix:
            messagebox.showinfo("Hinweis", "Bitte zuerst ein Topic oder einen Baum auswählen.", parent=self.explorer_window)
            return
        topics = self._explorer_topics_under(prefix)
        if not topics:
            if self.explorer_tree.exists(prefix):
                self._explorer_remove_topic_prefix(prefix)
                self._on_explorer_select()
                self._update_explorer_status()
                self._log(f"Baum lokal entfernt: {prefix}", category="Explorer")
            else:
                messagebox.showinfo(
                    "Hinweis",
                    "Unter der Auswahl sind keine Topics vorhanden.",
                    parent=self.explorer_window,
                )
            return
        preview = "\n".join(f"- {name}" for name in topics[:8])
        if len(topics) > 8:
            preview += f"\n- … und {len(topics) - 8} weitere"
        if not messagebox.askyesno(
            "Baum löschen",
            f"{len(topics)} Topic(s) unter '{prefix}' entfernen?\n\n{preview}\n\n"
            "Bei verbundener Session werden auch Retain-Nachrichten auf dem Broker entfernt.",
            parent=self.explorer_window,
        ):
            return
        self._explorer_suppress_topics(topics)
        self._explorer_remove_topic_prefix(prefix)
        cleared = 0
        if self.connected:
            for topic in topics:
                if self._mqtt_clear_retain(topic):
                    cleared += 1
        self._on_explorer_select()
        self._update_explorer_status()
        if self.connected:
            self._log(
                f"Baum gelöscht: {prefix} ({len(topics)} Topic(s)), Retain auf {cleared} Topic(s) gelöscht",
                category="Explorer",
            )
        else:
            self._log(f"Baum lokal gelöscht: {prefix} ({len(topics)} Topic(s))", category="Explorer")

    def _subscribe_explorer(self, client: mqtt.Client) -> None:
        try:
            result, _mid = client.subscribe("#", qos=0)
        except Exception as err:
            self._log(f"Explorer-Subscribe fehlgeschlagen: {err}", category="Fehler")
            return
        if result != mqtt.MQTT_ERR_SUCCESS:
            self._log(f"Explorer-Subscribe auf # fehlgeschlagen (Code {result})", category="Fehler")
            return
        self._log("Explorer lauscht auf alle Topics (#)", category="Explorer")
        if self.explorer_include_sys.get():
            self._subscribe_sys_topics(client)
        self.root.after(0, self._update_explorer_status)

    def _subscribe_sys_topics(self, client: mqtt.Client) -> None:
        try:
            result, _mid = client.subscribe("$SYS/#", qos=0)
        except Exception as err:
            self._log(f"Explorer-Subscribe auf $SYS/# fehlgeschlagen: {err}", category="Fehler")
            return
        if result != mqtt.MQTT_ERR_SUCCESS:
            self._log(f"Explorer-Subscribe auf $SYS/# fehlgeschlagen (Code {result})", category="Fehler")
            return
        self._log("Explorer lauscht zusätzlich auf $SYS/#", category="Explorer")

    def _on_explorer_sys_toggle(self) -> None:
        if not self.connected or self.client is None:
            return
        if self.explorer_include_sys.get():
            self._subscribe_sys_topics(self.client)
            return
        try:
            self.client.unsubscribe("$SYS/#")
            self._log("Explorer: $SYS/# abbestellt", category="Explorer")
        except Exception as err:
            self._log(f"Explorer-Unsubscribe $SYS/# fehlgeschlagen: {err}", category="Fehler")

    def _decode_mqtt_payload(self, payload: object) -> str:
        if payload is None:
            return ""
        if isinstance(payload, str):
            return payload
        if not isinstance(payload, (bytes, bytearray)):
            return str(payload)
        if not payload:
            return ""
        try:
            return bytes(payload).decode("utf-8")
        except UnicodeDecodeError:
            raw = bytes(payload)
            preview = raw[:32].hex()
            suffix = "…" if len(raw) > 32 else ""
            return f"<binär {len(raw)} Byte: {preview}{suffix}>"

    def _payload_preview(self, payload: str, limit: int = 80) -> str:
        compact = payload.replace("\n", " ").replace("\r", " ")
        if len(compact) <= limit:
            return compact
        return compact[: limit - 1] + "…"

    def _explorer_upsert(self, topic: str, payload: str, retain: bool = False) -> None:
        if not topic:
            return
        if topic in self._explorer_suppressed_topics:
            if payload.strip():
                self._explorer_suppressed_topics.discard(topic)
            else:
                return
        if getattr(self, "explorer_tree", None) is None or not self.explorer_tree.winfo_exists():
            return
        parts = topic.split("/")
        parent_iid = ""
        leaf_iid = ""
        for index, part in enumerate(parts):
            leaf_iid = "/".join(parts[: index + 1])
            if leaf_iid == "":
                leaf_iid = "/"
            display = part if part else "/"
            if not self.explorer_tree.exists(leaf_iid):
                self.explorer_tree.insert(parent_iid, "end", iid=leaf_iid, text=display, values=("", "", ""))
                if parent_iid:
                    self.explorer_tree.item(parent_iid, open=True)
            parent_iid = leaf_iid

        self._explorer_counts[topic] = self._explorer_counts.get(topic, 0) + 1
        self._explorer_payloads[topic] = payload
        count = self._explorer_counts[topic]
        timestamp = datetime.now().strftime("%H:%M:%S")
        preview = self._payload_preview(payload)
        if retain and count == 1:
            preview = f"[retain] {preview}" if preview else "[retain]"
        self.explorer_tree.item(leaf_iid, values=(preview, timestamp, str(count)))
        self._explorer_apply_sort()
        self._update_explorer_status()

        selected = self.explorer_tree.selection()
        if selected and selected[0] == leaf_iid:
            self._on_explorer_select()

    def _on_explorer_select(self, _event=None) -> None:
        if getattr(self, "explorer_payload_text", None) is None or not self.explorer_payload_text.winfo_exists():
            return
        selected = self.explorer_tree.selection()
        self.explorer_payload_text.configure(state=tk.NORMAL)
        self.explorer_payload_text.delete("1.0", tk.END)
        if selected:
            iid = selected[0]
            payload = self._explorer_payloads.get(iid)
            if payload is None:
                text = f"Topic: {iid}\n\n(kein eigenes Payload – Zwischenebene)"
            else:
                text = f"Topic: {iid}\nAnzahl: {self._explorer_counts.get(iid, 0)}\n\n{payload}"
            self.explorer_payload_text.insert("1.0", text)
        self.explorer_payload_text.configure(state=tk.DISABLED)

    def _clear_explorer(self, *, log_message: bool = True) -> None:
        if getattr(self, "explorer_tree", None) is None or not self.explorer_tree.winfo_exists():
            self._explorer_counts.clear()
            self._explorer_payloads.clear()
            self._explorer_suppressed_topics.clear()
            self._update_explorer_status()
            return
        for item_id in self.explorer_tree.get_children():
            self.explorer_tree.delete(item_id)
        self._explorer_counts.clear()
        self._explorer_payloads.clear()
        self._explorer_suppressed_topics.clear()
        self._on_explorer_select()
        self._update_explorer_status()
        if log_message:
            self._log("Explorer geleert", category="Explorer")

    def _explorer_set_open(self, item_id: str, opened: bool) -> None:
        for child in self.explorer_tree.get_children(item_id):
            self._explorer_set_open(child, opened)
        self.explorer_tree.item(item_id, open=opened)

    def _explorer_expand_all(self) -> None:
        for item_id in self.explorer_tree.get_children(""):
            self._explorer_set_open(item_id, True)

    def _explorer_collapse_all(self) -> None:
        for item_id in self.explorer_tree.get_children(""):
            self._explorer_set_open(item_id, False)

    def _update_explorer_status(self) -> None:
        count = len(self._explorer_counts)
        if self.connected:
            extra = " inkl. $SYS" if self.explorer_include_sys.get() else ""
            self.explorer_status.set(f"Lauscht auf #{extra}  ·  {count} Topic(s)")
        elif count:
            self.explorer_status.set(f"Nicht verbunden  ·  {count} Topic(s) im Speicher")
        else:
            self.explorer_status.set("Nicht verbunden – Explorer startet nach dem Verbinden")

    def _parse_float(self, value: str) -> float | None:
        try:
            return float(value.strip())
        except ValueError:
            return None

    def _generate_random_string(self, length: int) -> str:
        charset = string.ascii_letters + string.digits + string.punctuation
        return "".join(random.choice(charset) for _ in range(length))

    def _is_payload_change_checked(self, value: object) -> bool:
        text = str(value).strip().lower()
        return text in {"1", "true", "ja", "yes", "☑", PAYLOAD_CHANGE_CHECKED.lower()}

    def _payload_change_display(self, enabled: bool) -> str:
        return PAYLOAD_CHANGE_CHECKED if enabled else PAYLOAD_CHANGE_UNCHECKED

    def _coerce_bool(self, value: object, default: bool = False) -> bool:
        if isinstance(value, bool):
            return value
        if value is None or str(value).strip() == "":
            return default
        return self._is_payload_change_checked(value)

    def _unpack_topic_values(self, values: tuple | list) -> tuple[bool, str, str, str, str, str, str]:
        items = [str(v) if v is not None else "" for v in values]
        if len(items) >= 7:
            return (
                self._is_payload_change_checked(items[0]),
                items[1].strip(),
                items[2].strip(),
                items[3].strip() or "Zahl",
                items[4].strip(),
                items[5].strip(),
                items[6].strip(),
            )
        while len(items) < 6:
            items.append("")
        return (
            False,
            items[0].strip(),
            items[1].strip(),
            items[2].strip() or "Zahl",
            items[3].strip(),
            items[4].strip(),
            items[5].strip(),
        )

    def _topic_values_tuple(
        self,
        payload_change: bool,
        topic: str,
        payload: str,
        payload_type: str,
        range_low: str,
        range_high: str,
        string_length: str,
    ) -> tuple[str, str, str, str, str, str, str]:
        return (
            self._payload_change_display(payload_change),
            topic,
            payload,
            payload_type,
            range_low,
            range_high,
            string_length,
        )

    def _generate_updated_payload(
        self,
        payload: str,
        payload_type: str,
        row_low: str,
        row_high: str,
        str_length: str,
    ) -> str:
        if payload_type == "String":
            try:
                length = int(str_length)
            except (TypeError, ValueError):
                return payload
            if length <= 0:
                return payload
            return self._generate_random_string(length)

        parsed_payload = self._parse_float(payload)
        if parsed_payload is None:
            return payload

        row_low_num = self._parse_float(row_low)
        row_high_num = self._parse_float(row_high)
        if row_low_num is None or row_high_num is None:
            return payload
        use_low = row_low_num
        use_high = row_high_num
        if use_low > use_high:
            use_low, use_high = use_high, use_low

        if use_low == use_high:
            new_value = use_low
        elif use_low.is_integer() and use_high.is_integer():
            new_value = random.randint(int(use_low), int(use_high))
        else:
            new_value = round(random.uniform(use_low, use_high), 3)

        if float(new_value).is_integer():
            return str(int(new_value))
        return str(new_value)

    def _on_topic_tree_click(self, event) -> None:
        region = self.topic_tree.identify_region(event.x, event.y)
        # Separator-Drag für Spaltenbreiten nicht blockieren
        if region == "separator":
            return
        if region != "cell":
            return
        if self.topic_tree.identify_column(event.x) != "#1":
            return
        item_id = self.topic_tree.identify_row(event.y)
        if not item_id:
            return
        payload_change, topic, payload, payload_type, row_low, row_high, string_length = self._unpack_topic_values(
            self.topic_tree.item(item_id, "values")
        )
        self.topic_tree.item(
            item_id,
            values=self._topic_values_tuple(
                not payload_change, topic, payload, payload_type, row_low, row_high, string_length
            ),
        )
        self._update_range_visibility()
        self._restart_payload_change()

    def _on_topic_tree_double_click(self, event) -> None:
        region = self.topic_tree.identify_region(event.x, event.y)
        if region == "separator":
            return
        if region != "cell":
            return
        # Doppelklick auf die Checkbox-Spalte nicht als Bearbeiten werten
        if self.topic_tree.identify_column(event.x) == "#1":
            return
        item_id = self.topic_tree.identify_row(event.y)
        if not item_id:
            return
        self.topic_tree.selection_set(item_id)
        self.edit_selected_topic_row()

    def _topic_dialog(
        self,
        title: str,
        initial_topic: str = "",
        initial_payload: str = "",
        initial_payload_type: str = "Zahl",
        initial_low: str = "",
        initial_high: str = "",
        initial_string_length: str = "",
        initial_payload_change: bool = False,
    ) -> tuple[bool, str, str, str, str, str, str] | None:
        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(False, False)

        payload_change_var = tk.BooleanVar(value=initial_payload_change)
        topic_var = tk.StringVar(value=initial_topic)
        payload_var = tk.StringVar(value=initial_payload)
        payload_type_var = tk.StringVar(value=initial_payload_type if initial_payload_type in ("Zahl", "String") else "Zahl")
        low_var = tk.StringVar(value=initial_low)
        high_var = tk.StringVar(value=initial_high)
        string_length_var = tk.StringVar(value=initial_string_length)

        container = ttk.Frame(dialog, padding=12)
        container.grid(row=0, column=0, sticky="nsew")

        ttk.Checkbutton(
            container,
            text="Payload-Änderung aktivieren",
            variable=payload_change_var,
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))

        ttk.Label(container, text="Topic").grid(row=1, column=0, sticky="w")
        topic_entry = ttk.Entry(container, textvariable=topic_var, width=45)
        topic_entry.grid(row=1, column=1, sticky="ew", pady=(0, 6))

        ttk.Label(container, text="Payload").grid(row=2, column=0, sticky="w")
        ttk.Entry(container, textvariable=payload_var, width=20).grid(row=2, column=1, sticky="w", pady=(0, 6))

        ttk.Label(container, text="Payload-Typ").grid(row=3, column=0, sticky="w")
        payload_type_box = ttk.Combobox(
            container, textvariable=payload_type_var, values=["Zahl", "String"], state="readonly", width=18
        )
        payload_type_box.grid(row=3, column=1, sticky="w", pady=(0, 6))

        range_low_label = ttk.Label(container, text="Range von")
        range_low_label.grid(row=4, column=0, sticky="w")
        range_low_entry = ttk.Entry(container, textvariable=low_var, width=20)
        range_low_entry.grid(row=4, column=1, sticky="w", pady=(0, 6))

        range_high_label = ttk.Label(container, text="Range bis")
        range_high_label.grid(row=5, column=0, sticky="w")
        range_high_entry = ttk.Entry(container, textvariable=high_var, width=20)
        range_high_entry.grid(row=5, column=1, sticky="w", pady=(0, 6))

        string_length_label = ttk.Label(container, text="Stringlänge")
        string_length_label.grid(row=6, column=0, sticky="w")
        string_length_entry = ttk.Entry(container, textvariable=string_length_var, width=20)
        string_length_entry.grid(row=6, column=1, sticky="w", pady=(0, 6))

        def update_type_fields() -> None:
            is_string = payload_type_var.get() == "String"
            if is_string:
                range_low_label.grid_remove()
                range_low_entry.grid_remove()
                range_high_label.grid_remove()
                range_high_entry.grid_remove()
                string_length_label.grid()
                string_length_entry.grid()
            else:
                range_low_label.grid()
                range_low_entry.grid()
                range_high_label.grid()
                range_high_entry.grid()
                string_length_label.grid_remove()
                string_length_entry.grid_remove()

        payload_type_box.bind("<<ComboboxSelected>>", lambda _event: update_type_fields())
        update_type_fields()

        result: dict[str, tuple[bool, str, str, str, str, str, str] | None] = {"value": None}

        def submit() -> None:
            topic = topic_var.get().strip()
            if not topic:
                messagebox.showerror("Fehler", "Topic darf nicht leer sein.", parent=dialog)
                return
            payload_type = payload_type_var.get().strip() or "Zahl"
            low_value = low_var.get().strip()
            high_value = high_var.get().strip()
            string_length_value = string_length_var.get().strip()
            payload_change = bool(payload_change_var.get())

            if payload_type == "String":
                try:
                    str_len = int(string_length_value)
                except ValueError:
                    messagebox.showerror(
                        "Fehler",
                        "Bei Typ 'String' muss die Stringlänge eine ganze Zahl sein.",
                        parent=dialog,
                    )
                    return
                if str_len <= 0:
                    messagebox.showerror(
                        "Fehler",
                        "Bei Typ 'String' muss die Stringlänge größer als 0 sein.",
                        parent=dialog,
                    )
                    return
            elif payload_change:
                if self._parse_float(low_value) is None or self._parse_float(high_value) is None:
                    messagebox.showerror(
                        "Fehler",
                        "Bei Typ 'Zahl' müssen 'Range von' und 'Range bis' numerisch sein.",
                        parent=dialog,
                    )
                    return

            result["value"] = (
                payload_change,
                topic,
                payload_var.get().strip(),
                payload_type,
                low_value,
                high_value,
                string_length_value,
            )
            dialog.destroy()

        button_row = ttk.Frame(container)
        button_row.grid(row=7, column=0, columnspan=2, sticky="e", pady=(8, 0))
        ttk.Button(button_row, text="Speichern", command=submit).pack(side=tk.LEFT)
        ttk.Button(button_row, text="Abbrechen", command=dialog.destroy).pack(side=tk.LEFT, padx=(8, 0))

        topic_entry.focus_set()
        dialog.wait_window(dialog)
        return result["value"]

    def add_topic_row(
        self,
        topic: str = "",
        payload: str = "",
        payload_type: str = "Zahl",
        range_low: str = "",
        range_high: str = "",
        string_length: str = "",
        payload_change: bool = False,
        open_dialog: bool = True,
    ) -> None:
        if open_dialog and not topic and not payload and not range_low and not range_high and not string_length:
            dialog_data = self._topic_dialog("Topic hinzufügen")
            if dialog_data is None:
                return
            payload_change, topic, payload, payload_type, range_low, range_high, string_length = dialog_data

        item_id = self.topic_tree.insert(
            "",
            tk.END,
            values=self._topic_values_tuple(
                payload_change, topic, payload, payload_type, range_low, range_high, string_length
            ),
        )
        self.topic_tree.selection_set(item_id)
        self._update_range_visibility()
        self._restart_payload_change()
        if topic:
            self._log(f"Topic hinzugefügt: {topic}", category="Topic")
            self._publish_single_topic(topic, payload)

    def edit_selected_topic_row(self) -> None:
        selected = self.topic_tree.selection()
        if not selected:
            messagebox.showinfo("Hinweis", "Bitte zuerst ein Topic auswählen.")
            return
        item_id = selected[0]
        payload_change, topic, payload, payload_type, low, high, string_length = self._unpack_topic_values(
            self.topic_tree.item(item_id, "values")
        )

        dialog_data = self._topic_dialog(
            "Topic bearbeiten",
            initial_topic=topic,
            initial_payload=payload,
            initial_payload_type=payload_type,
            initial_low=low,
            initial_high=high,
            initial_string_length=string_length,
            initial_payload_change=payload_change,
        )
        if dialog_data is None:
            return
        payload_change, topic, payload, payload_type, range_low, range_high, string_length = dialog_data
        self.topic_tree.item(
            item_id,
            values=self._topic_values_tuple(
                payload_change, topic, payload, payload_type, range_low, range_high, string_length
            ),
        )
        self._update_range_visibility()
        self._restart_payload_change()
        self._log(f"Topic bearbeitet: {topic}", category="Topic")
        self._publish_single_topic(topic, payload)

    def remove_selected_topic_row(self) -> None:
        selected = self.topic_tree.selection()
        if not selected:
            return
        for item_id in selected:
            _payload_change, topic_name, *_rest = self._unpack_topic_values(self.topic_tree.item(item_id, "values"))
            self.topic_tree.delete(item_id)
            label = topic_name if topic_name.strip() else "(leere Zeile)"
            self._log(f"Topic gelöscht: {label}", category="Topic")

    def _on_payload_change_toggle(self) -> None:
        self._update_range_visibility()
        self._restart_payload_change()

    def _update_range_visibility(self) -> None:
        show_ranges = self.payload_change_enabled.get() or self._any_topic_payload_change_enabled()
        if show_ranges:
            self.topic_tree["displaycolumns"] = (
                "payload_change",
                "topic",
                "payload",
                "payload_type",
                "range_low",
                "range_high",
                "string_length",
            )
        else:
            self.topic_tree["displaycolumns"] = ("payload_change", "topic", "payload", "payload_type")

    def _get_topic_payloads(self) -> list[tuple[str, str, str, str, str, str, bool]]:
        result: list[tuple[str, str, str, str, str, str, bool]] = []
        for item_id in self.topic_tree.get_children():
            payload_change, topic, payload, payload_type, row_low, row_high, string_length = self._unpack_topic_values(
                self.topic_tree.item(item_id, "values")
            )
            if not topic:
                continue
            result.append((topic, payload, payload_type, row_low, row_high, string_length, payload_change))
        return result

    def _collect_topic_rows_for_preferences(self) -> list[dict[str, str | bool]]:
        rows: list[dict[str, str | bool]] = []
        for topic, payload, payload_type, row_low, row_high, string_length, payload_change in self._get_topic_payloads():
            rows.append(
                {
                    "topic": topic,
                    "payload": payload,
                    "payload_type": payload_type,
                    "range_low": row_low,
                    "range_high": row_high,
                    "string_length": string_length,
                    "payload_change": payload_change,
                }
            )
        return rows

    def _apply_topic_rows_from_preferences(self, rows: list[dict]) -> None:
        for item_id in self.topic_tree.get_children():
            self.topic_tree.delete(item_id)

        if not rows:
            return

        for row in rows:
            payload_change = self._coerce_bool(row.get("payload_change"), default=False)
            self.topic_tree.insert(
                "",
                tk.END,
                values=self._topic_values_tuple(
                    payload_change,
                    str(row.get("topic", "")),
                    str(row.get("payload", "")),
                    str(row.get("payload_type", "Zahl")),
                    str(row.get("range_low", "")),
                    str(row.get("range_high", "")),
                    str(row.get("string_length", "")),
                ),
            )

    def _collect_current_settings(self) -> dict[str, object]:
        return {
            "server_ip": self.server_ip.get().strip(),
            "server_port": self.server_port.get().strip(),
            "username": self.username.get().strip(),
            "password": self.password.get(),
            "retain": self.retain.get(),
            "qos": self.qos.get(),
            "heartbeat": self.heartbeat.get(),
            "topic_rows": self._collect_topic_rows_for_preferences(),
            "payload_change_enabled": self.payload_change_enabled.get(),
            "payload_change_interval": self._normalize_payload_change_interval(self.payload_change_interval.get()),
        }

    def _connection_key_from_settings(self, settings: dict[str, object]) -> tuple[str, str, str, str]:
        return (
            str(settings.get("server_ip", "")).strip(),
            str(settings.get("server_port", "")).strip(),
            str(settings.get("username", "")).strip(),
            str(settings.get("password", "")),
        )

    def _connection_credentials_differ(self, settings: dict[str, object]) -> bool:
        incoming = self._connection_key_from_settings(settings)
        current = self._active_connection
        if current is None:
            current = (
                self.server_ip.get().strip(),
                self.server_port.get().strip(),
                self.username.get().strip(),
                self.password.get(),
            )
        return incoming != current

    def _apply_settings(self, settings: dict[str, object]) -> None:
        self.server_ip.set(str(settings.get("server_ip", "127.0.0.1")))
        self.server_port.set(str(settings.get("server_port", "1883")))
        self.username.set(str(settings.get("username", "")))
        self.password.set(str(settings.get("password", "")))
        self.retain.set(bool(settings.get("retain", False)))
        self.qos.set(str(settings.get("qos", "0")))
        self.heartbeat.set(str(settings.get("heartbeat", "nie")))
        self.payload_change_enabled.set(bool(settings.get("payload_change_enabled", False)))
        saved_interval = str(settings.get("payload_change_interval", DEFAULT_PAYLOAD_CHANGE_INTERVAL))
        if saved_interval.strip().lower() == "nie":
            self.payload_change_enabled.set(False)
            self.payload_change_interval.set(DEFAULT_PAYLOAD_CHANGE_INTERVAL)
        else:
            self.payload_change_interval.set(self._normalize_payload_change_interval(saved_interval))

        topic_rows = settings.get("topic_rows")
        if isinstance(topic_rows, list):
            sanitized_rows = [item for item in topic_rows if isinstance(item, dict)]
            self._apply_topic_rows_from_preferences(sanitized_rows)
        else:
            legacy_text = str(settings.get("topic_payloads", "")).strip()
            if legacy_text:
                legacy_rows: list[dict[str, str]] = []
                for line in legacy_text.splitlines():
                    clean_line = line.strip()
                    if not clean_line:
                        continue
                    if "|" in clean_line:
                        topic, payload = clean_line.split("|", 1)
                    else:
                        topic, payload = clean_line, ""
                    legacy_rows.append(
                        {
                            "topic": topic.strip(),
                            "payload": payload.strip(),
                            "payload_type": "Zahl",
                            "range_low": "",
                            "range_high": "",
                            "string_length": "",
                            "payload_change": False,
                        }
                    )
                self._apply_topic_rows_from_preferences(legacy_rows)
            else:
                self._apply_topic_rows_from_preferences([])

        self._restart_heartbeat()
        self._update_range_visibility()
        self._restart_payload_change()

    def _load_json_templates(self, path: Path) -> dict[str, dict[str, object]]:
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        if not isinstance(loaded, dict):
            return {}
        result: dict[str, dict[str, object]] = {}
        for name, settings in loaded.items():
            if isinstance(name, str) and name.strip() and isinstance(settings, dict):
                result[name.strip()] = settings
        return result

    def _load_preferences_file(self) -> None:
        merged: dict[str, dict[str, object]] = {}
        loaded_from: list[str] = []
        for path in [*_legacy_template_paths(), self.templates_path]:
            if not path.exists() or path.stat().st_size <= 2:
                continue
            found = self._load_json_templates(path)
            if not found:
                continue
            merged.update(found)
            loaded_from.append(str(path))

        self.preferences = merged
        if not self.preferences:
            return

        current = self._load_json_templates(self.templates_path) if self.templates_path.exists() else {}
        if current != self.preferences:
            self._save_preferences_file()
            if loaded_from:
                self._log(
                    "Vorlagen aus vorhandenen Dateien zusammengeführt",
                    category="Vorlage",
                )

    def _save_preferences_file(self) -> None:
        if not self.preferences and self.templates_path.exists() and self.templates_path.stat().st_size > 2:
            return
        try:
            self.templates_path.parent.mkdir(parents=True, exist_ok=True)
            self.templates_path.write_text(
                json.dumps(self.preferences, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as err:
            messagebox.showerror("Fehler", f"Vorlagen konnten nicht gespeichert werden: {err}")

    def reveal_templates_file(self) -> None:
        path = self.templates_path
        if not path.exists():
            self._save_preferences_file()
        if not path.exists():
            messagebox.showinfo("Vorlagen-Datei", f"Datei wird hier gespeichert:\n{path}")
            return
        try:
            subprocess.run(["open", "-R", str(path)], check=False)
        except OSError:
            messagebox.showinfo("Vorlagen-Datei", str(path))
        self._log(f"Vorlagen-Datei: {path}", category="Vorlage")

    def import_templates_file(self) -> None:
        file_path = filedialog.askopenfilename(
            title="Vorlagen importieren",
            filetypes=[("JSON-Datei", "*.json"), ("Alle Dateien", "*.*")],
        )
        if not file_path:
            return
        try:
            loaded = json.loads(Path(file_path).read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as err:
            messagebox.showerror("Fehler", f"Vorlagen konnten nicht importiert werden: {err}")
            return
        if not isinstance(loaded, dict):
            messagebox.showerror("Fehler", "Die Datei enthält keine gültigen Vorlagen.")
            return
        imported = 0
        for name, settings in loaded.items():
            if not isinstance(name, str) or not name.strip() or not isinstance(settings, dict):
                continue
            self.preferences[name.strip()] = settings
            imported += 1
        if imported == 0:
            messagebox.showinfo("Hinweis", "In der Datei wurden keine Vorlagen gefunden.")
            return
        self._save_preferences_file()
        self._refresh_preferences_dropdown()
        self.status_text.set(f"{imported} Vorlage(n) importiert")
        self._log(f"{imported} Vorlage(n) importiert aus {file_path}", category="Vorlage")

    def _refresh_preferences_dropdown(self) -> None:
        names = sorted(self.preferences.keys())
        self.preferences_box["values"] = names

        if names and self.selected_preference.get() not in names:
            self.selected_preference.set(names[0])
        if not names:
            self.selected_preference.set("")

    def save_preference(self) -> None:
        name = self.preference_name.get().strip()
        if not name:
            messagebox.showerror("Fehler", "Bitte einen Namen für die Vorlage eingeben.")
            return

        self.preferences[name] = self._collect_current_settings()
        self._save_preferences_file()
        self._refresh_preferences_dropdown()
        self.selected_preference.set(name)
        self.status_text.set(f"Vorlage '{name}' gespeichert")
        self._log(f"Vorlage gespeichert: {name} ({self.templates_path.name})", category="Vorlage")

    def load_selected_preference(self) -> None:
        name = self.selected_preference.get().strip()
        if not name:
            return
        settings = self.preferences.get(name)
        if settings is None:
            messagebox.showerror("Fehler", f"Vorlage '{name}' wurde nicht gefunden.")
            return
        self.preference_name.set(name)
        if self.connected and self._connection_credentials_differ(settings):
            self.disconnect(
                reason="Verbindung getrennt: Zugangsdaten der geladenen Vorlage unterscheiden sich"
            )
        self._apply_settings(settings)
        self.status_text.set(f"Vorlage '{name}' geladen")
        self._log(f"Vorlage geladen: {name}", category="Vorlage")

    def delete_selected_preference(self) -> None:
        name = self.selected_preference.get().strip()
        if not name:
            return
        if name not in self.preferences:
            return
        if not messagebox.askyesno("Bestätigung", f"Vorlage '{name}' wirklich löschen?"):
            return
        del self.preferences[name]
        self._save_preferences_file()
        self._refresh_preferences_dropdown()
        self.status_text.set(f"Vorlage '{name}' gelöscht")
        self._log(f"Vorlage gelöscht: {name}", category="Vorlage")

    def _log(self, message: str, category: str = "System") -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_entries.append((timestamp, category, message))
        self._refresh_log_view()

    def _refresh_log_view(self) -> None:
        active_filter = self.selected_log_filter.get()
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)

        for timestamp, category, message in self.log_entries:
            if active_filter != "Alle" and category != active_filter:
                continue
            tag = category if category in LOG_CATEGORIES else "System"
            self.log_text.insert(tk.END, f"[{timestamp}] ", "muted")
            self.log_text.insert(tk.END, f"[{category}] ", tag)
            self.log_text.insert(tk.END, f"{message}\n")

        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _clear_log(self) -> None:
        self.log_entries.clear()
        self._refresh_log_view()
        self._log("Log gelöscht", category="System")

    def _export_log(self) -> None:
        active_filter = self.selected_log_filter.get()
        lines: list[str] = []
        for timestamp, category, message in self.log_entries:
            if active_filter != "Alle" and category != active_filter:
                continue
            lines.append(f"[{timestamp}] [{category}] {message}")

        if not lines:
            messagebox.showinfo("Hinweis", "Es sind keine Log-Einträge zum Exportieren vorhanden.")
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"mqtt_log_{timestamp}.txt"
        file_path = filedialog.asksaveasfilename(
            title="Log exportieren",
            defaultextension=".txt",
            initialfile=default_name,
            filetypes=[("Textdatei", "*.txt"), ("Alle Dateien", "*.*")],
        )
        if not file_path:
            return

        try:
            Path(file_path).write_text("\n".join(lines) + "\n", encoding="utf-8")
        except OSError as err:
            messagebox.showerror("Fehler", f"Log konnte nicht exportiert werden: {err}")
            self._log(f"Log-Export fehlgeschlagen: {err}", category="Fehler")
            return

        self._log(f"Log exportiert: {file_path}", category="System")

    def on_close(self) -> None:
        self._save_ui_settings()
        self._want_connected = False
        self._cancel_reconnect()
        if self.watchdog_job is not None:
            self.root.after_cancel(self.watchdog_job)
            self.watchdog_job = None
        self.disconnect()
        if self.explorer_window is not None and self.explorer_window.winfo_exists():
            self.explorer_window.destroy()
        self.root.destroy()


def main() -> None:
    if TTKBOOTSTRAP:
        root = ttk.Window(title="MQTT-Tool", themename=THEME_LIGHT, size=(820, 860), resizable=(True, True))
    else:
        root = tk.Tk()
        root.title("MQTT-Tool")
        root.geometry("820x860")
    app = MQTTToolApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
