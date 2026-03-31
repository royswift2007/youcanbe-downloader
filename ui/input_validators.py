import re
from urllib.parse import urlparse

from core.advanced_args_policy import parse_and_validate_advanced_args
from core.youtube_models import (
    DOWNLOAD_PRESET_FORMATS,
    P1080_FMT,
    TASK_MODE_GENERIC,
    TASK_MODE_YOUTUBE,
    URL_TYPE_UNKNOWN,
    URL_TYPE_YOUTUBE,
    YouTubeDownloadProfile,
    YouTubeTaskRecord,
    detect_url_type,
)


INVALID_FILENAME_CHARS = r'\/:*?"<>|'
AUDIO_OUTPUT_FORMATS = ("m4a", "mp3", "opus", "wav", "flac")
VIDEO_OUTPUT_FORMATS = ("mp4", "mkv")
BROWSER_COOKIES_CHOICES = ("chrome", "edge", "firefox")
TIME_RANGE_SEPARATOR = "-"
_TIME_CODE_RE = re.compile(r"^(?:\d{1,2}:)?\d{1,2}:\d{2}$")
_WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
}
_MAX_FILENAME_LENGTH = 120


def _t(frame, key, fallback=""):
    app = getattr(frame, "app", None)
    getter = getattr(app, "get_text", None)
    if callable(getter):
        try:
            return getter(key, fallback)
        except TypeError:
            return getter(key)
    return fallback or key


def _get_selected_preset_key(frame):
    return getattr(frame, "preset_var", None).get().strip() if getattr(frame, "preset_var", None) else "manual"


def _show_input_warning(frame, message):
    frame.manager.log(_t(frame, "input_invalid_fallback", "输入值无效，已回退默认值: {message}").format(message=message), "WARN")
    frame.app.SilentMessagebox.showwarning(_t(frame, "common_notice", "提示"), message)


def _get_video_output_formats(frame):
    values = getattr(frame, "video_output_formats", None)
    if values:
        return tuple(values)
    return VIDEO_OUTPUT_FORMATS


def _is_time_code(value):
    return bool(_TIME_CODE_RE.match(value or ""))


def _normalize_download_sections(value):
    raw = (value or "").strip()
    if not raw:
        return ""

    if TIME_RANGE_SEPARATOR not in raw:
        return ""

    start, end = [part.strip() for part in raw.split(TIME_RANGE_SEPARATOR, 1)]
    if not start or not end:
        return ""
    if not _is_time_code(start) or not _is_time_code(end):
        return ""
    return f"*{start}-{end}"


def _parse_and_validate_url(url, youtube_only=False):
    normalized = (url or "").strip()
    if not normalized:
        return "", "empty"

    try:
        parsed = urlparse(normalized)
    except Exception:
        return "", "parse"

    scheme = (parsed.scheme or "").lower()
    if scheme not in {"http", "https"}:
        return "", "scheme"

    host = (parsed.netloc or "").strip().lower().rstrip(".")
    if not host:
        return "", "host"
    if "@" in host:
        host = host.split("@", 1)[-1]
    if ":" in host:
        host = host.split(":", 1)[0]
    if not host:
        return "", "host"

    if youtube_only:
        allowed_hosts = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}
        if host not in allowed_hosts:
            return "", "domain"

    return normalized, ""


def _coerce_int_input(frame, var_name, default, minimum=None, maximum=None, label=None):
    variable = getattr(frame, var_name, None)
    if variable is None:
        return default

    label_text = label or _t(frame, "input_label_default", "数值")
    raw_value = str(variable.get()).strip()
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        variable.set(default)
        _show_input_warning(
            frame,
            _t(frame, "input_value_invalid", "{label}输入无效，已自动恢复为 {default}").format(label=label_text, default=default),
        )
        return default

    if minimum is not None and value < minimum:
        variable.set(default)
        _show_input_warning(
            frame,
            _t(frame, "input_value_too_small", "{label}不能小于 {minimum}，已自动恢复为 {default}").format(
                label=label_text,
                minimum=minimum,
                default=default,
            ),
        )
        return default

    if maximum is not None and value > maximum:
        variable.set(default)
        _show_input_warning(
            frame,
            _t(frame, "input_value_too_large", "{label}不能大于 {maximum}，已自动恢复为 {default}").format(
                label=label_text,
                maximum=maximum,
                default=default,
            ),
        )
        return default

    return value


