import os
import threading
import time

from ui.input_validators import sync_output_format_by_preset, validate_format_fetch_request


def _sort_quality_key(item):
    resolution = item.get("resolution") or ""
    height = 0
    if "x" in resolution:
        try:
            height = int(resolution.split("x")[-1])
        except ValueError:
            height = 0
    elif resolution.endswith("p"):
        try:
            height = int(resolution[:-1])
        except ValueError:
            height = 0
    fps = int(item.get("fps") or 0)
    dynamic_range = 1 if item.get("dynamic_range") == "HDR" else 0
    filesize = item.get("filesize_bytes") or 0
    return (height, fps, dynamic_range, filesize)


def _update_format_ui(frame, formats, video_info):
    frame.all_formats = list(formats)
    _update_video_info_ui(frame, video_info)
    refresh_format_view(frame)
    title = video_info.get("title", "未知标题")
    time_str = time.strftime("%H:%M:%S")
    frame.manager.log(f"获取到 {len(formats)} 个格式 | 时间: {time_str} | 标题: {title}")


def _handle_format_fetch_result(frame, format_result):
    if format_result["used_cookies"]:
        frame.format_fetch_used_cookies = True
        frame.manager.log("使用cookies成功获取格式")
    elif not format_result["ok"] and os.path.exists(frame._cookies_file_path):
        frame.manager.log("获取格式失败，请查看错误摘要与诊断信息", "WARN")

    if format_result["cookies_error"]:
        frame.manager.log("[错误]\tCookies可能已失效!", "ERROR")
        frame.manager.log("[提示]\t建议: 重新导出cookies文件 (www.youtube.com_cookies.txt)", "ERROR")
        if hasattr(frame.app, 'notify_cookies_error'):
            frame.app.root.after(0, frame.app.notify_cookies_error)

    if not format_result["ok"]:
        raise RuntimeError(f"获取格式失败: {format_result['error_output']}")

    formats = format_result["formats"]
    video_info = format_result.get("video_info", {})
    frame.app.root.after(0, lambda: _update_format_ui(frame, formats, video_info))


def fetch_formats_async(frame):
    """在后台获取 YouTube 可用格式，并在主线程中回填 UI。"""
    if getattr(frame, "_format_fetch_in_progress", False):
        frame.manager.log("⚠️\t格式获取正在进行中，请勿重复点击", "WARN")
        return

    url = validate_format_fetch_request(frame, frame.url_entry.get("1.0", "end-1c"))
    if not url:
        return

    sync_output_format_by_preset(frame)
    time_str = time.strftime("%H:%M:%S")
    frame.manager.log(f"正在获取 YouTube 可用格式... | 时间: {time_str} | 链接: {url}")
    frame.format_fetch_used_cookies = False
    frame._format_fetch_in_progress = True
    if getattr(frame, "fetch_formats_button", None):
        frame.fetch_formats_button.configure(state="disabled")

    def finish_fetch():
        frame._format_fetch_in_progress = False
        if getattr(frame, "fetch_formats_button", None):
            frame.fetch_formats_button.configure(state="normal")

    def run_fetch():
        try:
            time_str2 = time.strftime("%H:%M:%S")
            frame.manager.log(f"尝试获取格式... | 时间: {time_str2} | 链接: {url}")
            format_result = frame.app.metadata_service.fetch_formats(url)
            _handle_format_fetch_result(frame, format_result)
        except Exception as exc:
            err_msg = str(exc)
            time_str_err = time.strftime("%H:%M:%S")
            frame.app.root.after(0, lambda msg=err_msg, t=time_str_err: frame.manager.log(f"获取格式失败: {msg} | 时间: {t}"))
        finally:
            frame.app.root.after(0, finish_fetch)

    threading.Thread(target=run_fetch, daemon=True).start()


def _sort_size_key(item):
    filesize = item.get("filesize_bytes") or 0
    return (filesize, *_sort_quality_key(item)[:3])


