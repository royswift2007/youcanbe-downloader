import os

import core.ytdlp_builder as ytdlp_builder
from core.youtube_models import AUDIO_FMT, P1080_FMT, YouTubeDownloadProfile, YouTubeTaskRecord


def _make_task(tmp_path, profile):
    return YouTubeTaskRecord(
        url="https://www.youtube.com/watch?v=abc123",
        save_path=str(tmp_path),
        profile=profile,
    )


def test_default_output_template(tmp_path):
    profile = YouTubeDownloadProfile()
    task = _make_task(tmp_path, profile)
    cmd = ytdlp_builder.build_ytdlp_command("yt-dlp.exe", "ffmpeg.exe", "cookies.txt", task)
    expected_template = os.path.join(str(tmp_path), "%(title)s.%(ext)s")
    assert "-o" in cmd
    assert cmd[cmd.index("-o") + 1] == expected_template


def test_custom_filename_template(tmp_path):
    profile = YouTubeDownloadProfile(custom_filename="my_custom_name")
    task = _make_task(tmp_path, profile)
    cmd = ytdlp_builder.build_ytdlp_command("yt-dlp.exe", "ffmpeg.exe", "cookies.txt", task)
    expected_template = os.path.join(str(tmp_path), "my_custom_name.%(ext)s")
    assert cmd[cmd.index("-o") + 1] == expected_template


def test_audio_mode_parameters(tmp_path):
    profile = YouTubeDownloadProfile(
        format=AUDIO_FMT,
        merge_output_format="mp3",
        audio_quality="256",
        keep_video=True,
    )
    task = _make_task(tmp_path, profile)
    cmd = ytdlp_builder.build_ytdlp_command("yt-dlp.exe", "ffmpeg.exe", "cookies.txt", task)
    assert "-x" in cmd
    assert "--audio-format" in cmd
    assert cmd[cmd.index("--audio-format") + 1] == "mp3"
    assert cmd[cmd.index("--audio-quality") + 1] == "256"
    assert "--keep-video" in cmd


def test_video_mode_parameters(tmp_path):
    profile = YouTubeDownloadProfile(
        format=P1080_FMT,
        merge_output_format="mkv",
        h264_compat=True,
    )
    task = _make_task(tmp_path, profile)
    cmd = ytdlp_builder.build_ytdlp_command("yt-dlp.exe", "ffmpeg.exe", "cookies.txt", task)
    assert "--merge-output-format" in cmd
    assert cmd[cmd.index("--merge-output-format") + 1] == "mkv"
    assert "--remux-video" in cmd
    assert cmd[cmd.index("--remux-video") + 1] == "mkv"
    assert "--recode-video" in cmd
    assert cmd[cmd.index("--recode-video") + 1] == "mp4"
    assert "--postprocessor-args" in cmd
    assert cmd[cmd.index("--postprocessor-args") + 1] == "ffmpeg:-c:v libx264 -c:a aac"
    assert "-x" not in cmd


def test_metadata_and_thumbnail_flags(tmp_path):
    profile = YouTubeDownloadProfile(
        embed_metadata=True,
        embed_thumbnail=True,
        write_thumbnail=True,
        write_info_json=True,
        write_description=True,
        write_chapters=True,
    )
    task = _make_task(tmp_path, profile)
    cmd = ytdlp_builder.build_ytdlp_command("yt-dlp.exe", "ffmpeg.exe", "cookies.txt", task)
    assert "--embed-metadata" in cmd
    assert "--embed-thumbnail" in cmd
    assert "--write-thumbnail" in cmd
    assert "--write-info-json" in cmd
    assert "--write-description" in cmd
    assert "--embed-chapters" in cmd


def test_speed_sleep_and_subs(tmp_path):
    profile = YouTubeDownloadProfile(
        speed_limit=5,
        retry_interval=4,
        sleep_interval=1,
        max_sleep_interval=3,
        sleep_requests=2,
        sub_lang="en",
    )
    task = _make_task(tmp_path, profile)
    cmd = ytdlp_builder.build_ytdlp_command("yt-dlp.exe", "ffmpeg.exe", "cookies.txt", task)
    assert "-r" in cmd
    assert cmd[cmd.index("-r") + 1] == "5M"
    assert "--retry-sleep" in cmd
    assert cmd[cmd.index("--retry-sleep") + 1] == "http:4"
    assert "--sleep-interval" in cmd
    assert cmd[cmd.index("--sleep-interval") + 1] == "1"
    assert "--max-sleep-interval" in cmd
    assert cmd[cmd.index("--max-sleep-interval") + 1] == "3"
    assert "--sleep-requests" in cmd
    assert cmd[cmd.index("--sleep-requests") + 1] == "2"
    assert "--write-subs" in cmd
    assert "--sub-langs" in cmd
    assert cmd[cmd.index("--sub-langs") + 1] == "en"
    assert "--embed-subs" in cmd


def test_cookies_and_po_token(monkeypatch, tmp_path):
    profile = YouTubeDownloadProfile(use_po_token=True)
    task = _make_task(tmp_path, profile)
    task.needs_cookies = True
    cookies_path = tmp_path / "cookies.txt"
    cookies_path.write_text("test")

    class DummyManager:
        def get_token(self):
            return {"visitor_data": "vdata", "po_token": "ptok"}

    monkeypatch.setattr(ytdlp_builder, "_get_pot_manager", lambda: DummyManager())

    cmd = ytdlp_builder.build_ytdlp_command(
        "yt-dlp.exe",
        "ffmpeg.exe",
        str(cookies_path),
        task,
    )
    assert "--cookies" in cmd
    assert str(cookies_path) in cmd
    assert "--extractor-args" in cmd
    extractor_args = cmd[cmd.index("--extractor-args") + 1]
    assert "visitor_data=vdata" in extractor_args
    assert "po_token=ptok" in extractor_args
