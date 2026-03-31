import json
import os
import re
import shlex
import shutil
import subprocess
import tkinter as tk
from tkinter import ttk, filedialog

from core.media_jobs import (
    MEDIA_JOB_BURN_SUBTITLE,
    MEDIA_JOB_CONCAT,
    MEDIA_JOB_CROP,
    MEDIA_JOB_EXTRACT_AUDIO,
    MEDIA_JOB_LOUDNORM,
    MEDIA_JOB_REMUX,
    MEDIA_JOB_ROTATE,
    MEDIA_JOB_SCALE,
    MEDIA_JOB_TRIM,
    MEDIA_JOB_WATERMARK,
    MediaJobProfile,
    MediaJobRecord,
)


class MediaToolsPage(ttk.Frame):
    """本地媒体处理工具页。"""

    def __init__(self, parent, app, manager):
        super().__init__(parent)
        self.app = app
        self.manager = manager
        parent.add(self, text=self.app.get_text("tab_media_tools"))
        self._build_layout()

    def _build_layout(self):
        container = ttk.PanedWindow(self, orient='vertical')
        container.pack(fill='both', expand=True, padx=10, pady=(5, 10))
        self.container_pane = container

        font_family = getattr(self.app, 'FONT_FAMILY', 'Microsoft YaHei')
        font_size = getattr(self.app, 'FONT_SIZE_NORMAL', 10)
        title_font = (font_family, max(9, font_size - 1), 'bold')

        input_card = ttk.Frame(container, style="Card.TFrame", padding=6)
        input_header = ttk.Frame(input_card, style="Card.TFrame")
        input_header.pack(fill='x', pady=(0, 4))
        ttk.Label(input_header, text=self.app.get_text("media_input_frame"), style="Card.TLabel", font=title_font).pack(side='left')
        input_frame = ttk.Frame(input_card, style="Card.TFrame")
        input_frame.pack(fill='both', expand=True)

        queue_card = ttk.Frame(container, style="Card.TFrame", padding=6)
        queue_header = ttk.Frame(queue_card, style="Card.TFrame")
        queue_header.pack(fill='x', pady=(0, 4))
        ttk.Label(queue_header, text=self.app.get_text("media_queue_frame"), style="Card.TLabel", font=title_font).pack(side='left')
        queue_frame = ttk.Frame(queue_card, style="Card.TFrame")
        queue_frame.pack(fill='both', expand=True)

        log_card = ttk.Frame(container, style="Card.TFrame", padding=6)
        log_header = ttk.Frame(log_card, style="Card.TFrame")
        log_header.pack(fill='x', pady=(0, 4))
        ttk.Label(log_header, text=self.app.get_text("media_log_frame"), style="Card.TLabel", font=title_font).pack(side='left')
        log_frame = ttk.Frame(log_card, style="Card.TFrame")
        log_frame.pack(fill='both', expand=True)

        container.add(input_card, weight=10) # 极大延展配置区，强力下压队列
        container.add(queue_card, weight=1)
        container.add(log_card, weight=1)

        self._build_input(input_frame)
        self._build_queue(queue_frame)
        self._build_log(log_frame)

    def _build_input(self, frame):
        font_family = getattr(self.app, 'FONT_FAMILY', 'Microsoft YaHei')
        font_size = getattr(self.app, 'FONT_SIZE_NORMAL', 10)

        type_row = ttk.Frame(frame, style="Card.TFrame")
        type_row.pack(fill='x', pady=(0, 6))
        ttk.Label(type_row, text=self.app.get_text("media_type_label"), style="Card.TLabel", font=(font_family, font_size)).pack(side='left')
        self.job_type_var = tk.StringVar(value=MEDIA_JOB_REMUX)
        type_combo = ttk.Combobox(type_row, textvariable=self.job_type_var, state="readonly", width=20)
        type_combo.configure(values=(
            MEDIA_JOB_REMUX,
            MEDIA_JOB_EXTRACT_AUDIO,
            MEDIA_JOB_TRIM,
            MEDIA_JOB_CONCAT,
            MEDIA_JOB_BURN_SUBTITLE,
            MEDIA_JOB_SCALE,
            MEDIA_JOB_CROP,
            MEDIA_JOB_ROTATE,
            MEDIA_JOB_WATERMARK,
            MEDIA_JOB_LOUDNORM,
        ))
        type_combo.pack(side='left', padx=(6, 12))
        type_combo.bind("<<ComboboxSelected>>", lambda _e: self._refresh_visibility())

        input_row = ttk.Frame(frame, style="Card.TFrame")
        input_row.pack(fill='x', pady=(0, 6))
        ttk.Label(input_row, text=self.app.get_text("media_input_file"), style="Card.TLabel", font=(font_family, font_size)).pack(side='left')
        self.input_path_var = tk.StringVar()
        ttk.Entry(input_row, textvariable=self.input_path_var, width=60).pack(side='left', padx=(6, 6), fill='x', expand=True)
        ttk.Button(input_row, text=self.app.get_text("media_select"), command=self._choose_input).pack(side='left')

        output_row = ttk.Frame(frame, style="Card.TFrame")
        output_row.pack(fill='x', pady=(0, 6))
        ttk.Label(output_row, text=self.app.get_text("media_output_file"), style="Card.TLabel", font=(font_family, font_size)).pack(side='left')
        self.output_path_var = tk.StringVar()
        ttk.Entry(output_row, textvariable=self.output_path_var, width=60).pack(side='left', padx=(6, 6), fill='x', expand=True)
        ttk.Button(output_row, text=self.app.get_text("media_select"), command=self._choose_output).pack(side='left')

        audio_row = ttk.Frame(frame, style="Card.TFrame")
        audio_row.pack(fill='x', pady=(0, 6))
        ttk.Label(audio_row, text=self.app.get_text("media_audio_format"), style="Card.TLabel", font=(font_family, font_size)).pack(side='left')
        self.audio_format_var = tk.StringVar(value="mp3")
        ttk.Combobox(audio_row, textvariable=self.audio_format_var, state="readonly", width=10, values=("mp3", "m4a", "wav", "flac", "opus")).pack(side='left', padx=(6, 12))
        self.audio_row = audio_row

        trim_row = ttk.Frame(frame, style="Card.TFrame")
        trim_row.pack(fill='x', pady=(0, 6))
        ttk.Label(trim_row, text=self.app.get_text("media_trim_time"), style="Card.TLabel", font=(font_family, font_size)).pack(side='left')
        ttk.Label(trim_row, text=self.app.get_text("media_trim_start"), style="Card.TLabel", font=(font_family, font_size)).pack(side='left', padx=(6, 2))
        self.start_time_var = tk.StringVar()
        ttk.Entry(trim_row, textvariable=self.start_time_var, width=10).pack(side='left')
        ttk.Label(trim_row, text=self.app.get_text("media_trim_end"), style="Card.TLabel", font=(font_family, font_size)).pack(side='left', padx=(6, 2))
        self.end_time_var = tk.StringVar()
        ttk.Entry(trim_row, textvariable=self.end_time_var, width=10).pack(side='left')
        ttk.Label(trim_row, text=self.app.get_text("media_trim_hint"), style="Card.TLabel", font=(font_family, 8), foreground="#888888").pack(side='left', padx=(6, 0))
        self.trim_row = trim_row

        concat_row = ttk.Frame(frame, style="Card.TFrame")
        concat_row.pack(fill='x', pady=(0, 6))
        ttk.Label(concat_row, text=self.app.get_text("media_concat_list"), style="Card.TLabel", font=(font_family, font_size)).pack(side='left')
        self.concat_list_var = tk.StringVar()
        ttk.Entry(concat_row, textvariable=self.concat_list_var, width=60).pack(side='left', padx=(6, 6), fill='x', expand=True)
        ttk.Button(concat_row, text=self.app.get_text("media_select"), command=self._choose_concat_list).pack(side='left')
        self.concat_row = concat_row

        subtitle_row = ttk.Frame(frame, style="Card.TFrame")
        subtitle_row.pack(fill='x', pady=(0, 6))
        ttk.Label(subtitle_row, text=self.app.get_text("media_subtitle_file"), style="Card.TLabel", font=(font_family, font_size)).pack(side='left')
        self.subtitle_path_var = tk.StringVar()
        ttk.Entry(subtitle_row, textvariable=self.subtitle_path_var, width=60).pack(side='left', padx=(6, 6), fill='x', expand=True)
        ttk.Button(subtitle_row, text=self.app.get_text("media_select"), command=self._choose_subtitle).pack(side='left')
        self.subtitle_row = subtitle_row

        scale_row = ttk.Frame(frame, style="Card.TFrame")
        scale_row.pack(fill='x', pady=(0, 6))
        ttk.Label(scale_row, text=self.app.get_text("media_scale"), style="Card.TLabel", font=(font_family, font_size)).pack(side='left')
        ttk.Label(scale_row, text=self.app.get_text("media_width"), style="Card.TLabel", font=(font_family, font_size)).pack(side='left', padx=(6, 2))
        self.scale_width_var = tk.StringVar()
        ttk.Entry(scale_row, textvariable=self.scale_width_var, width=8).pack(side='left')
        ttk.Label(scale_row, text=self.app.get_text("media_height"), style="Card.TLabel", font=(font_family, font_size)).pack(side='left', padx=(6, 2))
        self.scale_height_var = tk.StringVar()
        ttk.Entry(scale_row, textvariable=self.scale_height_var, width=8).pack(side='left')
        ttk.Label(scale_row, text=self.app.get_text("media_scale_hint"), style="Card.TLabel", font=(font_family, 8), foreground="#888888").pack(side='left', padx=(6, 0))
        self.scale_row = scale_row

        crop_row = ttk.Frame(frame, style="Card.TFrame")
        crop_row.pack(fill='x', pady=(0, 6))
        ttk.Label(crop_row, text=self.app.get_text("media_crop"), style="Card.TLabel", font=(font_family, font_size)).pack(side='left')
        ttk.Label(crop_row, text=self.app.get_text("media_width"), style="Card.TLabel", font=(font_family, font_size)).pack(side='left', padx=(6, 2))
        self.crop_width_var = tk.StringVar()
        ttk.Entry(crop_row, textvariable=self.crop_width_var, width=8).pack(side='left')
        ttk.Label(crop_row, text=self.app.get_text("media_height"), style="Card.TLabel", font=(font_family, font_size)).pack(side='left', padx=(6, 2))
        self.crop_height_var = tk.StringVar()
        ttk.Entry(crop_row, textvariable=self.crop_height_var, width=8).pack(side='left')
        ttk.Label(crop_row, text=self.app.get_text("media_pos_x"), style="Card.TLabel", font=(font_family, font_size)).pack(side='left', padx=(6, 2))
        self.crop_x_var = tk.StringVar()
        ttk.Entry(crop_row, textvariable=self.crop_x_var, width=6).pack(side='left')
        ttk.Label(crop_row, text=self.app.get_text("media_pos_y"), style="Card.TLabel", font=(font_family, font_size)).pack(side='left', padx=(6, 2))
        self.crop_y_var = tk.StringVar()
        ttk.Entry(crop_row, textvariable=self.crop_y_var, width=6).pack(side='left')
        self.crop_row = crop_row

        rotate_row = ttk.Frame(frame, style="Card.TFrame")
        rotate_row.pack(fill='x', pady=(0, 6))
        ttk.Label(rotate_row, text=self.app.get_text("media_rotate"), style="Card.TLabel", font=(font_family, font_size)).pack(side='left')
        self.rotate_var = tk.StringVar()
        ttk.Combobox(rotate_row, textvariable=self.rotate_var, state="readonly", width=8, values=("", "90", "180", "270")).pack(side='left', padx=(6, 12))
        ttk.Label(rotate_row, text=self.app.get_text("media_watermark"), style="Card.TLabel", font=(font_family, font_size)).pack(side='left')
        self.watermark_path_var = tk.StringVar()
        ttk.Entry(rotate_row, textvariable=self.watermark_path_var, width=30).pack(side='left', padx=(6, 6), fill='x', expand=True)
        ttk.Button(rotate_row, text=self.app.get_text("media_select"), command=self._choose_watermark).pack(side='left')
        self.watermark_row = rotate_row

        watermark_pos_row = ttk.Frame(frame, style="Card.TFrame")
        watermark_pos_row.pack(fill='x', pady=(0, 6))
        ttk.Label(watermark_pos_row, text=self.app.get_text("media_watermark_pos"), style="Card.TLabel", font=(font_family, font_size)).pack(side='left')
        self.watermark_pos_var = tk.StringVar(value="bottom-right")
        ttk.Combobox(
            watermark_pos_row,
            textvariable=self.watermark_pos_var,
            state="readonly",
            width=14,
            values=("top-left", "top-right", "bottom-left", "bottom-right", "center"),
        ).pack(side='left', padx=(6, 12))
        ttk.Label(watermark_pos_row, text=self.app.get_text("media_loudnorm"), style="Card.TLabel", font=(font_family, font_size)).pack(side='left')
        ttk.Label(watermark_pos_row, text=self.app.get_text("media_loudnorm_hint"), style="Card.TLabel", font=(font_family, 8), foreground="#888888").pack(side='left', padx=(6, 0))
        self.watermark_pos_row = watermark_pos_row

        info_row = ttk.Frame(frame, style="Card.TFrame")
        info_row.pack(fill='x', pady=(0, 6))
        ttk.Label(info_row, text=self.app.get_text("media_info"), style="Card.TLabel", font=(font_family, font_size)).pack(side='left')
        self.media_info_var = tk.StringVar(value=self.app.get_text("media_info_pending"))
        ttk.Label(info_row, textvariable=self.media_info_var, style="Card.TLabel", foreground="#666666").pack(side='left', padx=(6, 0))
        self.media_info_row = info_row

        advanced_card = ttk.Frame(frame, style="Card.TFrame", padding=6)
        advanced_card.pack(fill='x', pady=(6, 4))
        ttk.Label(advanced_card, text=self.app.get_text("media_advanced"), style="Card.TLabel", font=(font_family, max(9, font_size - 1), 'bold')).pack(anchor='w', pady=(0, 4))

        encoding_row = ttk.Frame(advanced_card, style="Card.TFrame")
        encoding_row.pack(fill='x', pady=(0, 4))
        ttk.Label(encoding_row, text=self.app.get_text("media_video_codec"), style="Card.TLabel").pack(side='left')
        self.video_codec_var = tk.StringVar()
        ttk.Combobox(encoding_row, textvariable=self.video_codec_var, state="readonly", width=10, values=("", "h264", "h265", "vp9", "av1", "copy")).pack(side='left', padx=(4, 8))
        ttk.Label(encoding_row, text=self.app.get_text("media_audio_codec"), style="Card.TLabel").pack(side='left')
        self.audio_codec_var = tk.StringVar()
        ttk.Combobox(encoding_row, textvariable=self.audio_codec_var, state="readonly", width=10, values=("", "aac", "mp3", "opus", "flac", "copy")).pack(side='left', padx=(4, 8))
        ttk.Label(encoding_row, text=self.app.get_text("media_crf"), style="Card.TLabel").pack(side='left')
        self.crf_var = tk.StringVar()
        ttk.Entry(encoding_row, textvariable=self.crf_var, width=6).pack(side='left', padx=(4, 8))
        ttk.Label(encoding_row, text=self.app.get_text("media_preset"), style="Card.TLabel").pack(side='left')
        self.preset_var = tk.StringVar()
        ttk.Entry(encoding_row, textvariable=self.preset_var, width=10).pack(side='left', padx=(4, 0))

        bitrate_row = ttk.Frame(advanced_card, style="Card.TFrame")
        bitrate_row.pack(fill='x', pady=(0, 4))
        ttk.Label(bitrate_row, text=self.app.get_text("media_video_bitrate"), style="Card.TLabel").pack(side='left')
        self.video_bitrate_var = tk.StringVar()
        ttk.Entry(bitrate_row, textvariable=self.video_bitrate_var, width=10).pack(side='left', padx=(4, 8))
        ttk.Label(bitrate_row, text=self.app.get_text("media_audio_bitrate"), style="Card.TLabel").pack(side='left')
        self.audio_bitrate_var = tk.StringVar()
        ttk.Entry(bitrate_row, textvariable=self.audio_bitrate_var, width=10).pack(side='left', padx=(4, 8))
        ttk.Label(bitrate_row, text=self.app.get_text("media_vf_custom"), style="Card.TLabel").pack(side='left')
        self.vf_custom_var = tk.StringVar()
        ttk.Entry(bitrate_row, textvariable=self.vf_custom_var, width=16).pack(side='left', padx=(4, 8), fill='x', expand=True)
        ttk.Label(bitrate_row, text=self.app.get_text("media_af_custom"), style="Card.TLabel").pack(side='left')
        self.af_custom_var = tk.StringVar()
        ttk.Entry(bitrate_row, textvariable=self.af_custom_var, width=16).pack(side='left', padx=(4, 0), fill='x', expand=True)

        extra_row = ttk.Frame(advanced_card, style="Card.TFrame")
        extra_row.pack(fill='x')
        ttk.Label(extra_row, text=self.app.get_text("media_extra_args"), style="Card.TLabel").pack(side='left')
        self.extra_args_var = tk.StringVar()
        ttk.Entry(extra_row, textvariable=self.extra_args_var, width=64).pack(side='left', padx=(4, 0), fill='x', expand=True)

        btn_row = ttk.Frame(frame, style="Card.TFrame")
        btn_row.pack(fill='x', pady=(6, 0))
        ttk.Button(btn_row, text=self.app.get_text("media_add_job"), command=self._add_job, style="Primary.TButton").pack(side='left')
        ttk.Button(btn_row, text=self.app.get_text("media_start_all"), command=self.manager.start_all_jobs, style="Info.Small.TButton").pack(side='left', padx=(8, 0))
        ttk.Button(btn_row, text=self.app.get_text("media_clear_done"), command=self.manager.clear_completed, style="Small.TButton").pack(side='left', padx=(8, 0))

        self._refresh_visibility()

    def _build_queue(self, frame):
        columns = ("id", "status", "progress", "speed", "name")
        job_tree = ttk.Treeview(frame, columns=columns, show='headings', selectmode='extended', height=4)
        job_tree.heading("id", text=self.app.get_text("media_col_id"))
        job_tree.heading("status", text=self.app.get_text("media_col_status"))
        job_tree.heading("progress", text=self.app.get_text("media_col_progress"))
        job_tree.heading("speed", text=self.app.get_text("media_col_speed"))
        job_tree.heading("name", text=self.app.get_text("media_col_name"))
        job_tree.column("id", width=90, anchor='w')
        job_tree.column("status", width=110, anchor='w')
        job_tree.column("progress", width=100, anchor='w')
        job_tree.column("speed", width=100, anchor='w')
        job_tree.column("name", width=320, anchor='w')

        vsb = ttk.Scrollbar(frame, orient='vertical', command=job_tree.yview)
        hsb = ttk.Scrollbar(frame, orient='horizontal', command=job_tree.xview)
        job_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        job_tree.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        hsb.grid(row=1, column=0, sticky='ew')
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        btn_row = ttk.Frame(frame, style="Card.TFrame")
        btn_row.grid(row=2, column=0, columnspan=2, sticky='ew', pady=(6, 0))
        ttk.Button(btn_row, text=self.app.get_text("media_stop_selected"), command=lambda: self.manager.stop_selected(job_tree), style="Warning.Small.TButton").pack(side='left', padx=2)
        ttk.Button(btn_row, text=self.app.get_text("media_delete_selected"), command=lambda: self.manager.delete_selected(job_tree), style="Small.TButton").pack(side='left', padx=2)

        self.manager.job_tree = job_tree
        self.manager.update_list()

    def _build_log(self, frame):
        font_family = getattr(self.app, 'FONT_FAMILY', 'Microsoft YaHei')
        font_size = getattr(self.app, 'FONT_SIZE_NORMAL', 10)
        log_font_size = max(8, font_size - 1)
        log_text = tk.Text(
            frame,
            height=5,
            bg='#ffffff',
            fg='#333333',
            insertbackground='#333333',
            relief='flat',
            wrap='word',
            font=(font_family, log_font_size),
            padx=8,
            pady=8,
        )
        scrollbar = ttk.Scrollbar(frame, command=log_text.yview)
        log_text.config(yscrollcommand=scrollbar.set)
        log_text.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

        log_text.tag_config("ERROR", foreground="#d32f2f")
        log_text.tag_config("SUCCESS", foreground="#2e7d32")
        log_text.tag_config("INFO", foreground="#1565c0")
        log_text.tag_config("WARN", foreground="#e65100")
        log_text.tag_config("WARNING", foreground="#e65100")

        self.manager.log_text = log_text
        if hasattr(self.app, 'root') and self.app.root:
            self.app.root.after(120, self.manager.process_log_queue)

    def _choose_input(self):
        path = filedialog.askopenfilename(title=self.app.get_text("media_dialog_input"))
        if path:
            self.input_path_var.set(path)
            if not self.output_path_var.get():
                self.output_path_var.set(self._default_output_path(path))
            self._refresh_media_info(path)

    def _choose_output(self):
        path = filedialog.asksaveasfilename(title=self.app.get_text("media_dialog_output"), initialfile="output.mp4")
        if path:
            self.output_path_var.set(path)
            if getattr(self, "media_info_var", None) and not self.input_path_var.get().strip():
                self.media_info_var.set(self.app.get_text("media_info_pending"))

    def _choose_concat_list(self):
        path = filedialog.askopenfilename(title=self.app.get_text("media_dialog_concat"), filetypes=[("Text", "*.txt")])
        if path:
            self.concat_list_var.set(path)
            if not self.output_path_var.get():
                base_dir = os.path.dirname(path)
                self.output_path_var.set(os.path.join(base_dir, "concat_output.mp4"))

    def _choose_subtitle(self):
        path = filedialog.askopenfilename(title=self.app.get_text("media_dialog_subtitle"), filetypes=[("Subtitle", "*.srt *.ass *.vtt"), ("All", "*.*")])
        if path:
            self.subtitle_path_var.set(path)

    def _choose_watermark(self):
        path = filedialog.askopenfilename(title=self.app.get_text("media_dialog_watermark"), filetypes=[("Image", "*.png *.jpg *.jpeg *.webp"), ("All", "*.*")])
        if path:
            self.watermark_path_var.set(path)

    def _default_output_path(self, input_path):
        base, ext = os.path.splitext(input_path)
        if not ext:
            ext = ".mp4"
        return f"{base}_output{ext}"

    def _refresh_media_info(self, input_path):
        if not getattr(self, "media_info_var", None):
            return
        if not input_path:
            self.media_info_var.set(self.app.get_text("media_info_pending"))
            return
        ffprobe = shutil.which("ffprobe") or shutil.which("ffprobe.exe")
        if not ffprobe:
            self._refresh_media_info_without_ffprobe(input_path)
            return
        cmd = [
            ffprobe,
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            input_path,
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=8)
            if result.returncode != 0:
                self.media_info_var.set(self.app.get_text("media_info_parse_failed"))
                return
            payload = json.loads(result.stdout or "{}")
        except Exception:
            self.media_info_var.set(self.app.get_text("media_info_parse_failed"))
            return
        fmt = payload.get("format", {}) if isinstance(payload, dict) else {}
        duration = fmt.get("duration") or "-"
        size = fmt.get("size") or "-"
        bitrate = fmt.get("bit_rate") or "-"
        stream_count = len(payload.get("streams", []) or []) if isinstance(payload, dict) else 0
        self.media_info_var.set(self.app.get_text("media_info_summary").format(
            duration=duration,
            size=size,
            bitrate=bitrate,
            streams=stream_count,
        ))

    def _refresh_media_info_without_ffprobe(self, input_path):
        file_size = "-"
        try:
            file_size = str(os.path.getsize(input_path))
        except Exception:
            file_size = "-"

        ffmpeg = getattr(self.manager, "ffmpeg_path", "") or shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
        if not ffmpeg:
            self.media_info_var.set(self.app.get_text("media_info_no_ffprobe"))
            return

        cmd = [ffmpeg, "-i", input_path]
        duration = "-"
        bitrate = "-"
        stream_count = 0
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=8)
            probe_text = (result.stderr or "") + "\n" + (result.stdout or "")
            duration_match = re.search(r"Duration:\s*([0-9:.]+)", probe_text)
            bitrate_match = re.search(r"bitrate:\s*([0-9.]+\s*[kmg]?b/s)", probe_text, re.IGNORECASE)
            if duration_match:
                duration = duration_match.group(1)
            if bitrate_match:
                bitrate = bitrate_match.group(1)
            stream_count = len(re.findall(r"^\s*Stream #", probe_text, flags=re.MULTILINE))
        except Exception:
            self.media_info_var.set(self.app.get_text("media_info_no_ffprobe"))
            return

        self.media_info_var.set(self.app.get_text("media_info_summary").format(
            duration=duration,
            size=file_size,
            bitrate=bitrate,
            streams=stream_count or "-",
        ))

    def _refresh_visibility(self):
        job_type = self.job_type_var.get().strip()
        is_extract = job_type == MEDIA_JOB_EXTRACT_AUDIO
        is_trim = job_type == MEDIA_JOB_TRIM
        is_concat = job_type == MEDIA_JOB_CONCAT
        is_subtitle = job_type == MEDIA_JOB_BURN_SUBTITLE
        is_scale = job_type == MEDIA_JOB_SCALE
        is_crop = job_type == MEDIA_JOB_CROP
        is_rotate = job_type == MEDIA_JOB_ROTATE
        is_watermark = job_type == MEDIA_JOB_WATERMARK

        self.audio_row.pack_forget()
        self.trim_row.pack_forget()
        self.concat_row.pack_forget()
        self.subtitle_row.pack_forget()
        if getattr(self, "scale_row", None):
            self.scale_row.pack_forget()
        if getattr(self, "crop_row", None):
            self.crop_row.pack_forget()
        if getattr(self, "rotate_row", None):
            self.rotate_row.pack_forget()
        if getattr(self, "watermark_row", None):
            self.watermark_row.pack_forget()

        if is_extract:
            self.audio_row.pack(fill='x', pady=(0, 6))
        if is_trim:
            self.trim_row.pack(fill='x', pady=(0, 6))
        if is_concat:
            self.concat_row.pack(fill='x', pady=(0, 6))
        if is_subtitle:
            self.subtitle_row.pack(fill='x', pady=(0, 6))
        if is_scale and getattr(self, "scale_row", None):
            self.scale_row.pack(fill='x', pady=(0, 6))
        if is_crop and getattr(self, "crop_row", None):
            self.crop_row.pack(fill='x', pady=(0, 6))
        if is_rotate and getattr(self, "rotate_row", None):
            self.rotate_row.pack(fill='x', pady=(0, 6))
        if is_watermark and getattr(self, "watermark_row", None):
            self.watermark_row.pack(fill='x', pady=(0, 6))

    def _validate_inputs(self, job_type):
        if job_type != MEDIA_JOB_CONCAT and not self.input_path_var.get().strip():
            self.app.SilentMessagebox.showwarning(self.app.get_text("common_notice"), self.app.get_text("media_warn_input_missing"))
            return False
        if job_type == MEDIA_JOB_CONCAT:
            if not self.concat_list_var.get().strip():
                self.app.SilentMessagebox.showwarning(self.app.get_text("common_notice"), self.app.get_text("media_warn_concat_missing"))
                return False
        if job_type == MEDIA_JOB_BURN_SUBTITLE and not self.subtitle_path_var.get().strip():
            self.app.SilentMessagebox.showwarning(self.app.get_text("common_notice"), self.app.get_text("media_warn_subtitle_missing"))
            return False
        if job_type == MEDIA_JOB_WATERMARK and not getattr(self, "watermark_path_var", tk.StringVar()).get().strip():
            self.app.SilentMessagebox.showwarning(self.app.get_text("common_notice"), self.app.get_text("media_warn_watermark_missing"))
            return False
        if job_type != MEDIA_JOB_CONCAT and not self.output_path_var.get().strip():
            self.app.SilentMessagebox.showwarning(self.app.get_text("common_notice"), self.app.get_text("media_warn_output_missing"))
            return False
        return True

    def _add_job(self):
        job_type = self.job_type_var.get().strip()
        if not self._validate_inputs(job_type):
            return

        profile = MediaJobProfile(
            job_type=job_type,
            input_path=self.input_path_var.get().strip(),
            output_path=self.output_path_var.get().strip(),
            audio_format=self.audio_format_var.get().strip(),
            start_time=self.start_time_var.get().strip(),
            end_time=self.end_time_var.get().strip(),
            concat_list_path=self.concat_list_var.get().strip(),
            subtitle_path=self.subtitle_path_var.get().strip(),
            scale_width=getattr(self, "scale_width_var", tk.StringVar()).get().strip(),
            scale_height=getattr(self, "scale_height_var", tk.StringVar()).get().strip(),
            crop_width=getattr(self, "crop_width_var", tk.StringVar()).get().strip(),
            crop_height=getattr(self, "crop_height_var", tk.StringVar()).get().strip(),
            crop_x=getattr(self, "crop_x_var", tk.StringVar()).get().strip(),
            crop_y=getattr(self, "crop_y_var", tk.StringVar()).get().strip(),
            rotate=getattr(self, "rotate_var", tk.StringVar()).get().strip(),
            watermark_path=getattr(self, "watermark_path_var", tk.StringVar()).get().strip(),
            watermark_pos=getattr(self, "watermark_pos_var", tk.StringVar()).get().strip() or "bottom-right",
            video_codec=self.video_codec_var.get().strip(),
            audio_codec=self.audio_codec_var.get().strip(),
            video_bitrate=self.video_bitrate_var.get().strip(),
            audio_bitrate=self.audio_bitrate_var.get().strip(),
            crf=self.crf_var.get().strip(),
            preset=self.preset_var.get().strip(),
            vf_custom=self.vf_custom_var.get().strip(),
            af_custom=self.af_custom_var.get().strip(),
            extra_args=self.extra_args_var.get().strip(),
        )
        job = MediaJobRecord(profile=profile)
        self.manager.add_job(job)

        self.app.SilentMessagebox.showinfo(
            self.app.get_text("common_notice"),
            self.app.get_text("media_job_added").format(name=job.get_display_name()),
        )

        if job_type != MEDIA_JOB_CONCAT:
            self.input_path_var.set("")
        self.output_path_var.set("")
        self.start_time_var.set("")
        self.end_time_var.set("")
        self.concat_list_var.set("")
        self.subtitle_path_var.set("")
        if getattr(self, "scale_width_var", None):
            self.scale_width_var.set("")
        if getattr(self, "scale_height_var", None):
            self.scale_height_var.set("")
        if getattr(self, "crop_width_var", None):
            self.crop_width_var.set("")
        if getattr(self, "crop_height_var", None):
            self.crop_height_var.set("")
        if getattr(self, "crop_x_var", None):
            self.crop_x_var.set("")
        if getattr(self, "crop_y_var", None):
            self.crop_y_var.set("")
        if getattr(self, "rotate_var", None):
            self.rotate_var.set("")
        if getattr(self, "watermark_path_var", None):
            self.watermark_path_var.set("")
        if getattr(self, "watermark_pos_var", None):
            self.watermark_pos_var.set("bottom-right")
        self.video_codec_var.set("")
        self.audio_codec_var.set("")
        self.video_bitrate_var.set("")
        self.audio_bitrate_var.set("")
        self.crf_var.set("")
        self.preset_var.set("")
        self.vf_custom_var.set("")
        self.af_custom_var.set("")
        self.extra_args_var.set("")
