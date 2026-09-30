# YCB 下载器 全面 Debug 报告

- 生成日期：2026-09-10
- 审查范围：`YCB.pyw`、根目录脚本、`core/` 全部模块、`ui/` 全部模块、`tools/po_token/` 脚本
- 审查方式：通读源码 + `py_compile` 静态检查（40/40 通过）+ i18n 键一致性对照（zh 804 / en 804，运行时引用 580 键无缺失）+ `logs/ycb_downloader.log` 运行日志取证
- 严重程度分级：P0 = 数据丢失/功能错误/卡死风险；P1 = 功能缺陷/明显卡顿；P2 = 逻辑瑕疵/一致性问题；P3 = 代码卫生/边缘情况

---

## 一、验证结果摘要（通过项）

| 检查项 | 结果 |
|---|---|
| 全部 40 个 Python 文件 `py_compile` 语法检查 | 全部通过，无语法错误 |
| i18n 双语表一致性（`ui/i18n.py`） | zh=804 键、en=804 键，完全对齐 |
| 代码中实际使用的 580 个字面量 `get_text` 键 | 0 缺失 |

---

## 二、P0 级缺陷（必须优先修复）

### P0-1 看门狗对“静默卡死”的下载无效
- 位置：[核心 `core/download_manager.py`](../core/download_manager.py) `YouTubeDownloadManager._stream_download_output`（约 1127-1166 行）与 `_watchdog_tick`（约 1113-1125 行）
- 问题：`_watchdog_tick(task, timeout_idle, timeout_no_progress)` 只在**每读取到一行 stdout** 时才被调用。若 yt-dlp 子进程彻底沉默（不产生任何输出也不退出），读取循环永远阻塞在等待新行上，看门狗逻辑永远不会执行，`timeout_idle` / `timeout_no_progress` 形同虚设，下载线程永久挂起。
- 影响：任务长时间“运行中”但无任何进展，只能手动停止。
- 建议：改为独立看门狗线程定时检查 `last_output_time`/`last_progress_time`；或使用 `select`/带超时的读取，使超时判断不依赖“有新输出”。

### P0-2 ffmpeg 裁剪（trim）时间轴错误，产出片段时长错误
- 位置：[核心 `core/ffmpeg_builder.py`](../core/ffmpeg_builder.py) `build_ffmpeg_command` 的 trim 分支（161-382 行内）
- 问题：命令构造为 `ffmpeg -y -ss start -i input ... -to end ...`。`-ss` 在 `-i` **之前**属于输入快速定位，ffmpeg 会将时间戳重置为 0；而 `-to` 在 `-i` **之后**属于输出选项，其值是相对**重置后**的时间轴计量的。结果是 trim(60s→120s) 会输出约 120 秒而非预期的 60 秒片段。
- 对比：`core/download_manager.py::_run_local_section_fallback` 中 `-ss start -to end -i source -c copy`（两个时间都在 `-i` 之前）写法是正确的，仅 `ffmpeg_builder` 的 trim 分支有错。
- 建议：将 `-ss`/`-to` 同时放在 `-i` 前；或 `-ss` 保持在 `-i` 前、把 `-to end` 改为 `-t (end-start)`。

### P0-3 删除下载任务可能误删用户已有文件
- 位置：[核心 `core/download_manager.py`](../core/download_manager.py) `_delete_task_related_files`（约 1565-1590 行）、`_is_task_output_artifact`（约 1544-1563 行）、`_should_cleanup_related_files_on_delete`（约 1440-1444 行）
- 问题：删除任务时用 `custom_filename` / `final_title` 生成文件名主干，再用扩展名集合（`.mp4/.mkv/.webm/.m4a/.mp3` 等）在输出目录里按“主干匹配”删文件。一个**从未运行过**的等待任务，若其 `custom_filename` 与用户目录里已有文件同名，删除该任务会把用户的已有文件一并删掉。这是真实的数据丢失风险。
- 建议：仅清理“本任务实际创建过”的产物（记录实际输出路径或仅清理任务运行后出现的临时/分片文件）；至少对从未进入 running 状态的任务禁用按文件名删除。

---

## 三、P1 级缺陷

### P1-1 PO Token 的 `--extractor-args` 拼接格式错误（两处）
- 位置：[核心 `core/ytdlp_builder.py`](../core/ytdlp_builder.py) `build_ytdlp_command`（约 180 行附近）；[核心 `core/youtube_metadata.py`](../core/youtube_metadata.py) `_run_json_command`（约 392-442 行）
- 问题：构造了 `youtube:player_client=web,po_token=visitor_data={visitor_data},po_token={po_token}`——`po_token=` 键被重复使用了两次，且 `visitor_data` 应作为**独立键** `visitor_data=`，不是 `po_token` 的值。yt-dlp 侧通常还需要 `web.gvs+` 之类的作用域前缀。
- 影响：启用 PO Token 后提取器参数不被按预期解析，下载/元数据获取在需要 PO Token 的场景下仍可能失败。
- 建议：改为 `youtube:player_client=web;po_token=web.gvs+{token}` + 独立 `visitor_data={vd}`（依 yt-dlp 版本语法为准），两处同步修复。