def _get_text_value(frame, attr_name, default=""):
    var = getattr(frame, attr_name, None)
    if not var:
        return default
    return var.get().strip()


def _get_bool_value(frame, attr_name, default=False):
    var = getattr(frame, attr_name, None)
    if not var:
        return default
    return bool(var.get())


def _get_format_value(frame):
    format_widget = getattr(frame, "format_var_combo", None)
    format_value = format_widget.get().strip() if format_widget else ""
    if not format_value:
        selected_var = getattr(frame, "selected_format_id_var", None)
        format_value = selected_var.get().strip() if selected_var else ""
    return format_value or P1080_FMT


def _normalize_cookies_settings(frame, cookies_mode, cookies_browser):
    if cookies_mode == "browser" and not cookies_browser:
        _show_input_warning(frame, _t(frame, "input_warn_browser_missing", "已选择 browser cookies，但未填写浏览器名称"))
        return "file", ""
    if cookies_mode == "browser" and cookies_browser not in BROWSER_COOKIES_CHOICES:
        _show_input_warning(frame, _t(frame, "input_warn_browser_invalid", "Browser Cookies 仅支持 Chrome/Edge/Firefox，已回退为文件模式"))
        return "file", ""
    return cookies_mode, cookies_browser


def _resolve_download_sections(frame, raw_value):
    normalized = _normalize_download_sections(raw_value)
    if raw_value and not normalized:
        _show_input_warning(frame, _t(frame, "input_warn_sections_invalid", "区段格式无效，请使用 HH:MM:SS-MM:SS 或 MM:SS-MM:SS"))
        return ""
    return normalized


def _build_profile_inputs(frame):
    return {
        "format_value": _get_format_value(frame),
        "custom_filename": _get_text_value(frame, "custom_filename_var"),
        "retries": _coerce_int_input(
            frame,
            "retry_var",
            _coerce_int_input(frame.app, "download_retry_var", 3, minimum=0, maximum=10, label=_t(frame, "input_label_retries", "重试次数")) if getattr(frame, "app", None) and getattr(frame.app, "download_retry_var", None) else 3,
            minimum=0,
            maximum=10,
            label=_t(frame, "input_label_retries", "重试次数"),
        ),
        "retry_interval": _coerce_int_input(frame, "retry_interval_var", 0, minimum=0, maximum=300, label=_t(frame, "input_label_retry_interval", "重试间隔")),
        "sleep_interval": _coerce_int_input(frame, "sleep_interval_var", 0, minimum=0, maximum=60, label=_t(frame, "input_label_sleep_interval", "请求间隔")),
        "max_sleep_interval": _coerce_int_input(frame, "max_sleep_interval_var", 0, minimum=0, maximum=120, label=_t(frame, "input_label_max_sleep_interval", "最大请求间隔")),
        "sleep_requests": _coerce_int_input(frame, "sleep_requests_var", 0, minimum=0, maximum=30, label=_t(frame, "input_label_sleep_requests", "API请求间隔")),
        "speed_limit": _coerce_int_input(
            frame,
            "speedlimit_var",
            _coerce_int_input(frame.app, "download_speed_limit_var", 0, minimum=0, maximum=100, label=_t(frame, "input_label_speed_limit", "限速")) if getattr(frame, "app", None) and getattr(frame.app, "download_speed_limit_var", None) else 0,
            minimum=0,
            maximum=100,
            label=_t(frame, "input_label_speed_limit", "限速"),
        ),
        "concurrent": _coerce_int_input(
            frame,
            "concurrent_var",
            _coerce_int_input(frame.app, "download_concurrent_var", 1, minimum=1, maximum=10, label=_t(frame, "input_label_concurrency", "并发数")) if getattr(frame, "app", None) and getattr(frame.app, "download_concurrent_var", None) else 1,
            minimum=1,
            maximum=10,
            label=_t(frame, "input_label_concurrency", "并发数"),
        ),
        "preset_key": _get_selected_preset_key(frame),
        "output_format": _get_text_value(frame, "output_format_var", default="mp4"),
        "audio_quality": _get_text_value(frame, "audio_quality_var", default="192"),
        "embed_thumbnail": _get_bool_value(frame, "embed_thumbnail_var", default=True),
        "embed_metadata": _get_bool_value(frame, "embed_metadata_var", default=True),
        "write_thumbnail": _get_bool_value(frame, "write_thumbnail_var", default=False),
        "write_info_json": _get_bool_value(frame, "write_info_json_var", default=False),
        "write_description": _get_bool_value(frame, "write_description_var", default=False),
        "write_chapters": _get_bool_value(frame, "write_chapters_var", default=False),
        "keep_video": _get_bool_value(frame, "keep_video_var", default=False),
        "h264_compat": _get_bool_value(frame, "h264_compat_var", default=False),
        "use_po_token": _get_bool_value(frame, "use_po_token_var", default=False),
        "download_sections_raw": _get_text_value(frame, "download_sections_var"),
        "sponsorblock_enabled": _get_bool_value(frame, "sponsorblock_enabled_var", default=False),
        "sponsorblock_categories": _get_text_value(frame, "sponsorblock_categories_var"),
        "proxy_url": _get_text_value(frame, "proxy_url_var"),
        "advanced_args": _get_text_value(frame, "advanced_args_var"),
        "cookies_mode": _get_text_value(frame, "cookies_mode_var", default="file"),
        "cookies_browser": _get_text_value(frame, "cookies_browser_var").lower(),
        "subtitle_mode": _get_text_value(frame, "subtitle_mode_var", default="none"),
        "subtitle_langs": _get_text_value(frame, "subtitle_langs_var"),
        "subtitle_format": _get_text_value(frame, "subtitle_format_var"),
        "embed_subs": _get_bool_value(frame, "embed_subs_var", default=False),
        "write_subs": _get_bool_value(frame, "write_subs_var", default=True),
    }


