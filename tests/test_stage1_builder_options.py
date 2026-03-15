import core.ytdlp_builder as ytdlp_builder
from core.youtube_models import YouTubeDownloadProfile, YouTubeTaskRecord


def _make_task(tmp_path, profile):
    return YouTubeTaskRecord(
        url="https://www.youtube.com/watch?v=abc123",
        save_path=str(tmp_path),
        profile=profile,
    )


def test_download_sections_and_sponsorblock(tmp_path):
    profile = YouTubeDownloadProfile(
        download_sections="*00:01:00-00:02:30",
        sponsorblock_enabled=True,
        sponsorblock_categories="sponsor,intro",
    )
    task = _make_task(tmp_path, profile)
    cmd = ytdlp_builder.build_ytdlp_command("yt-dlp.exe", "ffmpeg.exe", "cookies.txt", task)
    assert "--download-sections" in cmd
    assert cmd[cmd.index("--download-sections") + 1] == "*00:01:00-00:02:30"
    assert "--sponsorblock-remove" in cmd
    assert cmd[cmd.index("--sponsorblock-remove") + 1] == "sponsor,intro"


def test_proxy_and_advanced_args(tmp_path):
    profile = YouTubeDownloadProfile(
        proxy_url="http://127.0.0.1:8080",
        advanced_args="--force-ipv4 --no-check-certificate",
    )
    task = _make_task(tmp_path, profile)
    cmd = ytdlp_builder.build_ytdlp_command("yt-dlp.exe", "ffmpeg.exe", "cookies.txt", task)
    assert "--proxy" in cmd
    assert cmd[cmd.index("--proxy") + 1] == "http://127.0.0.1:8080"
    assert "--force-ipv4" in cmd
    assert "--no-check-certificate" in cmd


def test_cookies_from_browser_precedence(tmp_path):
    profile = YouTubeDownloadProfile(
        cookies_mode="browser",
        cookies_browser="chrome",
    )
    task = _make_task(tmp_path, profile)
    task.needs_cookies = True
    cmd = ytdlp_builder.build_ytdlp_command("yt-dlp.exe", "ffmpeg.exe", "cookies.txt", task)
    assert "--cookies-from-browser" in cmd
    assert cmd[cmd.index("--cookies-from-browser") + 1] == "chrome"
    assert "--cookies" not in cmd
