"""
Nexra Video Converter & Compressor - Modern Desktop GUI
Features:
- Exact Target MB Size compression (2-pass & GPU acceleration)
- Hardware Acceleration (NVIDIA NVENC, AMD AMF, Intel QSV)
- Video Trimming / Cutting (start & end time range selection)
- Windows Right-Click Context Menu integration
- Video Thumbnail Preview & Drag-and-drop
- Batch Video Processing
"""

import os
import sys
import tempfile
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
from PIL import Image

from video_engine import (
    VideoMetadata,
    CompressionJob,
    calculate_bitrates,
    get_recommended_resolution,
    get_ffmpeg_path,
    detect_gpu_encoders,
    format_seconds,
    parse_time_str,
    generate_thumbnail
)

import context_menu

try:
    import windnd
    HAS_WINDND = True
except ImportError:
    HAS_WINDND = False


# Configure CustomTkinter Appearance
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

SUPPORTED_EXTENSIONS = (
    ".mp4", ".mov", ".mkv", ".avi", ".webm", ".flv",
    ".wmv", ".m4v", ".ts", ".m2ts", ".vob", ".3gp"
)


class NexraApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Nexra Video Converter & Compressor")
        self.geometry("980x880")
        self.minsize(880, 750)

        # Set Window Icon
        base_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        icon_path = os.path.join(base_dir, "icon.ico")
        if os.path.exists(icon_path):
            try:
                self.iconbitmap(icon_path)
            except Exception:
                pass

        # Detect GPU
        self.gpu_info = detect_gpu_encoders()

        # State Variables
        self.current_meta: VideoMetadata = None
        self.current_job: CompressionJob = None
        self.is_compressing = False
        self.custom_output_dir = None
        self.current_thumb_image = None
        self.temp_thumb_dir = tempfile.mkdtemp(prefix="nexra_thumb_")

        # Batch State
        self.batch_files = []
        self.batch_job = None
        self.batch_index = 0
        self.batch_cancelled = False

        # Build Interface
        self._build_header()
        self._build_tabs()
        self._build_single_tab()
        self._build_batch_tab()
        self._build_footer()

        # Hook Drag and Drop
        if HAS_WINDND:
            try:
                windnd.hook_dropfiles(self, func=self._on_files_dropped)
            except Exception as e:
                print(f"Drag and drop hook error: {e}")

        # Handle CLI Arguments (e.g. from Explorer right-click)
        self.after(200, self._process_cli_arguments)

    def _process_cli_arguments(self):
        """Processes files or flags passed via command line."""
        args = sys.argv[1:]
        target_file = None
        target_mb_val = None

        i = 0
        while i < len(args):
            arg = args[i]
            if arg in ("--target", "-t") and i + 1 < len(args):
                try:
                    target_mb_val = float(args[i + 1])
                except ValueError:
                    pass
                i += 2
            elif os.path.isfile(arg) and arg.lower().endswith(SUPPORTED_EXTENSIONS):
                target_file = arg
                i += 1
            else:
                i += 1

        if target_file:
            self._load_single_video(target_file)
            if target_mb_val:
                self.after(500, lambda: self.var_target_mb.set(f"{target_mb_val:.1f}".rstrip("0").rstrip(".")))

    # =========================================================================
    # HEADER & NAVIGATION
    # =========================================================================
    def _build_header(self):
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=25, pady=(16, 8))

        title_box = ctk.CTkFrame(header_frame, fg_color="transparent")
        title_box.pack(side="left")

        app_title = ctk.CTkLabel(
            title_box,
            text="🎬 Nexra Video Compressor",
            font=ctk.CTkFont(size=24, weight="bold")
        )
        app_title.pack(anchor="w")

        subtitle = ctk.CTkLabel(
            title_box,
            text="Videolarınızı istediğiniz MB boyutuna kaliteden ödün vermeden akıllıca küçültün",
            font=ctk.CTkFont(size=13),
            text_color="#94A3B8"
        )
        subtitle.pack(anchor="w", pady=(2, 0))

        # Controls (Theme + Context Menu)
        top_ctrl = ctk.CTkFrame(header_frame, fg_color="transparent")
        top_ctrl.pack(side="right", pady=4)

        # Context Menu Button
        is_menu_on = context_menu.is_installed()
        menu_text = "🖱️ Sağ Tık: Aktif" if is_menu_on else "🖱️ Sağ Tık: Ekle"
        menu_fg = ("#D1FAE5", "#064E3B") if is_menu_on else ("#E2E8F0", "#1E293B")
        menu_txt_col = ("#065F46", "#6EE7B7") if is_menu_on else ("#1E293B", "#F1F5F9")

        self.btn_context_menu = ctk.CTkButton(
            top_ctrl,
            text=menu_text,
            width=125,
            height=30,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=menu_fg,
            text_color=menu_txt_col,
            command=self._toggle_context_menu
        )
        self.btn_context_menu.pack(side="left", padx=(0, 8))

        self.theme_btn = ctk.CTkButton(
            top_ctrl,
            text="🌓 Tema",
            width=80,
            height=30,
            fg_color=("#E2E8F0", "#1E293B"),
            text_color=("#1E293B", "#F1F5F9"),
            hover_color=("#CBD5E1", "#334155"),
            command=self._toggle_theme
        )
        self.theme_btn.pack(side="left")

    def _toggle_theme(self):
        curr = ctk.get_appearance_mode()
        ctk.set_appearance_mode("light" if curr == "Dark" else "dark")

    def _toggle_context_menu(self):
        if context_menu.is_installed():
            if context_menu.uninstall():
                self.btn_context_menu.configure(
                    text="🖱️ Sağ Tık: Ekle",
                    fg_color=("#E2E8F0", "#1E293B"),
                    text_color=("#1E293B", "#F1F5F9")
                )
                messagebox.showinfo("Sağ Tık Menüsü", "Windows sağ tık menüsü kaldırıldı.")
        else:
            if context_menu.install():
                self.btn_context_menu.configure(
                    text="🖱️ Sağ Tık: Aktif",
                    fg_color=("#D1FAE5", "#064E3B"),
                    text_color=("#065F46", "#6EE7B7")
                )
                messagebox.showinfo(
                    "Sağ Tık Menüsü",
                    "Windows Gezgini sağ tık menüsüne başarıyla eklendi!\nArtık herhangi bir videoya sağ tıklayıp doğrudan Nexra ile sıkıştırabilirsiniz."
                )

    def _build_tabs(self):
        self.tabview = ctk.CTkTabview(self, corner_radius=12)
        self.tabview.pack(fill="both", expand=True, padx=25, pady=(4, 8))

        self.tab_single = self.tabview.add("⚡ Tek Video Sıkıştır")
        self.tab_batch = self.tabview.add("📁 Toplu Sıkıştırma (Çoklu Dosya)")

    # =========================================================================
    # SINGLE VIDEO TAB
    # =========================================================================
    def _build_single_tab(self):
        self.scroll_single = ctk.CTkScrollableFrame(self.tab_single, fg_color="transparent")
        self.scroll_single.pack(fill="both", expand=True, padx=4, pady=4)

        # 1. Video Selection & Info Card
        self.card_file = ctk.CTkFrame(self.scroll_single, corner_radius=10, fg_color=("#F1F5F9", "#1A1D24"))
        self.card_file.pack(fill="x", pady=(0, 8), ipady=6)

        file_header = ctk.CTkFrame(self.card_file, fg_color="transparent")
        file_header.pack(fill="x", padx=15, pady=(8, 4))

        ctk.CTkLabel(
            file_header,
            text="📁 Video Dosyası",
            font=ctk.CTkFont(size=15, weight="bold")
        ).pack(side="left")

        self.btn_select_file = ctk.CTkButton(
            file_header,
            text="Dosya Seç...",
            width=110,
            height=32,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._select_single_file
        )
        self.btn_select_file.pack(side="right")

        self.lbl_drop_hint = ctk.CTkLabel(
            self.card_file,
            text="Bir video dosyasını buraya sürükleyip bırakabilir veya 'Dosya Seç' butonuna tıklayabilirsiniz.\n(MP4, MKV, MOV, AVI, WEBM, WMV vb.)",
            font=ctk.CTkFont(size=12),
            text_color="#64748B",
            justify="center"
        )
        self.lbl_drop_hint.pack(pady=(6, 12))

        # Video Metadata Grid & Thumbnail (Hidden until file selected)
        self.frame_meta = ctk.CTkFrame(self.card_file, fg_color=("#E2E8F0", "#111317"), corner_radius=8)

        # Content row: Thumbnail (left) + Metadata text (right)
        meta_content_row = ctk.CTkFrame(self.frame_meta, fg_color="transparent")
        meta_content_row.pack(fill="x", padx=10, pady=8)

        # Thumbnail Label
        self.lbl_thumb = ctk.CTkLabel(meta_content_row, text="", width=140, height=80, fg_color=("#CBD5E1", "#1E222B"), corner_radius=6)
        self.lbl_thumb.pack(side="left", padx=(0, 15))

        # Meta Details
        meta_text_box = ctk.CTkFrame(meta_content_row, fg_color="transparent")
        meta_text_box.pack(side="left", fill="both", expand=True)

        self.lbl_meta_filename = ctk.CTkLabel(meta_text_box, text="", font=ctk.CTkFont(size=13, weight="bold"), anchor="w")
        self.lbl_meta_filename.pack(fill="x", pady=(0, 4))

        meta_grid = ctk.CTkFrame(meta_text_box, fg_color="transparent")
        meta_grid.pack(fill="x")

        self.lbl_orig_size = ctk.CTkLabel(meta_grid, text="Boyut: -", font=ctk.CTkFont(size=12))
        self.lbl_orig_size.grid(row=0, column=0, sticky="w", padx=(0, 20))

        self.lbl_orig_dur = ctk.CTkLabel(meta_grid, text="Süre: -", font=ctk.CTkFont(size=12))
        self.lbl_orig_dur.grid(row=0, column=1, sticky="w", padx=(0, 20))

        self.lbl_orig_res = ctk.CTkLabel(meta_grid, text="Çözünürlük: -", font=ctk.CTkFont(size=12))
        self.lbl_orig_res.grid(row=0, column=2, sticky="w", padx=(0, 20))

        self.lbl_orig_fps = ctk.CTkLabel(meta_grid, text="FPS: -", font=ctk.CTkFont(size=12))
        self.lbl_orig_fps.grid(row=0, column=3, sticky="w")

        # 2. Video Trimming (Kırpma) Card
        self.card_trim = ctk.CTkFrame(self.scroll_single, corner_radius=10, fg_color=("#F1F5F9", "#1A1D24"))
        self.card_trim.pack(fill="x", pady=6, ipady=6)

        trim_header = ctk.CTkFrame(self.card_trim, fg_color="transparent")
        trim_header.pack(fill="x", padx=15, pady=(8, 4))

        self.var_trim_enable = tk.BooleanVar(value=False)
        self.chk_trim = ctk.CTkCheckBox(
            trim_header,
            text="✂️ Videoyu Kırp / Kes (Yalnızca Belirli Bir Kısmı Sıkıştır)",
            variable=self.var_trim_enable,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._on_trim_toggle
        )
        self.chk_trim.pack(side="left")

        # Collapsible Trim Controls
        self.frame_trim_controls = ctk.CTkFrame(self.card_trim, fg_color="transparent")

        trim_inputs_row = ctk.CTkFrame(self.frame_trim_controls, fg_color="transparent")
        trim_inputs_row.pack(fill="x", padx=15, pady=(6, 4))

        ctk.CTkLabel(trim_inputs_row, text="Başlangıç:", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left", padx=(0, 6))
        self.var_trim_start = tk.StringVar(value="00:00:00")
        self.var_trim_start.trace_add("write", lambda *args: self._on_trim_input_changed())
        self.entry_trim_start = ctk.CTkEntry(trim_inputs_row, textvariable=self.var_trim_start, width=85, justify="center")
        self.entry_trim_start.pack(side="left", padx=(0, 18))

        ctk.CTkLabel(trim_inputs_row, text="Bitiş:", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left", padx=(0, 6))
        self.var_trim_end = tk.StringVar(value="00:00:00")
        self.var_trim_end.trace_add("write", lambda *args: self._on_trim_input_changed())
        self.entry_trim_end = ctk.CTkEntry(trim_inputs_row, textvariable=self.var_trim_end, width=85, justify="center")
        self.entry_trim_end.pack(side="left", padx=(0, 15))

        # Quick Range Buttons
        btn_first30 = ctk.CTkButton(
            trim_inputs_row,
            text="İlk 30s",
            width=65,
            height=28,
            font=ctk.CTkFont(size=11),
            fg_color=("#E2E8F0", "#2D3748"),
            text_color=("#1A202C", "#EDF2F7"),
            command=lambda: self._set_quick_trim(0, 30)
        )
        btn_first30.pack(side="left", padx=(0, 6))

        btn_first60 = ctk.CTkButton(
            trim_inputs_row,
            text="İlk 60s",
            width=65,
            height=28,
            font=ctk.CTkFont(size=11),
            fg_color=("#E2E8F0", "#2D3748"),
            text_color=("#1A202C", "#EDF2F7"),
            command=lambda: self._set_quick_trim(0, 60)
        )
        btn_first60.pack(side="left", padx=(0, 6))

        btn_last30 = ctk.CTkButton(
            trim_inputs_row,
            text="Son 30s",
            width=65,
            height=28,
            font=ctk.CTkFont(size=11),
            fg_color=("#E2E8F0", "#2D3748"),
            text_color=("#1A202C", "#EDF2F7"),
            command=self._set_quick_trim_last30
        )
        btn_last30.pack(side="left", padx=(0, 6))

        btn_reset_trim = ctk.CTkButton(
            trim_inputs_row,
            text="Tümü",
            width=60,
            height=28,
            font=ctk.CTkFont(size=11),
            fg_color=("#E2E8F0", "#2D3748"),
            text_color=("#1A202C", "#EDF2F7"),
            command=self._reset_trim
        )
        btn_reset_trim.pack(side="left")

        self.lbl_trim_summary = ctk.CTkLabel(
            self.frame_trim_controls,
            text="Seçilen Süre: -",
            font=ctk.CTkFont(size=11),
            text_color="#38BDF8",
            anchor="w"
        )
        self.lbl_trim_summary.pack(fill="x", padx=15, pady=(2, 4))

        # 3. Target MB Card
        self.card_target = ctk.CTkFrame(self.scroll_single, corner_radius=10, fg_color=("#F1F5F9", "#1A1D24"))
        self.card_target.pack(fill="x", pady=6, ipady=6)

        ctk.CTkLabel(
            self.card_target,
            text="🎯 Hedef Dosya Boyutu (MB)",
            font=ctk.CTkFont(size=15, weight="bold")
        ).pack(anchor="w", padx=15, pady=(8, 6))

        preset_frame = ctk.CTkFrame(self.card_target, fg_color="transparent")
        preset_frame.pack(fill="x", padx=15, pady=(0, 8))

        presets = [
            ("8 MB (Discord Free)", 8.0),
            ("16 MB (WhatsApp)", 16.0),
            ("25 MB (Discord Nitro / Mail)", 25.0),
            ("50 MB (Telegram)", 50.0),
            ("100 MB", 100.0)
        ]

        self.preset_buttons = []
        for text, val in presets:
            btn = ctk.CTkButton(
                preset_frame,
                text=text,
                height=30,
                font=ctk.CTkFont(size=11),
                fg_color=("#E2E8F0", "#2D3748"),
                text_color=("#1A202C", "#EDF2F7"),
                hover_color=("#CBD5E1", "#4A5568"),
                command=lambda v=val: self._set_target_mb(v)
            )
            btn.pack(side="left", padx=(0, 8), expand=True, fill="x")
            self.preset_buttons.append(btn)

        entry_row = ctk.CTkFrame(self.card_target, fg_color="transparent")
        entry_row.pack(fill="x", padx=15, pady=(4, 6))

        ctk.CTkLabel(entry_row, text="Özel Hedef:", font=ctk.CTkFont(size=13)).pack(side="left", padx=(0, 8))

        self.var_target_mb = tk.StringVar(value="25.0")
        self.var_target_mb.trace_add("write", lambda *args: self._update_calculation_preview())

        self.entry_target_mb = ctk.CTkEntry(
            entry_row,
            textvariable=self.var_target_mb,
            width=90,
            height=32,
            font=ctk.CTkFont(size=14, weight="bold"),
            justify="center"
        )
        self.entry_target_mb.pack(side="left", padx=(0, 6))

        ctk.CTkLabel(entry_row, text="MB", font=ctk.CTkFont(size=14, weight="bold")).pack(side="left", padx=(0, 20))

        self.lbl_calc_preview = ctk.CTkLabel(
            entry_row,
            text="",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#10B981"
        )
        self.lbl_calc_preview.pack(side="left")

        self.lbl_target_warning = ctk.CTkLabel(
            self.card_target,
            text="",
            font=ctk.CTkFont(size=11),
            text_color="#F59E0B",
            anchor="w"
        )
        self.lbl_target_warning.pack(fill="x", padx=15, pady=(0, 4))

        # 4. Advanced Settings Card
        self.card_advanced = ctk.CTkFrame(self.scroll_single, corner_radius=10, fg_color=("#F1F5F9", "#1A1D24"))
        self.card_advanced.pack(fill="x", pady=6, ipady=6)

        adv_header = ctk.CTkFrame(self.card_advanced, fg_color="transparent")
        adv_header.pack(fill="x", padx=15, pady=(8, 6))

        ctk.CTkLabel(
            adv_header,
            text="⚙️ Gelişmiş Ayarlar & Performans",
            font=ctk.CTkFont(size=15, weight="bold")
        ).pack(side="left")

        # Row 1: Hardware Acceleration (GPU) + Codec + Resolution
        adv_grid1 = ctk.CTkFrame(self.card_advanced, fg_color="transparent")
        adv_grid1.pack(fill="x", padx=15, pady=(0, 6))

        # Col: GPU Acceleration
        col_gpu = ctk.CTkFrame(adv_grid1, fg_color="transparent")
        col_gpu.grid(row=0, column=0, padx=(0, 15), pady=4, sticky="nsew")
        ctk.CTkLabel(col_gpu, text="⚡ Donanım Hızlandırma:", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w")

        gpu_options = ["Otomatik (En Hızlı)"]
        if self.gpu_info["nvenc"]:
            gpu_options.append("NVIDIA NVENC (Ultra Hızlı)")
        if self.gpu_info["amf"]:
            gpu_options.append("AMD AMF")
        if self.gpu_info["qsv"]:
            gpu_options.append("Intel QSV")
        gpu_options.append("İşlemci / CPU (Maksimum Sıkıştırma)")

        self.combo_gpu = ctk.CTkComboBox(
            col_gpu,
            values=gpu_options,
            width=230
        )
        if self.gpu_info["nvenc"]:
            self.combo_gpu.set("NVIDIA NVENC (Ultra Hızlı)")
        else:
            self.combo_gpu.set("Otomatik (En Hızlı)")
        self.combo_gpu.pack(anchor="w", pady=(2, 0))

        # Col: Codec
        col_codec = ctk.CTkFrame(adv_grid1, fg_color="transparent")
        col_codec.grid(row=0, column=1, padx=(0, 15), pady=4, sticky="nsew")
        ctk.CTkLabel(col_codec, text="Video Formatı / Codec:", font=ctk.CTkFont(size=12)).pack(anchor="w")
        self.combo_codec = ctk.CTkComboBox(
            col_codec,
            values=["H.264 / MP4 (En Uyumlu)", "H.265 / HEVC (Daha Küçük)"],
            width=190
        )
        self.combo_codec.set("H.264 / MP4 (En Uyumlu)")
        self.combo_codec.pack(anchor="w", pady=(2, 0))

        # Col: Resolution
        col_res = ctk.CTkFrame(adv_grid1, fg_color="transparent")
        col_res.grid(row=0, column=2, padx=(0, 15), pady=4, sticky="nsew")
        ctk.CTkLabel(col_res, text="Çözünürlük Ölçeği:", font=ctk.CTkFont(size=12)).pack(anchor="w")
        self.combo_res = ctk.CTkComboBox(
            col_res,
            values=["Otomatik (Önerilen)", "Orijinal Çözünürlük", "1080p (FHD)", "720p (HD)", "480p (SD)", "360p"],
            width=190,
            command=lambda _: self._update_calculation_preview()
        )
        self.combo_res.set("Otomatik (Önerilen)")
        self.combo_res.pack(anchor="w", pady=(2, 0))

        # Row 2: Audio + Sıkıştırma Hassasiyeti + Kayıt Yeri
        adv_grid2 = ctk.CTkFrame(self.card_advanced, fg_color="transparent")
        adv_grid2.pack(fill="x", padx=15, pady=(4, 6))

        # Audio settings
        col_aud = ctk.CTkFrame(adv_grid2, fg_color="transparent")
        col_aud.grid(row=0, column=0, padx=(0, 15), pady=4, sticky="nsew")
        ctk.CTkLabel(col_aud, text="Ses Ayarı:", font=ctk.CTkFont(size=12)).pack(anchor="w")
        self.combo_audio = ctk.CTkComboBox(
            col_aud,
            values=["Otomatik (Dengeli)", "128 kbps (Yüksek)", "96 kbps (Normal)", "64 kbps (Tasarruflu)", "Sesi Kaldır (Mute)"],
            width=230,
            command=lambda _: self._update_calculation_preview()
        )
        self.combo_audio.set("Otomatik (Dengeli)")
        self.combo_audio.pack(anchor="w", pady=(2, 0))

        # Mode
        col_mode = ctk.CTkFrame(adv_grid2, fg_color="transparent")
        col_mode.grid(row=0, column=1, padx=(0, 15), pady=4, sticky="nsew")
        ctk.CTkLabel(col_mode, text="Sıkıştırma Modu (CPU):", font=ctk.CTkFont(size=12)).pack(anchor="w")
        self.combo_mode = ctk.CTkComboBox(
            col_mode,
            values=["2-Pass (Tam Boyut & Kalite)", "1-Pass (Hızlı)"],
            width=190
        )
        self.combo_mode.set("2-Pass (Tam Boyut & Kalite)")
        self.combo_mode.pack(anchor="w", pady=(2, 0))

        # Output folder
        col_out = ctk.CTkFrame(adv_grid2, fg_color="transparent")
        col_out.grid(row=0, column=2, padx=(0, 15), pady=4, sticky="nsew")
        ctk.CTkLabel(col_out, text="Kayıt Konumu:", font=ctk.CTkFont(size=12)).pack(anchor="w")
        self.btn_custom_out = ctk.CTkButton(
            col_out,
            text="Girişle Aynı Klasör",
            width=190,
            fg_color=("#E2E8F0", "#2D3748"),
            text_color=("#1A202C", "#EDF2F7"),
            hover_color=("#CBD5E1", "#4A5568"),
            command=self._choose_custom_output_dir
        )
        self.btn_custom_out.pack(anchor="w", pady=(2, 0))

        # 5. Action & Progress Area
        self.card_action = ctk.CTkFrame(self.scroll_single, corner_radius=10, fg_color=("#F1F5F9", "#1A1D24"))
        self.card_action.pack(fill="x", pady=6, ipady=10)

        self.btn_start = ctk.CTkButton(
            self.card_action,
            text="🚀 SIKIŞTIRMAYI BAŞLAT",
            height=46,
            font=ctk.CTkFont(size=16, weight="bold"),
            fg_color="#2563EB",
            hover_color="#1D4ED8",
            command=self._start_single_compression
        )
        self.btn_start.pack(fill="x", padx=18, pady=(8, 6))

        self.btn_cancel = ctk.CTkButton(
            self.card_action,
            text="❌ İptal Et",
            height=36,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#DC2626",
            hover_color="#B91C1C",
            command=self._cancel_single_compression
        )

        self.progress_frame = ctk.CTkFrame(self.card_action, fg_color="transparent")

        self.progress_bar = ctk.CTkProgressBar(self.progress_frame, height=14, corner_radius=7)
        self.progress_bar.set(0)
        self.progress_bar.pack(fill="x", padx=18, pady=(8, 4))

        self.lbl_progress_status = ctk.CTkLabel(
            self.progress_frame,
            text="Hazırlanıyor...",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        self.lbl_progress_status.pack(side="left", padx=18)

        self.lbl_progress_time = ctk.CTkLabel(
            self.progress_frame,
            text="",
            font=ctk.CTkFont(size=12),
            text_color="#94A3B8"
        )
        self.lbl_progress_time.pack(side="right", padx=18)

        # 6. Success Result Card
        self.card_result = ctk.CTkFrame(self.scroll_single, corner_radius=10, fg_color=("#DCFCE7", "#064E3B"))

        self.lbl_result_title = ctk.CTkLabel(
            self.card_result,
            text="🎉 Video Başarıyla Sıkıştırıldı!",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=("#166534", "#A7F3D0")
        )
        self.lbl_result_title.pack(anchor="w", padx=18, pady=(12, 4))

        self.lbl_result_stats = ctk.CTkLabel(
            self.card_result,
            text="",
            font=ctk.CTkFont(size=13),
            text_color=("#14532D", "#D1FAE5"),
            justify="left"
        )
        self.lbl_result_stats.pack(anchor="w", padx=18, pady=(0, 8))

        res_btn_frame = ctk.CTkFrame(self.card_result, fg_color="transparent")
        res_btn_frame.pack(fill="x", padx=18, pady=(0, 12))

        self.btn_open_folder = ctk.CTkButton(
            res_btn_frame,
            text="📂 Klasörde Göster",
            width=140,
            height=32,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#059669",
            hover_color="#047857",
            command=self._open_output_folder
        )
        self.btn_open_folder.pack(side="left", padx=(0, 10))

        self.btn_play_video = ctk.CTkButton(
            res_btn_frame,
            text="▶️ Videoyu Oynat",
            width=140,
            height=32,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#0284C7",
            hover_color="#0369A1",
            command=self._play_output_video
        )
        self.btn_play_video.pack(side="left")

        self.last_output_path = None

    # =========================================================================
    # TRIM LOGIC
    # =========================================================================
    def _on_trim_toggle(self):
        if self.var_trim_enable.get():
            self.frame_trim_controls.pack(fill="x", pady=(2, 6))
            if self.current_meta and self.current_meta.is_valid:
                self.var_trim_start.set("00:00:00")
                self.var_trim_end.set(self.current_meta.duration_formatted)
        else:
            self.frame_trim_controls.pack_forget()
        self._update_calculation_preview()

    def _set_quick_trim(self, start_s: float, end_s: float):
        if not self.current_meta or not self.current_meta.is_valid:
            return
        end_s = min(end_s, self.current_meta.duration_seconds)
        self.var_trim_start.set(format_seconds(start_s))
        self.var_trim_end.set(format_seconds(end_s))
        self._update_calculation_preview()

    def _set_quick_trim_last30(self):
        if not self.current_meta or not self.current_meta.is_valid:
            return
        total = self.current_meta.duration_seconds
        start_s = max(0, total - 30)
        self.var_trim_start.set(format_seconds(start_s))
        self.var_trim_end.set(format_seconds(total))
        self._update_calculation_preview()

    def _reset_trim(self):
        if not self.current_meta or not self.current_meta.is_valid:
            return
        self.var_trim_start.set("00:00:00")
        self.var_trim_end.set(self.current_meta.duration_formatted)
        self._update_calculation_preview()

    def _on_trim_input_changed(self):
        self._update_calculation_preview()

    def _get_effective_duration(self) -> float:
        """Returns effective duration in seconds accounting for trim."""
        if not self.current_meta or not self.current_meta.is_valid:
            return 1.0

        if not self.var_trim_enable.get():
            return self.current_meta.duration_seconds

        s = parse_time_str(self.var_trim_start.get())
        e = parse_time_str(self.var_trim_end.get())

        if s is None or e is None or e <= s:
            return self.current_meta.duration_seconds

        return max(1.0, e - s)

    # =========================================================================
    # BATCH TAB (Toplu Sıkıştırma)
    # =========================================================================
    def _build_batch_tab(self):
        container = ctk.CTkFrame(self.tab_batch, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=10, pady=10)

        tb = ctk.CTkFrame(container, fg_color=("#F1F5F9", "#1A1D24"), corner_radius=10)
        tb.pack(fill="x", pady=(0, 10), ipady=6)

        ctk.CTkLabel(
            tb,
            text="📁 Toplu Video Listesi",
            font=ctk.CTkFont(size=15, weight="bold")
        ).pack(side="left", padx=15)

        self.btn_batch_add = ctk.CTkButton(
            tb,
            text="➕ Videoları Ekle...",
            width=130,
            height=32,
            command=self._batch_add_files
        )
        self.btn_batch_add.pack(side="right", padx=(0, 15))

        self.btn_batch_clear = ctk.CTkButton(
            tb,
            text="🗑️ Listeyi Temizle",
            width=120,
            height=32,
            fg_color=("#E2E8F0", "#374151"),
            text_color=("#1F2937", "#F9FAFB"),
            hover_color=("#CBD5E1", "#4B5563"),
            command=self._batch_clear
        )
        self.btn_batch_clear.pack(side="right", padx=(0, 10))

        batch_target_frame = ctk.CTkFrame(container, fg_color=("#F1F5F9", "#1A1D24"), corner_radius=10)
        batch_target_frame.pack(fill="x", pady=(0, 10), ipady=6)

        ctk.CTkLabel(
            batch_target_frame,
            text="Tüm Videolar İçin Hedef Boyut:",
            font=ctk.CTkFont(size=13, weight="bold")
        ).pack(side="left", padx=15)

        self.var_batch_target = tk.StringVar(value="25.0")
        ctk.CTkEntry(
            batch_target_frame,
            textvariable=self.var_batch_target,
            width=70,
            justify="center",
            font=ctk.CTkFont(size=13, weight="bold")
        ).pack(side="left", padx=(0, 4))

        ctk.CTkLabel(batch_target_frame, text="MB", font=ctk.CTkFont(size=13, weight="bold")).pack(side="left", padx=(0, 15))

        self.batch_list_frame = ctk.CTkScrollableFrame(container, fg_color=("#F8FAFC", "#111317"), corner_radius=10)
        self.batch_list_frame.pack(fill="both", expand=True, pady=(0, 10))

        self.lbl_batch_empty = ctk.CTkLabel(
            self.batch_list_frame,
            text="Henüz video eklenmedi.\n'Videoları Ekle' butonuna basarak veya birden çok videoyu sürükleyip bırakarak listeye ekleyebilirsiniz.",
            font=ctk.CTkFont(size=13),
            text_color="#64748B",
            justify="center"
        )
        self.lbl_batch_empty.pack(expand=True, pady=40)

        self.batch_action_frame = ctk.CTkFrame(container, fg_color=("#F1F5F9", "#1A1D24"), corner_radius=10)
        self.batch_action_frame.pack(fill="x", ipady=8)

        self.btn_batch_start = ctk.CTkButton(
            self.batch_action_frame,
            text="🚀 TÜMÜNÜ SIKIŞTIRMAYI BAŞLAT",
            height=42,
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color="#2563EB",
            hover_color="#1D4ED8",
            command=self._start_batch_compression
        )
        self.btn_batch_start.pack(fill="x", padx=15, pady=(8, 4))

        self.batch_pbar = ctk.CTkProgressBar(self.batch_action_frame, height=12)
        self.batch_pbar.set(0)
        self.batch_pbar.pack(fill="x", padx=15, pady=(6, 4))

        self.lbl_batch_status = ctk.CTkLabel(
            self.batch_action_frame,
            text="Hazır",
            font=ctk.CTkFont(size=12),
            text_color="#94A3B8"
        )
        self.lbl_batch_status.pack(anchor="w", padx=15, pady=(0, 6))

    # =========================================================================
    # FOOTER
    # =========================================================================
    def _build_footer(self):
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=25, pady=(0, 10))

        gpu_desc = self.gpu_info.get("description", "CPU")
        ctk.CTkLabel(
            footer,
            text=f"Nexra Video Compressor • Donanım Motoru: {gpu_desc}",
            font=ctk.CTkFont(size=11),
            text_color="#64748B"
        ).pack(side="left")

        try:
            get_ffmpeg_path()
            status_text = "🟢 FFmpeg Hazır"
            status_color = "#10B981"
        except Exception:
            status_text = "🔴 FFmpeg Bulunamadı"
            status_color = "#EF4444"

        ctk.CTkLabel(
            footer,
            text=status_text,
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=status_color
        ).pack(side="right")

    # =========================================================================
    # EVENT HANDLERS & LOGIC
    # =========================================================================
    def _on_files_dropped(self, files):
        if not files:
            return

        valid_files = []
        for f in files:
            if isinstance(f, bytes):
                f = f.decode("utf-8", errors="ignore")
            if os.path.isfile(f) and f.lower().endswith(SUPPORTED_EXTENSIONS):
                valid_files.append(f)

        if not valid_files:
            messagebox.showwarning("Desteklenmeyen Dosya", "Lütfen geçerli bir video dosyası sürükleyin!")
            return

        if len(valid_files) == 1 and self.tabview.get() == "⚡ Tek Video Sıkıştır":
            self._load_single_video(valid_files[0])
        else:
            self.tabview.set("📁 Toplu Sıkıştırma (Çoklu Dosya)")
            for vf in valid_files:
                self._add_video_to_batch(vf)

    def _select_single_file(self):
        filetypes = [
            ("Video Dosyaları", "*.mp4;*.mov;*.mkv;*.avi;*.webm;*.flv;*.wmv;*.m4v;*.ts"),
            ("Tüm Dosyalar", "*.*")
        ]
        path = filedialog.askopenfilename(title="Sıkıştırılacak Videoyu Seçin", filetypes=filetypes)
        if path:
            self._load_single_video(path)

    def _load_single_video(self, path: str):
        self.lbl_drop_hint.pack_forget()
        self.frame_meta.pack(fill="x", padx=15, pady=(4, 10))

        self.lbl_meta_filename.configure(text=f"📄 {os.path.basename(path)}")
        self.lbl_orig_size.configure(text="Okunuyor...")

        # Load metadata & generate thumbnail in background
        def load_worker():
            meta = VideoMetadata(path)
            thumb_path = os.path.join(self.temp_thumb_dir, "thumb.jpg")
            has_thumb = generate_thumbnail(path, 1.0, thumb_path)
            self.after(0, lambda: self._apply_metadata(meta, thumb_path if has_thumb else None))

        threading.Thread(target=load_worker, daemon=True).start()

    def _apply_metadata(self, meta: VideoMetadata, thumb_path: Optional[str]):
        self.current_meta = meta
        if not meta.is_valid:
            messagebox.showerror("Hata", f"Video okunamadı:\n{meta.error_message}")
            return

        self.lbl_orig_size.configure(text=f"Boyut: {meta.filesize_mb:.1f} MB")
        self.lbl_orig_dur.configure(text=f"Süre: {meta.duration_formatted}")
        self.lbl_orig_res.configure(text=f"Çözünürlük: {meta.width}x{meta.height}")
        self.lbl_orig_fps.configure(text=f"FPS: {int(meta.fps) if meta.fps.is_integer() else meta.fps:.1f}")

        # Apply Thumbnail
        if thumb_path and os.path.exists(thumb_path):
            try:
                pil_img = Image.open(thumb_path)
                pil_img.thumbnail((140, 80))
                self.current_thumb_image = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(140, 80))
                self.lbl_thumb.configure(image=self.current_thumb_image, text="")
            except Exception:
                self.lbl_thumb.configure(image=None, text="🎬 Video")
        else:
            self.lbl_thumb.configure(image=None, text="🎬 Video")

        # Trim defaults
        self.var_trim_start.set("00:00:00")
        self.var_trim_end.set(meta.duration_formatted)

        # Sensible target size
        if meta.filesize_mb > 30:
            self.var_target_mb.set("25.0")
        elif meta.filesize_mb > 10:
            self.var_target_mb.set("8.0")
        else:
            self.var_target_mb.set(f"{max(1.0, round(meta.filesize_mb * 0.6, 1))}")

        self._update_calculation_preview()

    def _set_target_mb(self, val: float):
        self.var_target_mb.set(f"{val:.1f}".rstrip("0").rstrip("."))

    def _update_calculation_preview(self):
        if not self.current_meta or not self.current_meta.is_valid:
            self.lbl_calc_preview.configure(text="")
            self.lbl_target_warning.configure(text="")
            return

        try:
            target_mb = float(self.var_target_mb.get().replace(",", "."))
        except ValueError:
            self.lbl_calc_preview.configure(text="Geçersiz MB girişi", text_color="#EF4444")
            self.lbl_target_warning.configure(text="")
            return

        if target_mb <= 0:
            self.lbl_calc_preview.configure(text="MB sıfırdan büyük olmalı", text_color="#EF4444")
            return

        eff_dur = self._get_effective_duration()

        # Update trim summary label if trim enabled
        if self.var_trim_enable.get():
            s_val = parse_time_str(self.var_trim_start.get()) or 0.0
            e_val = parse_time_str(self.var_trim_end.get()) or self.current_meta.duration_seconds
            self.lbl_trim_summary.configure(
                text=f"Seçilen Kırpma Aralığı: {format_seconds(s_val)} - {format_seconds(e_val)} (Süre: {format_seconds(eff_dur)}) ➔ Hedef {target_mb} MB bu süreye uygulanır"
            )

        aud_sel = self.combo_audio.get()
        if "Mute" in aud_sel:
            aud_mode = "mute"
        elif "128" in aud_sel:
            aud_mode = "128k"
        elif "96" in aud_sel:
            aud_mode = "96k"
        elif "64" in aud_sel:
            aud_mode = "64k"
        else:
            aud_mode = "auto"

        bitrates = calculate_bitrates(
            eff_dur,
            target_mb,
            self.current_meta.has_audio,
            aud_mode
        )

        orig_proportional_mb = self.current_meta.filesize_mb * (eff_dur / self.current_meta.duration_seconds)
        savings = (1.0 - (target_mb / orig_proportional_mb)) * 100 if orig_proportional_mb > 0 else 0

        if target_mb >= orig_proportional_mb:
            self.lbl_calc_preview.configure(
                text=f"⚠️ Hedef boyut video parçasından büyük (+%{abs(savings):.0f})",
                text_color="#F59E0B"
            )
        else:
            self.lbl_calc_preview.configure(
                text=f"🎯 -%{savings:.0f} Tasarruf | Video: ~{bitrates['video_kbps']} kbps | Ses: ~{bitrates['audio_kbps']} kbps",
                text_color="#10B981"
            )

        rec_res = get_recommended_resolution(bitrates["video_kbps"], self.current_meta.width, self.current_meta.height)
        warnings = []
        if bitrates.get("warning"):
            warnings.append(bitrates["warning"])

        if self.combo_res.get() == "Otomatik (Önerilen)":
            if rec_res != "original":
                warnings.append(f"💡 Kaliteyi korumak için çözünürlük otomatik olarak {rec_res} formatına ölçeklenecektir.")
        else:
            if rec_res != "original" and "Orijinal" in self.combo_res.get():
                warnings.append(f"💡 Bu boyutta yüksek netlik için '720p' veya '480p' seçmeniz tavsiye edilir.")

        self.lbl_target_warning.configure(text=" • ".join(warnings))

    def _choose_custom_output_dir(self):
        folder = filedialog.askdirectory(title="Çıktı Klasörünü Seçin")
        if folder:
            self.custom_output_dir = folder
            folder_name = os.path.basename(folder) or folder
            self.btn_custom_out.configure(text=f"📁 {folder_name[:18]}")
        else:
            self.custom_output_dir = None
            self.btn_custom_out.configure(text="Girişle Aynı Klasör")

    # =========================================================================
    # SINGLE COMPRESSION EXECUTION
    # =========================================================================
    def _start_single_compression(self):
        if not self.current_meta or not self.current_meta.is_valid:
            messagebox.showwarning("Video Seçilmedi", "Lütfen önce sıkıştırmak istediğiniz bir video dosyası seçin!")
            return

        try:
            target_mb = float(self.var_target_mb.get().replace(",", "."))
            if target_mb <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Geçersiz Boyut", "Lütfen geçerli bir hedef MB sayısı girin (Örn: 25.0)!")
            return

        # Prepare trim arguments
        t_start = None
        t_end = None
        if self.var_trim_enable.get():
            t_start = parse_time_str(self.var_trim_start.get())
            t_end = parse_time_str(self.var_trim_end.get())
            if t_start is None or t_end is None or t_end <= t_start:
                messagebox.showerror("Hatalı Kırpma", "Lütfen geçerli bir başlangıç ve bitiş zamanı girin!")
                return

        # Prepare output path
        in_dir, in_file = os.path.split(self.current_meta.filepath)
        name, _ = os.path.splitext(in_file)
        out_dir = self.custom_output_dir if self.custom_output_dir else in_dir
        clean_target_str = f"{target_mb:.1f}".rstrip("0").rstrip(".")
        trim_suffix = "_trimmed" if self.var_trim_enable.get() else ""
        out_filename = f"{name}{trim_suffix}_compressed_{clean_target_str}MB.mp4"
        out_path = os.path.join(out_dir, out_filename)

        if os.path.exists(out_path):
            ans = messagebox.askyesno("Dosya Mevcut", f"'{out_filename}' zaten mevcut. Üzerine yazılsın mı?")
            if not ans:
                return

        # Resolution mode
        res_sel = self.combo_res.get()
        if "1080p" in res_sel:
            res_mode = "1080p"
        elif "720p" in res_sel:
            res_mode = "720p"
        elif "480p" in res_sel:
            res_mode = "480p"
        elif "360p" in res_sel:
            res_mode = "360p"
        elif "Orijinal" in res_sel:
            res_mode = "original"
        else:
            res_mode = "auto"

        # Codec
        codec = "hevc" if "H.265" in self.combo_codec.get() else "h264"

        # Mode
        mode = "1pass" if "1-Pass" in self.combo_mode.get() else "2pass"

        # GPU acceleration mode
        gpu_sel = self.combo_gpu.get()
        if "NVENC" in gpu_sel:
            hw_accel = "nvenc"
        elif "AMF" in gpu_sel:
            hw_accel = "amf"
        elif "QSV" in gpu_sel:
            hw_accel = "qsv"
        elif "CPU" in gpu_sel or "İşlemci" in gpu_sel:
            hw_accel = "cpu"
        else:
            hw_accel = "auto"

        # Audio
        aud_sel = self.combo_audio.get()
        if "Mute" in aud_sel:
            aud_mode = "mute"
        elif "128" in aud_sel:
            aud_mode = "128k"
        elif "96" in aud_sel:
            aud_mode = "96k"
        elif "64" in aud_sel:
            aud_mode = "64k"
        else:
            aud_mode = "auto"

        # Update UI to running state
        self.is_compressing = True
        self.btn_start.pack_forget()
        self.btn_cancel.pack(fill="x", padx=18, pady=(8, 6))
        self.progress_frame.pack(fill="x", pady=(4, 0))
        self.card_result.pack_forget()
        self.progress_bar.set(0)
        self.lbl_progress_status.configure(text="Sıkıştırma başlatılıyor...")
        self.lbl_progress_time.configure(text="")

        # Start job
        self.current_job = CompressionJob(
            input_path=self.current_meta.filepath,
            output_path=out_path,
            target_mb=target_mb,
            resolution_mode=res_mode,
            codec=codec,
            mode=mode,
            audio_mode=aud_mode,
            speed_preset="medium",
            hardware_accel=hw_accel,
            trim_start=t_start,
            trim_end=t_end,
            on_progress=lambda data: self.after(0, lambda: self._on_single_progress(data)),
            on_complete=lambda success, msg, summary: self.after(0, lambda: self._on_single_complete(success, msg, summary))
        )
        self.current_job.start()

    def _cancel_single_compression(self):
        if self.current_job:
            self.lbl_progress_status.configure(text="İptal ediliyor...")
            self.current_job.cancel()

    def _on_single_progress(self, data: dict):
        pct = data.get("percent", 0.0)
        self.progress_bar.set(pct / 100.0)
        phase = data.get("phase", "")
        self.lbl_progress_status.configure(text=f"{phase} %{pct:.1f}")

        elapsed = data.get("elapsed", "")
        eta = data.get("eta", "")
        if elapsed and eta:
            self.lbl_progress_time.configure(text=f"Geçen: {elapsed} | Kalan: ~{eta}")

    def _on_single_complete(self, success: bool, msg: str, summary: dict):
        self.is_compressing = False
        self.btn_cancel.pack_forget()
        self.btn_start.pack(fill="x", padx=18, pady=(8, 6))
        self.progress_frame.pack_forget()

        if success:
            self.last_output_path = summary.get("output_path")
            orig_mb = summary.get("original_mb", 0)
            final_mb = summary.get("final_mb", 0)
            target_mb = summary.get("target_mb", 0)
            savings = summary.get("savings_pct", 0)
            elapsed = summary.get("elapsed_sec", 0)
            codec_info = summary.get("codec", "H264")
            dur_info = summary.get("duration", "")

            stats_str = (
                f"• Boyut: {orig_mb} MB  ➔  Yeni: {final_mb} MB (Hedef: {target_mb} MB)\n"
                f"• Tasarruf: %{savings:.1f}  |  Süre: {elapsed:.1f} sn  |  Motor: {codec_info}  |  Video Süresi: {dur_info}\n"
                f"• Dosya: {os.path.basename(self.last_output_path)}"
            )
            self.lbl_result_stats.configure(text=stats_str)
            self.card_result.pack(fill="x", pady=6, ipady=8)
        else:
            if "iptal" not in msg.lower():
                messagebox.showerror("Hata", f"Sıkıştırma sırasında bir hata oluştu:\n{msg}")

    def _open_output_folder(self):
        if self.last_output_path and os.path.exists(self.last_output_path):
            norm = os.path.normpath(self.last_output_path)
            subprocess.run(["explorer", "/select,", norm])
        elif self.last_output_path:
            norm = os.path.dirname(os.path.normpath(self.last_output_path))
            subprocess.run(["explorer", norm])

    def _play_output_video(self):
        if self.last_output_path and os.path.exists(self.last_output_path):
            try:
                os.startfile(self.last_output_path)
            except Exception as e:
                messagebox.showerror("Oynatılamadı", f"Medya oynatıcı başlatılamadı:\n{e}")

    # =========================================================================
    # BATCH OPERATIONS
    # =========================================================================
    def _batch_add_files(self):
        filetypes = [
            ("Video Dosyaları", "*.mp4;*.mov;*.mkv;*.avi;*.webm;*.flv;*.wmv;*.m4v;*.ts"),
            ("Tüm Dosyalar", "*.*")
        ]
        paths = filedialog.askopenfilenames(title="Toplu Sıkıştırılacak Videoları Seçin", filetypes=filetypes)
        for p in paths:
            self._add_video_to_batch(p)

    def _add_video_to_batch(self, path: str):
        for item in self.batch_files:
            if item["path"] == path:
                return

        self.lbl_batch_empty.pack_forget()

        row = ctk.CTkFrame(self.batch_list_frame, fg_color=("#E2E8F0", "#1E222B"), corner_radius=8)
        row.pack(fill="x", pady=3, padx=4)

        fname = os.path.basename(path)
        size_mb = os.path.getsize(path) / (1024 * 1024) if os.path.exists(path) else 0

        lbl_name = ctk.CTkLabel(row, text=f"🎬 {fname}", font=ctk.CTkFont(size=12, weight="bold"), width=350, anchor="w")
        lbl_name.pack(side="left", padx=10, pady=6)

        lbl_size = ctk.CTkLabel(row, text=f"{size_mb:.1f} MB", font=ctk.CTkFont(size=12), width=90)
        lbl_size.pack(side="left", padx=5)

        lbl_status = ctk.CTkLabel(row, text="Sırada", font=ctk.CTkFont(size=11), text_color="#94A3B8", width=120)
        lbl_status.pack(side="left", padx=10)

        btn_rem = ctk.CTkButton(
            row,
            text="✕",
            width=28,
            height=26,
            fg_color="transparent",
            text_color="#EF4444",
            hover_color=("#CBD5E1", "#334155"),
            command=lambda: self._batch_remove_item(path, row)
        )
        btn_rem.pack(side="right", padx=10)

        self.batch_files.append({
            "path": path,
            "size_mb": size_mb,
            "status_lbl": lbl_status,
            "row": row,
            "status": "ready"
        })

    def _batch_remove_item(self, path: str, row_widget):
        row_widget.destroy()
        self.batch_files = [f for f in self.batch_files if f["path"] != path]
        if not self.batch_files:
            self.lbl_batch_empty.pack(expand=True, pady=40)

    def _batch_clear(self):
        for item in self.batch_files:
            item["row"].destroy()
        self.batch_files = []
        self.lbl_batch_empty.pack(expand=True, pady=40)
        self.batch_pbar.set(0)
        self.lbl_batch_status.configure(text="Hazır")

    def _start_batch_compression(self):
        if not self.batch_files:
            messagebox.showwarning("Liste Boş", "Lütfen önce sıkıştırılacak videoları ekleyin!")
            return

        try:
            target_mb = float(self.var_batch_target.get().replace(",", "."))
            if target_mb <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Geçersiz Boyut", "Lütfen geçerli bir hedef MB sayısı girin!")
            return

        self.btn_batch_start.configure(state="disabled")
        self.batch_cancelled = False
        self.batch_index = 0
        self._process_next_batch_item(target_mb)

    def _process_next_batch_item(self, target_mb: float):
        if self.batch_cancelled or self.batch_index >= len(self.batch_files):
            self.btn_batch_start.configure(state="normal")
            self.lbl_batch_status.configure(text=f"Toplu işlem tamamlandı! ({len(self.batch_files)} video)")
            return

        item = self.batch_files[self.batch_index]
        in_path = item["path"]
        in_dir, in_file = os.path.split(in_path)
        name, _ = os.path.splitext(in_file)
        clean_target = f"{target_mb:.1f}".rstrip("0").rstrip(".")
        out_path = os.path.join(in_dir, f"{name}_compressed_{clean_target}MB.mp4")

        item["status_lbl"].configure(text="İşleniyor...", text_color="#3B82F6")
        self.lbl_batch_status.configure(text=f"İşleniyor: {self.batch_index + 1}/{len(self.batch_files)} ({os.path.basename(in_path)})")

        def on_prog(data):
            pct = data.get("percent", 0)
            overall_pct = (self.batch_index + (pct / 100.0)) / len(self.batch_files)
            self.after(0, lambda: self.batch_pbar.set(overall_pct))
            self.after(0, lambda: item["status_lbl"].configure(text=f"%{pct:.0f}"))

        def on_done(success, msg, summary):
            if success:
                new_mb = summary.get("final_mb", 0)
                item["status_lbl"].configure(text=f"✅ {new_mb} MB", text_color="#10B981")
            else:
                item["status_lbl"].configure(text="❌ Hata", text_color="#EF4444")

            self.batch_index += 1
            self.after(200, lambda: self._process_next_batch_item(target_mb))

        self.batch_job = CompressionJob(
            input_path=in_path,
            output_path=out_path,
            target_mb=target_mb,
            resolution_mode="auto",
            codec="h264",
            hardware_accel="auto",
            mode="2pass",
            audio_mode="auto",
            speed_preset="medium",
            on_progress=on_prog,
            on_complete=on_done
        )
        self.batch_job.start()


def main():
    app = NexraApp()
    app.mainloop()


if __name__ == "__main__":
    main()
