import json
import os
import re
import subprocess

from core.auth_models import (
    AUTH_LEVEL_ERROR,
    AUTH_LEVEL_INFO,
    AUTH_LEVEL_WARNING,
    AUTH_REASON_AGE_RESTRICTED,
    AUTH_REASON_BOT_CHECK,
    AUTH_REASON_FORBIDDEN,
    AUTH_REASON_JS_CHALLENGE,
    AUTH_REASON_LOGIN_REQUIRED,
    AUTH_REASON_MEMBERS_ONLY,
    AUTH_REASON_NETWORK,
    AUTH_REASON_NONE,
    AUTH_REASON_PAYMENT_REQUIRED,
    AUTH_REASON_PRIVATE_VIDEO,
    AUTH_REASON_UNKNOWN,
    AuthDiagnostic,
)
from core.youtube_models import (
    BATCH_SOURCE_CHANNEL,
    BATCH_SOURCE_PLAYLIST,
    BATCH_SOURCE_UNKNOWN,
    BATCH_SOURCE_UPLOADS,
    YouTubeBatchEntry,
    YouTubeBatchParseResult,
    YouTubeBatchSource,
)


def detect_auth_diagnostic(error_output):
    raw_output = (error_output or "").strip()
    if not raw_output:
        return AuthDiagnostic(ok=True, summary="未检测到认证问题")

    error_lower = raw_output.lower()
    rules = [
        (
            AUTH_REASON_AGE_RESTRICTED,
            ["confirm your age", "content is age-restricted", "age-restricted"],
            "ERROR",
            "检测到年龄限制内容",
            "请使用已登录且具备观看权限的 cookies，并重新导出 [`www.youtube.com_cookies.txt`](www.youtube.com_cookies.txt)。",
            True,
        ),
        (
            AUTH_REASON_PRIVATE_VIDEO,
            ["video is private", "private video"],
            "ERROR",
            "检测到私有视频或不可公开访问内容",
            "请确认当前账号具备访问权限，并重新导出有效 cookies。",
            True,
        ),
        (
            AUTH_REASON_MEMBERS_ONLY,
            ["members-only", "join this channel"],
            "ERROR",
            "检测到会员专属内容",
            "请确认当前 cookies 对应账号具备会员权限。",
            True,
        ),
        (
            AUTH_REASON_PAYMENT_REQUIRED,
            ["requires payment", "video requires purchase"],
            "ERROR",
            "检测到付费内容",
            "请确认当前账号已购买对应内容。",
            True,
        ),
        (
            AUTH_REASON_LOGIN_REQUIRED,
            [
                "sign in to confirm",
                "login required",
                "authentication required",
                "please sign in",
                "use --cookies-from-browser or --cookies",
                "this content isn't available",
                "login to view this video",
            ],
            "ERROR",
            "检测到需要登录后才能访问",
            "请重新导出已登录账号的 cookies 文件并重试。",
            True,
        ),
        (
            AUTH_REASON_FORBIDDEN,
            [
                "http error 403",
                "forbidden",
                "access denied",
                "requested format is not available",
                "this video is unavailable",
                "video unavailable",
                "not available in your country",
                "geo-restricted",
            ],
            "ERROR",
            "检测到访问受限、地区限制或资源不可用问题",
            "请优先检查 cookies、视频可见性、地区限制与代理设置；若内容本身不可用，则无法通过重试解决。",
            True,
        ),
        (
            AUTH_REASON_JS_CHALLENGE,
            [
                "challenge solving failed",
                "js challenge provider",
                "nsig extraction failed",
                "signature extraction failed",
                "player response could not be decoded",
                "unable to extract initial player response",
                "unable to extract yt initial data",
            ],
            "WARNING",
            "检测到 YouTube JS Challenge / 提取器环境问题",
            "这通常不是 cookies 本身失效，可优先检查 [`yt-dlp.exe`](yt-dlp.exe)、[`deno.exe`](deno.exe) 与当前网络环境。",
            False,
        ),
        (
            AUTH_REASON_BOT_CHECK,
            ["not a bot", "unusual traffic", "to continue, please type the characters"],
            "WARNING",
            "检测到机器人校验或异常流量限制",
            "请稍后重试，必要时更换网络环境，并准备有效 cookies。",
            True,
        ),
        (
            AUTH_REASON_NETWORK,
            [
                "timed out",
                "temporary failure",
                "name resolution",
                "network is unreachable",
                "connection reset",
                "connection aborted",
                "connection refused",
                "remote end closed connection",
                "read timed out",
                "proxy error",
                "proxyconnect",
                "getaddrinfo failed",
                "failed to resolve",
                "ssl",
                "tls",
            ],
            "WARNING",
            "检测到网络连接或代理环境问题",
            "请先检查网络连通性、代理配置与 TLS/SSL 环境，再判断是否需要重新导出 cookies。",
            False,
        ),
    ]

    for category, keywords, level_text, summary, action_hint, is_auth_related in rules:
        if any(keyword in error_lower for keyword in keywords):
            level = AUTH_LEVEL_ERROR if level_text == "ERROR" else AUTH_LEVEL_WARNING
            return AuthDiagnostic(
                ok=False,
                category=category,
                level=level,
                summary=summary,
                detail=raw_output[:500],
                action_hint=action_hint,
                is_auth_related=is_auth_related,
                raw_output=raw_output,
            )

    return AuthDiagnostic(
        ok=False,
        category=AUTH_REASON_UNKNOWN,
        level=AUTH_LEVEL_WARNING,
        summary="标题/元数据获取失败，原因暂未识别",
        detail=raw_output[:500],
        action_hint="请直接查看后续“标题获取原始日志”内容，优先判断是否为链接失效、网络异常、yt-dlp 版本问题或站点风控。",
        is_auth_related=False,
        raw_output=raw_output,
    )


