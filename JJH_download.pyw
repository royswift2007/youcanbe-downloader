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

from core.download_manager import YouTubeDownloadManager
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
)
from ui.app_actions import choose_directory, notify_cookies_error, open_save_directory, update_yt_dlp
from ui.queue_tab import QueueTab
from ui.bootstrap import debug_startup, run_app, setup_styles
from ui.download_tab import DownloadTab
from ui.history_actions import clear_all_history, load_history, show_auth_status, show_history, show_runtime_status
from ui.pages.batch_source import BatchSourceInputFrame
from ui.pages.single_video import UnifiedVideoInputFrame
from ui.app_shell import BottomBar, TopBar


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

yt_dlp_path = os.path.join(base_path, "yt-dlp.exe")  # yt-dlp下载工具路径
ffmpeg_path = os.path.join(base_path, "ffmpeg.exe")  # ffmpeg音视频处理工具路径
CONFIG_FILE = os.path.join(base_path, "window_pos.json")  # 窗口位置配置文件

# [新增] Cookies 文件路径定义
COOKIES_FILE_PATH = os.path.join(base_path, "www.youtube.com_cookies.txt")  # YouTube Cookies文件路径

startupinfo = None
if os.name == "nt":
    startupinfo = subprocess.STARTUPINFO()
    try:
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    except AttributeError:
        startupinfo.dwFlags |= 1

# ---------------- 配置 & 历史文件路径 ----------------
HISTORY_FILES = {
    'ytdlp': os.path.join(base_path, "download_history_ytdlp.json"),
}

LAST_SAVE_PATH_DEFAULT = os.path.expanduser("~/Downloads")  # 默认保存路径：用户下载文件夹