def build_profile_from_input(frame):
    """根据输入页控件状态构建下载配置。"""
    data = _build_profile_inputs(frame)
    download_sections = _resolve_download_sections(frame, data["download_sections_raw"])
    cookies_mode, cookies_browser = _normalize_cookies_settings(
        frame,
        data["cookies_mode"],
        data["cookies_browser"],
    )
    sponsorblock_categories = data["sponsorblock_categories"] or ("sponsor" if data["sponsorblock_enabled"] else "")

    frame.manager.max_concurrent = data["concurrent"]

    return YouTubeDownloadProfile(
        format=data["format_value"],
        subtitle_mode=data["subtitle_mode"] or "none",
        subtitle_langs=data["subtitle_langs"],
        subtitle_format=data["subtitle_format"],
        embed_subs=data["embed_subs"],
        write_subs=data["write_subs"],
        retries=data["retries"],
        retry_interval=data["retry_interval"],
        sleep_interval=data["sleep_interval"],
        max_sleep_interval=data["max_sleep_interval"],
        sleep_requests=data["sleep_requests"],
        speed_limit=data["speed_limit"],
        custom_filename=data["custom_filename"],
        preset_key=data["preset_key"] or "manual",
        merge_output_format=data["output_format"] or "mp4",
        audio_quality=data["audio_quality"] or "192",
        embed_thumbnail=data["embed_thumbnail"],
        embed_metadata=data["embed_metadata"],
        write_thumbnail=data["write_thumbnail"],
        write_info_json=data["write_info_json"],
        write_description=data["write_description"],
        write_chapters=data["write_chapters"],
        keep_video=data["keep_video"],
        h264_compat=data["h264_compat"],
        use_po_token=data["use_po_token"],
        download_sections=download_sections,
        sponsorblock_enabled=data["sponsorblock_enabled"],
        sponsorblock_categories=sponsorblock_categories,
        proxy_url=data["proxy_url"],
        advanced_args=data["advanced_args"],
        cookies_mode=cookies_mode,
        cookies_browser=cookies_browser,
        timeout_idle=300,
        timeout_no_progress=600,
        socket_timeout=15,
    )