### P1-2 `media_jobs.stop_job` 在调用线程上同步执行 taskkill，可冻结 UI 最长 10 秒
- 位置：[核心 `core/media_jobs.py`](../core/media_jobs.py) `stop_job`（361-380 行）
- 问题：`subprocess.run(['taskkill', '/F', '/T', '/PID', pid], timeout=10)` 在调用方（通常是 UI 线程）上同步执行。对比 `download_manager.stop_task` 已正确地把 taskkill 放到后台线程（`download_manager.py` 约 1340-1379 行），两者行为不一致。
- 建议：与 `stop_task` 一致，改为后台线程执行，立即返回。

### P1-3 选择 mkv 时同时下发 `--merge-output-format mkv` 与 `--remux-video mkv`
- 位置：[核心 `core/ytdlp_builder.py`](../core/ytdlp_builder.py) `build_ytdlp_command`
- 问题：两个选项都会触发封装/转封装处理，属于冗余的“双重后处理”，浪费一次ffmpeg调用并可能产生非预期的文件状态。
- 建议：二选一（推荐仅保留 `--merge-output-format mkv`）。

### P1-4 手动选择纯音频格式时错误追加 `+bestaudio[ext=m4a]`
- 位置：[界面 `ui/input_validators.py`](../ui/input_validators.py) `prepare_standard_task`（600-619 行）、`prepare_direct_task`（622-639 行）
- 问题：未区分所选格式是纯视频还是纯音频，统一拼接 `{format_id}+bestaudio[ext=m4a]`。当用户选的就是音频格式时，会出现“音频+音频”的合并或非法组合。
- 建议：仅当所选格式不含音频（vcodec 有值且 acodec 为 none）时才追加 `+bestaudio`。

---

## 四、P2 级缺陷

### P2-1 PO Token 状态信息把“原始 i18n 键”写进了日志
- 位置：[主入口 `YCB.pyw`](../YCB.pyw) `check_others`/`on_status_change` 回调
- 问题：状态回调直接把 message 键（如 `pot_msg_checking`）输出到日志而未翻译。运行日志 `logs/ycb_downloader.log` 已有实证：`PO Token 状态更新: [unknown] pot_msg_checking`。
- 建议：回调处先经 `get_text` 翻译再记录/展示。

### P2-2 剪贴板监听存在死代码，`delay_ms` 实际未生效
- 位置：[主入口 `YCB.pyw`](../YCB.pyw) `_start_clipboard_watch`
- 问题：局部变量 `interval` 被计算后从未使用；`on_paste_event` 传入的 `delay_ms` 也没有真正参与调度，属于误导性实现。
- 建议：删除无效变量或让 `delay_ms` 真正控制 `after` 的延迟。

### P2-3 关闭确认弹窗出现双连字符“- - 条目”
- 位置：[主入口 `YCB.pyw`](../YCB.pyw) 关闭确认逻辑（`close_confirm_message` 拼接处）
- 问题：消息模板本身已含 `- ` 前缀，调用方传入的条目又自带 `- ` 前缀，渲染结果变成 `- - xxx`。
- 建议：统一由模板负责前缀，调用方只传纯文本条目。

### P2-4 `po_token_manager` 的若干并发/卫生问题
- 位置：[核心 `core/po_token_manager.py`](../core/po_token_manager.py)
  - `import sys` 重复导入两处（约 13 行与 19 行）；
  - `_status_callbacks`（168-186 行）注册/注销/遍历未加锁，存在遍历期被修改的风险；
  - `_start_repair_thread`（242-250 行）中 `self._cancel.clear()` 可能把已挂起的 `request_stop()` 取消请求一并清除，导致“取消后又被意外复活”。
- 建议：回调列表加锁或遍历时快照；clear 前判断是否已有停止请求。

### P2-5 历史仓库两处不一致
- 位置：[核心 `core/history_repo.py`](../core/history_repo.py)
  - `load()`（369-430 行）返回条目丢弃了 `failure_detail` 字段，失败详情在 UI/排查链路丢失；
  - JSON 读取截断上限 100 条，而 SQLite `load` 上限 200 条，两个事实源不一致（`_load_json_history` 327-358 行 vs `load`）。
- 建议：补齐字段；统一上限。

