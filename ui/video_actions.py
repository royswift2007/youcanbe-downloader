import os
import threading
import time

from ui.input_validators import sync_output_format_by_preset, validate_format_fetch_request


def _t(frame, key, fallback=""):
    app = getattr(frame, "app", None)
    getter = getattr(app, "get_text", None)
    if callable(getter):
        try:
            return getter(key, fallback)
        except TypeError:
            return getter(key)
    return fallback or key


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
    if getattr(frame, "format_table", None):
        frame.format_table.selection_remove(frame.format_table.selection())
    title = video_info.get("title", _t(frame, "format_title_unknown", "未知标题"))
    time_str = time.strftime("%H:%M:%S")
    frame.manager.log(_t(frame, "format_fetch_success", "获取到 {count} 个格式 | 时间: {time} | 标题: {title}").format(
        count=len(formats),
        time=time_str,
        title=title,
    ))


def _handle_format_fetch_result(frame, format_result):
    if format_result["used_cookies"]:
        frame.format_fetch_used_cookies = True
        frame.manager.log(_t(frame, "format_fetch_used_cookies", "已使用 cookies 获取格式"))
    elif not format_result["ok"] and os.path.exists(frame._cookies_file_path):
        frame.manager.log(_t(frame, "format_fetch_failed_hint", "格式获取失败，请检查错误摘要与诊断"), "WARN")

    diagnostic = format_result.get("auth_diagnostic")
    if diagnostic:
        frame.app.latest_auth_diagnostic = diagnostic
        cookies_status = getattr(frame.app, "latest_cookies_status", None)
        if cookies_status is not None:
            try:
                cookies_status.update_from_diagnostic(diagnostic, used_cookies=format_result.get("used_cookies", False))
            except Exception:
                pass
        if hasattr(frame.app, 'top_bar'):
            frame.app.root.after(0, frame.app.top_bar.refresh_auth_status)

    if format_result["cookies_error"]:
        frame.manager.log(_t(frame, "format_cookies_error", "[错误]\tCookies 可能失效"), "ERROR")
        frame.manager.log(_t(frame, "format_cookies_hint", "[提示]\t建议启用 Browser Cookies 或重新导出 cookies 文件"), "ERROR")
        if hasattr(frame.app, 'notify_cookies_error'):
            frame.app.root.after(0, lambda diag=diagnostic: frame.app.notify_cookies_error(diag))

    if not format_result["ok"]:
        raise RuntimeError(_t(frame, "format_fetch_failed", "格式获取失败: {error}").format(error=format_result['error_output']))

    formats = format_result["formats"]
    video_info = format_result.get("video_info", {})
    frame.app.root.after(0, lambda: _update_format_ui(frame, formats, video_info))


def fetch_formats_async(frame):
    """在后台获取 YouTube 可用格式，并在主线程中回填 UI。"""
    if getattr(frame, "_format_fetch_in_progress", False):
        frame.manager.log(_t(frame, "format_fetch_in_progress", "格式获取进行中，请稍候"), "WARN")
        return

    url = validate_format_fetch_request(frame, frame.url_entry.get("1.0", "end-1c"))
    if not url:
        return

    sync_output_format_by_preset(frame)
    time_str = time.strftime("%H:%M:%S")
    frame.manager.log(_t(frame, "format_fetch_start", "开始获取格式 | 时间: {time} | URL: {url}").format(time=time_str, url=url))
    frame.format_fetch_used_cookies = False
    frame._format_fetch_in_progress = True
    if getattr(frame, "fetch_formats_button", None):
        frame.fetch_formats_button.configure(state="disabled")
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
            frame.manager.log(_t(frame, "format_fetch_try", "尝试获取格式 | 时间: {time} | URL: {url}").format(time=time_str2, url=url))
            use_po_token = getattr(frame, "use_po_token_var", None).get() if getattr(frame, "use_po_token_var", None) else False
            format_result = frame.app.metadata_service.fetch_formats(url, use_po_token=use_po_token)
            _handle_format_fetch_result(frame, format_result)
        except Exception as exc:
            err_msg = str(exc)
            time_str_err = time.strftime("%H:%M:%S")
            frame.app.root.after(0, lambda msg=err_msg, t=time_str_err: frame.manager.log(
                _t(frame, "format_fetch_fail_log", "格式获取失败: {error} | 时间: {time}").format(error=msg, time=t)
            ))
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


def _format_views(frame, view_count):
    count = int(view_count or 0)
    if count:
        return f"{count:,}"
    return _t(frame, "format_view_unknown", "未知")