def detect_cookies_error(error_output):
    diagnostic = detect_auth_diagnostic(error_output)
    return (not diagnostic.ok) and diagnostic.is_auth_related


def _safe_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _format_filesize(size_bytes):
    size = _safe_int(size_bytes)
    if size <= 0:
        return "未知"
    units = ["B", "KB", "MB", "GB", "TB"]
    size_float = float(size)
    for unit in units:
        if size_float < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(size_float)} {unit}"
            return f"{size_float:.1f} {unit}"
        size_float /= 1024
    return "未知"


def _build_format_entry(fmt):
    format_id = str(fmt.get("format_id") or "")
    if not format_id:
        return None

    height = _safe_int(fmt.get("height"))
    width = _safe_int(fmt.get("width"))
    fps = _safe_int(fmt.get("fps"))
    ext = fmt.get("ext") or "未知"
    protocol = fmt.get("protocol") or "未知"
    vcodec = fmt.get("vcodec") or "none"
    acodec = fmt.get("acodec") or "none"
    dynamic_range = fmt.get("dynamic_range") or "SDR"
    filesize = fmt.get("filesize") or fmt.get("filesize_approx")
    bitrate = _safe_int(fmt.get("tbr"))

    if protocol.startswith("m3u8") or ext == "mhtml" or format_id.startswith("sb"):
        return None

    resolution = "音频" if vcodec == "none" else (f"{width}x{height}" if width and height else (f"{height}p" if height else "未知"))
    is_video_only = vcodec != "none" and acodec == "none"
    is_audio_only = vcodec == "none" and acodec != "none"
    needs_merge = is_video_only

    return {
        "format_id": format_id,
        "resolution": resolution,
        "height": height,
        "fps": fps,
        "vcodec": vcodec,
        "acodec": acodec,
        "ext": ext,
        "protocol": protocol,
        "filesize": _format_filesize(filesize),
        "filesize_bytes": _safe_int(filesize),
        "dynamic_range": dynamic_range,
        "is_video_only": is_video_only,
        "is_audio_only": is_audio_only,
        "needs_merge": needs_merge,
        "tbr": bitrate,
    }


def _decode_bytes(output_bytes):
    if not output_bytes:
        return ""
    if isinstance(output_bytes, str):
        return output_bytes
    try:
        return output_bytes.decode('utf-8')
    except UnicodeDecodeError:
        try:
            return output_bytes.decode('gbk')
        except UnicodeDecodeError:
            return output_bytes.decode('utf-8', errors='replace')


def _extract_error_text(proc):
    err = proc.stderr if proc.stderr else proc.stdout
    return _decode_bytes(err).strip()