def validate_proxy_url(frame, proxy_url):
    if not proxy_url:
        return True
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", proxy_url):
        _show_input_warning(frame, _t(frame, "input_warn_proxy_invalid", "代理格式无效，请包含协议头，例如 http:// 或 socks5://"))
        return False
    return True


def validate_advanced_args(frame, advanced_args):
    if not advanced_args:
        return True
    _, error_message = parse_and_validate_advanced_args(advanced_args)
    if error_message:
        _show_input_warning(
            frame,
            _t(frame, "input_warn_advanced_conflicts", "高级参数包含冲突项: {items}").format(items=error_message),
        )
        return False
    return True


def validate_youtube_url(frame, url):
    """校验输入链接是否为可支持的 YouTube 链接。"""
    normalized, reason = _parse_and_validate_url(url, youtube_only=True)
    if not normalized:
        message_key = "input_warn_youtube_required" if reason == "empty" else "input_warn_youtube_only"
        message_fallback = "请输入 YouTube URL" if reason == "empty" else "当前版本仅支持 YouTube 链接"
        frame.app.SilentMessagebox.showwarning(
            _t(frame, "common_notice", "提示"),
            _t(frame, message_key, message_fallback),
        )
        return False
    return detect_youtube_url(frame, normalized) == URL_TYPE_YOUTUBE


def validate_generic_url(frame, url):
    normalized, reason = _parse_and_validate_url(url, youtube_only=False)
    if not normalized:
        message = _t(frame, "input_warn_download_url", "请输入下载链接") if reason == "empty" else _t(
            frame,
            "input_warn_url_invalid",
            "下载链接格式无效，仅支持 http/https 且必须包含域名",
        )
        frame.app.SilentMessagebox.showwarning(
            _t(frame, "common_notice", "提示"),
            message,
        )
        return False
    frame.detected_url_type = detect_url_type(normalized)
    return True


def detect_youtube_url(frame, url):
    """检测并记录当前输入链接的类型。"""
    normalized_url = (url or '').strip()
    if not normalized_url:
        frame.detected_url_type = None
        return None

    detected = frame.app.detect_video_url_type(normalized_url)
    frame.detected_url_type = detected
    return detected


def validate_custom_filename(frame, custom_filename):
    """校验自定义文件名是否包含非法字符。"""
    if not custom_filename:
        return True

    stripped = custom_filename.strip()
    if stripped != custom_filename:
        frame.app.SilentMessagebox.showerror(
            _t(frame, "common_error", "错误"),
            _t(frame, "input_warn_filename_trailing", "文件名不能以空格开头或结尾"),
        )
        return False

    if custom_filename.endswith("."):
        frame.app.SilentMessagebox.showerror(
            _t(frame, "common_error", "错误"),
            _t(frame, "input_warn_filename_trailing_dot", "文件名不能以点号结尾"),
        )
        return False

    if len(custom_filename) > _MAX_FILENAME_LENGTH:
        frame.app.SilentMessagebox.showerror(
            _t(frame, "common_error", "错误"),
            _t(frame, "input_warn_filename_too_long", "文件名过长（最多 {max_len} 字符）").format(max_len=_MAX_FILENAME_LENGTH),
        )
        return False

    upper_name = custom_filename.upper()
    if upper_name in _WINDOWS_RESERVED_NAMES:
        frame.app.SilentMessagebox.showerror(
            _t(frame, "common_error", "错误"),
            _t(frame, "input_warn_filename_reserved", "文件名为系统保留名，请更换"),
        )
        return False

    if ".." in custom_filename or "/" in custom_filename or "\\" in custom_filename:
        frame.app.SilentMessagebox.showerror(
            _t(frame, "common_error", "错误"),
            _t(frame, "input_warn_filename_path", "文件名不能包含路径分隔符或 .."),
        )
        return False

    if any(ord(ch) < 32 for ch in custom_filename):
        frame.app.SilentMessagebox.showerror(
            _t(frame, "common_error", "错误"),
            _t(frame, "input_warn_filename_control", "文件名不能包含控制字符"),
        )
        return False

    if any(char in custom_filename for char in INVALID_FILENAME_CHARS):
        frame.manager.log(
            _t(frame, "input_log_filename_invalid", "❌ 添加任务失败: 文件名包含非法字符 {chars}").format(chars=INVALID_FILENAME_CHARS),
            "ERROR",
        )
        frame.app.SilentMessagebox.showerror(
            _t(frame, "common_error", "错误"),
            _t(frame, "input_warn_filename_invalid", "文件名不能包含以下字符:\n{chars}").format(chars=INVALID_FILENAME_CHARS),
        )
        return False

    frame.manager.log(_t(frame, "input_log_filename_used", "[完成] 将使用自定义文件名: {name}").format(name=custom_filename))
    return True


