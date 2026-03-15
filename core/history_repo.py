import json
import logging
import os
import sqlite3
import threading
import time

logger = logging.getLogger(__name__)


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

    def _init_db(self):
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
            with sqlite3.connect(self.db_path) as conn:
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
                        return_code INTEGER,
                        created_at TEXT NOT NULL,
                        source TEXT DEFAULT 'youtube'
                    )
                    """
                )
                existing_columns = {
                    row[1]
                    for row in conn.execute("PRAGMA table_info(youtube_download_history)").fetchall()
                }
                if "archive_subdir" not in existing_columns:
                    conn.execute("ALTER TABLE youtube_download_history ADD COLUMN archive_subdir TEXT")
                if "source_type" not in existing_columns:
                    conn.execute("ALTER TABLE youtube_download_history ADD COLUMN source_type TEXT")
                if "source_name" not in existing_columns:
                    conn.execute("ALTER TABLE youtube_download_history ADD COLUMN source_name TEXT")
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

    def _build_history_item(self, task, status="完成", failure_stage="", failure_summary="", return_code=None):
        display_title = task.final_title if task.final_title else task.get_display_name()
        archive_subdir = getattr(task, "archive_subdir", "")
        archive_output_path = getattr(task, "archive_output_path", "") or getattr(task, "save_path", "")
        return {
            "title": display_title,
            "type": task.task_type,
            "url": task.url,
            "path": archive_output_path,
            "archive_subdir": archive_subdir,
            "source_type": getattr(task, "source_type", "manual"),
            "source_name": getattr(task, "source_name", "手动任务"),
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "task_id": task.id,
            "status": status,
            "video_id": self._extract_video_id(task),
            "playlist_id": self._extract_playlist_id(task),
            "channel_id": getattr(task, "channel_id", "") or "",
            "used_cookies": bool(getattr(task, "needs_cookies", False)),
            "failure_stage": failure_stage,
            "failure_summary": failure_summary,
            "return_code": return_code,
            "profile": {
                "format": task.profile.format,
                "sub_lang": task.profile.sub_lang,
                "speed_limit": task.profile.speed_limit,
                "retries": task.profile.retries,
                "custom_filename": task.profile.custom_filename,
                "preset_key": getattr(task.profile, "preset_key", "manual"),
                "merge_output_format": getattr(task.profile, "merge_output_format", "mp4"),
                "audio_quality": getattr(task.profile, "audio_quality", "192"),
            }
        }

    def _insert_db_record(self, item):
        if not self.db_available:
            return False
        for attempt in range(self._db_retry_count):
            try:
                with sqlite3.connect(self.db_path, timeout=2.0) as conn:
                    conn.execute(
                        """
                        INSERT INTO youtube_download_history (
                            task_id, video_id, playlist_id, channel_id, url, task_type, status,
                            output_path, archive_subdir, source_type, source_name, format, final_title, used_cookies,
                            failure_stage, failure_summary, return_code, created_at, source
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            item.get("task_id", ""),
                            item.get("video_id", ""),
                            item.get("playlist_id", ""),
                            item.get("channel_id", ""),
                            item.get("url", ""),
                            item.get("type", "youtube"),
                            item.get("status", "完成"),
                            item.get("path", ""),
                            item.get("archive_subdir", ""),
                            item.get("source_type", "manual"),
                            item.get("source_name", "手动任务"),
                            item.get("profile", {}).get("format", ""),
                            item.get("title", ""),
                            1 if item.get("used_cookies") else 0,
                            item.get("failure_stage", ""),
                            item.get("failure_summary", ""),
                            item.get("return_code"),
                            item.get("time", ""),
                            "youtube",
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
            "type": merged.get("type") or merged.get("task_type") or "youtube",
            "url": merged.get("url") or "",
            "path": merged.get("path") or merged.get("output_path") or "",
            "archive_subdir": merged.get("archive_subdir") or "",
            "source_type": merged.get("source_type") or "manual",
            "source_name": merged.get("source_name") or "手动任务",
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
        with open(self.history_file, "w", encoding="utf-8") as f:
            json.dump(history_data, f, ensure_ascii=False, indent=2)

    def _save_json_item(self, history_item):
        with self._json_lock:
            history_data = self._load_json_history()
            history_data.insert(0, history_item)
            self._write_json_history(history_data[:100])

    def load(self):
        if self.db_available:
            try:
                with sqlite3.connect(self.db_path, timeout=2.0) as conn:
                    conn.row_factory = sqlite3.Row
                    rows = conn.execute(
                        """
                        SELECT final_title, task_type, url, output_path, created_at, task_id, status,
                               video_id, playlist_id, channel_id, used_cookies,
                               failure_stage, failure_summary, return_code, format
                        FROM youtube_download_history
                        ORDER BY datetime(created_at) DESC, id DESC
                        LIMIT 200
                        """
                    ).fetchall()
                result = []
                for row in rows:
                    result.append({
                        "title": row["final_title"] or "",
                        "type": row["task_type"] or "youtube",
                        "url": row["url"] or "",
                        "path": row["output_path"] or "",
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
                        },
                    })
                return result
            except sqlite3.OperationalError as exc:
                message = str(exc).lower()
                if "database is locked" not in message and "database table is locked" not in message:
                    self.db_available = False
                    self.init_error = str(exc)
            except Exception as exc:
                self.db_available = False
                self.init_error = str(exc)

        return self._load_json_history()

    def save_task(self, task):
        history_item = self._build_history_item(task, status="完成")
        db_saved = self._insert_db_record(history_item)
        self._save_json_item(history_item)
        return db_saved

    def save_failed_task(self, task, failure_stage="download", failure_summary="", return_code=None):
        history_item = self._build_history_item(
            task,
            status="失败",
            failure_stage=failure_stage,
            failure_summary=failure_summary,
            return_code=return_code,
        )
        db_saved = self._insert_db_record(history_item)
        self._save_json_item(history_item)
        return db_saved

    def has_success_record(self, url=None, video_id=None):
        if not self.db_available:
            return False
        try:
            with sqlite3.connect(self.db_path, timeout=2.0) as conn:
                if video_id:
                    row = conn.execute(
                        "SELECT 1 FROM youtube_download_history WHERE status = ? AND video_id = ? LIMIT 1",
                        ("完成", video_id),
                    ).fetchone()
                    if row:
                        return True
                if url:
                    row = conn.execute(
                        "SELECT 1 FROM youtube_download_history WHERE status = ? AND url = ? LIMIT 1",
                        ("完成", self._normalize_url(url)),
                    ).fetchone()
                    if row:
                        return True
        except sqlite3.OperationalError as exc:
            message = str(exc).lower()
            if "database is locked" not in message and "database table is locked" not in message:
                self.db_available = False
                self.init_error = str(exc)
        except Exception as exc:
            self.db_available = False
            self.init_error = str(exc)
        return False

    def clear(self):
        if self.db_available:
            try:
                with sqlite3.connect(self.db_path, timeout=2.0) as conn:
                    conn.execute("DELETE FROM youtube_download_history")
                    conn.commit()
            except sqlite3.OperationalError as exc:
                message = str(exc).lower()
                if "database is locked" not in message and "database table is locked" not in message:
                    self.db_available = False
                    self.init_error = str(exc)
            except Exception as exc:
                self.db_available = False
                self.init_error = str(exc)
        self._write_json_history([])
