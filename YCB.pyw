import tkinter as tk
from tkinter import ttk, filedialog, messagebox, font
import subprocess
import threading
import json
import os
import re
import sys
import urllib.request
import queue
import time
import shutil

from core.auth_models import CookiesStatus

from core.download_manager import YouTubeDownloadManager
from core.media_jobs import MediaJobManager
from core.components_manager import ComponentsManager
from core.release_validator import validate_release_bundle
from core.settings import WindowPositionRepository, is_geometry_visible
from core.youtube_metadata import YouTubeMetadataService
from core.youtube_models import (
    TASK_STATUS_WAITING,
    TASK_STATUS_RUNNING,
    TASK_STATUS_SUCCESS,
    TASK_STATUS_FAILED,
    TASK_STATUS_STOPPED,
    AUDIO_FMT,
    P1080_FMT,
    P720_FMT,
    URL_TYPE_YOUTUBE,
    detect_url_type,
)
from ui.app_actions import (
    choose_directory,
    notify_cookies_error,
    open_save_directory,
    update_yt_dlp,
)
from ui.queue_tab import QueueTab
from ui.bootstrap import debug_startup, run_app, setup_styles
from ui.download_tab import DownloadTab
from ui.history_actions import clear_all_history, load_history, show_auth_status, show_history, show_runtime_status
from ui.pages.batch_source import BatchSourceInputFrame
from ui.pages.history_page import HistoryPage
from ui.pages.media_tools import MediaToolsPage
from ui.pages.single_video import UnifiedVideoInputFrame
from ui.app_shell import BottomBar
from ui.pages.settings_page import SettingsPage
from ui.components_center import ComponentsCenterWindow
from ui.i18n import DEFAULT_LANG, normalize_lang, tr


PANE_CONFIG_KEY_SINGLE_VIDEO = "single_video"
PANE_CONFIG_KEY_BATCH_SOURCE = "batch_source"
PANE_CONFIG_KEY_QUEUE_TAB = "queue_tab"

# ---------------- 统一的全局样式配置 ----------------
FONT_FAMILY = "Microsoft YaHei"  # 全局字体：微软雅黑
FONT_SIZE_TITLE = 10  # 标题文字大小
FONT_SIZE_NORMAL = 10  # 普通文字大小
FONT_SIZE_BUTTON = 10  # 按钮文字大小
FONT_SIZE_PERCENT = 14  # 百分比显示文字大小
COMBOBOX_WIDTH = 70  # 下拉框宽度
URL_ENTRY_WIDTH = 70  # URL输入框宽度
BUTTON_WIDTH_OP = 10  # 操作按钮宽度
BUTTON_WIDTH_MAIN = 12  # 主按钮宽度

# ---------------- 基础路径 ----------------
try:
    if getattr(sys, 'frozen', False):
        base_path = os.path.dirname(sys.executable)
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
except NameError:
    base_path = os.getcwd()



def _get_app_data_dir():
    if not getattr(sys, 'frozen', False):
        return base_path
    for env_key in ("LOCALAPPDATA", "APPDATA"):
        root = (os.environ.get(env_key) or "").strip()
        if not root:
            continue
        candidate = os.path.join(root, "YCB")
        try:
            os.makedirs(candidate, exist_ok=True)
            return candidate
        except OSError:
            continue
    return base_path


APP_DATA_DIR = _get_app_data_dir()


def get_resource_path(relative_path):
    """获取资源文件的绝对路径，优先返回实际存在的资源路径。"""
    candidate_roots = []
    if getattr(sys, 'frozen', False):
        meipass = getattr(sys, '_MEIPASS', '')
        if meipass:
            candidate_roots.append(meipass)
        candidate_roots.append(base_path)
    else:
        candidate_roots.append(os.path.dirname(os.path.abspath(__file__)))
        if base_path not in candidate_roots:
            candidate_roots.append(base_path)

    fallback_root = candidate_roots[0] if candidate_roots else base_path
    for root in candidate_roots:
        candidate = os.path.join(root, relative_path)
        if os.path.exists(candidate):
            return candidate
    return os.path.join(fallback_root, relative_path)

def _is_executable_file(path):
    if not path or not os.path.isfile(path):
        return False
    if os.name != "nt":
        return os.access(path, os.X_OK)
    ext = os.path.splitext(path)[1].lower()
    return ext in {".exe", ".bat", ".cmd"}


def _debug_exception(context, exc):
    try:
        debug_startup(f"{context}: {exc}")
    except Exception:
        pass


def _resolve_component_binary(base_dir, name):
    candidates = [f"{name}.exe", name] if os.name == "nt" else [name, f"{name}.exe"]
    for candidate in candidates:
        full_path = os.path.join(base_dir, candidate)
        if _is_executable_file(full_path):
            return full_path
    for candidate in candidates:
        found = shutil.which(candidate)
        if found and _is_executable_file(found):
            return found
    return None


yt_dlp_path = _resolve_component_binary(base_path, "yt-dlp")
ffmpeg_path = _resolve_component_binary(base_path, "ffmpeg")
deno_path = _resolve_component_binary(base_path, "deno")
CONFIG_FILE = os.path.join(APP_DATA_DIR, "window_pos.json")  # 窗口位置配置文件
INSTALLER_PREFS_FILE = os.path.join(base_path, "install_prefs.json")
INSTALLER_PREFS_SENTINEL = os.path.join(APP_DATA_DIR, ".installer_lang_consumed")

# [新增] Cookies 文件路径定义
COOKIES_DEFAULT_PATH = os.path.join(APP_DATA_DIR, "www.youtube.com_cookies.txt")  # YouTube Cookies文件路径

startupinfo = None
if os.name == "nt":
    startupinfo = subprocess.STARTUPINFO()
    try:
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    except AttributeError:
        startupinfo.dwFlags |= 1

# ---------------- 配置 & 历史文件路径 ----------------
HISTORY_FILES = {
    'ytdlp': os.path.join(APP_DATA_DIR, "download_history_ytdlp.json"),
}

LAST_SAVE_PATH_DEFAULT = os.path.expanduser("~/Downloads")  # 默认保存路径：用户下载文件夹