# ============ 静音消息框替代类 ============
class SilentMessagebox:
    """静音消息框替代类 - 无系统提示音"""
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
        tk.Button(btn_frame, text="确定", command=dialog.destroy, 
                 bg="#e6f7ff", relief='flat', padx=15, font=("Microsoft YaHei", 9)).pack(pady=5)
        SilentMessagebox._show_modal(dialog, parent)

    @staticmethod
    def showwarning(title, message, parent=None):
        dialog, btn_frame = SilentMessagebox._create_dialog(title, message)
        tk.Button(btn_frame, text="确定", command=dialog.destroy, 
                 bg="#fff7e6", relief='flat', padx=15, font=("Microsoft YaHei", 9)).pack(pady=5)
        SilentMessagebox._show_modal(dialog, parent)

    @staticmethod
    def showerror(title, message, parent=None):
        dialog, btn_frame = SilentMessagebox._create_dialog(title, message)
        tk.Button(btn_frame, text="确定", command=dialog.destroy, 
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
            
        tk.Button(btn_frame, text="是", command=on_yes, 
                 bg="#e6f7ff", relief='flat', padx=15, width=6).pack(side='left', padx=20, expand=True)
        tk.Button(btn_frame, text="否", command=on_no, 
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
            height = int(pos.get('height', 750) or 750)
            width = max(900, min(width, screen_width))
            height = max(600, min(height, screen_height))
            x = max(0, (screen_width - width) // 2)
            y = max(0, (screen_height - height) // 2)
            root_window.geometry(f"{width}x{height}+{x}+{y}")
            return

        geo = f"{pos['width']}x{pos['height']}+{pos['x']}+{pos['y']}"
        root_window.geometry(geo)
    except Exception:
        pass

def save_window_pos(root_window, position_repo):
    """保存窗口位置"""
    try:
        position_repo.save(root_window)
    except Exception:
        pass

def detect_video_url_type(url):
    """检测并归类输入链接，目前仅支持 YouTube。"""
    normalized_url = (url or "").strip().lower()
    if 'youtube.com' in normalized_url or 'youtu.be' in normalized_url:
        return 'youtube'
    return 'unsupported'

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
        self.root.title("JJH YouTube Downloader - 20260308")
        self.root.geometry("1400x750")
        self.root.minsize(1200, 600)  # 设置最小窗口尺寸
        self.position_repo = WindowPositionRepository(CONFIG_FILE)
        self.ui_state = self.position_repo.get_ui_state()
        load_window_pos(self.root, self.position_repo)
        debug_startup("window position loaded")
        self.yt_dlp_update_in_progress = False

        self.HISTORY_FILES = HISTORY_FILES
        
        # 加载历史记录时使用
        self.current_history_data = []
        
        # --- 初始化共享状态变量 ---
        self.shared_save_dir_var = tk.StringVar(value=LAST_SAVE_PATH_DEFAULT)
        self.main_status_var = tk.StringVar(value="就绪")
        self.cookies_error_notified = False
        self.latest_auth_diagnostic = None
        self.latest_cookies_status = None
        self.latest_runtime_issue = None
        self.input_frames = []

        self.FONT_FAMILY = FONT_FAMILY
        self.FONT_SIZE_TITLE = FONT_SIZE_TITLE
        self.FONT_SIZE_NORMAL = FONT_SIZE_NORMAL
        self.SilentMessagebox = SilentMessagebox
        self.detect_video_url_type = detect_video_url_type
        self.COOKIES_FILE_PATH = COOKIES_FILE_PATH
        
        # --- 初始化任务管理器 ---
        self.metadata_service = YouTubeMetadataService(yt_dlp_path, COOKIES_FILE_PATH, startupinfo=startupinfo)
        debug_startup("metadata_service ready")
        self.ytdlp_manager = YouTubeDownloadManager(
            self,
            HISTORY_FILES['ytdlp'],
            yt_dlp_path,
            ffmpeg_path,
            COOKIES_FILE_PATH,
            startupinfo=startupinfo,
            max_concurrent=2,
        )
        
        # --- 构建UI ---
        self._create_top_bar()
        debug_startup("top bar created")
        self._create_bottom_bar()
        debug_startup("bottom bar created")
        self._create_notebook()
        debug_startup("notebook created")
        
        # --- 启动后台进程 ---
        self._start_log_processors()
        debug_startup("log processors started")

        # --- 环境与依赖自检 ---
        self._check_dependencies_and_log()
        debug_startup("dependency checks started")

        # --- 启动 PO Token 管理器（后台检测 Node.js）---
        from core.po_token_manager import get_manager as _get_pot_manager
        _get_pot_manager().initialize_async()
        debug_startup("po_token_manager initialized")
        
        # --- 绑定关闭事件 ---
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        debug_startup("DownloadApplication.__init__ done")

    def _create_top_bar(self):
        """创建顶部工具栏 - 紧凑布局"""
        self.top_bar = TopBar(self.root, self)

    def _create_notebook(self):
        """创建标签页"""
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(padx=10, expand=True, fill="both")

        DownloadTab(self.notebook, self, '📺 单视频下载', self.ytdlp_manager, UnifiedVideoInputFrame)
        DownloadTab(self.notebook, self, '📚 播放列表 / 频道', self.ytdlp_manager, BatchSourceInputFrame)
        QueueTab(self.notebook, self, self.ytdlp_manager)

    def _create_bottom_bar(self):
        """创建底部保存路径栏"""
        self.bottom_bar = BottomBar(self.root, self)

    def register_input_frame(self, frame):
        """登记输入页实例，供关闭保护统一检查页面状态。"""
        if frame and frame not in self.input_frames:
            self.input_frames.append(frame)
        self.ytdlp_manager.input_frame = frame

    def get_ui_state_value(self, *keys, default=None):
        current = self.ui_state if isinstance(self.ui_state, dict) else {}
        for key in keys:
            if not isinstance(current, dict):
                return default
            current = current.get(key)
        return default if current is None else current

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
            self.position_repo.save_ui_state(self.root, self.ui_state)
        except Exception:
            pass

    def _start_log_processors(self):
        """启动所有管理器的日志队列处理器"""
        self.root.after(100, self.ytdlp_manager.process_log_queue)

    def _check_dependencies_and_log(self):
        """检测并记录启动环境状态到实时日志"""
        self.ytdlp_manager.log("正在检测运行环境...")
        
        # 1. 检测 yt-dlp
        def check_ytdlp():
            try:
                # 使用 subprocess.run 检测版本
                res = subprocess.run([yt_dlp_path, "--version"], capture_output=True, text=True, startupinfo=startupinfo, timeout=10)
                if res.returncode == 0:
                    self.ytdlp_manager.log(f"[完成] yt-dlp 环境就绪 (版本: {res.stdout.strip()})", "SUCCESS")
                else:
                    self.ytdlp_manager.log("yt-dlp 检测异常，请通过右上角按钮尝试更新", "WARN")
            except Exception as e:
                self.ytdlp_manager.log(f"未检测到 yt-dlp.exe: {e}", "ERROR")

        # 2. 检测 ffmpeg
        def check_ffmpeg():
            try:
                res = subprocess.run([ffmpeg_path, "-version"], capture_output=True, text=True, startupinfo=startupinfo, timeout=10)
                if res.returncode == 0:
                    ver = res.stdout.strip().split('\n')[0]
                    # 简化 ffmpeg 输出，只取第一段
                    if ver.startswith("ffmpeg version"):
                        ver = ver.split("Copyright")[0].strip()
                    self.ytdlp_manager.log(f"[完成] ffmpeg 环境就绪 ({ver})", "SUCCESS")
                else:
                    self.ytdlp_manager.log("ffmpeg 检测异常，部分格式合并可能受限", "WARN")
            except Exception:
                self.ytdlp_manager.log("未检测到 ffmpeg.exe，视频合并功能将不可用", "ERROR")

        # 3. 检测 Cookies & PO Token
        def check_others():
            # Cookies
            if os.path.exists(self.COOKIES_FILE_PATH):
                self.ytdlp_manager.log(f"已加载本地 Cookies 文件: {os.path.basename(self.COOKIES_FILE_PATH)}", "INFO")
            else:
                self.ytdlp_manager.log("未检测到本地 Cookies 文件 (选填)", "INFO")

            # PO Token
            from core.po_token_manager import get_manager as _get_pot_manager
            pot_manager = _get_pot_manager()
            status, msg = pot_manager.get_status()
            self.ytdlp_manager.log(f"PO Token 初始状态: [{status}] {msg}", "INFO")
            
            # 状态变更监听：直接在日志更新
            pot_manager.on_status_change(lambda code, message: self.ytdlp_manager.log(f"PO Token 状态更新: [{code}] {message}", "INFO"))

        # 后台执行耗时检测，不阻塞UI渲染
        threading.Thread(target=check_ytdlp, daemon=True).start()
        threading.Thread(target=check_ffmpeg, daemon=True).start()
        threading.Thread(target=check_others, daemon=True).start()

    def _on_close(self):
        """关闭窗口时保存位置并检查运行中的任务"""
        running_count = len(self.ytdlp_manager.running_tasks)
        waiting_count = sum(1 for task in self.ytdlp_manager.task_queue if task.status == TASK_STATUS_WAITING)
        busy_states = []
        if running_count > 0:
            busy_states.append(f"{running_count} 个运行中任务")
        if waiting_count > 0:
            busy_states.append(f"{waiting_count} 个等待中任务")
        if self.yt_dlp_update_in_progress:
            busy_states.append("yt-dlp 更新中")

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
                busy_states.append("批量解析中")
            if getattr(input_frame, '_enqueue_in_progress', False):
                busy_states.append("批量入队处理中")

        if busy_states:
            result = SilentMessagebox.askyesno(
                "确认关闭",
                "当前仍有后台操作进行中：\n- " + "\n- ".join(busy_states) + "\n\n是否要继续关闭程序？",
                parent=self.root
            )
            if not result:
                return

            for input_frame in active_frames:
                if getattr(input_frame, '_fetch_in_progress', False):
                    self.latest_runtime_issue = {
                        "summary": "窗口关闭时批量解析仍在执行",
                        "detail": "用户在批量解析尚未完成时关闭程序，当前结果可能未完整刷新到界面。",
                        "level": "WARN",
                        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                    }
                if getattr(input_frame, '_enqueue_in_progress', False):
                    self.latest_runtime_issue = {
                        "summary": "窗口关闭时批量入队仍在执行",
                        "detail": "用户在批量入队尚未完成时关闭程序，部分条目可能尚未进入队列。",
                        "level": "WARN",
                        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                    }

            self.ytdlp_manager.stop_all()
            time.sleep(0.2)

        self.save_ui_state()
        save_window_pos(self.root, self.position_repo)
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

    def notify_cookies_error(self, diagnostic=None):
        """提示认证/Cookies问题（仅认证类问题提示一次）。"""
        self.latest_auth_diagnostic = diagnostic
        notify_cookies_error(self, diagnostic=diagnostic)

    def show_usage_introduction(self):
        """显示程序功能及使用说明窗口。"""
        doc_path = os.path.join(base_path, "usage_intro.md")
        if not os.path.exists(doc_path):
            self.SilentMessagebox.showerror("错误", f"未找到使用说明文件: {doc_path}", parent=self.root)
            return

        try:
            with open(doc_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            self.SilentMessagebox.showerror("错误", f"读取说明文件失败: {e}", parent=self.root)
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("YouTube 下载器 - 使用说明 & 参数手册")
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
        scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=text_area.yview)
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
        ttk.Button(btn_frame, text="我知道了", command=dialog.destroy, style="Primary.TButton").pack()

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
