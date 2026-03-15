# YouTube 下载程序全面修复实施指南（分步含代码详情）

本文档根据前期的系统性代码审查与试运行发现的问题，提供逐一排查并修复程序页面布局与内部逻辑错误的**完整、细致、可复制的代码修复方案**。您可以（或由 AI）按照先后顺序将以下代码片段合入对应文件。

---

## Step 1: 修复单视频任务构建主链路问题 (ui/input_validators.py, ui/pages/single_video.py)

**问题描述**：
1. `prepare_direct_task` 中忽略了手动格式下拉选择，直接赋值 `None`。
2. 直接下载模式未继承格式获取阶段成功的 `cookies` 需求。
3. 获取到的 `format` 下拉项存在分隔符解析与界面选择不同步的安全漏洞（需挂载 `ComboboxSelected`）。

**修改 1：`ui/input_validators.py`**
修复 `get_selected_format_id` 按 `|` 安全切割，并在 `prepare_direct_task` 中规范化格式获取与 cookies 继承。
```python
# 修改点：get_selected_format_id
def get_selected_format_id(frame):
    """返回当前选中的格式 ID。"""
    selected = getattr(frame, "selected_format_id_var", None)
    if selected:
        format_id = selected.get().strip()
        if format_id:
            return format_id

    fmt_choice = frame.format_var_combo.get().strip()
    if not fmt_choice:
        frame.app.SilentMessagebox.showwarning("提示", "请先获取并选择格式")
        return None
    return fmt_choice.split('|', 1)[0].strip()  # 指定按 | 分割

# 修改点：prepare_direct_task
def prepare_direct_task(frame, url):
    """构建直接下载任务。"""
    preset_key = sync_output_format_by_preset(frame)
    profile = build_profile_from_input(frame)
    profile.preset_key = preset_key or "manual"
    preset_format = get_selected_preset_format(frame)
    if preset_format:
        profile.format = preset_format
    else:
        format_id = get_selected_format_id(frame)
        if not format_id:
            return None
        profile.format = f"{format_id}+bestaudio[ext=m4a]"
    profile.merge_output_format = get_selected_output_format(frame, profile.preset_key)
    task = create_task_record(frame, url, profile)
    apply_task_save_path(frame, task)
    apply_task_cookies_requirement(frame, task) # 继承 Cookies 需求
    return task
```

**修改 2：`ui/pages/single_video.py`**
在初始化区域为 `format_combo` 增加下拉选中事件绑定。
```python
        # 添加绑定事件
        self.format_combo.bind("<<ComboboxSelected>>", self._on_format_combo_selected)

    # 补充回调函数
    def _on_format_combo_selected(self, _event=None):
        raw = self.format_var_combo.get().strip()
        format_id = raw.split('|', 1)[0].strip() if raw else ""
        self.selected_format_id_var.set(format_id)
        if format_id:
            self.preset_var.set("manual")
            self._on_preset_changed()
            self._update_filename_preview()
```

---

## Step 2: 修复输入合法性与回调稳定性 (ui/input_validators.py)

**问题描述**：
如果用户在“重试次数”、“并发数”等框中输入非数字字符，旧版由于直接强转 `int()` 而触发 `ValueError` 导致整个界面挂起或抛错。

**修改：`ui/input_validators.py`**
增加通用的安全整数类型转换并显示警告：
```python
def _show_input_warning(frame, message):
    frame.manager.log(f"⚠️ 输入值无效，已回退默认值: {message}", "WARN")
    frame.app.SilentMessagebox.showwarning("提示", message)

def _coerce_int_input(frame, var_name, default, minimum=None, maximum=None, label="数值"):
    variable = getattr(frame, var_name, None)
    if variable is None:
        return default

    raw_value = str(variable.get()).strip()
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        variable.set(default)
        _show_input_warning(frame, f"{label}输入无效，已自动恢复为 {default}")
        return default

    if minimum is not None and value < minimum:
        variable.set(default)
        _show_input_warning(frame, f"{label}不能小于 {minimum}，已自动恢复为 {default}")
        return default

    if maximum is not None and value > maximum:
        variable.set(default)
        _show_input_warning(frame, f"{label}不能大于 {maximum}，已自动恢复为 {default}")
        return default

    return value

# 修改 build_profile_from_input：改用防护转换
def build_profile_from_input(frame):
    format_value = frame.format_var_combo.get().strip() or P1080_FMT
    custom_filename = frame.custom_filename_var.get().strip()
    retries = _coerce_int_input(frame, "retry_var", 3, minimum=0, maximum=10, label="重试次数")
    speed_limit = _coerce_int_input(frame, "speedlimit_var", 0, minimum=0, maximum=100, label="限速")
    concurrent = _coerce_int_input(frame, "concurrent_var", 1, minimum=1, maximum=10, label="并发数")
    ...
```

---

## Step 3: 修复历史写入并发与降级策略 (core/history_repo.py)

**问题描述**：
1. 多线程并发完成任务时，写入 `JSON` 会触发 `PermissionError`，导致记录丢失。
2. SQLite 如果遇到短暂的 `database is locked`，当前代码会永远禁用 DB（`self.db_available = False`）。