def _build_format_label(frame, item):
    tags = []
    if item["is_video_only"]:
        tags.append(_t(frame, "format_tag_video_only", "仅视频"))
    elif item["is_audio_only"]:
        tags.append(_t(frame, "format_tag_audio_only", "仅音频"))
    else:
        tags.append(_t(frame, "format_tag_with_audio", "含音频"))
    if item["needs_merge"]:
        tags.append(_t(frame, "format_tag_needs_merge", "需合并"))
    tags.append(item["dynamic_range"])
    if item["fps"]:
        tags.append(_t(frame, "format_tag_fps", "{fps}fps").format(fps=item['fps']))
    return f"{item['format_id']} | {item['resolution']} | {item['ext']} | {item['filesize']} | {' / '.join(tags)}"


def _update_video_info_ui(frame, video_info):
    frame.video_title_var.set(video_info.get("title") or _t(frame, "video_info_unparsed", "未解析"))

    # 合并所有元数据到一行
    meta_parts = [
        f"{_t(frame, 'video_meta_id', 'ID')}: {video_info.get('video_id') or '-'}",
        f"{_t(frame, 'video_meta_channel', '频道')}: {video_info.get('channel') or '-'}",
        f"{_t(frame, 'video_meta_duration', '时长')}: {_format_duration(video_info.get('duration'))}",
        f"{_t(frame, 'video_meta_views', '观看')}: {_format_views(frame, video_info.get('view_count'))}",
        f"{_t(frame, 'video_meta_upload', '上传')}: {video_info.get('upload_date') or '-'}",
        f"{_t(frame, 'video_meta_lang', '语言')}: {video_info.get('language') or _t(frame, 'video_meta_lang_unknown', '未知')}"
    ]

    # 补充 Shorts 和 直播状态
    if video_info.get('is_shorts'):
        meta_parts.append(_t(frame, "video_meta_shorts_yes", "Shorts: 是"))
    if video_info.get('was_live'):
        meta_parts.append(_t(frame, "video_meta_live_yes", "直播回放: 是"))

    frame.video_meta_var.set(" | ".join(meta_parts))


def _populate_format_list(frame, formats):
    frame.format_rows = {}
    if getattr(frame, "format_table", None):
        for child in frame.format_table.get_children():
            frame.format_table.delete(child)

    for index, item in enumerate(formats):
        row_id = str(index)
        label = _build_format_label(frame, item)
        entry = dict(item)
        entry["label"] = label
        frame.format_rows[row_id] = entry
        if getattr(frame, "format_table", None):
            frame.format_table.insert(
                "",
                "end",
                iid=row_id,
                values=(
                    entry.get("format_id", ""),
                    entry.get("ext", ""),
                    entry.get("resolution", ""),
                    entry.get("fps", ""),
                    entry.get("vcodec", ""),
                    entry.get("acodec", ""),
                    entry.get("protocol", ""),
                    entry.get("filesize", ""),
                    entry.get("dynamic_range", ""),
                    entry.get("note", ""),
                ),
            )

    if formats:
        selected_item = formats[0]
        selected_label = _build_format_label(frame, selected_item)
        frame.selected_format_id_var.set(selected_item["format_id"])
        frame.format_var_combo.set(selected_label)
        if getattr(frame, "selected_format_label_var", None):
            frame.selected_format_label_var.set(selected_label)
        if getattr(frame, "format_table", None):
            frame.format_table.selection_set("0")
    else:
        frame.selected_format_id_var.set("")
        frame.format_var_combo.set("")
        if getattr(frame, "selected_format_label_var", None):
            frame.selected_format_label_var.set(_t(frame, "single_selected_format_none", "未选择"))


def refresh_format_view(frame):
    all_formats = list(getattr(frame, "all_formats", []))
    filtered_formats = _apply_format_filters(frame, all_formats)
    frame.current_formats = filtered_formats
    _populate_format_list(frame, filtered_formats)

    if not all_formats:
        frame.filter_summary_var.set(_t(frame, "format_filter_summary_need_fetch", "尚未获取格式，请先点击“获取分辨率/格式”"))
    elif filtered_formats:
        frame.filter_summary_var.set(_t(frame, "format_filter_summary_some", "已显示 {shown} / {total} 个格式").format(
            shown=len(filtered_formats),
            total=len(all_formats),
        ))
    else:
        frame.filter_summary_var.set(_t(frame, "format_filter_summary_none", "筛选后无可用格式（原始 {total} 个）").format(total=len(all_formats)))
        frame.manager.log(_t(frame, "format_filter_summary_none_warn", "⚠️ 无匹配格式，请放宽筛选条件"), "WARNING")

    if not filtered_formats:
        frame.selected_format_id_var.set("")
        frame.format_var_combo.set("")
        if getattr(frame, "selected_format_label_var", None):
            frame.selected_format_label_var.set(_t(frame, "single_selected_format_none", "未选择"))
        if getattr(frame, 'format_list_var', None):
            frame.format_list_var.set("")







