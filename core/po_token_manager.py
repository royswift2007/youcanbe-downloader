"""
core/po_token_manager.py

管理 YouTube PO Token 的自动生成与缓存。
依赖本地安装的 Node.js (>= v20) 和 tools/po_token/ 目录中的 JS 脚本。
生成脚本基于 bgutils-js：每次运行从 YouTube 主页动态获取 BotGuard challenge，
不依赖静态播放器代码快照，不会因 YouTube 更新而失效。
失败时静默降级，不影响正常下载流程。
"""

import json
import logging
import os
import subprocess
import sys
import threading
import time

logger = logging.getLogger(__name__)


TOKEN_KEY_VISITOR_DATA = "visitor_data"
TOKEN_KEY_PO_TOKEN = "po_token"
LEGACY_TOKEN_KEY_VISITOR_DATA = "visitorData"
LEGACY_TOKEN_KEY_PO_TOKEN = "token"


# 获取基础目录（支持 PyInstaller）
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    _BASE_DIR = getattr(sys, '_MEIPASS')
else:
    _BASE_DIR = os.path.dirname(os.path.dirname(__file__))

_TOOLS_DIR = os.path.join(_BASE_DIR, "tools", "po_token")
_SCRIPT_PATH = os.path.join(_TOOLS_DIR, "generate_token.mjs")
_TOKEN_TTL = 3600  # Token 有效期 1 小时
# 生成管线标识：用于日志版本戳与退避状态绑定。
# 更换生成脚本/超时策略时必须更新此值，使旧管线的 gave_up/退避状态自动失效。
_PIPELINE_ID = "pot-mjs-v2"
# 生成脚本内部 JS watchdog 为 90 秒；Python 侧超时需大于该值，确保失败时
# 能拿到脚本自行输出的结构化错误（而非被 Python 强杀后丢失 stderr）
_GENERATE_TIMEOUT = 100
# 生成脚本所需的核心 npm 依赖（缺失则触发 npm install 重装）
_REQUIRED_NODE_MODULES = ("bgutils-js", "youtubei.js", "jsdom")

# 修复失败后的指数退避序列（秒）：5min → 15min → 30min → 1h，之后每轮翻倍，封顶 4 小时
_BACKOFF_SEQUENCE = (300, 900, 1800, 3600)
_BACKOFF_MAX_SECONDS = 4 * 3600
# 连续自动修复失败达到该次数后进入 gave_up 终态：不再自动重试（含重启后），
# 仅手动"安装/修复"可恢复，彻底终止 失败→重装→再失败 的刷屏循环
_MAX_CONSECUTIVE_REPAIR_FAILURES = 3
# 相同状态消息的日志去重窗口下限（秒）；实际窗口取记录该消息时的退避间隔与该值中的较大者
_STATUS_DEDUP_MIN_WINDOW = 300
# 退避状态持久化文件（跨会话保持指数增长；成功或手动修复时删除）
_BACKOFF_STATE_FILE = os.path.join(_TOOLS_DIR, ".ycb_backoff_state")

# 当 tools/po_token 目录不存在时，说明当前版本未包含 PO Token 工具，需静默降级
_TOOLS_AVAILABLE = os.path.isdir(_TOOLS_DIR)

# 单例全局状态
STATUS_UNKNOWN = "unknown"
STATUS_NO_NODE = "no_node"
STATUS_OLD_NODE = "old_node"
STATUS_INSTALLING = "installing"
STATUS_READY = "ready"
STATUS_ERROR = "error"
STATUS_DISABLED = "disabled"
STATUS_RETRY_WAIT = "retry_wait"
STATUS_GAVE_UP = "gave_up"


