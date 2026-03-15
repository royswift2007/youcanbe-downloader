import json

from core.history_repo import YouTubeHistoryRepository
from core.youtube_models import YouTubeDownloadProfile, YouTubeTaskRecord


def _make_task(url, tmp_path):
    return YouTubeTaskRecord(
        url=url,
        save_path=str(tmp_path),
        profile=YouTubeDownloadProfile(),
    )


def test_db_initialization(tmp_path):
    history_file = tmp_path / "history.json"
    db_path = tmp_path / "history.sqlite3"
    repo = YouTubeHistoryRepository(str(history_file), db_path=str(db_path))
    assert repo.db_available is True
    assert db_path.exists()


def test_save_success_and_load(tmp_path):
    history_file = tmp_path / "history.json"
    db_path = tmp_path / "history.sqlite3"
    repo = YouTubeHistoryRepository(str(history_file), db_path=str(db_path))
    task = _make_task("https://www.youtube.com/watch?v=vid123&list=pl456", tmp_path)
    repo.save_task(task)
    records = repo.load()
    assert records
    first = records[0]
    assert first["status"] == "完成"
    assert first["video_id"] == "vid123"
    assert first["playlist_id"] == "pl456"


def test_save_failed_and_failure_stage(tmp_path):
    history_file = tmp_path / "history.json"
    db_path = tmp_path / "history.sqlite3"
    repo = YouTubeHistoryRepository(str(history_file), db_path=str(db_path))
    task = _make_task("https://youtu.be/abc999", tmp_path)
    repo.save_failed_task(task, failure_stage="download", failure_summary="boom", return_code=1)
    records = repo.load()
    assert records
    first = records[0]
    assert first["status"] == "失败"
    assert first["failure_stage"] == "download"
    assert "boom" in first["failure_summary"]


def test_legacy_field_migration(tmp_path):
    history_file = tmp_path / "history.json"
    legacy_item = {
        "标题": "旧标题",
        "类型": "youtube",
        "下载链接": "https://www.youtube.com/watch?v=legacy1&list=pl1",
        "保存路径": "C:/downloads",
        "时间": "2026-03-15 00:00:00",
        "任务ID": "legacy-task",
        "状态": "完成",
        "视频ID": "legacy1",
        "播放列表ID": "pl1",
        "使用Cookies": "是",
        "失败阶段": "download",
        "失败摘要": "old error",
        "返回码": 2,
        "kwargs": {"format": "best"},
    }
    history_file.write_text(json.dumps([legacy_item], ensure_ascii=False), encoding="utf-8")
    repo = YouTubeHistoryRepository(str(history_file), db_path=str(tmp_path / "history.sqlite3"))
    repo.db_available = False
    records = repo.load()
    assert records
    first = records[0]
    assert first["title"] == "旧标题"
    assert first["url"].endswith("legacy1&list=pl1")
    assert first["used_cookies"] is True
    assert first["failure_stage"] == "download"
    assert first["profile"]["format"] == "best"


def test_extract_video_and_playlist_ids(tmp_path):
    history_file = tmp_path / "history.json"
    repo = YouTubeHistoryRepository(str(history_file), db_path=str(tmp_path / "history.sqlite3"))
    task = _make_task("https://www.youtube.com/watch?v=vid777&list=pl777", tmp_path)
    item = repo._build_history_item(task)
    assert item["video_id"] == "vid777"
    assert item["playlist_id"] == "pl777"