def create_task_record(frame, url, profile, task_type=TASK_MODE_YOUTUBE):
    """创建任务记录对象。"""
    url_type = detect_youtube_url(frame, url)
    task = YouTubeTaskRecord(
        url=url,
        save_path=frame.shared_save_dir_var.get(),
        profile=profile,
        task_type=task_type,
        source_platform=URL_TYPE_YOUTUBE,
        url_type=url_type or URL_TYPE_UNKNOWN,
    )
    if not getattr(profile, "custom_filename", ""):
        title = frame.video_title_var.get().strip() if getattr(frame, "video_title_var", None) else ""
        unparsed_title = frame.app.get_text("single_info_unparsed") if getattr(frame, "app", None) else ""
        generic_title = frame.app.get_text("single_generic_title") if getattr(frame, "app", None) else ""
        if title and title not in {unparsed_title, generic_title}:
            task.final_title = title
    return task


def get_selected_format_id(frame):
    """返回当前选中的格式 ID。"""
    selected = getattr(frame, "selected_format_id_var", None)
    if selected:
        format_id = selected.get().strip()
        if format_id:
            return format_id

    fmt_choice = frame.format_var_combo.get().strip() if getattr(frame, "format_var_combo", None) else ""
    if not fmt_choice:
        frame.app.SilentMessagebox.showwarning(
            _t(frame, "common_notice", "提示"),
            _t(frame, "input_warn_format_missing", "请先获取并选择格式"),
        )
        return None
    return fmt_choice.split('|', 1)[0].strip()


def get_selected_preset_format(frame):
    preset_key = _get_selected_preset_key(frame)
    if preset_key and preset_key != "manual":
        return DOWNLOAD_PRESET_FORMATS.get(preset_key)
    return None


def get_selected_output_format(frame, preset_key):
    raw_value = getattr(frame, "output_format_var", None).get().strip() if getattr(frame, "output_format_var", None) else "mp4"
    if preset_key == "audio_only":
        return raw_value if raw_value in AUDIO_OUTPUT_FORMATS else "m4a"
    video_output_formats = _get_video_output_formats(frame)
    return raw_value if raw_value in video_output_formats else "mp4"


def sync_output_format_by_preset(frame):
    preset_key = _get_selected_preset_key(frame)
    if not getattr(frame, "output_format_var", None):
        return preset_key

    if preset_key == "audio_only":
        frame.output_format_combo.configure(values=AUDIO_OUTPUT_FORMATS)
        if frame.output_format_var.get().strip() not in AUDIO_OUTPUT_FORMATS:
            frame.output_format_var.set("m4a")
    else:
        video_output_formats = _get_video_output_formats(frame)
        frame.output_format_combo.configure(values=video_output_formats)
        if frame.output_format_var.get().strip() not in video_output_formats:
            frame.output_format_var.set("mp4")
    return preset_key


def validate_output_format_compatibility(frame):
    preset_key = _get_selected_preset_key(frame)
    if preset_key == "audio_only":
        return True

    output_format = get_selected_output_format(frame, preset_key)
    h264_compat = _get_bool_value(frame, "h264_compat_var", default=False)
    if output_format == "webm" and h264_compat:
        _show_input_warning(
            frame,
            _t(
                frame,
                "input_warn_webm_h264_conflict",
                "webm output does not support H.264 compatibility transcoding. Use mp4/mkv or disable H.264 compatibility.",
            ),
        )
        return False
    return True


