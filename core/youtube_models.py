from dataclasses import dataclass, field
from typing import List, Optional
import itertools
import os
import re
import time
from urllib.parse import urlparse

from core.auth_models import AuthDiagnostic

TASK_STATUS_WAITING = "等待中"
TASK_STATUS_RUNNING = "下载中"
TASK_STATUS_SUCCESS = "完成"
TASK_STATUS_FAILED = "失败"
TASK_STATUS_STOPPED = "已停止"

AUDIO_FMT = "bestaudio[ext=m4a]/bestaudio"
P1080_FMT = "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080]"
P720_FMT = "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720]"
BEST_COMPAT_FMT = P1080_FMT
BEST_QUALITY_FMT = "bestvideo*+bestaudio/best"
MAX_4K_FMT = "bestvideo[height<=2160]+bestaudio/best[height<=2160]"
MIN_SIZE_FMT = "best[height<=480]/worst"
KEEP_ORIGINAL_FMT = "bestvideo+bestaudio/best"
HDR_PRIORITY_FMT = "bestvideo[dynamic_range=HDR]+bestaudio/best"
HIGH_FPS_FMT = "bestvideo[fps>=50]+bestaudio/best"

BATCH_SOURCE_PLAYLIST = "playlist"
BATCH_SOURCE_CHANNEL = "channel"
BATCH_SOURCE_UPLOADS = "uploads"
BATCH_SOURCE_UNKNOWN = "unknown"

URL_TYPE_YOUTUBE = "youtube"
URL_TYPE_BILIBILI = "bilibili"
URL_TYPE_VIMEO = "vimeo"
URL_TYPE_SOUNDCLOUD = "soundcloud"
URL_TYPE_UNKNOWN = "unknown"

TASK_MODE_YOUTUBE = "youtube"
TASK_MODE_GENERIC = "generic"

DOWNLOAD_PRESET_LABELS = {
    "best_quality": "最佳画质",
    "best_compat": "最佳兼容",
    "max_1080p": "最高 1080p",
    "max_4k": "最高 4K",
    "audio_only": "仅音频",
    "min_size": "最小体积",
    "keep_original": "保留原始编码",
    "hdr_priority": "HDR 优先",
    "high_fps": "高帧率优先",
    "manual": "手动选择格式",
}

DOWNLOAD_PRESET_FORMATS = {
    "best_quality": BEST_QUALITY_FMT,
    "best_compat": BEST_COMPAT_FMT,
    "max_1080p": P1080_FMT,
    "max_4k": MAX_4K_FMT,
    "audio_only": AUDIO_FMT,
    "min_size": MIN_SIZE_FMT,
    "keep_original": KEEP_ORIGINAL_FMT,
    "hdr_priority": HDR_PRIORITY_FMT,
    "high_fps": HIGH_FPS_FMT,
}


@dataclass
class YouTubeDownloadProfile:
    format: Optional[str] = None
    sub_lang: Optional[str] = None
    subtitle_mode: str = "none"
    subtitle_langs: str = ""
    subtitle_format: str = ""
    embed_subs: bool = False
    write_subs: bool = True
    speed_limit: int = 0
    retries: int = 3
    retry_interval: int = 0
    sleep_interval: int = 0
    max_sleep_interval: int = 0
    sleep_requests: int = 0
    custom_filename: Optional[str] = None
    preset_key: str = "manual"
    merge_output_format: str = "mp4"
    audio_quality: str = "192"
    embed_thumbnail: bool = True
    embed_metadata: bool = True
    write_thumbnail: bool = False
    write_info_json: bool = False
    write_description: bool = False
    write_chapters: bool = False
    keep_video: bool = False
    h264_compat: bool = False
    use_po_token: bool = False
    download_sections: str = ""
    sponsorblock_enabled: bool = False
    sponsorblock_categories: str = ""
    proxy_url: str = ""
    advanced_args: str = ""
    cookies_mode: str = "file"
    cookies_browser: str = ""
    timeout_idle: int = 300
    timeout_no_progress: int = 600
    socket_timeout: int = 15


@dataclass
class YouTubeBatchEntry:
    video_id: str = ""
    title: str = ""
    url: str = ""
    channel: str = ""
    channel_id: str = ""
    duration: int = 0
    view_count: int = 0
    upload_date: str = ""
    availability: str = "public"
    is_live: bool = False
    was_live: bool = False
    is_shorts: bool = False
    playlist_index: int = 0
    thumbnail: str = ""
    selected: bool = True
    available: bool = True
    reason_unavailable: str = ""

    def get_display_title(self):
        if self.title:
            return self.title
        if self.video_id:
            return f"YouTube-{self.video_id}"
        return "YouTube-未命名条目"


@dataclass
class YouTubeBatchSource:
    source_type: str = BATCH_SOURCE_UNKNOWN
    source_url: str = ""
    source_id: str = ""
    title: str = ""
    channel: str = ""
    channel_id: str = ""
    uploader: str = ""
    uploader_id: str = ""
    availability: str = "public"
    webpage_url: str = ""
    description: str = ""
    thumbnail: str = ""
    item_count: int = 0
    selected_count: int = 0
    unavailable_count: int = 0

    def get_display_name(self):
        if self.title:
            return self.title
        if self.source_type == BATCH_SOURCE_PLAYLIST:
            return "YouTube 播放列表"
        if self.source_type in {BATCH_SOURCE_CHANNEL, BATCH_SOURCE_UPLOADS}:
            return "YouTube 频道"
        return "YouTube 批量来源"