# ============ 静音消息框替代类 ============
class SilentMessagebox:
    """静音消息框替代类 - 无系统提示音"""
    lang_getter = staticmethod(lambda: DEFAULT_LANG)

    @staticmethod
    def _get_lang():
        try:
            getter = getattr(SilentMessagebox, "lang_getter", None)
            if callable(getter):
                return normalize_lang(getter())
        except Exception:
            pass
        return DEFAULT_LANG

    @staticmethod
    def _create_dialog(title, message, bg_color="#ffffff", fg_color="#333333"):
        dialog = tk.Toplevel()
        dialog.title(title)
        dialog.configure(bg=bg_color)
        dialog.withdraw()
        
        content_frame = tk.Frame(dialog, bg=bg_color, padx=20, pady=20)
        content_frame.pack(expand=True, fill='both')
        
        tk.Label(content_frame, text=message, bg=bg_color, fg=fg_color, 
                 wraplength=300, justify='left', font=("Microsoft YaHei", 10)).pack(expand=True)
                 
        btn_frame = tk.Frame(dialog, bg=bg_color, pady=10)
        btn_frame.pack(fill='x')
        return dialog, btn_frame

    @staticmethod
    def _show_modal(dialog, parent=None):
        dialog.update_idletasks()
        width = 350
        height = dialog.winfo_reqheight()
        # 简单居中
        screen_width = dialog.winfo_screenwidth()
        screen_height = dialog.winfo_screenheight()
        x = (screen_width - width) // 2
        y = (screen_height - height) // 2
        dialog.geometry(f'{width}x{height}+{int(x)}+{int(y)}')
        
        dialog.deiconify()
        dialog.transient(parent) if parent else None
        dialog.grab_set()
        dialog.wait_window()

    @staticmethod
    def showinfo(title, message, parent=None):
        dialog, btn_frame = SilentMessagebox._create_dialog(title, message)
        ok_text = tr("common_ok", SilentMessagebox._get_lang())
        tk.Button(btn_frame, text=ok_text, command=dialog.destroy,
                 bg="#e6f7ff", relief='flat', padx=15, font=("Microsoft YaHei", 9)).pack(pady=5)
        SilentMessagebox._show_modal(dialog, parent)

    @staticmethod
    def showwarning(title, message, parent=None):
        dialog, btn_frame = SilentMessagebox._create_dialog(title, message)
        ok_text = tr("common_ok", SilentMessagebox._get_lang())
        tk.Button(btn_frame, text=ok_text, command=dialog.destroy,
                 bg="#fff7e6", relief='flat', padx=15, font=("Microsoft YaHei", 9)).pack(pady=5)
        SilentMessagebox._show_modal(dialog, parent)

    @staticmethod
    def showerror(title, message, parent=None):
        dialog, btn_frame = SilentMessagebox._create_dialog(title, message)
        ok_text = tr("common_ok", SilentMessagebox._get_lang())
        tk.Button(btn_frame, text=ok_text, command=dialog.destroy,
                 bg="#fff1f0", relief='flat', padx=15, font=("Microsoft YaHei", 9)).pack(pady=5)
        SilentMessagebox._show_modal(dialog, parent)

    @staticmethod
    def askyesno(title, message, parent=None):
        dialog, btn_frame = SilentMessagebox._create_dialog(title, message)
        result = [False]
        def on_yes():
            result[0] = True
            dialog.destroy()
        def on_no():
            result[0] = False
            dialog.destroy()
            
        yes_text = tr("common_yes", SilentMessagebox._get_lang())
        no_text = tr("common_no", SilentMessagebox._get_lang())
        tk.Button(btn_frame, text=yes_text, command=on_yes,
                 bg="#e6f7ff", relief='flat', padx=15, width=6).pack(side='left', padx=20, expand=True)
        tk.Button(btn_frame, text=no_text, command=on_no,
                 bg="#f5f5f5", relief='flat', padx=15, width=6).pack(side='right', padx=20, expand=True)
        SilentMessagebox._show_modal(dialog, parent)
        return result[0]