def validate_download_sections(frame, raw_value):
    if not raw_value:
        return True
    normalized = _normalize_download_sections(raw_value)
    if not normalized:
        _show_input_warning(frame, _t(frame, "input_warn_sections_invalid", "区段格式无效，请使用 HH:MM:SS-MM:SS 或 MM:SS-MM:SS"))
        return False
    return True


def apply_task_save_path(frame, task):
    """为任务写入当前保存目录。"""
    task.save_path = frame.shared_save_dir_var.get()
    return task


def apply_task_cookies_requirement(frame, task):
    """根据格式获取阶段的状态为任务标记 cookies 需求。"""
    if frame.format_fetch_used_cookies:
        task.needs_cookies = True
        frame.manager.log(_t(frame, "input_log_cookies_required", "[信息] 此任务将使用cookies下载"))
    return task


def validate_format_fetch_request(frame, url):
    """校验“获取格式”请求是否满足基本条件。"""
    normalized_url = (url or '').strip()
    if not normalized_url:
        frame.app.root.after(
            0,
            lambda: frame.app.SilentMessagebox.showwarning(
                _t(frame, "common_notice", "提示"),
                _t(frame, "input_warn_youtube_required", "请输入 YouTube URL"),
            ),
        )
        return None

    detected = detect_youtube_url(frame, normalized_url)
    if detected != URL_TYPE_YOUTUBE:
        frame.app.root.after(
            0,
            lambda: frame.app.SilentMessagebox.showwarning(
                _t(frame, "common_notice", "提示"),
                _t(frame, "input_warn_youtube_only", "当前版本仅支持 YouTube 链接"),
            ),
        )
        return None

    return normalized_url


def prepare_generic_task(frame, url):
    """构建 Generic 模式下载任务。"""
    preset_key = sync_output_format_by_preset(frame)
    preset_format = get_selected_preset_format(frame)
    profile = build_profile_from_input(frame)
    profile.preset_key = preset_key or "manual"
    profile.merge_output_format = get_selected_output_format(frame, profile.preset_key)

    if preset_format:
        profile.format = preset_format
    else:
        if not profile.format:
            profile.format = ""

    task = create_task_record(frame, url, profile, task_type=TASK_MODE_GENERIC)
    detected_type = detect_url_type(url)
    task.source_platform = detected_type or URL_TYPE_UNKNOWN
    task.url_type = detected_type or URL_TYPE_UNKNOWN
    apply_task_save_path(frame, task)
    apply_task_cookies_requirement(frame, task)
    return task


def prepare_standard_task(frame, url):
    """构建标准格式下载任务。"""
    preset_key = sync_output_format_by_preset(frame)
    preset_format = get_selected_preset_format(frame)
    profile = build_profile_from_input(frame)
    profile.preset_key = preset_key or "manual"
    profile.merge_output_format = get_selected_output_format(frame, profile.preset_key)

    if preset_format:
        profile.format = preset_format
    else:
        format_id = get_selected_format_id(frame)
        if not format_id:
            return None
        profile.format = f"{format_id}+bestaudio[ext=m4a]"

    task = create_task_record(frame, url, profile)
    apply_task_save_path(frame, task)
    apply_task_cookies_requirement(frame, task)
    return task


def prepare_direct_task(frame, url):
    """构建直接下载任务。"""
    preset_key = sync_output_format_by_preset(frame)
    profile = build_profile_from_input(frame)
    profile.preset_key = preset_key or "manual"
    preset_format = get_selected_preset_format(frame)
    if preset_format:
        profile.format = preset_format
    else:
        format_id = get_selected_format_id(frame)
        if not format_id:
            return None
        profile.format = f"{format_id}+bestaudio[ext=m4a]"
    profile.merge_output_format = get_selected_output_format(frame, profile.preset_key)
    task = create_task_record(frame, url, profile)
    apply_task_save_path(frame, task)
    apply_task_cookies_requirement(frame, task)
    return task