def _apply_format_filters(frame, formats):
    filtered = list(formats)
    if getattr(frame, "filter_mp4_var", None) and frame.filter_mp4_var.get():
        filtered = [item for item in filtered if item.get("ext") == "mp4"]
    if getattr(frame, "filter_with_audio_var", None) and frame.filter_with_audio_var.get():
        filtered = [item for item in filtered if not item.get("is_video_only")]
    if getattr(frame, "filter_60fps_var", None) and frame.filter_60fps_var.get():
        filtered = [item for item in filtered if int(item.get("fps") or 0) >= 50]
    if getattr(frame, "filter_4k_var", None) and frame.filter_4k_var.get():
        filtered = [item for item in filtered if _sort_quality_key(item)[0] >= 2160]
    if getattr(frame, "filter_audio_only_var", None) and frame.filter_audio_only_var.get():
        filtered = [item for item in filtered if item.get("is_audio_only")]

    sort_mode = getattr(frame, "sort_mode_var", None).get().strip() if getattr(frame, "sort_mode_var", None) else "quality_desc"
    if sort_mode == "size_desc":
        filtered.sort(key=_sort_size_key, reverse=True)
    elif sort_mode == "size_asc":
        filtered.sort(key=_sort_size_key)
    elif sort_mode == "quality_asc":
        filtered.sort(key=_sort_quality_key)
    else:
        filtered.sort(key=_sort_quality_key, reverse=True)
    return filtered


def _format_duration(seconds):
    seconds = int(seconds or 0)
    hours, remain = divmod(seconds, 3600)
    minutes, secs = divmod(remain, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _format_views(view_count):
    count = int(view_count or 0)
    return f"{count:,}" if count else "未知"


def _build_format_label(item):
    tags = []
    if item["is_video_only"]:
        tags.append("仅视频")
    elif item["is_audio_only"]:
        tags.append("仅音频")
    else:
        tags.append("含音频")
    if item["needs_merge"]:
        tags.append("需合并")
    tags.append(item["dynamic_range"])
    if item["fps"]:
        tags.append(f"{item['fps']}fps")
    return f"{item['format_id']} | {item['resolution']} | {item['ext']} | {item['filesize']} | {' / '.join(tags)}"


def _update_video_info_ui(frame, video_info):
    frame.video_title_var.set(video_info.get("title") or "未解析")
    
    # 合并所有元数据到一行
    meta_parts = [
        f"ID: {video_info.get('video_id') or '-'}",
        f"频道: {video_info.get('channel') or '-'}",
        f"时长: {_format_duration(video_info.get('duration'))}",
        f"观看: {_format_views(video_info.get('view_count'))}",
        f"上传: {video_info.get('upload_date') or '-'}",
        f"语言: {video_info.get('language') or '未知'}"
    ]
    
    # 补充 Shorts 和 直播状态
    if video_info.get('is_shorts'):
        meta_parts.append("Shorts: 是")
    if video_info.get('was_live'):
        meta_parts.append("直播回放: 是")
        
    frame.video_meta_var.set(" | ".join(meta_parts))


def _populate_format_list(frame, formats):
    frame.format_rows = {}
    for index, item in enumerate(formats):
        frame.format_rows[str(index)] = item

    if formats:
        selected_item = formats[0]
        selected_label = _build_format_label(selected_item)
        frame.selected_format_id_var.set(selected_item["format_id"])
        frame.format_var_combo.set(selected_label)
    else:
        frame.selected_format_id_var.set("")
        frame.format_var_combo.set("")


def refresh_format_view(frame):
    all_formats = list(getattr(frame, "all_formats", []))
    filtered_formats = _apply_format_filters(frame, all_formats)
    frame.current_formats = filtered_formats
    _populate_format_list(frame, filtered_formats)
    frame.format_combo.configure(values=[_build_format_label(item) for item in filtered_formats])

    if not all_formats:
        frame.filter_summary_var.set("尚未获取格式，请先点击“获取分辨率/格式”")
    elif filtered_formats:
        frame.filter_summary_var.set(f"已显示 {len(filtered_formats)} / {len(all_formats)} 个格式")
    else:
        frame.filter_summary_var.set(f"筛选后无可用格式（原始 {len(all_formats)} 个）")
        frame.manager.log("⚠️ 当前筛选条件下没有可用格式，请放宽筛选条件后重试", "WARNING")

    if not filtered_formats:
        frame.selected_format_id_var.set("")
        frame.format_var_combo.set("")
        if getattr(frame, 'format_list_var', None):
            frame.format_list_var.set("")