### P2-6 Hook 配置缺少 `events` 键时任何事件都不会触发
- 位置：[核心 `core/hooks.py`](../core/hooks.py) `load_hook_config`（21-39 行），`events=list(data.get("events") or [])`
- 问题：配置缺省时归一化为空列表，后续 `HookDispatcher.emit` 不会发射任何事件——一个“启用但未配 events”的配置静默失效。
- 建议：缺 `events` 时给出默认全集或在加载时警告。

### P2-7 组件中心窗口在 UI 线程上同步跑 3 个子进程检测
- 位置：[界面 `ui/components_center.py`](../ui/components_center.py) `_render_statuses`（94-103 行）
- 问题：`check_yt_dlp()`、`check_ffmpeg()`、`check_deno()` 各自可能阻塞至 6 秒（`components_manager._run_version` 默认 timeout=6），合计最坏约 18 秒卡死窗口。
- 建议：改为后台线程检测，`after` 回填 UI（与 `media_tools._refresh_media_info` 的异步模式一致）。

### P2-8 硬编码中文泄漏（不受 i18n 控制）
- 位置：[核心 `core/youtube_models.py`](../core/youtube_models.py) `get_display_name`（269-298 行）/ `sanitize_archive_segment(value, fallback="未命名")`（218-226 行）；[核心 `core/media_jobs.py`](../core/media_jobs.py) `MediaJobRecord.get_display_name`（73-95 行，英文界面下仍出现中文名称）
- 建议：回退文案走 `get_text` 键。

### P2-9 开发态调试日志被写到 `ui/` 目录，与根目录日志重复
- 位置：[界面 `ui/bootstrap.py`](../ui/bootstrap.py) `DEBUG_STARTUP_LOG`（开发态以 `ui/` 为 base）与根目录 `startup_debug.log`
- 现状：工作区同时存在 `startup_debug.log` 与 `ui/startup_debug.log`。
- 建议：开发态也统一写到项目根目录。

---

## 五、P3 级（卫生/边缘情况）

1. `fix_metadata.py` —— 写死了开发者机器绝对路径 `c:\Users\qinghua\...`，仅供本机使用，应参数化或移入 `tools/`。
2. `backend_setup.py` —— 文件头已标注“已废弃、未接线”，属死代码；建议移出仓库或隔离到 `legacy/` 以免误导维护（其附带打包规格 `backend_setup.spec`、`build/backend_setup/` 同理）。
3. `YCB.pyw::_check_dependencies_and_log` —— 当 `yt_dlp_path` 为 `None` 时会把底层 `TypeError: expected str, bytes or os.PathLike object, not NoneType` 原文写进日志（日志中已有实证），应先判空给出友好文案。
4. `ui/pages/batch_source.py::add_selected_tasks`（1136-1241 行）—— 不加 `_state_lock` 直接读取 `manager.task_queue` / `running_tasks` 判断容量，与工作线程存在竞态。
5. `core/ffmpeg_builder.py` —— `extract_audio` 分支在用户同时指定 `audio_codec` 时可能输出重复的 `-c:a` 选项。
6. `ui/pages/media_tools.py` —— concat 任务 UI 未强制要求输出路径，而 `ffmpeg_builder` 必需该值，会在运行期才报错；`_validate_inputs` 中水印分支 `getattr(..., tk.StringVar())` 会构造一次性弃用变量；trim 时间输入缺少格式校验。
7. `ui/input_validators.py::_coerce_int_app` —— 嵌套的二次强转路径可能重复弹告警；`validate_custom_filename` 的“首尾空格”检查因上游已 `strip()` 而成为不可达代码。
8. `tools/po_token/generate_token.js` —— 结构与看门狗（`armWatchdog`/`scheduleExit`）设计正确；建议补充一点：Node 侧 stdout JSON 解析失败时 Python 侧 `_extract_node_error` 仅取 stderr 首几行，`console.log` 之外的多余输出会污染 JSON 解析（`po_token_manager._generate_token` 已 strip，但日志噪音仍会增加排障成本）。

---

## 六、建议的修复优先级

1. **第一批（本周）**：P0-1 看门狗线程化、P0-2 trim 时间轴、P0-3 删除任务误删文件保护。
2. **第二批**：P1-1 PO Token extractor-args（两处）、P1-2 stop_job 异步化、P1-3 mkv 双参数、P1-4 音频格式追加条件。
3. **第三批**：P2 系列（i18n 日志、组件中心异步化、po_token_manager 锁/重复导入、历史字段与上限一致）。
4. **日常清理**：P3 系列。

> 报告完成。所有结论均来源于对上述源码文件的直接阅读，并部分以 `logs/ycb_downloader.log` 的真实运行记录佐证。