def _run_json_command(base_cmd, cookies_path, timeout, startupinfo):
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.run(
        base_cmd,
        capture_output=True,
        timeout=timeout,
        startupinfo=startupinfo,
        env=env
    )

    used_cookies = False
    if proc.returncode != 0 and cookies_path and os.path.exists(cookies_path):
        proc = subprocess.run(
            base_cmd[:-1] + ["--cookies", cookies_path, base_cmd[-1]],
            capture_output=True,
            timeout=timeout,
            startupinfo=startupinfo,
            env=env
        )
        used_cookies = proc.returncode == 0

    return proc, used_cookies


def _detect_batch_source_type(webpage_url, extractor_key, original_url):
    joined = " ".join([
        (webpage_url or "").lower(),
        (extractor_key or "").lower(),
        (original_url or "").lower(),
    ])
    if "playlist" in joined or "list=" in joined:
        return BATCH_SOURCE_PLAYLIST
    if "/videos" in joined or "/streams" in joined:
        return BATCH_SOURCE_CHANNEL
    if "/@" in joined or "/channel/" in joined or "/c/" in joined or "/user/" in joined:
        return BATCH_SOURCE_UPLOADS
    return BATCH_SOURCE_UNKNOWN


def _build_batch_source(info, source_url):
    entries = info.get("entries") or []
    available_count = 0
    unavailable_count = 0
    for item in entries:
        if not isinstance(item, dict):
            unavailable_count += 1
            continue
        if item.get("id") and (item.get("url") or item.get("webpage_url") or item.get("original_url")):
            available_count += 1
        else:
            unavailable_count += 1

    source_type = _detect_batch_source_type(
        info.get("webpage_url") or "",
        info.get("extractor_key") or info.get("extractor") or "",
        source_url,
    )
    return YouTubeBatchSource(
        source_type=source_type,
        source_url=source_url,
        source_id=info.get("id") or "",
        title=info.get("title") or info.get("playlist_title") or "",
        channel=info.get("channel") or info.get("uploader") or "",
        channel_id=info.get("channel_id") or info.get("uploader_id") or "",
        uploader=info.get("uploader") or "",
        uploader_id=info.get("uploader_id") or "",
        availability=info.get("availability") or "public",
        webpage_url=info.get("webpage_url") or source_url,
        description=info.get("description") or "",
        thumbnail=info.get("thumbnail") or "",
        item_count=_safe_int(info.get("playlist_count") or len(entries)),
        selected_count=available_count,
        unavailable_count=unavailable_count,
    )


def _build_batch_entry(item, default_channel, default_channel_id):
    if not isinstance(item, dict):
        return None

    url = item.get("url") or item.get("webpage_url") or item.get("original_url") or ""
    video_id = item.get("id") or ""
    title = item.get("title") or ""
    channel = item.get("channel") or item.get("uploader") or default_channel or ""
    channel_id = item.get("channel_id") or item.get("uploader_id") or default_channel_id or ""
    availability = item.get("availability") or "public"
    is_live = bool(item.get("is_live"))
    was_live = bool(item.get("was_live"))
    reason_unavailable = ""
    available = bool(video_id and url)

    if not available:
        reason_unavailable = item.get("_type") or "条目不可用"

    return YouTubeBatchEntry(
        video_id=video_id,
        title=title,
        url=url,
        channel=channel,
        channel_id=channel_id,
        duration=_safe_int(item.get("duration")),
        view_count=_safe_int(item.get("view_count")),
        upload_date=item.get("upload_date") or "",
        availability=availability,
        is_live=is_live,
        was_live=was_live,
        is_shorts="/shorts/" in (item.get("webpage_url") or url),
        playlist_index=_safe_int(item.get("playlist_index")),
        thumbnail=item.get("thumbnail") or "",
        selected=available,
        available=available,
        reason_unavailable=reason_unavailable,
    )


