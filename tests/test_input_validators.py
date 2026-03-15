from types import SimpleNamespace

import ui.input_validators as input_validators


class DummyVar:
    def __init__(self, value=None):
        self._value = value

    def get(self):
        return self._value

    def set(self, value):
        self._value = value


class DummyCombo:
    def __init__(self, value=""):
        self._value = value

    def get(self):
        return self._value

    def set(self, value):
        self._value = value

    def configure(self, values=None):
        self.values = values


class DummyManager:
    def __init__(self):
        self.logged = []

    def log(self, message, level="INFO"):
        self.logged.append((message, level))


class DummyMessageBox:
    def __init__(self):
        self.warnings = []
        self.errors = []

    def showwarning(self, title, message):
        self.warnings.append((title, message))

    def showerror(self, title, message):
        self.errors.append((title, message))


class DummyApp:
    def __init__(self):
        self.SilentMessagebox = DummyMessageBox()

    def detect_video_url_type(self, url):
        if "youtube" in url or "youtu.be" in url:
            return "youtube"
        return "unsupported"


class DummyFrame:
    def __init__(self):
        self.manager = DummyManager()
        self.app = DummyApp()
        self.preset_var = DummyVar("manual")
        self.format_var_combo = DummyCombo("best")
        self.output_format_var = DummyVar("mp4")
        self.output_format_combo = DummyCombo("mp4")
        self.custom_filename_var = DummyVar("")
        self.retry_var = DummyVar("3")
        self.retry_interval_var = DummyVar("0")
        self.sleep_interval_var = DummyVar("0")
        self.max_sleep_interval_var = DummyVar("0")
        self.sleep_requests_var = DummyVar("0")
        self.speedlimit_var = DummyVar("0")
        self.concurrent_var = DummyVar("1")
        self.audio_quality_var = DummyVar("192")
        self.embed_thumbnail_var = DummyVar(True)
        self.embed_metadata_var = DummyVar(True)
        self.write_thumbnail_var = DummyVar(False)
        self.write_info_json_var = DummyVar(False)
        self.write_description_var = DummyVar(False)
        self.write_chapters_var = DummyVar(False)
        self.keep_video_var = DummyVar(False)
        self.h264_compat_var = DummyVar(False)
        self.use_po_token_var = DummyVar(False)
        self.shared_save_dir_var = DummyVar("C:/Downloads")
        self.format_fetch_used_cookies = False
        self.detected_url_type = None


def test_coerce_int_input_invalid_value():
    frame = DummyFrame()
    frame.retry_var = DummyVar("abc")
    value = input_validators._coerce_int_input(frame, "retry_var", 3, minimum=0, maximum=10, label="重试次数")
    assert value == 3
    assert frame.retry_var.get() == 3
    assert frame.app.SilentMessagebox.warnings


def test_validate_custom_filename_invalid_chars():
    frame = DummyFrame()
    result = input_validators.validate_custom_filename(frame, "bad:name")
    assert result is False
    assert frame.app.SilentMessagebox.errors


def test_get_selected_format_id():
    frame = DummyFrame()
    frame.selected_format_id_var = DummyVar("")
    frame.format_var_combo = DummyCombo("137 | 1080p")
    assert input_validators.get_selected_format_id(frame) == "137"


def test_sync_output_format_by_preset_audio_only():
    frame = DummyFrame()
    frame.preset_var = DummyVar("audio_only")
    input_validators.sync_output_format_by_preset(frame)
    assert frame.output_format_var.get() in input_validators.AUDIO_OUTPUT_FORMATS


def test_prepare_direct_task_sets_profile_and_cookies():
    frame = DummyFrame()
    frame.format_var_combo = DummyCombo("137 | 1080p")
    frame.format_fetch_used_cookies = True
    task = input_validators.prepare_direct_task(frame, "https://www.youtube.com/watch?v=abc")
    assert task is not None
    assert task.needs_cookies is True
    assert task.profile.format.startswith("137")


def test_validate_youtube_url():
    frame = DummyFrame()
    assert input_validators.validate_youtube_url(frame, "https://www.youtube.com/watch?v=abc") is True
    assert input_validators.validate_youtube_url(frame, "https://example.com") is False