def normalize_token_payload(token_data):
    if not isinstance(token_data, dict):
        return None
    visitor_data = (
        token_data.get(TOKEN_KEY_VISITOR_DATA)
        or token_data.get(LEGACY_TOKEN_KEY_VISITOR_DATA)
        or ""
    )
    po_token = (
        token_data.get(TOKEN_KEY_PO_TOKEN)
        or token_data.get(LEGACY_TOKEN_KEY_PO_TOKEN)
        or ""
    )
    visitor_data = str(visitor_data or "").strip()
    po_token = str(po_token or "").strip()
    if not visitor_data or not po_token:
        return None
    return {
        TOKEN_KEY_VISITOR_DATA: visitor_data,
        TOKEN_KEY_PO_TOKEN: po_token,
    }


class PoTokenManager:
    """
    负责 PO Token 的生命周期管理：
    - 检测 Node.js 是否可用及版本
    - 首次使用时自动运行 npm install
    - 生成并缓存 Token（1 小时有效）
    - 所有失败均静默降级，返回 None
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._background_threads: list = []
        self._cached_token: dict | None = None
        self._cached_at: float = 0.0
        self._status: str = STATUS_UNKNOWN
        self._status_message: str = ""
        self._status_callbacks: list = []
        self._node_path: str = self._find_node_path()
        self._repair_in_progress: bool = False
        self._repair_attempts: int = 0
        self._next_repair_at: float = 0.0
        self._last_updated_at: float = 0.0
        self._last_error: str = ""
        # 指数退避与日志去重状态（会话内保持；成功或手动触发时通过 _reset_backoff 重置）
        self._consecutive_repair_failures: int = 0
        self._last_logged_status_key: tuple = ()
        self._last_logged_status_at: float = 0.0
        self._last_logged_status_window: float = 0.0
        self._pending_dedup_window: float = 0.0
        
        # Windows 静默启动配置，防止 cmd 窗口闪烁
        if sys.platform == "win32":
            self._startupinfo = subprocess.STARTUPINFO()
            self._startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            self._startupinfo.wShowWindow = subprocess.SW_HIDE
        else:
            self._startupinfo = None

        # 恢复跨会话的指数退避状态（若上次会话处于冷却期内）
        self._load_backoff_state_file()

    @staticmethod
    def _find_node_path() -> str:
        """查找 node 可执行文件路径，优先 PATH，兜底 Windows 常见安装位置。"""
        import shutil
        found = shutil.which("node")
        if found:
            return found
        if sys.platform == "win32":
            candidates = [
                r"C:\Program Files\nodejs\node.exe",
                r"C:\Program Files (x86)\nodejs\node.exe",
                os.path.join(os.environ.get("APPDATA", ""), r"nvm\current\node.exe"),
                os.path.join(os.environ.get("ProgramFiles", ""), r"nodejs\node.exe"),
            ]
            for path in candidates:
                if os.path.isfile(path):
                    return path
        return "node"  # 最终兜底，让系统自行查找

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def initialize_async(self):
        """启动时在后台线程检测环境，不阻塞主线程。"""
        self._cancel.clear()
        t = threading.Thread(target=self._initialize, daemon=True)
        self._background_threads.append(t)
        t.start()

    def request_stop(self):
        """请求停止后台安装/修复线程。"""
        self._cancel.set()
        with self._lock:
            threads = list(self._background_threads)
        for t in threads:
            if t is threading.current_thread():
                continue
            t.join(timeout=2)

    def get_status(self) -> tuple[str, str]:
        """返回 (status_code, status_message)"""
        return self._status, self._status_message

    def get_status_detail(self) -> dict:
        return {
            "status": self._status,
            "message": self._status_message,
            "last_updated_at": self._last_updated_at,
            "last_error": self._last_error,
            "repair_in_progress": self._repair_in_progress,
            "repair_attempts": self._repair_attempts,
            "next_repair_at": self._next_repair_at,
            "consecutive_repair_failures": self._consecutive_repair_failures,
            "pipeline": _PIPELINE_ID,
        }

    def is_ready(self) -> bool:
        return self._status == STATUS_READY

    def on_status_change(self, callback):
        """注册状态变更回调，callback(status_code, message)。

        返回取消函数，调用后注销该回调，便于窗口关闭等场景解除闭包引用。
        """
        if callback not in self._status_callbacks:
            self._status_callbacks.append(callback)

        def unsubscribe():
            self.off_status_change(callback)

        return unsubscribe

    def off_status_change(self, callback):
        """注销已注册的状态变更回调。"""
        try:
            self._status_callbacks.remove(callback)
        except ValueError:
            pass

    def get_token(self) -> dict | None:
        """
        返回 {"visitor_data": "...", "po_token": "..."} 或 None。
        缓存 1 小时内直接复用，过期后重新生成。
        生成失败时自动修复一次（重新 npm install），再次失败则更新顶栏状态。
        """
        if not self.is_ready():
            return None

        with self._lock:
            if self._cached_token and (time.time() - self._cached_at) < _TOKEN_TTL:
                logger.debug("PO Token: 使用缓存")
                return self._cached_token

        token = self._generate_token()
        if token:
            self._store_token(token)
            return token

        # 生成失败 → 后台触发修复（只修复一次，不阻塞当前下载）
        self._schedule_repair_after_failure()
        return None

    def reset_backoff(self):
        """重置指数退避状态（连续失败计数与下次修复时间），下次失败立即重试。

        手动触发修复或成功生成 Token 时调用；线程安全。
        """
        self._reset_backoff()

    def _reset_backoff(self):
        with self._lock:
            self._consecutive_repair_failures = 0
            self._next_repair_at = 0.0
            self._clear_status_log_dedup_locked()
        self._delete_backoff_state_file()

    def _load_backoff_state_file(self):
        """启动时恢复跨会话的退避状态；文件缺失或损坏时静默忽略。

        状态文件记录生成时的 _PIPELINE_ID；不匹配（旧管线遗留）时视为
        全新状态直接丢弃，避免新管线继承旧管线的 gave_up 判决。
        冷却期已过时仍恢复连续失败计数（下次失败退避继续指数增长），
        仅不再恢复已过期的冷却截止时间（允许立即重试）。
        """
        try:
            if not _TOOLS_AVAILABLE or not os.path.isfile(_BACKOFF_STATE_FILE):
                return
            with open(_BACKOFF_STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("pipeline") != _PIPELINE_ID:
                logger.info(
                    f"PO Token 退避状态为旧管线遗留（{data.get('pipeline')} != {_PIPELINE_ID}），已重置"
                )
                self._delete_backoff_state_file()
                return
            failures = int(data.get("failures", 0) or 0)
            next_at = float(data.get("next_repair_at", 0.0) or 0.0)
            if failures > 0:
                self._consecutive_repair_failures = failures
                if next_at > time.time():
                    self._next_repair_at = next_at
                self._last_error = data.get("last_error", "") or ""
        except Exception:
            logger.debug("PO Token 退避状态文件读取失败，忽略", exc_info=True)

    def _save_backoff_state_file(self, message: str):
        """将当前退避状态持久化，保证重启后指数继续增长。"""
        try:
            if not _TOOLS_AVAILABLE:
                return
            payload = {
                "pipeline": _PIPELINE_ID,
                "failures": self._consecutive_repair_failures,
                "next_repair_at": self._next_repair_at,
                "last_error": message,
            }
            with open(_BACKOFF_STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)
        except Exception:
            logger.debug("PO Token 退避状态文件写入失败，忽略", exc_info=True)

    def _delete_backoff_state_file(self):
        try:
            if _TOOLS_AVAILABLE and os.path.isfile(_BACKOFF_STATE_FILE):
                os.remove(_BACKOFF_STATE_FILE)
        except Exception:
            logger.debug("PO Token 退避状态文件删除失败，忽略", exc_info=True)

    def _clear_status_log_dedup_locked(self):
        """清除日志去重记忆（需持有 self._lock）。"""
        self._last_logged_status_key = ()
        self._last_logged_status_at = 0.0
        self._last_logged_status_window = 0.0
        self._pending_dedup_window = 0.0

    def repair(self):
        """手动触发安装/修复过程，修复后立即验证 Token 生成。

        与自动修复不同：手动修复失败时直接进入 gave_up 终态
        （用户已主动确认修复无效，不再自动重试），且重装完成后必须
        验证生成成功才置 ready，避免"手动修复→ready→下次下载又自动
        循环"的刷屏复发路径。
        """
        with self._lock:
            if self._repair_in_progress:
                return
            self._repair_in_progress = True
            self._repair_attempts = 0
            self._next_repair_at = 0.0
            self._last_error = ""
            self._clear_status_log_dedup_locked()
        self._delete_backoff_state_file()
        self._set_status(STATUS_INSTALLING, "pot_msg_installing")
        self._start_repair_thread(verify_token=True, manual=True)

    def invalidate_cache(self):
        """手动使缓存失效（例如 IP 变化后调用）。"""
        with self._lock:
            self._cached_token = None
            self._cached_at = 0.0

    def _store_token(self, token: dict):
        with self._lock:
            self._cached_token = token
            self._cached_at = time.time()
            self._last_updated_at = self._cached_at
            self._last_error = ""
            self._repair_attempts = 0
            self._consecutive_repair_failures = 0
            self._next_repair_at = 0.0
            self._clear_status_log_dedup_locked()
        self._delete_backoff_state_file()

    def _next_backoff_seconds(self) -> int:
        """按连续修复失败次数返回指数退避间隔（秒）。

        序列：300 → 900 → 1800 → 3600 → 之后每轮翻倍，封顶 _BACKOFF_MAX_SECONDS（4 小时）。
        """
        failures = self._consecutive_repair_failures
        if failures <= 0:
            return 0
        if failures <= len(_BACKOFF_SEQUENCE):
            return _BACKOFF_SEQUENCE[failures - 1]
        extra_doublings = failures - len(_BACKOFF_SEQUENCE)
        return min(_BACKOFF_MAX_SECONDS, _BACKOFF_SEQUENCE[-1] * (2 ** extra_doublings))

    def _start_repair_thread(self, verify_token: bool, manual: bool = False):
        self._cancel.clear()
        t = threading.Thread(
            target=self._repair_and_retry,
            kwargs={"verify_token": verify_token, "manual": manual},
            daemon=True,
        )
        self._background_threads.append(t)
        t.start()

    def _schedule_repair_after_failure(self):
        now = time.time()
        gave_up = False
        with self._lock:
            if self._repair_in_progress:
                return
            if self._consecutive_repair_failures >= _MAX_CONSECUTIVE_REPAIR_FAILURES:
                # 已达连续失败上限：进入 gave_up 终态，本次及后续自动触发一律静默拒绝
                gave_up = True
                self._pending_dedup_window = float(_BACKOFF_MAX_SECONDS)
            elif self._next_repair_at and now < self._next_repair_at:
                should_wait = True
            else:
                should_wait = False
                self._repair_in_progress = True
                self._repair_attempts += 1
        if gave_up:
            # 注意：_set_status 内部会获取 self._lock，必须在锁外调用（Lock 不可重入）
            self._set_status(STATUS_GAVE_UP, "pot_msg_gave_up")
            return
        if should_wait:
            # 冷却期内重复触发：将去重窗口对齐为剩余冷却时间，
            # 使"冷却中"提示在整个冷却周期内只记录/广播一次
            with self._lock:
                self._pending_dedup_window = max(0.0, self._next_repair_at - now)
            self._set_status(STATUS_RETRY_WAIT, "pot_msg_retry_wait")
            return
        self._set_status(STATUS_INSTALLING, "pot_msg_repairing")
        self._start_repair_thread(verify_token=True, manual=False)

    def _set_retry_wait(self, message: str):
        now = time.time()
        gave_up = False
        with self._lock:
            self._consecutive_repair_failures += 1
            if self._consecutive_repair_failures >= _MAX_CONSECUTIVE_REPAIR_FAILURES:
                # 达到连续失败上限：进入 gave_up 终态并持久化，
                # 重启后也不再自动重试，仅手动"安装/修复"可恢复
                gave_up = True
                self._last_updated_at = now
                self._last_error = message
                self._pending_dedup_window = float(_BACKOFF_MAX_SECONDS)
            else:
                delay = self._next_backoff_seconds()
                self._next_repair_at = now + delay
                self._last_updated_at = now
                self._last_error = message
                # 以本周期退避间隔作为日志去重窗口，同一失败消息在窗口内只记录一次；
                # 通过 pending 传递给随后的 _set_status，由其记录首次日志与窗口
                self._pending_dedup_window = float(delay)
        # 注意：_set_status / _save_backoff_state_file 内部会获取 self._lock，
        # 必须在锁外调用（Lock 不可重入）
        if gave_up:
            self._set_status(STATUS_GAVE_UP, "pot_msg_gave_up")
        else:
            self._set_status(STATUS_RETRY_WAIT, message)
        self._save_backoff_state_file(message)

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------

    def _set_status(self, code: str, message: str):
        now = time.time()
        should_log = True
        with self._lock:
            self._status = code
            self._status_message = message
            self._last_updated_at = now
            if code == STATUS_ERROR:
                self._last_error = message
            elif code == STATUS_READY:
                self._last_error = ""
                # 注意：此处不清 _next_repair_at。initialize 置 ready 仅代表环境就绪，
                # 不代表 Token 生成成功；退避清零统一由 _store_token / repair() /
                # reset_backoff 处理，避免重启后跨会话退避被初始化流程重置。
            # 日志去重：同一 (code, message) 在上次记录后的窗口内重复出现时，
            # 仅首次输出 INFO 日志并触发回调，后续降级为 DEBUG 且不再触发回调，
            # 避免失败循环刷屏（UI 日志与顶栏对重复状态渲染结果相同，可安全跳过）。
            # 窗口默认取 _STATUS_DEDUP_MIN_WINDOW；_set_retry_wait 通过
            # _pending_dedup_window 将窗口对齐为当前退避周期长度。
            key = (code, message)
            pending_window = self._pending_dedup_window
            self._pending_dedup_window = 0.0
            if (
                key == self._last_logged_status_key
                and self._last_logged_status_at > 0.0
                and (now - self._last_logged_status_at) < max(
                    self._last_logged_status_window, _STATUS_DEDUP_MIN_WINDOW
                )
            ):
                should_log = False
            else:
                self._last_logged_status_key = key
                self._last_logged_status_at = now
                self._last_logged_status_window = pending_window
        if should_log:
            logger.info(f"PO Token 状态: [{code}] {message}")
            for cb in self._status_callbacks:
                try:
                    cb(code, message)
                except Exception:
                    pass
        else:
            logger.debug(f"PO Token 状态(重复，已抑制): [{code}] {message}")

    def _initialize(self):
        """后台初始化：检测 node → 确保依赖 → 置为 ready。"""
        try:
            # 管线版本戳：让"当前运行的是哪套生成代码"可直接从日志验证
            logger.info(
                f"PO Token 管线: {_PIPELINE_ID} | 脚本: {os.path.basename(_SCRIPT_PATH)} | 超时: {_GENERATE_TIMEOUT}s"
            )
            self._set_status(STATUS_UNKNOWN, "pot_msg_checking")

            # 0. 工具目录缺失时静默降级，避免 subprocess cwd 指向不存在目录导致 WinError 267
            if not _TOOLS_AVAILABLE:
                self._set_status(STATUS_DISABLED, "pot_msg_disabled")
                return

            # 1. 检测 node（youtubei.js 18.x / bgutils-js 需要 Node >= 20）
            node_version = self._detect_node()
            if node_version is None:
                self._set_status(STATUS_NO_NODE, "pot_msg_no_node")
                return
            if node_version < 20:
                self._set_status(STATUS_OLD_NODE, "pot_msg_old_node")
                return

            # 2. 确保 npm 依赖已安装
            if not self._ensure_deps():
                self._set_status(STATUS_ERROR, "pot_msg_npm_fail")
                return

            # 3. 准备就绪；若重启后已达到连续失败上限，保持 gave_up 终态；
            #    若仍在冷却期，则直接进入 retry_wait，而不是误报 ready
            if self._consecutive_repair_failures >= _MAX_CONSECUTIVE_REPAIR_FAILURES:
                self._set_status(STATUS_GAVE_UP, "pot_msg_gave_up")
                return
            if self._next_repair_at and time.time() < self._next_repair_at:
                self._set_status(STATUS_RETRY_WAIT, "pot_msg_retry_wait")
                return
            self._set_status(STATUS_READY, "pot_msg_ready")
        except Exception as e:
            logger.error(f"PO Token 初始化崩溃: {e}", exc_info=True)
            self._set_status(STATUS_ERROR, f"初始化异常: {str(e)}")

    def _detect_node(self) -> int | None:
        """返回 Node.js 主版本号，或 None（未安装）。"""
        try:
            result = subprocess.run(
                [self._node_path, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
                startupinfo=self._startupinfo,
            )
            if result.returncode != 0:
                return None
            # v20.11.0 → 20
            version_str = result.stdout.strip().lstrip("v")
            major = int(version_str.split(".")[0])
            return major
        except (FileNotFoundError, ValueError, subprocess.TimeoutExpired, OSError):
            logger.debug("Node.js 不可用", exc_info=True)
            return None

    def _ensure_deps(self) -> bool:
        """检查核心 npm 依赖是否齐全，缺失则运行 npm install。"""
        for module_name in _REQUIRED_NODE_MODULES:
            module_path = os.path.join(_TOOLS_DIR, "node_modules", module_name)
            if not os.path.isdir(module_path):
                return self._run_npm_install()
        return True

    def _run_npm_install(self) -> bool:
        """执行 npm install，Windows 使用 npm.cmd。"""
        self._set_status(STATUS_INSTALLING, "pot_msg_installing")
        logger.warning("PO Token repair/install will execute local npm install; only continue in trusted environments.")
        import shutil
        npm_cmd = shutil.which("npm.cmd") or shutil.which("npm") or ("npm.cmd" if sys.platform == "win32" else "npm")
        try:
            result = subprocess.run(
                [npm_cmd, "install"],
                cwd=_TOOLS_DIR,
                capture_output=True,
                text=True,
                timeout=300,
                startupinfo=self._startupinfo,
            )
            if result.returncode != 0:
                logger.error(f"npm install 失败: {result.stderr}")
                self._set_status(STATUS_ERROR, "pot_msg_npm_fail")
                return False

            logger.info("npm install 完成")
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
            logger.error(f"npm install 异常: {e}")
            self._set_status(STATUS_ERROR, "pot_msg_npm_fail")
            return False
        except Exception as e:
            logger.error(f"npm install 未知异常: {e}", exc_info=True)
            self._set_status(STATUS_ERROR, "pot_msg_npm_fail")
            return False

    def _repair_and_retry(self, verify_token: bool = True, manual: bool = False):
        """删除 node_modules 后重新安装；修复完成后校验 Token 生成。

        manual=True（用户在组件中心点击）时：失败直接进入 gave_up 终态，
        不再走自动退避重试。
        """
        try:
            if self._cancel.is_set():
                return
            if manual:
                logger.info("PO Token 手动安装/修复开始…")
                self._set_status(STATUS_INSTALLING, "pot_msg_installing")
            else:
                logger.warning("PO Token 生成失败，尝试重新安装依赖…")
                self._set_status(STATUS_INSTALLING, "pot_msg_repairing")

            # 将旧 node_modules 折叠移动到 .old 目录（降低半删除损坏风险），安装成功后再删除
            import shutil
            node_modules = os.path.join(_TOOLS_DIR, "node_modules")
            old_node_modules = os.path.join(_TOOLS_DIR, "node_modules.old")
            moved_old = False
            if os.path.isdir(node_modules):
                if os.path.exists(old_node_modules):
                    shutil.rmtree(old_node_modules, ignore_errors=True)
                try:
                    shutil.move(node_modules, old_node_modules)
                    moved_old = True
                except OSError:
                    logger.warning("移动 node_modules 到 .old 失败，回退为直接删除", exc_info=True)
                    shutil.rmtree(node_modules, ignore_errors=True)

            if self._cancel.is_set():
                return

            # 重新安装
            if not self._run_npm_install():
                msg = "pot_msg_repair_fail"
                logger.error(msg)
                if verify_token:
                    self._set_retry_wait(msg)
                else:
                    self._set_status(STATUS_ERROR, msg)
                return

            # 安装成功后删除旧的折叠目录
            if moved_old and os.path.exists(old_node_modules):
                shutil.rmtree(old_node_modules, ignore_errors=True)

            if self._cancel.is_set():
                return

            # 修复完成后验证 Token 生成（手动与自动路径一致）
            self._set_status(STATUS_INSTALLING, "pot_msg_repair_generating")
            token = self._generate_token()
            if token:
                self._store_token(token)
                logger.info("PO Token 修复后生成成功")
                self._set_status(STATUS_READY, "pot_msg_ready_repaired")
            else:
                msg = "pot_msg_repair_final_fail"
                logger.error(msg)
                if manual:
                    # 手动修复失败：用户已主动确认，直接停用，不再自动重试
                    with self._lock:
                        self._consecutive_repair_failures = _MAX_CONSECUTIVE_REPAIR_FAILURES
                        self._last_error = msg
                        self._pending_dedup_window = float(_BACKOFF_MAX_SECONDS)
                    self._set_status(STATUS_GAVE_UP, "pot_msg_gave_up")
                    self._save_backoff_state_file(msg)
                else:
                    self._set_retry_wait(msg)
        finally:
            with self._lock:
                self._repair_in_progress = False

    def _extract_node_error(self, result: subprocess.CompletedProcess) -> str:
        streams = []
        stdout = (result.stdout or "").strip()
        stderr = (result.stderr or "").strip()
        if stderr:
            streams.append(stderr)
        if stdout:
            streams.append(stdout)

        for stream in streams:
            for line in reversed(stream.splitlines()):
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict) and payload.get("success") is False:
                    return json.dumps(payload, ensure_ascii=False)

        combined = "\n".join(streams).strip()
        return combined

    def _generate_token(self) -> dict | None:
        """调用 Node.js 脚本生成 Token。"""
        if not os.path.exists(_SCRIPT_PATH):
            logger.warning(f"Token 脚本不存在: {_SCRIPT_PATH}")
            return None
            
        env = os.environ.copy()

        try:
            # 脚本内部 JS watchdog 为 90 秒（unref），超时自行输出结构化错误并退出；
            # Python 侧超时略大于该值，作为事件循环被 BotGuard 同步计算长时间阻塞时的兜底。
            result = subprocess.run(
                [self._node_path, _SCRIPT_PATH],
                cwd=_TOOLS_DIR,
                capture_output=True,
                text=True,
                timeout=_GENERATE_TIMEOUT,
                startupinfo=self._startupinfo,
                env=env,
            )
            if result.returncode != 0:
                error_detail = self._extract_node_error(result)
                logger.warning(f"Token 生成失败: {error_detail}")
                self._last_error = error_detail
                return None
            data = json.loads(result.stdout.strip())
            normalized = normalize_token_payload(data)
            if normalized:
                logger.info("PO Token 生成成功")
                return normalized
            logger.warning(f"Token 响应格式异常: {result.stdout.strip()}")
            return None
        except json.JSONDecodeError as e:
            logger.warning(f"Token 响应解析异常: {e}")
            self._last_error = f"Token 响应解析异常: {e}"
            return None
        except subprocess.TimeoutExpired as e:
            logger.warning(f"Token 生成超时: {e}")
            self._last_error = f"Token 生成超时: {e}"
            return None
        except OSError as e:
            logger.warning(f"Token 生成异常: {e}")
            self._last_error = f"Token 生成异常: {e}"
            return None


# 全局单例
_manager: PoTokenManager | None = None


def get_manager() -> PoTokenManager:
    global _manager
    if _manager is None:
        _manager = PoTokenManager()
    return _manager