**修改：`core/history_repo.py`**
加入文件级别互斥锁以及 SQLite 锁等待重试机制。
```python
    def __init__(self, history_file, db_path=None):
        ...
        self._json_lock = threading.Lock() # 新增 JSON 写锁
        self._db_retry_count = 3
        self._db_retry_delay = 0.15
        self._init_db()

    def _save_json_item(self, history_item):
        with self._json_lock: # 使用互斥锁保证安全写文件
            history_data = self._load_json_history()
            history_data.insert(0, history_item)
            self._write_json_history(history_data[:100])

    def _insert_db_record(self, item):
        if not self.db_available:
            return False
        for attempt in range(self._db_retry_count):
            try:
                with sqlite3.connect(self.db_path, timeout=2.0) as conn:
                    conn.execute(...)
                    conn.commit()
                self.init_error = ""
                return True
            except sqlite3.OperationalError as exc:
                message = str(exc).lower()
                # 遇到锁资源问题加入退避重试，不立即宣告彻底失败
                if "database is locked" in message or "database table is locked" in message:
                    if attempt < self._db_retry_count - 1:
                        time.sleep(self._db_retry_delay * (attempt + 1))
                        continue
                    self.init_error = str(exc)
                    return False
                self.db_available = False
                self.init_error = str(exc)
                return False
            except Exception as exc:
                self.db_available = False
                self.init_error = str(exc)
                return False
        return False
```

---

## Step 4: 修复元数据解析抗崩溃性 (core/youtube_metadata.py)

**问题描述**：
`yt-dlp` 返回非期望信息（如报错、警告字符串）时，`json.loads(proc.stdout)` 会直接触发 `JSONDecodeError` 崩溃。

**修改：`core/youtube_metadata.py`**
包裹所有的 JSON 操作，并封装标准化安全错误对象输出。
```python
    def fetch_formats(self, url):
        cmd = [self.yt_dlp_path, "--dump-single-json", "--no-warnings", url]
        proc, used_cookies = _run_json_command(cmd, self.cookies_file_path, 60, self.startupinfo)
        # ...
        try:
            info = json.loads(proc.stdout.strip())
        except Exception as exc:
            return self._json_parse_error_result(f"JSON 解析失败: {exc}", used_cookies=used_cookies)
```

---

## Step 5: 修复外部依赖原子更新安全性 (ui/app_actions.py)

**问题描述**：
yt-dlp 更新时直接覆盖 `yt-dlp.exe`，网络一旦中断就会留下一个损坏的 exe。

**修改：`ui/app_actions.py`**
改为先下载到 `.tmp` 文件，校验通过后再经由 `.bak` 做原子覆盖。
```python
    def run_update():
        tmp_path = yt_dlp_path + ".tmp"
        backup_path = yt_dlp_path + ".bak"
        try:
            # 清理历史缓存
            if os.path.exists(tmp_path): os.remove(tmp_path)
            if os.path.exists(backup_path): os.remove(backup_path)

            urllib.request.urlretrieve(url, tmp_path)
            
            # 校验临时文件
            verify_proc = subprocess.run([tmp_path, "--version"], capture_output=True, text=True, timeout=15)
            if verify_proc.returncode != 0:
                raise RuntimeError("临时文件校验失败")

            # 原子级覆盖文件
            if os.path.exists(yt_dlp_path):
                os.replace(yt_dlp_path, backup_path)
            try:
                os.replace(tmp_path, yt_dlp_path)
            except Exception:
                if os.path.exists(backup_path):
                    os.replace(backup_path, yt_dlp_path)
                raise
```

---

## Step 6: 解决交互事件双开与进程树残留 (JJH_download.pyw, ui/video_actions.py)

**问题描述**：
1. 连续点击快速获取格式会开出多线程。
2. 直接关闭窗口时没有妥善通知 manager 停止 ffmpeg 进程。

**修改 1：`ui/video_actions.py` (防双击)**
```python
def fetch_formats_async(frame):
    if getattr(frame, "_format_fetch_in_progress", False):
        frame.manager.log("⚠️ 格式获取正在进行中，请勿重复点击", "WARN")
        return

    frame._format_fetch_in_progress = True
    if getattr(frame, "fetch_formats_button", None):
        frame.fetch_formats_button.configure(state="disabled")

    def finish_fetch():
        frame._format_fetch_in_progress = False
        if getattr(frame, "fetch_formats_button", None):
            frame.fetch_formats_button.configure(state="normal")
            
    # run_fetch 后需调用 finish_fetch
```

**修改 2：`JJH_download.pyw` (安全退出清理)**
```python
    def _on_close(self):
        # ...弹窗确认后
        if busy_states:
            # ...
            self.ytdlp_manager.stop_all() # 停止所有子进程队列
            time.sleep(0.2) # 给信号传递留一点点时间

        self.save_ui_state()
        save_window_pos(self.root, self.position_repo)
        self.root.destroy()
```

以上为依据排查结果所产生的完整配套修理逻辑细节。目前当前代码库实际上已应用了上述所有修复。