# ============ YouTube 下载辅助函数 ============
def load_window_pos(root_window, position_repo):
    """加载窗口位置；若历史位置不可见则回退到居中默认位置。"""
    pos = position_repo.load()
    if not pos:
        return
    try:
        screen_width = root_window.winfo_screenwidth()
        screen_height = root_window.winfo_screenheight()
        if not is_geometry_visible(pos, screen_width, screen_height):
            width = int(pos.get('width', 1400) or 1400)
            height = int(pos.get('height', 1000) or 1000)
            width = max(900, min(width, screen_width))
            height = max(600, min(height, screen_height))
            x = max(0, (screen_width - width) // 2)
            y = max(0, (screen_height - height) // 2)
            root_window.geometry(f"{width}x{height}+{x}+{y}")
            return

        geo = f"{pos['width']}x{pos['height']}+{pos['x']}+{pos['y']}"
        root_window.geometry(geo)
    except Exception as exc:
        _debug_exception("load_window_pos failed", exc)

def save_window_pos(root_window, position_repo, extra_state=None):
    """保存窗口位置"""
    try:
        position_repo.save(root_window, extra_state=extra_state)
    except Exception as exc:
        _debug_exception("save_window_pos failed", exc)


def consume_installer_language_preference():
    if os.path.exists(INSTALLER_PREFS_SENTINEL):
        try:
            if os.path.isfile(INSTALLER_PREFS_FILE):
                os.remove(INSTALLER_PREFS_FILE)
        except OSError:
            pass
        return None
    if not os.path.isfile(INSTALLER_PREFS_FILE):
        return None
    consumed_lang = None
    try:
        with open(INSTALLER_PREFS_FILE, "r", encoding="utf-8") as f:
            payload = json.load(f)
        if isinstance(payload, dict):
            raw_lang = payload.get("lang")
            if raw_lang in ("zh", "en"):
                consumed_lang = normalize_lang(raw_lang)
        with open(INSTALLER_PREFS_SENTINEL, "w", encoding="utf-8") as f:
            f.write(consumed_lang or "consumed")
    except Exception as exc:
        _debug_exception("consume_installer_language_preference failed", exc)
    finally:
        try:
            os.remove(INSTALLER_PREFS_FILE)
        except OSError:
            pass
    return consumed_lang


def detect_video_url_type(url):
    """检测并归类输入链接，返回标准 URL 类型。"""
    return detect_url_type(url)

# ============ UI 样式定义 ============
UI_COLORS = {  # UI色彩配置方案
    "bg_main": "#f0f2f5",           # 主背景色：浅灰白，用于窗口背景
    "bg_secondary": "#ffffff",      # 次级背景色：纯白，用于卡片/内容区背景
    "text_primary": "#333333",      # 主文本颜色：深灰
    "text_secondary": "#666666",    # 副文本颜色：中灰，用于辅助说明
    "primary": "#1890ff",           # 主色调：蓝色，用于主要操作按钮
    "success": "#52c41a",           # 成功/开始色：绿色
    "warning": "#faad14",           # 警告/暂停色：橙色
    "danger": "#ff4d4f",            # 错误/停止色：红色
    "info": "#13c2c2",              # 信息色：青色
    "border": "#d9d9d9",            # 边框色：浅灰
}

# ============ (重构) 主应用程序类 ============
class DownloadApplication:
    """主应用程序 GUI 类"""
    def __init__(self, root):
        debug_startup("DownloadApplication.__init__ start")
        self.root = root
        setup_styles(UI_COLORS, FONT_FAMILY, FONT_SIZE_NORMAL)
        debug_startup("setup_styles done")
        self.root.configure(background=UI_COLORS["bg_main"])
        self.root.geometry("1650x1000")
        self.root.minsize(1200, 700)  # 设置最小窗口尺寸
        self.position_repo = WindowPositionRepository(CONFIG_FILE)
        self.ui_state = self.position_repo.get_ui_state()
        self._initial_lang_from_installer = False
        saved_lang = self.get_ui_state_value("i18n", "lang", default=None)
        installer_lang = consume_installer_language_preference()
        debug_startup(
            f"lang bootstrap base_path={base_path} app_data_dir={APP_DATA_DIR} "
            f"prefs_file={INSTALLER_PREFS_FILE} sentinel={INSTALLER_PREFS_SENTINEL} "
            f"saved_lang={saved_lang!r} installer_lang={installer_lang!r} "
            f"installer_prefs_exists={os.path.isfile(INSTALLER_PREFS_FILE)} sentinel_exists={os.path.exists(INSTALLER_PREFS_SENTINEL)}"
        )
        if saved_lang in ("zh", "en"):
            self.current_lang = normalize_lang(saved_lang)
            debug_startup(f"lang bootstrap source=settings value={self.current_lang}")
        elif installer_lang in ("zh", "en"):
            self.current_lang = normalize_lang(installer_lang)
            self.set_ui_state_value("i18n", "lang", value=self.current_lang)
            self._initial_lang_from_installer = True
            debug_startup(f"lang bootstrap source=installer value={self.current_lang}")
        else:
            self.current_lang = DEFAULT_LANG
            debug_startup(f"lang bootstrap source=default value={self.current_lang}")
        SilentMessagebox.lang_getter = staticmethod(lambda: self.current_lang)
        self.root.title(tr("app_title", self.current_lang))
        load_window_pos(self.root, self.position_repo)
        if self._initial_lang_from_installer:
            self.save_ui_state()
            self._initial_lang_from_installer = False
        debug_startup("window position loaded")
        self.yt_dlp_update_in_progress = False

        self._init_core_state()
        self._init_shared_vars()
        self._init_managers()
        self._build_ui()
        self._start_background_tasks()
        self._bind_events()
        debug_startup("DownloadApplication.__init__ done")

    def _init_core_state(self):
        self.HISTORY_FILES = HISTORY_FILES
        self.base_path = base_path
        self.components_manager = ComponentsManager(yt_dlp_path, ffmpeg_path, deno_path=deno_path, text_getter=self.get_text)
        self.current_history_data = []

    def _init_shared_vars(self):
        self.shared_save_dir_var = tk.StringVar(value=LAST_SAVE_PATH_DEFAULT)
        self.main_status_var = tk.StringVar(value=self.get_text("app_main_status_ready"))
        self.auth_status_var = tk.StringVar(value="")
        self.runtime_status_var = tk.StringVar(value="")
        self.pot_status_var = tk.StringVar(value="")
        self.cookies_error_notified = False
        self.latest_auth_diagnostic = None
        cookies_path = self.get_ui_state_value("cookies", "file_path", default=COOKIES_DEFAULT_PATH)
        if not cookies_path:
            cookies_path = COOKIES_DEFAULT_PATH
        self.COOKIES_FILE_PATH = cookies_path
        self.latest_cookies_status = CookiesStatus(file_path=self.COOKIES_FILE_PATH)
        self.latest_runtime_issue = None
        self.input_frames = []
        self.clipboard_watch_var = tk.BooleanVar(value=self.get_ui_state_value("clipboard", "watch", default=False))
        self.clipboard_auto_parse_var = tk.BooleanVar(value=self.get_ui_state_value("clipboard", "auto_parse", default=False))
        self.clipboard_last_text = ""
        self.clipboard_last_url = ""
        self.clipboard_watch_var.trace_add('write', lambda *_args: self._on_clipboard_setting_change())
        self.clipboard_auto_parse_var.trace_add('write', lambda *_args: self._on_clipboard_setting_change())
        self.cookies_mode_var = tk.StringVar(value=self.get_ui_state_value("cookies", "mode", default="file"))
        self.cookies_browser_var = tk.StringVar(value=self.get_ui_state_value("cookies", "browser", default=""))
        self.download_retry_var = tk.StringVar(value=str(self.get_ui_state_value("downloads", "retry", default=3)))
        self.download_concurrent_var = tk.StringVar(value=str(self.get_ui_state_value("downloads", "concurrent", default=1)))
        self.download_speed_limit_var = tk.StringVar(value=str(self.get_ui_state_value("downloads", "speed_limit", default="2")))
        self.use_po_token_var = tk.BooleanVar(value=self.get_ui_state_value("pot", "enabled", default=False))
        
        self.cookies_mode_var.trace_add('write', lambda *_args: self._on_cookies_setting_change())
        self.cookies_browser_var.trace_add('write', lambda *_args: self._on_cookies_setting_change())
        self.use_po_token_var.trace_add('write', lambda *_args: self._on_pot_setting_change())
        
        self._settings_syncing = False
        self.default_cookies_mode = self.cookies_mode_var.get().strip() or "file"
        self.default_browser_cookies = self.cookies_browser_var.get().strip()
        self.default_use_po_token = bool(self.use_po_token_var.get())
        self._clipboard_poll_idle_ms = 2500
        self._clipboard_poll_busy_ms = 900

        self.refresh_all_statuses()

        self.FONT_FAMILY = FONT_FAMILY
        self.FONT_SIZE_TITLE = FONT_SIZE_TITLE
        self.FONT_SIZE_NORMAL = FONT_SIZE_NORMAL
        self.SilentMessagebox = SilentMessagebox
        self.detect_video_url_type = detect_video_url_type

    def _init_managers(self):
        self.metadata_service = YouTubeMetadataService(
            yt_dlp_path,
            self.COOKIES_FILE_PATH,
            startupinfo=startupinfo,
            cookies_mode=self.cookies_mode_var.get().strip(),
            cookies_browser=self.cookies_browser_var.get().strip(),
            use_po_token=self.use_po_token_var.get(),
        )
        debug_startup("metadata_service ready")
        self.ytdlp_manager = YouTubeDownloadManager(
            self,
            HISTORY_FILES['ytdlp'],
            yt_dlp_path,
            ffmpeg_path,
            self.COOKIES_FILE_PATH,
            startupinfo=startupinfo,
            max_concurrent=max(1, int((self.download_concurrent_var.get() or "1").strip() or 1)),
        )
        self.media_manager = MediaJobManager(
            self,
            ffmpeg_path,
            startupinfo=startupinfo,
            max_concurrent=1,
        )

    def _build_ui(self):
        self._create_bottom_bar()
        debug_startup("bottom bar created")
        self._create_notebook()
        debug_startup("notebook created")

    def _start_background_tasks(self):
        self._start_log_processors()
        debug_startup("log processors started")
        try:
            restored = self.ytdlp_manager.load_pending_tasks()
            if restored:
                self.ytdlp_manager.log(f"已恢复未完成任务: {restored} 个", "INFO")
        except Exception as exc:
            self.ytdlp_manager.log(f"恢复未完成任务失败: {exc}", "WARN")
        self._check_dependencies_and_log()
        debug_startup("dependency checks started")
        self.default_cookies_mode = self.cookies_mode_var.get().strip() if getattr(self, "cookies_mode_var", None) else "file"
        self.default_browser_cookies = self.cookies_browser_var.get().strip() if getattr(self, "cookies_browser_var", None) else ""
        from core.po_token_manager import get_manager as _get_pot_manager
        _get_pot_manager().initialize_async()
        debug_startup("po_token_manager initialized")

    def _bind_events(self):
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._start_clipboard_watch()

    def _on_pot_setting_change(self):
        """当 PO Token 设置变更时，同步到 UI 状态并通知 metadata 服务"""
        self._sync_settings_state(source="app")

    def _on_cookies_setting_change(self):
        self._sync_settings_state(source="app")

    def _on_clipboard_setting_change(self):
        self._sync_settings_state(source="app")

    # ============ (状态刷新) ============
    def refresh_all_statuses(self):
        """全量刷新各状态条"""
        self.refresh_auth_status()
        self.refresh_runtime_status()
        self.refresh_pot_status()

    def refresh_auth_status(self):
        """刷新认证状态显示"""
        try:
            status = getattr(self, "latest_cookies_status", None)
            diagnostic = getattr(self, "latest_auth_diagnostic", None)
            exists = status.exists if status else (os.path.exists(self.COOKIES_FILE_PATH) if self.COOKIES_FILE_PATH else False)
            mode = (self.cookies_mode_var.get() or "file").strip()
            browser = (self.cookies_browser_var.get() or "").strip()
            
            text = ""
            if diagnostic and not diagnostic.ok:
                summary = (getattr(diagnostic, "summary", "") or "").strip()
                if summary == "未检测到本地 Cookies 文件 (选填)":
                    summary = self.get_text("app_cookies_missing_optional")
                text = self.get_text("topbar_auth_error").format(summary=summary)
            elif mode == "browser":
                text = self.get_text("topbar_auth_browser").format(browser=browser or "-")
            elif exists:
                text = self.get_text("topbar_auth_file_configured")
            elif status and getattr(status, "last_message", "") and status.last_message != self.get_text("auth_last_check_none"):
                message = (status.last_message or "").strip()
                if message == "未检测到本地 Cookies 文件 (选填)":
                    message = self.get_text("app_cookies_missing_optional")
                text = self.get_text("topbar_auth_last_message").format(message=message)
            else:
                text = self.get_text("topbar_auth_unconfigured")
            
            self.auth_status_var.set(text)
        except Exception:
            self.auth_status_var.set(self.get_text("topbar_auth_unconfigured"))

    def refresh_runtime_status(self):
        """刷新运行环境状态显示"""
        issue = getattr(self, "latest_runtime_issue", None) or {}
        summary = (issue.get("summary") or "").strip()
        
        # 优化显示逻辑，不再尝试对此处已翻译的内容进行二次翻译匹配
        if not summary or summary == "就绪" or summary.lower() == "ready" or summary == self.get_text("app_main_status_ready"):
            text = self.get_text("topbar_runtime_ok")
        else:
            # 如果 summary 已经是带翻译键构造的 (如 "发布资源缺失: ...")，直接显示即可
            # 这里的 summary 已经在检测线程内部通过 get_text 构造好了
            text = self.get_text("topbar_runtime_issue").format(summary=summary)
            
        self.runtime_status_var.set(text)

    def refresh_pot_status(self):
        """刷新 PO Token 状态显示"""
        from core.po_token_manager import get_manager as _get_pot_manager
        code, _msg = _get_pot_manager().get_status()
        icons = {
            "unknown": "⏳",
            "no_node": "❌",
            "old_node": "⚠️",
            "installing": "⏳",
            "retry_wait": "⏳",
            "ready": "✅",
            "error": "❌",
            "disabled": "",
        }
        icon = icons.get(code, "⏳")
        if code == "disabled":
            text = self.get_text("pot_status_disabled").format(icon=icon)
        elif code == "ready":
            text = self.get_text("pot_status_ready").format(icon=icon)
        elif code == "no_node":
            text = self.get_text("pot_status_no_node").format(icon=icon)
        elif code == "old_node":
            text = self.get_text("pot_status_old_node").format(icon=icon)
        elif code == "installing":
            text = self.get_text("pot_status_installing").format(icon=icon)
        elif code == "retry_wait":
            text = self.get_text("pot_status_retry_wait").format(icon=icon)
        elif code == "error":
            text = self.get_text("pot_status_error").format(icon=icon)
        else:
            text = self.get_text("pot_status_checking").format(icon=icon)
        
        self.pot_status_var.set(text)

    def _start_clipboard_watch(self):
        def poll_clipboard(delay_ms=None):
            interval = self._clipboard_poll_idle_ms if delay_ms is None else delay_ms
            if not self.clipboard_watch_var.get():
                self.root.after(self._clipboard_poll_idle_ms, poll_clipboard)
                return

            handled = False
            try:
                text = self.root.clipboard_get().strip()
            except Exception:
                text = ""

            if text and text != self.clipboard_last_text:
                self.clipboard_last_text = text
                if self.detect_video_url_type(text) == "youtube" and text != self.clipboard_last_url:
                    self.clipboard_last_url = text
                    for frame in list(self.input_frames):
                        try:
                            if not hasattr(frame, "url_entry"):
                                continue
                            current_text = frame.url_entry.get("1.0", "end-1c").strip()
                            if current_text:
                                continue
                            frame.url_entry.delete("1.0", "end")
                            frame.url_entry.insert("1.0", text)
                            if getattr(self, "clipboard_auto_parse_var", None) and self.clipboard_auto_parse_var.get():
                                if hasattr(frame, "fetch_formats"):
                                    frame.fetch_formats()
                            handled = True
                            break
                        except Exception as exc:
                            _debug_exception("clipboard sync failed", exc)

            next_interval = self._clipboard_poll_busy_ms if handled else self._clipboard_poll_idle_ms
            self.root.after(next_interval, poll_clipboard)

        def on_paste_event(_event=None):
            self.root.after(120, poll_clipboard, self._clipboard_poll_busy_ms)

        try:
            self.root.bind_all("<<Paste>>", on_paste_event)
        except Exception as exc:
            _debug_exception("bind <<Paste>> failed", exc)

        self.root.after(self._clipboard_poll_idle_ms, poll_clipboard)

    def _create_top_bar(self):
        """顶部工具栏已迁移到设置页，保留空入口兼容旧调用。"""
        self.top_bar = None

    def _create_notebook(self):
        """创建标签页"""
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(padx=10, expand=True, fill="both")

        DownloadTab(self.notebook, self, self.get_text("tab_single"), self.ytdlp_manager, UnifiedVideoInputFrame)
        DownloadTab(self.notebook, self, self.get_text("tab_batch"), self.ytdlp_manager, BatchSourceInputFrame)
        QueueTab(self.notebook, self, self.ytdlp_manager)
        MediaToolsPage(self.notebook, self, self.media_manager)
        self.history_page = HistoryPage(self.notebook, self)
        self.settings_page = SettingsPage(self.notebook, self)
        self.top_bar = self.settings_page
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

    def _create_bottom_bar(self):
        """创建底部保存路径栏"""
        self.bottom_bar = BottomBar(self.root, self)

    def register_input_frame(self, frame):
        """登记输入页实例，供关闭保护统一检查页面状态。"""
        if frame and frame not in self.input_frames:
            self.input_frames.append(frame)
        self.ytdlp_manager.input_frame = frame
        if frame and getattr(frame, "clipboard_auto_parse_var", None) is None:
            frame.clipboard_auto_parse_var = self.clipboard_auto_parse_var
        if frame and getattr(frame, "cookies_mode_var", None):
            frame.cookies_mode_var.set(self.default_cookies_mode)
        if frame and getattr(frame, "cookies_browser_var", None):
            frame.cookies_browser_var.set(self.default_browser_cookies)

        if frame and getattr(frame, "cookies_mode_var", None) and not getattr(frame, "_cookies_sync_bound", False):
            def sync_from_frame(*_args):
                self._sync_settings_state(source="frame", frame=frame)

            add_trace_helper = getattr(frame, "_add_trace", lambda var, mode, cb: var.trace_add(mode, cb))
            add_trace_helper(frame.cookies_mode_var, 'write', lambda *_args: sync_from_frame())
            if getattr(frame, "cookies_browser_var", None):
                add_trace_helper(frame.cookies_browser_var, 'write', lambda *_args: sync_from_frame())
            frame._cookies_sync_bound = True

    def get_ui_state_value(self, *keys, default=None):
        current = self.ui_state if isinstance(self.ui_state, dict) else {}
        for key in keys:
            if not isinstance(current, dict):
                return default
            current = current.get(key)
        return default if current is None else current

    def get_text(self, key, fallback=""):
        return tr(key, self.current_lang, fallback=fallback)

    def set_language(self, lang_code):
        normalized = normalize_lang(lang_code)
        if normalized == self.current_lang:
            debug_startup(f"set_language skipped current={self.current_lang} requested={lang_code!r} normalized={normalized}")
            return
        previous_lang = self.current_lang
        self.current_lang = normalized
        self.set_ui_state_value("i18n", "lang", value=normalized)
        debug_startup(
            f"set_language changed previous={previous_lang} current={self.current_lang} "
            f"ui_state_lang={self.get_ui_state_value('i18n', 'lang', default=None)!r}"
        )
        self.save_ui_state()
        try:
            self.root.title(tr("app_title", self.current_lang))
        except Exception as exc:
            _debug_exception("set_language title refresh failed", exc)
        self._rebuild_ui_for_language()

    def _rebuild_ui_for_language(self):
        current_tab_index = 0
        try:
            if getattr(self, "notebook", None):
                current_tab_index = self.notebook.index(self.notebook.select())
        except Exception as exc:
            _debug_exception("rebuild_ui read current tab failed", exc)
            current_tab_index = 0

        # Avoid inserting logs into stale widgets while rebuilding.
        if getattr(self, "ytdlp_manager", None):
            self.ytdlp_manager.task_tree = None
            self.ytdlp_manager.log_text = None
        if getattr(self, "media_manager", None):
            self.media_manager.job_tree = None
            self.media_manager.log_text = None

        for attr_name in ("top_bar", "bottom_bar", "notebook"):
            widget = getattr(self, attr_name, None)
            if widget:
                try:
                    widget.destroy()
                except Exception as exc:
                    _debug_exception(f"rebuild_ui destroy {attr_name} failed", exc)
                setattr(self, attr_name, None)

        self.input_frames = []
        self._create_bottom_bar()
        self._create_notebook()
        try:
            if getattr(self, "notebook", None):
                tab_count = len(self.notebook.tabs())
                if tab_count:
                    self.notebook.select(min(current_tab_index, tab_count - 1))
        except Exception as exc:
            _debug_exception("rebuild_ui restore tab failed", exc)
        if hasattr(self, "top_bar"):
            self.refresh_all_statuses()

    def _sync_settings_state(self, source="app", frame=None):
        if getattr(self, "_settings_syncing", False):
            return
        self._settings_syncing = True
        try:
            if source == "frame" and frame is not None:
                mode = frame.cookies_mode_var.get().strip() if getattr(frame, "cookies_mode_var", None) else "file"
                browser = frame.cookies_browser_var.get().strip() if getattr(frame, "cookies_browser_var", None) else ""
                use_pot = bool(frame.use_po_token_var.get()) if getattr(frame, "use_po_token_var", None) else False
                
                if mode and mode != self.cookies_mode_var.get():
                    self.cookies_mode_var.set(mode)
                if browser != self.cookies_browser_var.get():
                    self.cookies_browser_var.set(browser)
                if use_pot != self.use_po_token_var.get():
                    self.use_po_token_var.set(use_pot)
            else:
                mode = self.cookies_mode_var.get().strip() if getattr(self, "cookies_mode_var", None) else "file"
                browser = self.cookies_browser_var.get().strip() if getattr(self, "cookies_browser_var", None) else ""

            self.default_cookies_mode = mode or "file"
            self.default_browser_cookies = browser
            self.set_ui_state_value("cookies", "mode", value=self.default_cookies_mode)
            self.set_ui_state_value("cookies", "browser", value=self.default_browser_cookies)
            self.set_ui_state_value("cookies", "file_path", value=self.COOKIES_FILE_PATH)
            self.set_ui_state_value("clipboard", "watch", value=bool(self.clipboard_watch_var.get()))
            self.set_ui_state_value("clipboard", "auto_parse", value=bool(self.clipboard_auto_parse_var.get()))
            self.set_ui_state_value("downloads", "retry", value=max(0, int((self.download_retry_var.get() or "3").strip() or 3)))
            self.set_ui_state_value("downloads", "concurrent", value=max(1, int((self.download_concurrent_var.get() or "1").strip() or 1)))
            self.set_ui_state_value("downloads", "speed_limit", value=max(0, int((self.download_speed_limit_var.get() or "0").strip() or 0)))
            self.save_ui_state()
            if getattr(self, "metadata_service", None):
                try:
                    self.metadata_service.update_cookies_settings(self.default_cookies_mode, self.default_browser_cookies)
                except Exception as exc:
                    _debug_exception("sync_settings update metadata cookies failed", exc)
            for target in getattr(self, "input_frames", []) or []:
                if not target:
                    continue
                if getattr(target, "cookies_mode_var", None):
                    target.cookies_mode_var.set(self.default_cookies_mode)
                if getattr(target, "cookies_browser_var", None):
                    target.cookies_browser_var.set(self.default_browser_cookies)
                if getattr(target, "use_po_token_var", None):
                    target.use_po_token_var.set(self.default_use_po_token)
        finally:
            self._settings_syncing = False

    def set_ui_state_value(self, *keys, value):
        if not keys:
            return
        if not isinstance(self.ui_state, dict):
            self.ui_state = {}
        current = self.ui_state
        for key in keys[:-1]:
            next_value = current.get(key)
            if not isinstance(next_value, dict):
                next_value = {}
                current[key] = next_value
            current = next_value
        current[keys[-1]] = value

    def save_ui_state(self):
        try:
            debug_startup(
                f"save_ui_state lang={self.get_ui_state_value('i18n', 'lang', default=None)!r} "
                f"ui_state_keys={sorted(self.ui_state.keys()) if isinstance(self.ui_state, dict) else 'non-dict'}"
            )
            self.position_repo.save_ui_state(self.root, self.ui_state)
        except Exception as exc:
            _debug_exception("save_ui_state failed", exc)

    def _on_tab_changed(self, _event=None):
        current = None
        if getattr(self, "notebook", None):
            current = self.notebook.select()
        active_frame = None
        for frame in self.input_frames:
            try:
                if frame and str(frame) == str(current):
                    active_frame = frame
                    break
            except Exception:
                continue
        if active_frame and getattr(active_frame, "cookies_mode_var", None):
            self.default_cookies_mode = active_frame.cookies_mode_var.get().strip() or "file"
        if active_frame and getattr(active_frame, "cookies_browser_var", None):
            self.default_browser_cookies = active_frame.cookies_browser_var.get().strip()
        if active_frame and getattr(active_frame, "use_po_token_var", None):
            self.default_use_po_token = bool(active_frame.use_po_token_var.get())

    def _start_log_processors(self):
        """启动所有管理器的日志队列处理器"""
        self.root.after(100, self.ytdlp_manager.process_log_queue)
        if getattr(self, "media_manager", None):
            self.root.after(120, self.media_manager.process_log_queue)

    def _check_dependencies_and_log(self):
        """检测并记录启动环境状态到实时日志"""
        self.ytdlp_manager.log(self.get_text("app_env_check_start"))
        
        # 1. 检测 yt-dlp
        def check_ytdlp():
            try:
                # 使用 subprocess.run 检测版本
                res = subprocess.run([yt_dlp_path, "--version"], capture_output=True, text=True, startupinfo=startupinfo, timeout=10)
                if res.returncode == 0:
                    self.ytdlp_manager.log(
                        self.get_text("app_ytdlp_ready").format(version=res.stdout.strip()),
                        "SUCCESS",
                    )
                else:
                    self.ytdlp_manager.log(self.get_text("app_ytdlp_issue"), "WARN")
            except Exception as e:
                self.ytdlp_manager.log(self.get_text("app_ytdlp_missing").format(error=e), "ERROR")

        # 2. 检测 ffmpeg
        def check_ffmpeg():
            try:
                res = subprocess.run([ffmpeg_path, "-version"], capture_output=True, text=True, startupinfo=startupinfo, timeout=10)
                if res.returncode == 0:
                    ver = res.stdout.strip().split('\n')[0]
                    # 简化 ffmpeg 输出，只取第一段
                    if ver.startswith("ffmpeg version"):
                        ver = ver.split("Copyright")[0].strip()
                    self.ytdlp_manager.log(
                        self.get_text("app_ffmpeg_ready").format(version=ver),
                        "SUCCESS",
                    )
                else:
                    self.ytdlp_manager.log(self.get_text("app_ffmpeg_issue"), "WARN")
            except Exception:
                self.ytdlp_manager.log(self.get_text("app_ffmpeg_missing"), "ERROR")

        def check_deno():
            deno_status = self.components_manager.check_deno()
            if deno_status.ok:
                self.ytdlp_manager.log(
                    self.get_text("app_deno_ready").format(version=deno_status.version),
                    "SUCCESS",
                )
                return
            if deno_status.message:
                self.ytdlp_manager.log(
                    f"{self.get_text('app_deno_issue')} ({deno_status.message})",
                    "WARN",
                )
            else:
                self.ytdlp_manager.log(self.get_text("app_deno_missing"), "ERROR")

        def check_release_bundle():
            # 在源码运行环境（开发模式）下，不检测 docs 和 sample_hook 等非二进制资源
            from core.release_validator import REQUIRED_DATA_FILES, validate_release_bundle
            is_dev = not getattr(sys, "frozen", False)
            result = validate_release_bundle(base_path, only_binaries=is_dev)
            if not is_dev and result["missing"]:
                resolved_missing = []
                for item in result["missing"]:
                    if item in REQUIRED_DATA_FILES and os.path.exists(get_resource_path(item)):
                        continue
                    resolved_missing.append(item)
                result["missing"] = resolved_missing
                result["ok"] = not resolved_missing
            if result["ok"]:
                self.ytdlp_manager.log(self.get_text("app_bundle_ready"), "SUCCESS")
                return

            missing_items = ", ".join(result["missing"])
            summary = self.get_text("app_bundle_missing").format(items=missing_items)
            detail = self.get_text("app_bundle_check_detail").format(root=result["root"])
            self.latest_runtime_issue = {
                "summary": summary,
                "detail": detail,
                "level": "WARN",
                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            self.ytdlp_manager.log(summary, "WARN")
            self.ytdlp_manager.log(detail, "WARN")

        # 3. 检测 Cookies & PO Token
        def check_others():
            # Cookies
            cookies_status = getattr(self, "latest_cookies_status", None)
            if cookies_status is None:
                cookies_status = CookiesStatus(file_path=self.COOKIES_FILE_PATH)
                self.latest_cookies_status = cookies_status
            if self.COOKIES_FILE_PATH and os.path.exists(self.COOKIES_FILE_PATH):
                cookies_status.exists = True
                cookies_status.last_message = self.get_text("app_cookies_exists")
                cookies_status.status = "ok"
                self.ytdlp_manager.log(
                    self.get_text("app_cookies_loaded").format(filename=os.path.basename(self.COOKIES_FILE_PATH)),
                    "INFO",
                )
            else:
                cookies_status.mark_missing(
                    self.get_text("app_cookies_missing_optional"),
                    self.get_text("app_cookies_missing_hint"),
                )
                self.ytdlp_manager.log(self.get_text("app_cookies_missing_optional"), "INFO")

            if hasattr(self, "top_bar"):
                try:
                    self.root.after(0, self.top_bar.refresh_auth_status)
                except Exception as exc:
                    _debug_exception("refresh_auth_status after failed", exc)

            # PO Token
            from core.po_token_manager import get_manager as _get_pot_manager
            pot_manager = _get_pot_manager()
            status, msg = pot_manager.get_status()
            self.ytdlp_manager.log(
                self.get_text("app_pot_initial_status").format(status=status, message=msg),
                "INFO",
            )
            
            # 状态变更监听：直接在日志更新
            pot_manager.on_status_change(
                lambda code, message: self.ytdlp_manager.log(
                    self.get_text("app_pot_status_update").format(status=code, message=message),
                    "INFO",
                )
            )

        # 后台执行耗时检测，不阻塞UI渲染
        threads = [
            threading.Thread(target=check_ytdlp, daemon=True),
            threading.Thread(target=check_ffmpeg, daemon=True),
            threading.Thread(target=check_deno, daemon=True),
            threading.Thread(target=check_release_bundle, daemon=True),
            threading.Thread(target=check_others, daemon=True),
        ]
        
        def run_and_refresh():
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=15)
            # 全量检测完成后立即刷新 UI
            self.root.after(0, self.refresh_all_statuses)

        threading.Thread(target=run_and_refresh, daemon=True).start()

    def _on_close(self):
        """关闭窗口时保存位置并检查运行中的任务"""
        if getattr(self, "_closing", False):
            return
        self._closing = True

        # 记录真实活动任务数量（在状态强制重构之前）
        with self.ytdlp_manager._state_lock:
            running_count = len(self.ytdlp_manager.running_tasks)
            # 只有真正的“等待中”才计入退出提示的等待数
            waiting_count = sum(1 for t in self.ytdlp_manager.task_queue if getattr(t, "status", None) == TASK_STATUS_WAITING)

        # 关闭前将运行中和非终止任务统一标记为 WAITING，确保下一次启动能恢复
        try:
            with self.ytdlp_manager._state_lock:
                for task in self.ytdlp_manager.running_tasks.values():
                    if getattr(task, "status", None) not in {TASK_STATUS_SUCCESS, TASK_STATUS_FAILED}:
                        task.status = TASK_STATUS_WAITING
                for task in self.ytdlp_manager.task_queue:
                    if getattr(task, "status", None) not in {TASK_STATUS_SUCCESS, TASK_STATUS_FAILED}:
                        task.status = TASK_STATUS_WAITING
        except Exception:
            pass
        busy_states = []
        if running_count > 0:
            busy_states.append(self.get_text("close_busy_running").format(count=running_count))
        if waiting_count > 0:
            busy_states.append(self.get_text("close_busy_waiting").format(count=waiting_count))
        if self.yt_dlp_update_in_progress:
            busy_states.append(self.get_text("close_busy_updating"))

        active_frames = []
        seen_frame_ids = set()
        for frame in list(getattr(self, 'input_frames', []) or []):
            if frame is None:
                continue
            frame_id = id(frame)
            if frame_id in seen_frame_ids:
                continue
            seen_frame_ids.add(frame_id)
            active_frames.append(frame)

        for input_frame in active_frames:
            if getattr(input_frame, '_fetch_in_progress', False):
                busy_states.append(self.get_text("close_busy_batch_fetch"))
            if getattr(input_frame, '_enqueue_in_progress', False):
                busy_states.append(self.get_text("close_busy_batch_enqueue"))

        if busy_states:
            result = SilentMessagebox.askyesno(
                self.get_text("close_confirm_title"),
                self.get_text("close_confirm_message").format(items="- " + "\n- ".join(busy_states)),
                parent=self.root
            )
            if not result:
                self._closing = False
                return

            for input_frame in active_frames:
                if getattr(input_frame, '_fetch_in_progress', False):
                    self.latest_runtime_issue = {
                        "summary": self.get_text("runtime_issue_close_batch_fetch_summary"),
                        "detail": self.get_text("runtime_issue_close_batch_fetch_detail"),
                        "level": "WARN",
                        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                    }
                if getattr(input_frame, '_enqueue_in_progress', False):
                    self.latest_runtime_issue = {
                        "summary": self.get_text("runtime_issue_close_batch_enqueue_summary"),
                        "detail": self.get_text("runtime_issue_close_batch_enqueue_detail"),
                        "level": "WARN",
                        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                    }

            self.ytdlp_manager.save_pending_tasks()
            self.ytdlp_manager.stop_all()
            self.root.after(200, self._finalize_close)
            return

        try:
            self.ytdlp_manager.save_pending_tasks()
        except Exception:
            pass
        self._finalize_close()

    def _finalize_close(self):
        if getattr(self, "_close_finalized", False):
            return
        self._close_finalized = True
        try:
            self.save_ui_state()
            save_window_pos(self.root, self.position_repo, extra_state=self.ui_state)
        finally:
            self.root.destroy()

    # --- (重构) 核心UI构建函数 ---

    # --- (重构) UI 辅助方法 ---
    def load_history(self, mode):
        """加载指定模式的历史记录到 self.current_history_data"""
        load_history(self, mode)
 
    def show_history(self):
        """(重构) 显示 self.current_history_data"""
        show_history(self)

    def show_history_window(self, mode='ytdlp'):
        """加载并打开指定模式的历史窗口。"""
        self.load_history(mode)
        self.show_history()
    
    def clear_all_history(self, mode):
        """清空指定模式的全部历史记录"""
        clear_all_history(self, mode)

    def show_auth_status(self):
        """显示认证状态窗口。"""
        show_auth_status(self)
        if hasattr(self, 'top_bar'):
            self.top_bar.refresh_auth_status()

    def show_runtime_status(self):
        """显示运行状态窗口。"""
        show_runtime_status(self)

    def choose_directory(self):
        """(重构) 选择保存文件夹"""
        choose_directory(self)

    def open_save_directory(self):
        """(重构) 打开当前设置的保存目录"""
        open_save_directory(self)

    def update_yt_dlp(self):
        """(重构) 更新 yt-dlp.exe"""
        update_yt_dlp(self, yt_dlp_path)

    def show_components_center(self):
        """组件中心窗口入口。"""
        ComponentsCenterWindow(self)

    def notify_cookies_error(self, diagnostic=None):
        """提示认证/Cookies问题（仅认证类问题提示一次）。"""
        self.latest_auth_diagnostic = diagnostic
        notify_cookies_error(self, diagnostic=diagnostic)

    def show_usage_introduction(self):
        """显示程序功能及使用说明窗口。"""
        doc_filename = "usage_intro_en.md" if normalize_lang(self.current_lang) == "en" else "usage_intro.md"
        doc_path = get_resource_path(doc_filename)
        if not os.path.exists(doc_path):
            self.SilentMessagebox.showerror(
                self.get_text("common_error"),
                self.get_text("usage_missing").format(path=doc_path),
                parent=self.root,
            )
            return

        try:
            with open(doc_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            self.SilentMessagebox.showerror(
                self.get_text("common_error"),
                self.get_text("usage_read_fail").format(error=e),
                parent=self.root,
            )
            return

        dialog = tk.Toplevel(self.root)
        dialog.title(self.get_text("usage_title"))
        dialog.geometry("900x750")
        dialog.configure(bg=UI_COLORS["bg_secondary"])
        dialog.transient(self.root)
        dialog.grab_set()

        # 居中窗口
        dialog.update_idletasks()
        pw = dialog.winfo_screenwidth()
        ph = dialog.winfo_screenheight()
        dialog.geometry(f"900x750+{int((pw-900)/2)}+{int((ph-750)/2)}")

        main_frame = ttk.Frame(dialog, padding="20")
        main_frame.pack(expand=True, fill="both")

        text_area = tk.Text(
            main_frame,
            wrap="word",
            font=(self.FONT_FAMILY, 9),
            bg=UI_COLORS["bg_secondary"],
            fg=UI_COLORS["text_primary"],
            relief="flat",
            padx=20,
            pady=20,
            spacing1=2, # 段落上方间距
            spacing3=2  # 段落下方间距
        )
        scrollbar = tk.Scrollbar(
            main_frame,
            orient="vertical",
            command=text_area.yview,
            width=14,
            relief="flat",
            bd=0,
            highlightthickness=0,
            bg="#f0f0f0",
            activebackground="#d9d9d9",
            troughcolor=UI_COLORS["bg_main"],
        )
        text_area.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        text_area.pack(side="left", expand=True, fill="both")

        # 样式标签配置
        text_area.tag_configure("bold", font=(self.FONT_FAMILY, 9, "bold"))
        text_area.tag_configure("h1", font=(self.FONT_FAMILY, 15, "bold"), foreground=UI_COLORS["primary"], spacing1=15, spacing3=12)
        text_area.tag_configure("h2", font=(self.FONT_FAMILY, 12, "bold"), foreground="#262626", spacing1=12, spacing3=8)
        text_area.tag_configure("h3", font=(self.FONT_FAMILY, 10, "bold"), foreground="#434343", spacing1=8, spacing3=4)
        text_area.tag_configure("list", lmargin1=20, lmargin2=35) # 列表缩进
        text_area.tag_configure("hr", font=(self.FONT_FAMILY, 2), background=UI_COLORS["border"], spacing1=10, spacing3=10)

        lines = content.split("\n")
        for line in lines:
            line = line.rstrip()
            if line.startswith("# "):
                text_area.insert("end", line[2:] + "\n", "h1")
            elif line.startswith("## "):
                text_area.insert("end", line[3:] + "\n", "h2")
            elif line.startswith("### "):
                text_area.insert("end", line[4:] + "\n", "h3")
            elif line.startswith("---"):
                text_area.insert("end", " " * 100 + "\n", "hr")
            elif line.strip().startswith(("- ", "* ", "1. ", "2. ", "3. ", "4. ", "5. ")):
                # 列表渲染
                prefix = ""
                if line.startswith("    "):
                    prefix = "    "
                    line = line.strip()
                self._insert_styled_text(text_area, prefix + line + "\n", "list")
            else:
                self._insert_styled_text(text_area, line + "\n")

        text_area.configure(state="disabled")

        btn_frame = ttk.Frame(dialog, padding=(0, 15))
        btn_frame.pack(fill="x")
        ttk.Button(btn_frame, text=self.get_text("usage_button_ack"), command=dialog.destroy, style="Primary.TButton").pack()

    def _insert_styled_text(self, text_widget, text, base_tag=None):
        """解析并插入带样式的文本（如加粗）。"""
        parts = text.split("**")
        for i, part in enumerate(parts):
            tags = []
            if base_tag:
                tags.append(base_tag)
            if i % 2 == 1:
                tags.append("bold")
            
            text_widget.insert("end", part, tuple(tags))


if __name__ == '__main__':
    run_app(DownloadApplication)
