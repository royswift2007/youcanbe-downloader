import json
import logging
import os
import sqlite3
import threading
import time
from contextlib import contextmanager

from core.settings import write_json_atomic

logger = logging.getLogger(__name__)

STATUS_SUCCESS = "完成"
STATUS_FAILED = "失败"
SOURCE_TYPE_DEFAULT = "manual"
SOURCE_NAME_DEFAULT = "手动任务"
SOURCE_PLATFORM_DEFAULT = "youtube"
URL_TYPE_UNKNOWN = "unknown"
HISTORY_JSON_LIMIT = 100


class YouTubeHistoryRepository:
    def __init__(self, history_file, db_path=None):
        self.history_file = history_file
        if db_path:
            self.db_path = db_path
        else:
            base_dir = os.path.dirname(os.path.abspath(history_file)) or "."
            self.db_path = os.path.join(base_dir, "download_history_ytdlp.sqlite3")
        self.db_available = False
        self.init_error = ""
        self._json_lock = threading.Lock()
        self._db_retry_count = 3
        self._db_retry_delay = 0.15
        self._init_db()

    @contextmanager
    def _get_conn(self):
        """统一 SQLite 连接上下文：正常退出 commit，异常不 commit，始终 close。"""
        conn = sqlite3.connect(self.db_path, timeout=2.0)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self):
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
            with self._get_conn() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS youtube_download_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        task_id TEXT,
                        video_id TEXT,
                        playlist_id TEXT,
                        channel_id TEXT,
                        url TEXT NOT NULL,
                        task_type TEXT,
                        url_type TEXT,
                        status TEXT NOT NULL,
                        output_path TEXT,
                        archive_subdir TEXT,
                        source_type TEXT,
                        source_name TEXT,
                        format TEXT,
                        final_title TEXT,
                        used_cookies INTEGER DEFAULT 0,
                        failure_stage TEXT,
                        failure_summary TEXT,
                        failure_detail TEXT,
                        return_code INTEGER,
                        created_at TEXT NOT NULL,
                        source TEXT DEFAULT 'youtube',
                        sub_lang TEXT,
                        retries INTEGER,
                        custom_filename TEXT,
                        preset_key TEXT,
                        merge_output_format TEXT,
                        audio_quality TEXT,
                        speed_limit TEXT
                    )
                    """
                )
                existing_columns = {
                    row[1]
                    for row in conn.execute("PRAGMA table_info(youtube_download_history)").fetchall()
                }
                profile_column_defaults = {
                    "archive_subdir": "TEXT",
                    "source_type": "TEXT",
                    "source_name": "TEXT",
                    "url_type": "TEXT",
                    "failure_detail": "TEXT",
                    "sub_lang": "TEXT",
                    "retries": "INTEGER",
                    "custom_filename": "TEXT",
                    "preset_key": "TEXT",
                    "merge_output_format": "TEXT",
                    "audio_quality": "TEXT",
                    "speed_limit": "TEXT",
                }
                for column_name, column_type in profile_column_defaults.items():
                    if column_name not in existing_columns:
                        conn.execute(f"ALTER TABLE youtube_download_history ADD COLUMN {column_name} {column_type}")
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_youtube_history_created_at ON youtube_download_history(created_at DESC)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_youtube_history_video_id ON youtube_download_history(video_id)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_youtube_history_url ON youtube_download_history(url)"
                )
                conn.commit()
            self.db_available = True
            self.init_error = ""
        except Exception as exc:
            self.db_available = False
            self.init_error = str(exc)

    def _normalize_url(self, url):
        return (url or "").strip()

    def _extract_video_id(self, task):
        url = self._normalize_url(getattr(task, "url", ""))
        if "watch?v=" in url:
            return url.split("watch?v=", 1)[1].split("&", 1)[0].strip()
        if "youtu.be/" in url:
            return url.split("youtu.be/", 1)[1].split("?", 1)[0].split("&", 1)[0].strip()
        return ""

    def _extract_playlist_id(self, task):
        url = self._normalize_url(getattr(task, "url", ""))
        if "list=" in url:
            return url.split("list=", 1)[1].split("&", 1)[0].strip()
        return ""

    def _build_history_item(self, task, status=STATUS_SUCCESS, failure_stage="", failure_summary="", return_code=None):
        display_title = getattr(task, "final_title", "") or (task.get_display_name() if hasattr(task, "get_display_name") else "")
        archive_subdir = getattr(task, "archive_subdir", "")
        archive_output_path = getattr(task, "archive_output_path", "") or getattr(task, "save_path", "")
        failure_detail = getattr(task, "latest_error_detail", "") if failure_summary else ""
        profile = getattr(task, "profile", None)
        if profile is None:
            profile = {}
        return {
            "title": display_title,
            "type": getattr(task, "task_type", "youtube"),
            "url": getattr(task, "url", ""),
            "path": archive_output_path,
            "archive_subdir": archive_subdir,
            "source_type": getattr(task, "source_type", SOURCE_TYPE_DEFAULT),
            "source_name": getattr(task, "source_name", SOURCE_NAME_DEFAULT),
            "source_platform": getattr(task, "source_platform", SOURCE_PLATFORM_DEFAULT),
            "url_type": getattr(task, "url_type", URL_TYPE_UNKNOWN),
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "task_id": getattr(task, "id", ""),
            "status": status,
            "video_id": self._extract_video_id(task),
            "playlist_id": self._extract_playlist_id(task),
            "channel_id": getattr(task, "channel_id", "") or "",
            "used_cookies": bool(getattr(task, "used_cookies", getattr(task, "needs_cookies", False))),
            "actual_cookies_mode": getattr(task, "actual_cookies_mode", "none") or "none",
            "failure_stage": failure_stage,
            "failure_summary": failure_summary,
            "failure_detail": failure_detail,
            "return_code": return_code,
            "profile": {
                "format": getattr(profile, "format", ""),
                "sub_lang": getattr(profile, "sub_lang", ""),
                "speed_limit": getattr(profile, "speed_limit", "0"),
                "retries": getattr(profile, "retries", 3),
                "custom_filename": getattr(profile, "custom_filename", ""),
                "preset_key": getattr(profile, "preset_key", "manual"),
                "merge_output_format": getattr(profile, "merge_output_format", "mp4"),
                "audio_quality": getattr(profile, "audio_quality", "192"),
            }
        }

    def _insert_db_record(self, item):
        if not self.db_available:
            return False
        profile = item.get("profile") or {}
        for attempt in range(self._db_retry_count):
            try:
                with self._get_conn() as conn:
                    conn.execute(
                        """
                        INSERT INTO youtube_download_history (
                            task_id, video_id, playlist_id, channel_id, url, task_type, url_type, status,
                            output_path, archive_subdir, source_type, source_name, format, final_title, used_cookies,
                            failure_stage, failure_summary, failure_detail, return_code, created_at, source,
                            sub_lang, retries, custom_filename, preset_key, merge_output_format, audio_quality, speed_limit
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            item.get("task_id", ""),
                            item.get("video_id", ""),
                            item.get("playlist_id", ""),
                            item.get("channel_id", ""),
                            item.get("url", ""),
                            item.get("type", SOURCE_PLATFORM_DEFAULT),
                            item.get("url_type", URL_TYPE_UNKNOWN),
                            item.get("status", STATUS_SUCCESS),
                            item.get("path", ""),
                            item.get("archive_subdir", ""),
                            item.get("source_type", SOURCE_TYPE_DEFAULT),
                            item.get("source_name", SOURCE_NAME_DEFAULT),
                            profile.get("format", ""),
                            item.get("title", ""),
                            1 if item.get("used_cookies") else 0,
                            item.get("failure_stage", ""),
                            item.get("failure_summary", ""),
                            item.get("failure_detail", ""),
                            item.get("return_code"),
                            item.get("time", ""),
                            item.get("source_platform", SOURCE_PLATFORM_DEFAULT),
                            profile.get("sub_lang", ""),
                            profile.get("retries", 3),
                            profile.get("custom_filename", ""),
                            profile.get("preset_key", "manual"),
                            profile.get("merge_output_format", "mp4"),
                            profile.get("audio_quality", "192"),
                            profile.get("speed_limit", "0"),
                        ),
                    )
                    conn.commit()
                self.init_error = ""
                return True
            except sqlite3.OperationalError as exc:
                message = str(exc).lower()
                if "database is locked" in message or "database table is locked" in message:
                    if attempt < self._db_retry_count - 1:
                        time.sleep(self._db_retry_delay * (attempt + 1))
                        continue
                    self.init_error = str(exc)
                    return False
                self.db_available = False
                self.init_error = str(exc)
                return False
            except Exception as exc:
                self.db_available = False
                self.init_error = str(exc)
                return False
        return False

    def _to_bool(self, value):
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        text = str(value or "").strip().lower()
        return text in {"1", "true", "yes", "y", "on", "是", "已启用"}

    def _normalize_history_profile(self, item):
        profile = item.get("profile")
        if isinstance(profile, dict):
            return profile
        legacy_profile = item.get("kwargs")
        if isinstance(legacy_profile, dict):
            return legacy_profile
        return {}

    def _normalize_history_item(self, item):
        if not isinstance(item, dict):
            return None, False

        key_map = {
            "标题": "title",
            "类型": "type",
            "链接": "url",
            "下载链接": "url",
            "保存路径": "path",
            "时间": "time",
            "任务ID": "task_id",
            "状态": "status",
            "视频ID": "video_id",
            "播放列表ID": "playlist_id",
            "频道ID": "channel_id",
            "使用Cookies": "used_cookies",
            "失败阶段": "failure_stage",
            "失败摘要": "failure_summary",
            "返回码": "return_code",
            "来源平台": "source_platform",
            "链接类型": "url_type",
        }

        migrated = False
        merged = dict(item)
        for legacy_key, current_key in key_map.items():
            if current_key not in merged and legacy_key in merged:
                merged[current_key] = merged.get(legacy_key)
                migrated = True

        profile = self._normalize_history_profile(merged)
        if "profile" not in merged and "kwargs" in merged:
            migrated = True
        if merged.get("used_cookies") is not None and not isinstance(merged.get("used_cookies"), bool):
            migrated = True

        normalized = {
            "title": merged.get("title") or merged.get("final_title") or merged.get("name") or "",
            "type": merged.get("type") or merged.get("task_type") or SOURCE_PLATFORM_DEFAULT,
            "url": merged.get("url") or "",
            "path": merged.get("path") or merged.get("output_path") or "",
            "archive_subdir": merged.get("archive_subdir") or "",
            "source_type": merged.get("source_type") or SOURCE_TYPE_DEFAULT,
            "source_name": merged.get("source_name") or SOURCE_NAME_DEFAULT,
            "source_platform": merged.get("source_platform") or SOURCE_PLATFORM_DEFAULT,
            "url_type": merged.get("url_type") or URL_TYPE_UNKNOWN,
            "time": merged.get("time") or merged.get("created_at") or "",
            "task_id": merged.get("task_id") or "",
            "status": merged.get("status") or "",
            "video_id": merged.get("video_id") or "",
            "playlist_id": merged.get("playlist_id") or "",
            "channel_id": merged.get("channel_id") or "",
            "used_cookies": self._to_bool(merged.get("used_cookies")),
            "failure_stage": merged.get("failure_stage") or "",
            "failure_summary": merged.get("failure_summary") or "",
            "return_code": merged.get("return_code"),
            "profile": profile,
        }
        return normalized, migrated

    def _load_json_history(self):
        if not os.path.exists(self.history_file):
            return []
        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
        except Exception as exc:
            logger.warning("Failed to load JSON history from %s: %s", self.history_file, exc)
            return []

        if not isinstance(raw_data, list):
            logger.warning("Invalid history data shape in %s: expected list, got %s", self.history_file, type(raw_data).__name__)
            return []

        normalized_data = []
        migrated_count = 0
        skipped_count = 0
        for item in raw_data:
            normalized_item, migrated = self._normalize_history_item(item)
            if normalized_item is None:
                skipped_count += 1
                continue
            if migrated:
                migrated_count += 1
            normalized_data.append(normalized_item)

        if migrated_count:
            logger.info("Migrated %d legacy history records from %s", migrated_count, self.history_file)
        if skipped_count:
            logger.warning("Skipped %d invalid history records from %s", skipped_count, self.history_file)

        return normalized_data

    def _write_json_history(self, history_data):
        write_json_atomic(self.history_file, history_data)

    def _save_json_item(self, history_item):
        with self._json_lock:
            history_data = self._load_json_history()
            history_data.insert(0, history_item)
            self._write_json_history(history_data[:HISTORY_JSON_LIMIT])

    def load(self):
        if self.db_available:
            try:
                with self._get_conn() as conn:
                    conn.row_factory = sqlite3.Row
                    rows = conn.execute(
                        """
                        SELECT final_title, task_type, url, output_path, created_at, task_id, status,
                               video_id, playlist_id, channel_id, used_cookies,
                               failure_stage, failure_summary, return_code, format,
                               source_type, source_name, source, url_type,
                               sub_lang, retries, custom_filename, preset_key, merge_output_format, audio_quality, speed_limit
                        FROM youtube_download_history
                        ORDER BY datetime(created_at) DESC, id DESC
                        LIMIT 200
                        """
                    ).fetchall()
                result = []
                for row in rows:
                    result.append({
                        "title": row["final_title"] or "",
                        "type": row["task_type"] or SOURCE_PLATFORM_DEFAULT,
                        "url": row["url"] or "",
                        "path": row["output_path"] or "",
                        "source_type": row["source_type"] or SOURCE_TYPE_DEFAULT,
                        "source_name": row["source_name"] or SOURCE_NAME_DEFAULT,
                        "source_platform": row["source"] or SOURCE_PLATFORM_DEFAULT,
                        "url_type": row["url_type"] or URL_TYPE_UNKNOWN,
                        "time": row["created_at"] or "",
                        "task_id": row["task_id"] or "",
                        "status": row["status"] or "",
                        "video_id": row["video_id"] or "",
                        "playlist_id": row["playlist_id"] or "",
                        "channel_id": row["channel_id"] or "",
                        "used_cookies": bool(row["used_cookies"]),
                        "failure_stage": row["failure_stage"] or "",
                        "failure_summary": row["failure_summary"] or "",
                        "return_code": row["return_code"],
                        "profile": {
                            "format": row["format"] or "",
                            "sub_lang": row["sub_lang"] or "",
                            "retries": row["retries"] if row["retries"] is not None else 3,
                            "custom_filename": row["custom_filename"] or "",
                            "preset_key": row["preset_key"] or "manual",
                            "merge_output_format": row["merge_output_format"] or "mp4",
                            "audio_quality": row["audio_quality"] or "192",
                            "speed_limit": row["speed_limit"] or "0",
                        },
                    })
                return result
            except sqlite3.OperationalError as exc:
                message = str(exc).lower()
                if "database is locked" not in message and "database table is locked" not in message:
                    self.db_available = False
                    self.init_error = str(exc)
                    return self._load_json_history()
            except Exception as exc:
                self.db_available = False
                self.init_error = str(exc)
                return self._load_json_history()

        return self._load_json_history()

    def save_task(self, task):
        history_item = self._build_history_item(task, status=STATUS_SUCCESS)
        return self._save_history_item(history_item)

    def save_failed_task(self, task, failure_stage="download", failure_summary="", return_code=None):
        history_item = self._build_history_item(
            task,
            status=STATUS_FAILED,
            failure_stage=failure_stage,
            failure_summary=failure_summary,
            return_code=return_code,
        )
        return self._save_history_item(history_item)

    def _save_history_item(self, history_item):
        """JSON 作为最终事实源先写；DB 作为冗余后写。任一失败不互相污染。"""
        json_saved = False
        db_saved = False
        try:
            self._save_json_item(history_item)
            json_saved = True
        except Exception as exc:
            logger.warning("Failed to write JSON history: %s", exc)
        try:
            db_saved = self._insert_db_record(history_item)
        except Exception as exc:
            logger.warning("Failed to write DB history: %s", exc)
        # 返回值仍以 DB 是否写成功为准（供 UI 提示“已保存到 DB/JSON”），
        # 保证 JSON 写入优先且两源字段口径一致（由 _build_history_item 统一）。
        return db_saved

    def has_success_record(self, url=None, video_id=None):
        if self.db_available:
            try:
                with self._get_conn() as conn:
                    if video_id:
                        row = conn.execute(
                            "SELECT 1 FROM youtube_download_history WHERE status = ? AND video_id = ? LIMIT 1",
                            (STATUS_SUCCESS, video_id),
                        ).fetchone()
                        if row:
                            return True
                    if url:
                        row = conn.execute(
                            "SELECT 1 FROM youtube_download_history WHERE status = ? AND url = ? LIMIT 1",
                            (STATUS_SUCCESS, self._normalize_url(url)),
                        ).fetchone()
                        if row:
                            return True
            except (sqlite3.OperationalError, sqlite3.DatabaseError) as exc:
                message = str(exc).lower()
                if "database is locked" not in message and "database table is locked" not in message:
                    self.db_available = False
                    self.init_error = str(exc)
            except Exception as exc:
                self.db_available = False
                self.init_error = str(exc)

        # DB 不可用或未命中时回退 JSON 做存在性判断
        return self._json_has_success_record(url=url, video_id=video_id)

    def _json_has_success_record(self, url=None, video_id=None):
        normalized_url = self._normalize_url(url) if url else ""
        for item in self._load_json_history():
            if item.get("status") != STATUS_SUCCESS:
                continue
            if video_id and item.get("video_id") == video_id:
                return True
            if normalized_url and self._normalize_url(item.get("url") or "") == normalized_url:
                return True
        return False

    def clear(self):
        if self.db_available:
            try:
                with self._get_conn() as conn:
                    conn.execute("DELETE FROM youtube_download_history")
            except sqlite3.OperationalError as exc:
                message = str(exc).lower()
                if "database is locked" not in message and "database table is locked" not in message:
                    self.db_available = False
                    self.init_error = str(exc)
            except Exception as exc:
                self.db_available = False
                self.init_error = str(exc)
        self._write_json_history([])
