import core.ytdlp_builder as ytdlp_builder
from core.youtube_models import YouTubeDownloadProfile, YouTubeTaskRecord


def _make_task(tmp_path, profile):
    return YouTubeTaskRecord(
        url="https://www.youtube.com/watch?v=abc123",
        save_path=str(tmp_path),
        profile=profile,
    )


def test_subtitle_manual_mode(tmp_path):
    profile = YouTubeDownloadProfile(
        subtitle_mode="manual",
        subtitle_langs="en,zh-Hans",
        subtitle_format="srt",
        embed_subs=True,
        write_subs=True,
    )
    task = _make_task(tmp_path, profile)
    cmd = ytdlp_builder.build_ytdlp_command("yt-dlp.exe", "ffmpeg.exe", "cookies.txt", task)
    assert "--write-subs" in cmd
    assert "--write-auto-subs" not in cmd
    assert "--sub-langs" in cmd
    assert cmd[cmd.index("--sub-langs") + 1] == "en,zh-Hans"
    assert "--sub-format" in cmd
    assert cmd[cmd.index("--sub-format") + 1] == "srt"
    assert "--embed-subs" in cmd


def test_subtitle_auto_mode(tmp_path):
    profile = YouTubeDownloadProfile(
        subtitle_mode="auto",
        subtitle_langs="en",
        subtitle_format="vtt",
        embed_subs=False,
        write_subs=True,
    )
    task = _make_task(tmp_path, profile)
    cmd = ytdlp_builder.build_ytdlp_command("yt-dlp.exe", "ffmpeg.exe", "cookies.txt", task)
    assert "--write-auto-subs" in cmd
    assert "--write-subs" not in cmd
    assert "--sub-langs" in cmd
    assert cmd[cmd.index("--sub-langs") + 1] == "en"
    assert "--sub-format" in cmd
    assert cmd[cmd.index("--sub-format") + 1] == "vtt"
    assert "--embed-subs" not in cmd


def test_subtitle_both_mode(tmp_path):
    profile = YouTubeDownloadProfile(
        subtitle_mode="both",
        subtitle_langs="ja,en",
        subtitle_format="ass",
        embed_subs=True,
        write_subs=True,
    )
    task = _make_task(tmp_path, profile)
    cmd = ytdlp_builder.build_ytdlp_command("yt-dlp.exe", "ffmpeg.exe", "cookies.txt", task)
    assert "--write-subs" in cmd
    assert "--write-auto-subs" in cmd
    assert "--sub-langs" in cmd
    assert cmd[cmd.index("--sub-langs") + 1] == "ja,en"
    assert "--sub-format" in cmd
    assert cmd[cmd.index("--sub-format") + 1] == "ass"
    assert "--embed-subs" in cmd


def test_subtitle_none_mode(tmp_path):
    profile = YouTubeDownloadProfile(
        subtitle_mode="none",
        subtitle_langs="en",
        subtitle_format="srt",
        embed_subs=True,
        write_subs=True,
    )
    task = _make_task(tmp_path, profile)
    cmd = ytdlp_builder.build_ytdlp_command("yt-dlp.exe", "ffmpeg.exe", "cookies.txt", task)
    assert "--write-subs" not in cmd
    assert "--write-auto-subs" not in cmd
    assert "--sub-langs" not in cmd
    assert "--sub-format" not in cmd
    assert "--embed-subs" not in cmd


def test_subtitle_compat_sub_lang(tmp_path):
    profile = YouTubeDownloadProfile(
        sub_lang="fr",
    )
    task = _make_task(tmp_path, profile)
    cmd = ytdlp_builder.build_ytdlp_command("yt-dlp.exe", "ffmpeg.exe", "cookies.txt", task)
    assert "--write-subs" in cmd
    assert "--sub-langs" in cmd
    assert cmd[cmd.index("--sub-langs") + 1] == "fr"
    assert "--embed-subs" in cmd