@dataclass
class YouTubeBatchParseResult:
    ok: bool = False
    source: YouTubeBatchSource = field(default_factory=YouTubeBatchSource)
    entries: List[YouTubeBatchEntry] = field(default_factory=list)
    used_cookies: bool = False
    cookies_error: bool = False
    auth_diagnostic: AuthDiagnostic = field(default_factory=AuthDiagnostic)
    error_output: str = ""

    def selected_entries(self):
        return [entry for entry in self.entries if entry.selected and entry.available and entry.url]

    def available_entries(self):
        return [entry for entry in self.entries if entry.available and entry.url]


def normalize_url(url):
    return (url or "").strip()


def _extract_host(url):
    try:
        parsed = urlparse((url or "").strip())
    except Exception:
        return ""
    host = (parsed.netloc or "").strip().lower().rstrip(".")
    if not host:
        return ""
    if "@" in host:
        host = host.split("@", 1)[-1]
    if ":" in host:
        host = host.split(":", 1)[0]
    return host


def detect_url_type(url):
    normalized = normalize_url(url)
    if not normalized:
        return URL_TYPE_UNKNOWN
    host = _extract_host(normalized)
    if not host:
        return URL_TYPE_UNKNOWN
    if host in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}:
        return URL_TYPE_YOUTUBE
    if host in {"bilibili.com", "www.bilibili.com", "m.bilibili.com", "b23.tv"}:
        return URL_TYPE_BILIBILI
    if host in {"vimeo.com", "www.vimeo.com"}:
        return URL_TYPE_VIMEO
    if host in {"soundcloud.com", "www.soundcloud.com"}:
        return URL_TYPE_SOUNDCLOUD
    return URL_TYPE_UNKNOWN


def sanitize_archive_segment(value, fallback="未命名"):
    text = (value or "").strip()
    if not text:
        return fallback
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', text)
    text = re.sub(r'\s+', ' ', text).strip(' .')
    if not text:
        return fallback
    return text[:80]


_TASK_ID_COUNTER = itertools.count(1)


def generate_task_id():
    task_no = ((next(_TASK_ID_COUNTER) - 1) % 999) + 1
    return f"{task_no:03d}"


@dataclass
class YouTubeTaskRecord:
    url: str
    save_path: str
    profile: YouTubeDownloadProfile
    task_type: str = TASK_MODE_YOUTUBE
    source_platform: str = URL_TYPE_YOUTUBE
    url_type: str = URL_TYPE_YOUTUBE
    id: str = field(default_factory=generate_task_id)
    status: str = TASK_STATUS_WAITING
    progress: str = "0%"
    speed: str = "0 M/s"
    process: object = None
    stop_flag: bool = False
    final_title: Optional[str] = None
    needs_cookies: bool = False
    source_type: str = "manual"
    source_name: str = "手动任务"
    source_id: str = ""
    channel_name: str = ""
    channel_id: str = ""
    upload_date: str = ""
    archive_root: str = ""
    archive_subdir: str = ""
    archive_output_path: str = ""
    latest_error_summary: str = ""
    latest_error_detail: str = ""
    add_time: float = field(default_factory=lambda: time.time())
    start_time: Optional[float] = None
    end_time: Optional[float] = None

    def get_display_name(self):
        if self.final_title:
            return self.final_title

        preset_key = getattr(self.profile, "preset_key", "manual")
        preset_labels_en = {
            "best_quality": "Best Quality",
            "best_compat": "Best Compat",
            "max_1080p": "Max 1080p",
            "max_4k": "Max 4K",
            "audio_only": "Audio Only",
            "min_size": "Min Size",
            "keep_original": "Keep Original Codec",
            "hdr_priority": "HDR Priority",
            "high_fps": "High FPS Priority",
            "manual": "Manual Format",
        }
        if preset_key in DOWNLOAD_PRESET_LABELS:
            return f"YouTube-{preset_labels_en.get(preset_key, DOWNLOAD_PRESET_LABELS[preset_key])}"

        fmt = self.profile.format
        if not fmt:
            return "YouTube-默认"
        if fmt == AUDIO_FMT:
            return "YouTube-音频"
        if fmt == P1080_FMT:
            return "YouTube-1080p"
        if fmt == P720_FMT:
            return "YouTube-720p"
        return f"YouTube-{fmt.split('+')[0]}"

    def resolve_archive_subdir(self):
        source_segment = sanitize_archive_segment(self.source_name or self.source_type or "手动任务", "手动任务")
        channel_segment = sanitize_archive_segment(self.channel_name or self.channel_id or "未知频道", "未知频道")
        raw_date = (self.upload_date or "").strip()
        if len(raw_date) == 8 and raw_date.isdigit():
            date_segment = f"{raw_date[0:4]}-{raw_date[4:6]}-{raw_date[6:8]}"
        else:
            date_segment = "unknown-date"
        return os.path.join(channel_segment, source_segment, date_segment)

    def resolve_output_dir(self):
        root_dir = (self.archive_root or self.save_path or "").strip()
        sub_dir = (self.archive_subdir or "").strip()
        if root_dir and sub_dir:
            return os.path.join(root_dir, sub_dir)
        return root_dir