def _parse_batch_result(info, source_url, used_cookies, error_output):
    source = _build_batch_source(info, source_url)
    entries = []
    for item in info.get("entries") or []:
        entry = _build_batch_entry(item, source.channel, source.channel_id)
        if entry:
            entries.append(entry)

    diagnostic = detect_auth_diagnostic(error_output)
    source.item_count = max(source.item_count, len(entries))
    source.selected_count = len([item for item in entries if item.selected and item.available])
    source.unavailable_count = len([item for item in entries if not item.available])

    if not entries:
        return YouTubeBatchParseResult(
            ok=False,
            source=source,
            entries=[],
            used_cookies=used_cookies,
            cookies_error=(not diagnostic.ok) and diagnostic.is_auth_related,
            auth_diagnostic=diagnostic,
            error_output=error_output or "未解析到批量条目",
        )

    return YouTubeBatchParseResult(
        ok=bool(source.selected_count),
        source=source,
        entries=entries,
        used_cookies=used_cookies,
        cookies_error=(not diagnostic.ok) and diagnostic.is_auth_related,
        auth_diagnostic=diagnostic,
        error_output="" if source.selected_count else (error_output or "未解析到可用条目"),
    )


class YouTubeMetadataService:
    def __init__(self, yt_dlp_path, cookies_file_path, startupinfo=None):
        self.yt_dlp_path = yt_dlp_path
        self.cookies_file_path = cookies_file_path
        self.startupinfo = startupinfo

    def _json_parse_error_result(self, message, used_cookies=False):
        diagnostic = detect_auth_diagnostic(message)
        return {
            "ok": False,
            "formats": [],
            "video_info": {},
            "used_cookies": used_cookies,
            "cookies_error": (not diagnostic.ok) and diagnostic.is_auth_related,
            "auth_diagnostic": diagnostic,
            "error_output": message[:400],
        }

    def inspect_cookies_status(self):
        exists = bool(self.cookies_file_path and os.path.exists(self.cookies_file_path))
        if exists:
            return {
                "exists": True,
                "summary": "cookies 文件存在",
                "action_hint": "如近期出现登录或 403 问题，可重新导出 [`www.youtube.com_cookies.txt`](www.youtube.com_cookies.txt)。",
            }
        return {
            "exists": False,
            "summary": "未找到 cookies 文件",
            "action_hint": "如需访问登录、年龄限制或会员内容，请导出 [`www.youtube.com_cookies.txt`](www.youtube.com_cookies.txt)。",
        }

    def fetch_title(self, url):
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        title_cmd = [self.yt_dlp_path, "--get-title", "--skip-download", "--no-warnings", url]
        title_proc = subprocess.run(
            title_cmd,
            capture_output=True,
            timeout=30,
            startupinfo=self.startupinfo,
            env=env
        )

        used_cookies = False
        if title_proc.returncode != 0 and os.path.exists(self.cookies_file_path):
            title_cmd_with_cookies = [
                self.yt_dlp_path,
                "--get-title",
                "--skip-download",
                "--no-warnings",
                "--cookies",
                self.cookies_file_path,
                url,
            ]
            title_proc = subprocess.run(
                title_cmd_with_cookies,
                capture_output=True,
                timeout=30,
                startupinfo=self.startupinfo,
                env=env
            )
            used_cookies = title_proc.returncode == 0

        title = None
        if title_proc.returncode == 0 and title_proc.stdout:
            parsed_title = _decode_bytes(title_proc.stdout).strip().split('\n')[0]
            if parsed_title:
                title = parsed_title

        error_output = _extract_error_text(title_proc)
        diagnostic = detect_auth_diagnostic(error_output)
        return {
            "ok": title is not None,
            "title": title,
            "used_cookies": used_cookies,
            "cookies_error": (not diagnostic.ok) and diagnostic.is_auth_related,
            "auth_diagnostic": diagnostic,
            "error_output": error_output or "",
            "returncode": title_proc.returncode,
        }

    def fetch_formats(self, url):
        cmd = [self.yt_dlp_path, "--dump-single-json", "--no-warnings", url]
        proc, used_cookies = _run_json_command(cmd, self.cookies_file_path, 60, self.startupinfo)

        if proc.returncode != 0:
            error_msg = _extract_error_text(proc)
            diagnostic = detect_auth_diagnostic(error_msg)
            return {
                "ok": False,
                "formats": [],
                "video_info": {},
                "used_cookies": used_cookies,
                "cookies_error": (not diagnostic.ok) and diagnostic.is_auth_related,
                "auth_diagnostic": diagnostic,
                "error_output": (error_msg or "")[:200],
            }

        try:
            info = json.loads(_decode_bytes(proc.stdout).strip())
        except Exception as exc:
            return self._json_parse_error_result(f"JSON 解析失败: {exc}", used_cookies=used_cookies)
        video_info = {
            "title": info.get("title") or "",
            "video_id": info.get("id") or "",
            "channel": info.get("channel") or info.get("uploader") or "",
            "channel_id": info.get("channel_id") or info.get("uploader_id") or "",
            "upload_date": info.get("upload_date") or "",
            "duration": _safe_int(info.get("duration")),
            "thumbnail": info.get("thumbnail") or "",
            "view_count": _safe_int(info.get("view_count")),
            "language": info.get("language") or info.get("original_language") or "未知",
            "is_live": bool(info.get("is_live")),
            "was_live": bool(info.get("was_live")),
            "is_shorts": "/shorts/" in (info.get("webpage_url") or url),
            "age_limit": _safe_int(info.get("age_limit")),
            "availability": info.get("availability") or "public",
        }

        formats = []
        for fmt in info.get("formats", []):
            entry = _build_format_entry(fmt)
            if entry:
                formats.append(entry)

        formats.sort(key=lambda item: (item["height"], item["fps"], item["filesize_bytes"]), reverse=True)
        return {
            "ok": bool(formats),
            "formats": formats,
            "video_info": video_info,
            "used_cookies": used_cookies,
            "cookies_error": False,
            "auth_diagnostic": AuthDiagnostic(ok=True, category=AUTH_REASON_NONE, level=AUTH_LEVEL_INFO, summary="格式获取成功"),
            "error_output": "未找到符合条件的格式" if not formats else "",
        }

    def fetch_playlist_entries(self, url):
        cmd = [self.yt_dlp_path, "--dump-single-json", "--flat-playlist", "--no-warnings", url]
        proc, used_cookies = _run_json_command(cmd, self.cookies_file_path, 90, self.startupinfo)
        if proc.returncode != 0:
            error_msg = _extract_error_text(proc)
            diagnostic = detect_auth_diagnostic(error_msg)
            return YouTubeBatchParseResult(
                ok=False,
                used_cookies=used_cookies,
                cookies_error=(not diagnostic.ok) and diagnostic.is_auth_related,
                auth_diagnostic=diagnostic,
                error_output=(error_msg or "")[:400],
            )

        try:
            info = json.loads(_decode_bytes(proc.stdout).strip())
        except Exception as exc:
            message = f"JSON 解析失败: {exc}"
            diagnostic = detect_auth_diagnostic(message)
            return YouTubeBatchParseResult(
                ok=False,
                used_cookies=used_cookies,
                cookies_error=(not diagnostic.ok) and diagnostic.is_auth_related,
                auth_diagnostic=diagnostic,
                error_output=message[:400],
            )
        return _parse_batch_result(info, url, used_cookies, "")

    def fetch_channel_entries(self, url):
        normalized_url = (url or "").strip()
        if normalized_url and not re.search(r"/(videos|streams|shorts|featured)([/?#]|$)", normalized_url):
            normalized_url = normalized_url.rstrip("/") + "/videos"

        cmd = [self.yt_dlp_path, "--dump-single-json", "--flat-playlist", "--playlist-end", "100", "--no-warnings", normalized_url]
        proc, used_cookies = _run_json_command(cmd, self.cookies_file_path, 90, self.startupinfo)
        if proc.returncode != 0:
            error_msg = _extract_error_text(proc)
            diagnostic = detect_auth_diagnostic(error_msg)
            return YouTubeBatchParseResult(
                ok=False,
                used_cookies=used_cookies,
                cookies_error=(not diagnostic.ok) and diagnostic.is_auth_related,
                auth_diagnostic=diagnostic,
                error_output=(error_msg or "")[:400],
            )

        try:
            info = json.loads(_decode_bytes(proc.stdout).strip())
        except Exception as exc:
            message = f"JSON 解析失败: {exc}"
            diagnostic = detect_auth_diagnostic(message)
            return YouTubeBatchParseResult(
                ok=False,
                used_cookies=used_cookies,
                cookies_error=(not diagnostic.ok) and diagnostic.is_auth_related,
                auth_diagnostic=diagnostic,
                error_output=message[:400],
            )
        result = _parse_batch_result(info, normalized_url, used_cookies, "")
        if result.source.source_type == BATCH_SOURCE_UNKNOWN:
            result.source.source_type = BATCH_SOURCE_UPLOADS
        return result
