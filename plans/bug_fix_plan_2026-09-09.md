# YCB Downloader 函数级修复计划

- **日期**：2026-09-09
- **对应报告**：`plans/bug_audit_report_2026-09-09.md`（54 条问题：高 7 / 中 17 / 低 25 / 待确认 5）
- **计划性质**：只读审查后的修复规划，尚未实施任何代码改动
- **修复原则**：
  1. 按「高 → 中 → 低 → 待确认」分批实施，每批完成须 `python -m py_compile` 通过并跑通冒烟路径。
  2. 凡涉及线程/子进程竞态的改动，统一引入「持有锁状态下只判不再读、统一收口到 cleanup 方法」的模式，避免继续叠加无锁读写。
  3. i18n 相关改动一律「比较状态枚举/常量，不比较翻译文本」。
  4. 每处修复标注「改动函数：`模块.函数()`」，并给出「改动前 → 改动后」思路与验收标准。

---

## 0. 修复前置：Cookies 路径同步（非 bug，但必须先做）

- **改动文件**：`YCB.pyw`（已完成）、部署副本
- **动作**：将已修复的 [`YCB.pyw`](YCB.pyw:175)、[`YCB.pyw:450-458`](YCB.pyw:450) 同步到 `D:\Program Files\youcanbe downloader\` 的旧源码副本，或重新 PyInstaller 打包覆盖 `build/YCB/YCB.exe`。
- **验收**：在安装目录运行，启动日志的 `cookies_file=` 不再指向 C 盘开发目录；`window_pos.json` 首次运行后自动写回新默认路径。

---

## 第一批：高严重度（7 条）

> 目标：消除「孤儿进程、停止失效、偶发崩溃、数据库锁、组件半成品、死代码误改」六类最严重风险。

---

### H1 · 退出时停止 media 任务与 po_token 后台线程，为 `MediaJobManager` 增加 `stop_all`

- **改动函数**：
  1. `core/media_jobs.py::MediaJobManager.stop_all()`（**新增**）
  2. `YCB.pyw::_on_close()`（[`YCB.pyw:1070`](YCB.pyw:1070)）
  3. `YCB.pyw::_finalize_close()`（[`YCB.pyw:1144`](YCB.pyw:1144)）
- **改动前**：
  - `MediaJobManager` 只有 `stop_job`/`stop_selected`，无 `stop_all`。
  - `_on_close` 的 `busy_states` 仅检查 `running_count/waiting_count/yt_dlp_update_in_progress/input_frames`，完全不含 `media_manager`。
  - `_finalize_close` 只做 `save_ui_state` + `save_window_pos` + `root.destroy`。
- **改动后**：
  - 新增 `MediaJobManager.stop_all()`：仿照 [`core/download_manager.py:1305`](core/download_manager.py:1305) 的 `stop_all`，在 `_state_lock` 下取出所有 `running_jobs` 的 id，逐个调用 `self.stop_job(job_id)`。
  - `_on_close` 增加 `media_running_count = len(self.media_manager.running_jobs)` 与 `po_token_busy`（`get_manager().status in {STATUS_INSTALLING, STATUS_REPAIRING}`），追加到 `busy_states`；确认退出分支中在 `self.ytdlp_manager.stop_all()` 之后同步调用 `self.media_manager.stop_all()`。
  - `_finalize_close` 前置调用 `self.media_manager.stop_all()`，并对 po_token 后台线程做「不再发起新任务」的停止标志（见 M9）。
- **验收**：关闭窗口后，任务管理器中没有残留的 ffmpeg/npm/deno 子进程。

---

### H3 · `stop_all` 增加全局停止标志，阻断任务再拉起

- **改动函数**：
  1. `core/download_manager.py::DownloadManager.__init__()`（增加 `self._stopping = False` 与 `self._state_lock` 保护）
  2. `core/download_manager.py::DownloadManager.run_task()`（[`core/download_manager.py:542`](core/download_manager.py:542)，末尾 [`core/download_manager.py:564`](core/download_manager.py:564)）
  3. `core/download_manager.py::DownloadManager.stop_all()`（[`core/download_manager.py:1305`](core/download_manager.py:1305)）
- **改动前**：
  - `run_task` 末尾无条件 `self._safe_after(100, self.start_next_task)`。
  - `stop_all` 仅遍历 `running_tasks` 调 `stop_task`，无全局停止标志。
- **改动后**：
  - `__init__` 增加 `self._stopping = False`。
  - `run_task` 末尾改为：`with self._state_lock: should_continue = not self._stopping`；仅当 `should_continue` 为真时才 `self._safe_after(100, self.start_next_task)`。
  - `stop_all` 开头：`with self._state_lock: self._stopping = True`；清空等待队列（将 `task_queue` 中 `WAITING` 任务标记为 `STOPPED`）。
  - 新增 `resume_all` / 新任务入队时重置：`with self._state_lock: self._stopping = False`（在 `start_next_task` 或 `enqueue` 入口处复位）。
- **验收**：点击「停止全部」后，队列中后续任务不再被自动启动；手动再点「开始」可恢复调度。

---

### H2 · 消除 `stop_job` 关闭 stdout 与 worker 线程迭代的竞态

- **改动函数**：
  1. `core/media_jobs.py::MediaJobManager._run_ffmpeg_job()`（[`core/media_jobs.py:314`](core/media_jobs.py:314) 的 `for line in job.process.stdout` 循环）
  2. `core/media_jobs.py::MediaJobManager.stop_job()`（[`core/media_jobs.py:351`](core/media_jobs.py:351)）
  3. `core/media_jobs.py::MediaJobManager._cleanup_job_process()`（`finally` 收口，[`core/media_jobs.py:349`](core/media_jobs.py:349) 调用）
- **改动前**：
  - `stop_job` 杀进程后立即 `_cleanup_job_process(job, force=True)`，关闭了 `job.process.stdout`。
  - worker 线程仍阻塞在 `for line in job.process.stdout`，随后对 `job.process.kill()`。
- **改动后**（选择「worker 自行收口 + stop 仅发信号」模式）：
  - `stop_job` 中**不再**直接 `_cleanup_job_process`，只置 `job.stop_flag = True` 并 `taskkill`（进程被杀后，worker 的 stdout 迭代会自然 `StopIteration` 或抛出 `OSError`）。
  - 在 `_run_ffmpeg_job` 的 `except` 分支内，区分「因停止导致的 OSError」与真实错误，前者改判 `STOPPED`。
  - `_cleanup_job_process` 移到 worker 线程 `finally` 独占调用；`stop_job` 只在已知 worker 已结束时才兜底清理。
  - 对 `job.process` 的读写在 `_state_lock` 或独立 `threading.Lock` 下进行，kill 前判空。
- **验收**：停止媒体任务不产生 `AttributeError`/`ValueError` 误报，状态稳定为 `STOPPED`。

---

### H4 · 消除 `stop_task` 与 `_stream_download_output` 对 `task.process` 的竞态

- **改动函数**：
  1. `core/download_manager.py::DownloadManager._stream_download_output()`（[`core/download_manager.py:1083`](core/download_manager.py:1083) 附近）
  2. `core/download_manager.py::DownloadManager.stop_task()`（[`core/download_manager.py:1282`](core/download_manager.py:1282)）
  3. `core/download_manager.py::DownloadManager._cleanup_task_process()`
- **改动前**：
  - 下载线程检测到 `stop_flag` 就 `task.process.kill()`；`stop_task` 同时 `taskkill` 并把 `task.process` 置 `None` 并关 stdout。
- **改动后**（与 H2 同模式）：
  - `stop_task` 只置 `stop_flag` + `taskkill`，**不**直接 `_cleanup_task_process`。
  - `_stream_download_output` 内 `kill()` 前先 `proc = task.process; if proc is not None: proc.kill()`，并捕获 `OSError/ValueError`（进程已退出）。
  - `_cleanup_task_process` 由 worker 线程 `finally` 独占执行；`stop_task` 仅在确认 worker 已结束时兜底。
  - 对 `task.process` 的置空/关闭统一到 `_cleanup_task_process` 内部，避免两处并发写。
- **验收**：停止下载不触发 `AttributeError`/`ValueError: I/O operation on closed file`。

---

### H5 · `history_repo` SQLite 连接及时 `close()`，避免依赖 GC

- **改动函数**（所有 `with sqlite3.connect(...)` 处）：
  - `core/history_repo.py::_insert_db_record()`（[`core/history_repo.py:159`](core/history_repo.py:159)）
  - `_delete_db_record()`、`load()`（[`core/history_repo.py:335`](core/history_repo.py:335)）、`has_success_record()`（[`core/history_repo.py:409`](core/history_repo.py:409)）、`clear()`（[`core/history_repo.py:437`](core/history_repo.py:437)）等。
- **改动前**：`with sqlite3.connect(...) as conn:` 末尾不对 `conn.close()`，依赖对象出作用域后 GC 回收。
- **改动后**：统一改为显式 `conn = sqlite3.connect(...); try: ...; finally: conn.close()`，或将连接集中到 `self._get_conn()` 上下文管理器。必要时把 `timeout` 增大并保留 `_db_retry_count` 重试。
- **备注**：若项目其他地方依赖 `with conn` 自动 commit 的语义，保留 `conn.commit()` 调用；重点只在 `finally` 补 `close()`。
- **验收**：批量下载后 Windows 下不再高频出现 `database is locked`；外部能删除 sqlite 文件。

---

### H6 · `backend_setup` 组件替换改为「临时文件 + 原子替换」，移除先删后 replace

- **改动函数**：
  1. `backend_setup.py::download_file()`（[`backend_setup.py:552`](backend_setup.py:552)，尤其 570-572 行）
  2. `backend_setup.py::extract_zip_member()`（[`backend_setup.py:582`](backend_setup.py:582)，尤其 597-599 行）
- **改动前**：`if os.path.exists(target_path): os.remove(target_path)` 然后再 `replace_file_with_retry(temp_path, target_path)`；删除无重试、无占用兜底。
- **改动后**：
  - 删除 `os.remove(target_path)` 前置步骤，直接走 `replace_file_with_retry`（该函数已含重试 + 原子替换语义）。
  - 若 `replace_file_with_retry` 内部对 Windows 占用（`PermissionError` winerror 5/32）无重试，则在其内部补充对占用错误的显式重试与「占用则回退临时文件 + 提示重启」策略。
- **验收**：目标 exe 被占用时更新不会丢失原件，也不会留下半成品；替换要么全成功、要么保留旧文件。

---

### H7 · 下架或标注 `backend_setup.py` / `build/backend_setup` / `build/component_downloader` 死代码

- **改动函数**：
  1. `backend_setup.py`（文件级）
  2. `ui/app_actions.py::update_components()`（[`ui/app_actions.py:303`](ui/app_actions.py:303)）
- **改动前**：UI 组件更新走 `app_actions.py` 内联 urllib 下载；`backend_setup.py` 与两个 build 产物无任何主程序 `subprocess` 调用入口。
- **改动后**（二选一，推荐后者）：
  - 方案 A（彻底）：删除 `backend_setup.py` 及 `build/backend_setup/`、`build/component_downloader/`，只保留 `app_actions.py` 内联下载作为唯一实现。
  - 方案 B（保守）：在 `backend_setup.py` 顶部与 `YCB.spec` 注释标注「已废弃，未接线」，并在 `app_actions.update_components` 顶部注释说明「组件更新唯一实现入口」，防止后续维护者误改死代码。
- **验收**：代码库中「组件更新」只有一个有效实现路径，审计成本下降。

---

## 第二批：中严重度（17 条）

> 目标：修复 i18n 硬编码、数据一致性、po_token 安装残留、UI 响应与若干死代码。

---

### M2 · 用状态枚举/常量替代硬编码文本比较

- **改动函数**：
  1. `YCB.pyw::refresh_auth_status()`（[`YCB.pyw:577,587`](YCB.pyw:577)）
  2. `ui/pages/settings_page.py`（[`settings_page.py:159`](ui/pages/settings_page.py:159) 的 `"就绪"` 判断）
  3. `ui/history_actions.py`（[`history_actions.py:148,150`](ui/history_actions.py:148) 的 `"就绪"/"Ready"` 判断）
- **改动前**：`summary == "未检测到本地 Cookies 文件 (选填)"`、`text == "就绪"`、`in {"就绪","Ready"}`。
- **改动后**：
  - 定义状态常量（如 `AUTH_MISSING_OPTIONAL = "auth_missing_optional"`、`READY_STATUS_CODE = "ready"`）；不要比较 `get_text` 返回的本地化文本。
  - 认证缺失判断改为比较 `diagnostic.code` 或 `CookiesStatus` 的语义字段；就绪判断改为比较内部状态码而非翻译文案。
- **验收**：切换到英文界面后，认证缺失提示与「就绪」复位逻辑仍正确。

---

### M1 · 修复 `_on_tab_changed` 恒不相等

- **改动函数**：`YCB.pyw::_on_tab_changed()`（[`YCB.pyw:903`](YCB.pyw:903)）
- **改动前**：`str(frame) == str(current)` 比较 Notebook tab 容器（`DownloadTab`）与内层页实例（`UnifiedVideoInputFrame`），恒 False。
- **改动后**：改用 `self.notebook.index(current)` 或维护 `tab_path -> input_frame` 映射（`register_input_frame` 时记录），再据此找到 `active_frame`。
- **验收**：切换下载 Tab 时 `_sync_settings_state(source="frame", frame=active_frame)` 真实触发一次。

---

### M3 · 消除关闭时对 `window_pos.json` 的双重写

- **改动函数**：`YCB.pyw::_finalize_close()`（[`YCB.pyw:1144`](YCB.pyw:1144)）
- **改动前**：`save_ui_state()` 与 `save_window_pos(...extra_state=self.ui_state)` 均写 `window_pos.json`。
- **改动后**：明确单一写入口——保留 `save_window_pos(..., extra_state=self.ui_state)` 作为唯一落盘，`save_ui_state()` 改为仅构造 `self.ui_state`，或反之。确保退出路径只写一次。
- **验收**：退出时 `window_pos.json` 只发生一次原子写。

---

### M4 · `stop_task` 支持停止等待中任务

- **改动函数**：`core/download_manager.py::stop_task()`（[`core/download_manager.py:1282`](core/download_manager.py:1282)）
- **改动前**：只从 `running_tasks` 取任务，等待中任务 `return`。
- **改动后**：在 `_state_lock` 下同时查 `running_tasks` 与 `task_queue`；若为等待中，直接标记 `STOPPED` 并从队列移除，不杀进程。
- **验收**：选中排队任务点「停止」能立即移除该任务。

---

### M6 · 为 `log_queue` 设置上限，避免内存无限增长

- **改动函数**：`core/download_manager.py::DownloadManager.__init__()`（`self.log_queue = queue.Queue()`, [`core/download_manager.py`](core/download_manager.py)）
- **改动前**：无限队列，`put` 无上限。
- **改动后**：改为 `queue.Queue(maxsize=2000)` 或合理上限；`log()` 用 `put_nowait` + `except queue.Full` 丢弃最旧或丢弃新条（记错误计数）。
- **验收**：长时间高输出场景下内存曲线平稳。

---

### M5 · 成功下载后统一清理 `.part/.ytdl/.frag` 临时文件

- **改动函数**：
  1. `core/download_manager.py::_run_ytdlp_task()`（成功收尾，[`core/download_manager.py:1226`](core/download_manager.py:1226) 附近）
  2. `_delete_task_related_files()`（[`core/download_manager.py:1484`](core/download_manager.py:1484) 附近）
- **改动前**：成功后无统一清理，仅删除任务时清理。
- **改动后**：成功路径调用清理函数扫描输出目录下该任务的 `.part/.ytdl/.frag` 残留；**注意**保留 yt-dlp 断点续传所需的 `.part` 语义——仅在「确认任务最终成功」时清理，失败/停止时不清。
- **验收**：成功任务不残留临时文件；中断任务仍保留 `.part` 可供续传。

---

### M7 · `has_success_record` DB 异常时回退 JSON

- **改动函数**：`core/history_repo.py::has_success_record()`（[`core/history_repo.py:405`](core/history_repo.py:405)）
- **改动前**：`if not self.db_available: return False`。
- **改动后**：捕获 `sqlite3.OperationalError` 等 DB 异常后，回退到 `_load_json_history()` 的结果做存在性判断；空 JSON 时才返回 False。
- **验收**：DB 被锁期间批量下载不重复下载已成功视频。

---

### M8 · SQLite 与 JSON 双写一致性

- **改动函数**：
  1. `core/history_repo.py::save_task()`（[`core/history_repo.py:387`](core/history_repo.py:387)）
  2. `_save_failed_task()`（[`core/history_repo.py:393`](core/history_repo.py:393)）
- **改动前**：`db_saved = _insert_db_record(...); _save_json_item(...)`，两写独立。
- **改动后**：
  - 先写 JSON 作为「最终事实源」成功后再写 DB（或明确 DB 为主、JSON 为冗余）。
  - 统一字段口径：DB 侧 `profile` 至少补齐 `sub_lang/retries/custom_filename/preset_key`（联动 M13）。
  - 任一方失败时记录警告，但不在两源间产生互相矛盾的默认值。
- **验收**：两源记录字段一致，不出现重复/缺失。

---

### M13 · `load()` DB 分支补齐 profile 字段

- **改动函数**：`core/history_repo.py::load()` DB 分支（[`core/history_repo.py:369-371`](core/history_repo.py:369)）
- **改动前**：`profile` 只有 `{"format": row["format"]}`。
- **改动后**：DB 新增列（`sub_lang/retries/custom_filename/preset_key/merge_output_format/audio_quality/speed_limit`），迁移 schema；`load()` 读取并还原这些字段。
- **验收**：从 DB 加载的历史与 JSON 路径字段一致，UI 不再永远显示默认值。

---

### M9 · po_token 安装线程退出保护

- **改动函数**：
  1. `core/po_token_manager.py::_repair_and_retry()`（[`core/po_token_manager.py:350`](core/po_token_manager.py:350)，含 360-364 的 `shutil.rmtree`）
  2. `initialize_async()` / `_start_repair_thread()`（[`core/po_token_manager.py:133,213`](core/po_token_manager.py:133)）
  3. `YCB.pyw::_finalize_close()`（配合 H1）
- **改动前**：daemon 线程 `rmtree(node_modules)` + `npm install`（120s），退出时不等待。
- **改动后**：
  - 增加 `self._cancel = threading.Event()`；`_repair_and_retry` 在 `rmtree` 与 `npm install` 前后检查 `_cancel`，收到取消则跳过后续安装。
  - `_finalize_close` 通过该 Event 通知取消，并对安装线程做有限 `join(timeout=2)`，超时则不强杀 npm 子进程（记录提示）。
  - 将 `rmtree` 改为「先移动到 `.old` 折叠目录，安装成功后删」以降低半删除损坏风险。
- **验收**：退出时不残留 npm/node 子进程，`node_modules` 不被删到半成品。

---

### M10 · 修正常异常捕获元组

- **改动函数**：`core/po_token_manager.py::_detect_node()`（[`core/po_token_manager.py:314`](core/po_token_manager.py:314)）
- **改动前**：`except (FileNotFoundError, ValueError, subprocess.TimeoutExpired, OSError, Exception)` 含基类。
- **改动后**：移除 `Exception` 基类，改为 `except (FileNotFoundError, ValueError, subprocess.TimeoutExpired, OSError) as e:`，并 `logger.debug` 记录真实异常。
- **验收**：真实异常不再被静默伪装成「node 未安装」。

---

### M11 · `_run_npm_install` 补全异常捕获与状态复位

- **改动函数**：`core/po_token_manager.py::_run_npm_install()`（[`core/po_token_manager.py:346`](core/po_token_manager.py:346)）
- **改动前**：只捕 `FileNotFoundError/TimeoutExpired`，其它 `OSError` 冒泡导致 `STATUS_INSTALLING` 卡住。
- **改动后**：`except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:` 并在 `finally` 视结果置 `STATUS_ERROR`/`retry_wait`，确保状态机不会停在中途；`_repair_and_retry` 的 `finally` 也加状态兜底。
- **验收**：npm 安装失败后 UI 进入可重试的错误态，不卡「安装中」。

---

### M14 · 媒体探测移出 UI 线程

- **改动函数**：
  1. `ui/pages/media_tools.py::_refresh_media_info()`（[`media_tools.py:379`](ui/pages/media_tools.py:379)）
  2. `ui/pages/media_tools.py::_refresh_media_info_without_ffprobe()`（[`media_tools.py:416`](ui/pages/media_tools.py:416)）
- **改动前**：UI 线程同步 `subprocess.run(timeout=8)`。
- **改动后**：抽到 `threading.Thread(daemon=True)`，结果通过 `self.root.after(0, ...)` 回填 UI；加「探测中」禁用态防重入。
- **验收**：选择大文件媒体时 UI 不冻结。

---

### M16 · `components_center` 回调去重与注销

- **改动函数**：`ui/components_center.py::ComponentsCenter.__init__()`（[`components_center.py:29`](ui/components_center.py:29)）
- **改动前**：`get_manager().on_status_change(cb)` 无去重、无 `off_status_change`。
- **改动后**：
  - 为 `ComponentsCenter` 记录已注册回调用量，避免重复注册。
  - 增加 `destroy()`/取消注册逻辑（`on_status_change` 返回取消函数或提供 `off_status_change`），窗口关闭时注销，并解除对 `self` 的闭包引用。
- **验收**：反复开窗不累积回调，对象可被 GC。

---

### M17 · 历史中心分页/搜索

- **改动函数**：
  1. `ui/history_center.py::show_history()`（[`history_center.py:31`](ui/history_center.py:31)）
  2. `ui/pages/history_page.py`（[`history_page.py:67`](ui/pages/history_page.py:67)）
- **改动前**：`tk.Text` 逐条 `insert`，无分页无搜索。
- **改动后**：增加顶部搜索框（按标题/URL 过滤）与「上一页/下一页」分页（如每页 100 条），按需渲染当前页。
- **验收**：大量记录时 UI 流畅，可按关键词检索。

---

### M12 · 修复 `_build_pot_text` 的 `disabled` 分支不可达

- **改动函数**：`ui/app_shell.py::_build_pot_text()`（[`app_shell.py:183`](ui/app_shell.py:183)）
- **改动前**：`icons` 定义 `"disabled"` 但 if/elif 顺序未命中，落入「检测中」兜底。
- **改动后**：显式加入 `code == "disabled"` 分支，返回禁用专属文案/图标。
- **验收**：PO Token 禁用时顶栏显示「未启用」而非「检测中…」。

---

### M15 · 统一数字千分位格式化（避开 locale 敏感）

- **改动函数**：
  1. `ui/video_actions.py::_format_views()`（[`video_actions.py:173`](ui/video_actions.py:173)）
  2. `ui/pages/batch_source.py::_format_views()`（[`batch_source.py:407`](ui/pages/batch_source.py:407)）
- **改动前**：`f"{count:,}"` 依赖 locale。
- **改动后**：统一用 `"{:,}".format(count)` 之前先 `locale.setlocale(locale.LC_ALL, "C")`，或手写千分位插入不使用 locale；避免多处重复，可抽公共函数。
- **验收**：任意系统 locale 下观看数显示一致。

---

## 第三批：低严重度（25 条）

> 目标：清理会累积/污染状态的缺陷与死代码、冗余，风险低、可批量处理。

---

### L1 · 统一 `download_speed_limit` 默认值

- **改动函数**：`YCB.pyw::_init_shared_vars()`（[`YCB.pyw:472`](YCB.pyw:472)）与 `_sync_settings_state()`（[`YCB.pyw:849`](YCB.pyw:849)）
- **改动**：统一默认值口径（UI 与配置读取都用同一个常量，例如 `0` 表示不限速），消除 `"2"` 与 `0` 不一致。

### L2 · 修复 `_safe_int_config` 对 0 的短路

- **改动函数**：`YCB.pyw::_safe_int_config()`（[`YCB.pyw:129`](YCB.pyw:129)）
- **改动**：用 `if raw_value is None or raw_value == ""` 判断空值，避免 `0` 被当作默认值。

### L3 · `DEBUG_STARTUP_LOG` 改用 `base_path`

- **改动函数**：`ui/bootstrap.py`（[`bootstrap.py:6`](ui/bootstrap.py:6)）
- **改动**：`DEBUG_STARTUP_LOG = os.path.join(base_path, "startup_debug.log")`，frozen 下与程序目录一致。

### L4 · `load_window_pos` 键解引用安全化

- **改动函数**：`YCB.pyw`（[`YCB.pyw:324`](YCB.pyw:324)）
- **改动**：用 `pos.get("width")` 等带默认值读取，避免缺键 KeyError。

### L6 · `debug_startup` 增加大小限制

- **改动函数**：`ui/bootstrap.py::debug_startup()`（[`bootstrap.py:9`](ui/bootstrap.py:9)）
- **改动**：写前检查文件大小，超过阈值（如 1MB）做单次轮转或清空重写。

### L14 · 修正日志轮转 off-by-one

- **改动函数**：`core/log_sink.py::_rotate_if_needed()`（[`log_sink.py:38`](core/log_sink.py:38)）
- **改动**：调整 `range` 与 `backup_count` 语义，使 `backup_count=N` 恰好保留 N 个备份（不含当前文件）。

### L15 · `LogFileSink.flush` 加锁与多次轮转

- **改动函数**：`core/log_sink.py::LogFileSink.flush()`（[`log_sink.py:20`](core/log_sink.py:20)）
- **改动**：加 `threading.Lock`；写完后再次 `_rotate_if_needed()`，超限时循环轮转直到满足。

### L17 · `_build_history_item` 对 `task.profile` 安全解包

- **改动函数**：`core/history_repo.py::_build_history_item()`（[`history_repo.py:142`](core/history_repo.py:142)）
- **改动**：`task.profile` 判空或 `getattr` 默认值，避免 `profile is None` 时 AttributeError 丢历史。

### L18 · `settings.load()` 增加 `.bak` 兜底

- **改动函数**：`core/settings.py::WindowPositionRepository.load()`（[`settings.py`](core/settings.py)`load`）
- **改动**：加载失败时尝试读 `.bak`；写入前把旧文件复制为 `.bak` 再原子替换。

### L19 · `check_yt_dlp` 空版本号不返回 ok=True

- **改动函数**：`core/components_manager.py::check_yt_dlp()`（[`components_manager.py:85`](core/components_manager.py:85)）
- **改动**：`--version` 成功但 stdout 为空时，置 `ok=False` 或 `version="unknown"` 并提示，避免「正常但无版本号」矛盾态。

### L20 · `ConsoleLogger.log` 复用文件句柄

- **改动函数**：`backend_setup.py::ConsoleLogger`（[`backend_setup.py:82`](backend_setup.py:82)）
- **改动**：改为打开一次、复用句柄（或使用标准 logging），避免每次 open/close。属死代码，可按 H7 一并处理。

### L22 · 修复 TSpinbox 样式重复 configure

- **改动函数**：`ui/bootstrap.py`（TSpinbox 样式）
- **改动**：删除第一次被覆盖的 configure，仅保留一处正确的字体配置，去掉异常 `+3`。

### L7 · 异步化 `stop_task` 的 taskkill

- **改动函数**：`core/download_manager.py::stop_task()`（[`core/download_manager.py:1293`](core/download_manager.py:1293)）
- **改动**：`subprocess.run(taskkill)` 移到后台线程，避免 UI 线程最长 10s 阻塞。

### L12 · 增量更新选中态，避免全量 `selection_remove`

- **改动函数**：`core/download_manager.py::update_list()`（[`core/download_manager.py:365`](core/download_manager.py:365)）
- **改动**：记录每个被选中项的 id，刷新后仅对变化项做移除/恢复，消除高频刷新闪烁。

### L16 · `deno_runner` 增加 `startupinfo` 隐藏窗口

- **改动函数**：`core/deno_runner.py::run_deno_script()`（[`deno_runner.py:55`](core/deno_runner.py:55)）
- **改动**：传入 `STARTF_USESHOWWINDOW` 的 `startupinfo`，消除 hook 触发黑窗。

### L8 · `build_ytdlp_command` 去除 setattr 副作用

- **改动函数**：`core/ytdlp_builder.py::build_ytdlp_command()`（[`ytdlp_builder.py:38`](core/ytdlp_builder.py:38)）
- **改动**：将 `used_cookies/actual_cookies_mode` 作为返回值或单独参数回传，不在构建函数内 `setattr` 改 task 对象。

### L11 · `_delete_tasks` 与 `run_task` 收尾时序固化为状态机

- **改动函数**：`core/download_manager.py::_delete_tasks()`（[`download_manager.py:1341`](core/download_manager.py:1341)）与 `run_task()`（[`download_manager.py:553`](core/download_manager.py:553)）
- **改动**：已有 `_delete_after_stop` 兜底，进一步把「删除 vs 收尾」收口到 `_state_lock` 下的状态判定，消除重入队列窗口。

### L13 · watchdog 超时参数化（待确认后处理）

- **改动函数**：`core/download_manager.py` 看门狗
- **改动**：将 `timeout_idle=300/timeout_no_progress=600` 提为可配置项；若确认无需暴露，保留默认并可暂缓。

### L5 · 移除 `register_input_frame` 的 `input_frame` 死赋值

- **改动函数**：`YCB.pyw::register_input_frame()`（[`YCB.pyw:719`](YCB.pyw:719)）及 `ui/download_tab.py`
- **改动**：删除 `self.ytdlp_manager.input_frame = frame` 或补上实际用途，消除无读用的死代码。

### L23 · 清理 `load_history` 的 mode 冗余

- **改动函数**：`ui/history_actions.py::load_history()`（[`history_actions.py:168`](ui/history_actions.py:168)）
- **改动**：若 mode 确实无差异化，删除无效 `os.path.exists` 分支；否则补全 mode 差异化实现。

### L24 · 删除 `video_actions.py:99-106` 重复语句块

- **改动函数**：`ui/video_actions.py::fetch_formats_async()`
- **改动**：删除重复的 `frame.format_fetch_used_cookies = False` 等语句块。

### L25 · `batch_source` 移除循环内重复校验

- **改动函数**：`ui/pages/batch_source.py::add_selected_tasks()`（[`batch_source.py:1150,1197`](ui/pages/batch_source.py:1150)）
- **改动**：将 `validate_download_sections` 移到循环外单次校验。

### L9 / L10 / L21（含待确认，见下方确认后实施）

- **L9** `ffmpeg_args_policy.py` 黑名单：需产品确认是否放行 `-c/-vf/-af`。
- **L10** `youtube_metadata.py:654` `fetch_title` 首行截断：确认后改为完整标题拼接。
- **L21** `ui/i18n.py` 重复 key（`batch_manual_hint`、`media_warn_*` 英文段）：确认保留哪一份后删除重复。

---

## 待确认项（5 条）

| 编号 | 内容 | 需要确认的问题 | 确认后动作 |
|---|---|---|---|
| T1 | `run_and_refresh` 5 个检测线程 `join(timeout=15)` 后子进程残留 | 是否需要在退出时强制回收检测子进程 | 是→在 `_finalize_close` 记录检测进程并 taskkill |
| T2 | cookies 运行时无更换入口 | 是否是有意设计（仅默认位置） | 是→保持；否→在设置页补「浏览 cookies 文件」并持久化 |
| T3 | `os.remove` 失败实际频率 | 组件占用触发频率（决定 H6 优先级） | 实测后调整 H6 是否紧急 |
| T4 | URL 白名单不含 `music.youtube.com` | 是否需支持 YouTube Music | 是→把 `music.youtube.com` 加入 [`ui/input_validators.py:104`](ui/input_validators.py:104) |
| T5 | `repair_po_token` 同步 npm install 阻塞 UI | `repair()` 是否走同步安装路径 | 是→改走 `initialize_async` 后台线程（联动 M9/M11） |

---

## 修复顺序与依赖关系总结

1. **先做第 0 节**（Cookies 同步），否则用户侧仍不可见已有修复。
2. **第一批 H1→H3→H2/H4→H5→H6→H7**：先闭环退出/停止（H1/H3 引出的锁与标志），再解竞态（H2/H4 复用同一套路），再修数据与安装器，最后下架死代码。
3. **第二批 M2/M1/M3→M13/M7/M8（数据一致性）→M9/M10/M11（po_token）→M14/M16/M17/M12/M15（UI）**；M4 建议并入第一批停止机制重构时一并完成。
4. **第三批按「会累积/污染状态」优先**：L2→L21→L18→L14/L15→L17，其余死代码与冗余（L5/L23/L24/L25）批量清理。
5. **待确认项**先落地 T4、T5 这两个有明确用户感知的项，再跟进 T1/T3 实测，T2 按产品意图决定。

---

## 验收总则

- 每批完成后统一执行 `python -m py_compile YCB.pyw` 与涉及模块的语法检查。
- 回归冒烟路径：启动 → 加载配置 → 单视频下载 → 批量下载 → 停止任务 → 退出，确认无孤儿进程、无崩溃、历史/配置落盘正确。
- 高/中严重度修改建议各自加最小化日志，便于后续定位。