# 批量下载：手动分辨率/编码/格式开发方案（修订版）

## 1. 目标（为什么要做）
当前程序在“单视频下载”场景中已经支持：拉取可用格式列表 → 用户手动选择某个分辨率/编码/容器 → 发起下载。

但在“播放列表/频道下载（批量）”场景中，只支持固定的“下载策略预设”（最佳画质/最佳兼容/最高1080p/最高4K/仅音频/最小体积），无法让用户像单视频那样精确指定“分辨率 + 编码 + 容器偏好”。

本次修订后的目标分为两层：
- 批量页现有“全局输出格式”从 `mp4/mkv` 扩展为 `mp4/mkv/webm`。
- 在批量下载页面的现有策略区后面新增一个“手动设置”按钮。
- 点击按钮弹出独立窗口：支持手动策略，并分阶段交付。
- 用户在手动策略中只关心 **分辨率（按高度）**、**编码**、**视频流容器偏好 mp4/webm**；**忽略帧率**。
- 批量运行时尽量保证下载成功率；当发生回退/降级时给出明确提示。

说明：
- “全局输出格式”指最终文件容器，沿用现有 `merge_output_format` 语义。
- “视频流容器偏好 mp4/webm”指 `-f` 表达式中的视频流筛选条件，不等同于最终输出格式。
- 为避免 UI 歧义，后续文案建议把手动弹窗中的“输出格式 mp4/webm”改名为“视频流容器偏好”。

## 2. 约束与现实边界（做之前必须想清楚）
### 2.1 性能约束：不能对每条视频拉一次 formats
播放列表/频道可能包含大量视频。若为每条视频都调用一次 `fetch_formats`，会导致：
- UI 卡顿/等待时间大幅增加。
- 请求次数高，容易触发风控或失败。
- 体验不稳定。

因此确定策略：
- **只拉取“样本视频”的 formats 一次**，用于给用户提供预设1/2的可选项。
- 批量中其他视频不拉 formats，仅使用规则表达式让 yt-dlp 自行匹配。

### 2.2 “逐条最终命中格式”的提示边界
由于批量不逐条拉 formats，入队时无法 100% 确认每条视频最终选中了哪个具体 format_id。
- 入队阶段最多只能提示“将按规则尝试”的表达式。
- 若要做到“提示这条视频最终采用什么分辨率/码率下载”，需要在下载过程中解析 yt-dlp 输出的最终 format 并回填日志/历史记录，放入 V3。

### 2.3 规则落地的最优解：表达式法优先
批量不拉 formats，无法使用“format_id 精确拼接法”。

因此批量最优解是：把预设转换为 yt-dlp 的 `-f` **格式选择表达式**（含多段回退），交由 yt-dlp 在每条视频上自行匹配。

### 2.4 输出格式与手动容器偏好必须分层
当前代码里：
- `profile.format` 负责注入 `-f` 表达式。
- `merge_output_format` 负责最终输出容器。
- `preset_key` 影响任务展示、日志摘要、历史记录。

因此本方案必须统一以下口径：
- 批量页主面板上的“全局输出格式”扩展为 `mp4/mkv/webm`。
- 手动弹窗里的 `mp4/webm` 只表示“视频流容器偏好”。
- 启用手动策略后，需要同时覆写 `profile.format`，并将 `profile.preset_key` 设为 `manual`，避免摘要/历史仍显示旧预设。

### 2.5 音频能力先收敛，避免 UI 承诺超出后端能力
现有格式数据结构对音频码率筛选支持不够完整；“选择音频格式/码率”不适合在第一阶段就做成强承诺。

因此：
- V1 只支持 `default` / `no_audio`。
- `audio select`（格式/码率）放到 V3。
- 若未来需要严格音频码率约束，应先补强格式元数据与后处理逻辑。

### 2.6 “最近分辨率”不宜在 V2 做硬承诺
只靠 `-f` 表达式，不逐条预抓 formats，很难稳定实现严格意义上的“最近更高 / 最近更低 / 最接近”。

因此文案与实现口径建议调整为：
- 预设1/2：严格匹配目标高度 + 编码优先级回退。
- 兜底链：优先同高，其次更高可用，再次更低可用，最后任意可用。
- 不在 V2 文案中承诺“绝对最近”，避免误导。

## 3. 现有代码切入点（我们复用什么）
### 3.1 单视频格式拉取与列表刷新
- `ui/video_actions.fetch_formats_async()`：后台拉格式、回填 UI。
- `ui/video_actions.refresh_format_view()`：刷新格式视图。

### 3.2 yt-dlp 命令注入点
只要设置 `task.profile.format`，命令构建会在以下位置注入 `-f`：
- `core/ytdlp_builder.build_ytdlp_command()` 中：如果 `fmt` 存在则 `cmd.extend(["-f", fmt])`。

### 3.3 批量页策略区与输出格式区
- 批量页策略 radiobutton 位于 `ui/pages/batch_source.BatchSourceInputFrame._create_widgets()` 中的 `preset_row`。
- 批量页现有输出格式下拉框位于 `output_row`，本次需要把视频输出格式从 `mp4/mkv` 扩展为 `mp4/mkv/webm`。

### 3.4 入队与任务展示链路
- 批量入队统一通过 `build_profile_from_input(self)` 构建 profile。
- 若启用手动策略，需要在入队时覆写 `profile.format` 与 `profile.preset_key`。
- 任务展示、日志摘要、历史记录都会读取 `preset_key` 与 `format`，因此不能只改 `format` 不改 `preset_key`。

## 4. 用户规则口径（修订后）
### 4.1 预设1/2 的严格匹配规则
- 目标维度：高度、编码、视频流容器偏好。
- fps 一律忽略。
- 同高度不同编码时，编码优先级固定为：`h264 > av1 > vp9`。
- 若用户未指定编码，则允许同高度任意编码。
- 若用户未指定视频流容器偏好，则允许同高度任意视频流容器。

### 4.2 兜底规则（V2 开始）
- 第一优先级：同高度。
- 第二优先级：更高可用。
- 第三优先级：更低可用。
- 最终兜底：`bestvideo` 或 `/best`。
- 文案使用“回退/降级到可用格式”，不使用“绝对最近分辨率”。

### 4.3 音频规则
- V1：仅支持
  - `default`：按现有行为拼接 `+bestaudio`
  - `no_audio`：不拼音频
- V3：再扩展
  - 选择音频格式
  - 选择音频码率
  - 必要时补充后处理逻辑

### 4.4 全局输出格式规则
- 批量页主面板“全局输出格式”支持：`mp4` / `mkv` / `webm`。
- 手动策略不直接决定最终输出格式，仍由主面板全局输出格式决定。
- 若用户选择 `webm` 作为全局输出格式，需要验证与封面、字幕内嵌、元数据等后处理组合的兼容性；这属于实现与验收重点。

## 5. 分期交付策略（降低风险）
- **V1（最小闭环）**
  - 批量页全局输出格式增加 `webm`。
  - 批量页新增“手动设置”按钮 + 弹窗。
  - 只实现预设1。
  - 只实现视频维度：分辨率 / 编码 / 视频流容器偏好。
  - 音频只支持 `default` / `no_audio`。
  - 生成 yt-dlp `-f` 表达式写入 `profile.format`。
  - 启用手动策略时将 `profile.preset_key` 设为 `manual`。
  - 入队时输出“规则提示”（表达式 + 样本限制说明）。

- **V2（功能扩展）**
  - 预设2 可选。
  - 增加兜底链。
  - 完善编码优先级回退表达式。
  - 批量摘要、日志、结果提示中补充“手动策略已启用 / 启用兜底”。

- **V3（体验增强）**
  - 音频 `select`（格式/码率）更完整。
  - 必要时增加音频后处理逻辑。
  - 下载过程中解析 yt-dlp 实际命中，回填“逐条最终命中提示”。

### 5.1 建议再拆成可落地补丁
为提高开发成功率，建议把 V1 再拆成两个独立补丁：

- **V1a：仅补全批量页全局输出格式 `webm`**
  - 修改 `VIDEO_OUTPUT_FORMATS`
  - 验证 `webm` 与现有后处理链的兼容性
  - 不引入手动策略 UI

- **V1b：仅补手动预设1**
  - 在 V1a 稳定后再加“手动设置”按钮与弹窗
  - 只支持预设1
  - 只支持 `default/no_audio`
  - 只覆盖 `profile.format` 与 `profile.preset_key`

- **V2：补预设2与兜底链**
  - 基于 V1b 继续扩展

- **V3：补音频 select 与逐条命中提示**
  - 只在前两阶段稳定后进入

### 5.2 每阶段完成判定
| 阶段 | 完成标志 | 不包含 |
|---|---|---|
| V1a | 批量页可选 `webm`，基本下载链路可用 | 手动策略 |
| V1b | 手动预设1可生成 `-f` 并正确入队 | 预设2、兜底、音频 select |
| V2 | 预设2与兜底链生效，摘要与日志正确反映 | 逐条最终命中 |
| V3 | 音频 select 与逐条命中回填完成 | 更复杂的策略编辑器 |

---

## 6. 函数级开发步骤（按修订版清单实现）

### 6.1 先补现有批量页全局输出格式
文件：`ui/input_validators.py`
- 将 `VIDEO_OUTPUT_FORMATS` 从 `("mp4", "mkv")` 扩展为 `("mp4", "mkv", "webm")`。

文件：`ui/pages/batch_source.py`
- `output_format_combo` 自动继承新的视频输出格式列表，无需单独再造控件。
- `_sync_output_format_by_preset()` 保持现有逻辑，但视频模式下允许 `webm`。

文件：`core/ytdlp_builder.py`
- 复核 `--merge-output-format webm` 在当前命令链中的行为。
- 验证 `webm` 与以下选项的组合：
  - `--embed-thumbnail`
  - `--embed-subs`
  - `--embed-metadata`
  - `--remux-video`
  - `--recode-video`
- 若存在不兼容组合，需要补条件分支或限制提示。

#### 6.1.1 `webm` 兼容性矩阵
建议按下表逐项验证，而不是一次性混合调试：

| 组合 | 预期 | 风险级别 | 建议 |
|---|---|---|---|
| `webm + embed-thumbnail` | 需确认 ffmpeg/容器是否稳定 | 高 | 优先单测/实测 |
| `webm + embed-subs` | 需确认内嵌字幕是否稳定 | 高 | 优先单测/实测 |
| `webm + embed-metadata` | 大概率可用，但需验证 | 中 | 冒烟测试 |
| `webm + h264_compat` | 语义冲突概率高 | 高 | 建议直接限制或给提示 |
| `webm + keep_video` | 需确认中间文件保留行为 | 中 | 冒烟测试 |
| `webm + sponsorblock` | 理论独立，但仍需验证 | 低 | 回归测试 |

#### 6.1.2 `webm` 的推荐策略
- 若 `merge_output_format == "webm"` 且 `h264_compat == True`，建议直接禁止该组合，给出明确提示。
- 若 `merge_output_format == "webm"` 且某些嵌入型后处理不稳定，优先选择“限制功能并提示”，不要做隐式降级。
- `V1a` 的目标不是把所有 `webm` 组合都做满，而是先把基础下载链路做通，并把已知不兼容项拦住。

### 6.2 新增核心模块：`core/manual_format_policy.py`
目的：承载 policy 数据结构、表达式生成、提示文本。

#### 6.2.1 数据结构
- `class ManualPresetSpec:`
  - `target_height: int | None`
  - `video_codec_pref: str | None`  # 'h264'|'av1'|'vp9'|None
  - `video_container_pref: str | None`  # 'mp4'|'webm'|None
  - `audio_mode: str`  # 'default'|'no_audio'|'select'
  - `audio_ext: str | None`
  - `audio_quality_kbps: int | None`

- `class ManualBatchPolicy:`
  - `enabled: bool`
  - `sample_video_url: str | None`
  - `preset1: ManualPresetSpec`
  - `preset2: ManualPresetSpec | None`
  - `fallback_enabled: bool`
  - `codec_rank: list[str]`  # 固定 ['h264','av1','vp9']
  - `ignore_fps: bool`  # 固定 True

- `manual_policy_to_dict(policy) -> dict`
- `manual_policy_from_dict(data: dict) -> ManualBatchPolicy`

#### 6.2.2 表达式生成
- `def _vcodec_filter_token(codec: str) -> str | None`
  - `'h264'` → `vcodec*=avc1`
  - `'av1'` → `vcodec*=av01`
  - `'vp9'` → `vcodec*=vp09`

- `def build_video_expr(height: int | None, ext: str | None, codec: str | None) -> str`
  - 返回如：`bestvideo[height=1080][ext=mp4][vcodec*=avc1]`

- `def build_audio_expr(preset: ManualPresetSpec) -> str`
  - `preset.audio_mode == 'no_audio'` → `""`
  - `preset.audio_mode == 'default'` → `"+bestaudio"`
  - `preset.audio_mode == 'select'` → 先保留接口，V3 再完整启用

- `def build_expr_for_preset_strict(preset: ManualPresetSpec, codec_rank: list[str]) -> str`
  - 生成“同高度 + 编码优先级”的回退段。
  - 用 `/` 连接多个 video 段，并对每段拼接音频表达式。

- `def build_expr_for_fallback(preset1: ManualPresetSpec, codec_rank: list[str]) -> str`
  - 按以下口径构造表达式：
    1. `height=H`
    2. `height>H`
    3. `height<H`
    4. 最终 `bestvideo`
  - 每段同样拼接音频表达式。
  - 这里只表达“优先顺序”，不承诺严格最近高度。

- `def build_ytdlp_format_expr(policy: ManualBatchPolicy) -> str`
  - 组合顺序：`preset1(strict) / preset2(strict, 可空) / fallback(可选)`
  - 最后可再 `/best` 兜底，以下载成功率优先。

#### 6.2.3 提示文本
- `def build_manual_rule_hint(policy: ManualBatchPolicy, expr: str) -> str`
  - 输出：样本视频来源 + 预设参数 + 是否启用兜底 + 生成的 `-f` 表达式。
  - 明确说明“批量不逐条探测，实际命中以 yt-dlp 为准”。

#### 6.2.4 模块职责约束
`core/manual_format_policy.py` 建议保持为纯函数模块：
- 不直接依赖 Tk 变量。
- 不直接依赖下载管理器。
- 不直接写日志。
- 输入是普通 dict / dataclass，输出是普通 dict / str。

这样做的好处：
- 先把表达式生成和策略校验跑通，再接 UI。
- 便于后续补单元测试。
- 出问题时更容易定位是“策略层”还是“界面层”。

### 6.3 批量页 UI：`ui/pages/batch_source.py`
目的：在现有策略区后加“手动设置”按钮，弹窗编辑 policy。

#### 6.3.1 在 `_create_widgets()` 增加按钮与状态
新增成员：
- `self.manual_policy_dict = None`
- `self.manual_enabled_var = tk.BooleanVar(value=False)`
- `self._manual_sample_formats = []`

在 `preset_row` 后追加：
- `ttk.Button(..., text="手动设置", command=self.open_manual_format_window)`

#### 6.3.2 弹窗入口
- `def open_manual_format_window(self):`
  - `win = tk.Toplevel(self)`
  - `self._build_manual_window_widgets(win)`
  - `win.grab_set()`（可选）

#### 6.3.3 弹窗控件构建
- `def _build_manual_window_widgets(self, win):`
  - 样本 URL 输入框：`sample_url_var`
  - 按钮：
    - “从已选条目取样本”：从 `self._selected_entries()` 取第一条 url
    - “获取格式”：调用 `_manual_fetch_sample_formats_async(sample_url)`
  - 预设1控件：
    - 分辨率高度 combobox
    - 编码 combobox（h264/av1/vp9/任意）
    - 视频流容器偏好 combobox（mp4/webm/任意）
    - 音频模式 radio（default/no_audio）
  - V2 再补预设2与兜底相关控件。
  - 提示文字：
    - “预设1/2基于样本视频提供选择；批量按规则匹配；实际命中以 yt-dlp 为准。”
    - “视频流容器偏好不等于最终输出格式；最终输出格式由主页面统一决定。”
  - 保存/取消按钮：
    - 保存调用 `_manual_save_policy_from_ui()` 并关闭。

#### 6.3.4 样本格式拉取（线程）
- `def _manual_fetch_sample_formats_async(self, sample_url: str):`
  - 线程中调用：`self.app.metadata_service.fetch_formats(sample_url)`
  - 成功后保存：`self._manual_sample_formats = result['formats']`
  - 然后 `self.app.root.after(0, self._manual_refresh_preset_options)`

- `def _manual_refresh_preset_options(self):`
  - 从 `self._manual_sample_formats` 聚合：
    - heights
    - ext（只取 `mp4/webm`）
    - vcodec 归一化（h264/av1/vp9）
    - V3 再补 audio ext / audio bitrate 聚合
  - 更新预设 combobox values

#### 6.3.5 保存 policy
- `def _manual_save_policy_from_ui(self):`
  - 从 UI 变量读取 preset1 配置
  - 构建 `ManualBatchPolicy`
  - `self.manual_policy_dict = manual_policy_to_dict(policy)`
  - `self.manual_enabled_var.set(True)`
  - 调用 `_update_batch_summary()`

#### 6.3.6 输入校验规则
为避免开发中途反复改口径，建议先固定以下校验：

| 场景 | 建议规则 |
|---|---|
| 未填写样本 URL | 不允许点击“获取格式” |
| 样本 URL 无法拉到 formats | 不允许保存手动策略 |
| 预设1未选择任何条件 | 不允许保存手动策略 |
| 手动启用但 `manual_policy_dict` 为空 | 入队前阻止并提示 |
| `no_audio` 与音频输出格式冲突 | 以 `no_audio` 为准，并在摘要里提示 |
| `webm` 与 `h264_compat` 同时启用 | 直接阻止并提示 |
| 弹窗关闭未保存 | 不改变现有手动状态 |

#### 6.3.7 状态机定义
为避免 UI 状态和实际入队行为不一致，建议明确下表：

| 状态 | `manual_enabled_var` | `manual_policy_dict` | `preset_var` | 入队行为 | 摘要显示 |
|---|---|---|---|---|---|
| 普通批量 | False | None 或旧值 | 普通 preset | 按普通 preset | 显示普通 preset |
| 手动已配置未禁用 | True | 有效 dict | 任意 | 覆写 `profile.format` 和 `profile.preset_key=manual` | 显示“手动策略” |
| 手动配置损坏 | True | 无效 dict | 任意 | 阻止入队 | 显示错误状态 |
| 手动已关闭 | False | 可保留 | 任意 | 不覆写 profile | 显示普通 preset |

补充约束：
- `manual_enabled_var` 才是入队时是否启用手动的唯一开关。
- `preset_var` 仅在手动关闭时决定下载策略。
- 手动启用后，摘要与任务展示不能继续只看 `preset_var`。

### 6.4 批量入队：注入 `profile.format`
目的：在 `add_selected_tasks()` 中对每条任务 profile 注入 `-f` 表达式。

新增 helper：
- `def _apply_manual_policy_to_profile(self, profile):`
  - `policy = manual_policy_from_dict(self.manual_policy_dict)`
  - `expr = build_ytdlp_format_expr(policy)`
  - `profile.format = expr`
  - `profile.preset_key = "manual"`
  - `hint = build_manual_rule_hint(policy, expr)`
  - `self.manager.log(hint, "INFO")`

在 `add_selected_tasks()` 里：
- 构建 profile 后：
  - 如果 `self.manual_enabled_var.get()` 为 `True`，调用 `_apply_manual_policy_to_profile(profile)`
- 入队逻辑保持不变。

#### 6.4.1 失败回退策略
入队阶段建议采用“显式失败优先”，不要静默降级：

| 失败场景 | 建议行为 |
|---|---|
| policy 反序列化失败 | 阻止入队并提示 |
| 表达式生成失败 | 阻止入队并提示 |
| 表达式为空 | 阻止入队并提示 |
| 手动状态开启但样本缺失 | 阻止入队并提示 |
| 仅日志提示、不阻止入队 | 不推荐 |

原因：
- 批量任务一旦入队，问题会被放大到整批。
- 静默回退到普通 preset 会让用户误以为手动策略已经生效。

### 6.5 批量摘要与结果提示
文件：`ui/pages/batch_source.py`
- `_build_batch_summary()` 中增加手动策略标记，例如：
  - `手动策略`
  - `样本已加载`
  - `兜底启用`
- 摘要不要继续只显示旧的 `preset_var` 结果；当手动启用时，应显示“manual”或本地化后的“手动策略”。

#### 6.5.1 建议补充的日志点
为提高可观测性，建议固定以下日志：

- 点击保存手动策略后：
  - 记录样本 URL
  - 记录预设1关键参数
  - 记录是否启用兜底

- 入队前：
  - 记录最终 `expr`
  - 记录 `profile.preset_key=manual`

- 下载前命令摘要：
  - 能区分普通 preset 与手动策略
  - 能看出最终输出格式和 `-f` 表达式是否同时生效

---

## 6.6 文件变更范围表
建议先按下表控制职责，避免一个文件承载过多逻辑：

| 文件 | 变更职责 | 阶段 |
|---|---|---|
| `ui/input_validators.py` | 增加 `webm` 到视频输出格式 | V1a |
| `core/ytdlp_builder.py` | 处理 `webm` 输出与后处理兼容性 | V1a |
| `core/manual_format_policy.py` | 新增策略数据结构、校验、表达式生成 | V1b |
| `ui/pages/batch_source.py` | 手动策略 UI、状态管理、入队注入、摘要显示 | V1b/V2 |
| `ui/i18n.py` | 新增文案键值 | V1a/V1b/V2 |
| `core/download_manager.py` | 如有需要，仅补日志摘要，不承载策略生成 | V1b/V2 |

建议限制：
- 表达式生成不要写在 `batch_source.py`。
- Tk 变量解析不要写进 `manual_format_policy.py`。
- `download_manager.py` 只做消费，不做策略判断。

---

## 6.7 开发顺序清单（建议严格按顺序推进）
下面的顺序目标只有一个：每一步都能形成可验证的小闭环，尽量避免“多点同时改，出问题时无法定位”。

### Step 1：只做 `V1a` 的常量层改动
目标：
- 先让批量页主面板的视频输出格式下拉框支持 `webm`。

修改点：
- `ui/input_validators.py`
  - 修改 `VIDEO_OUTPUT_FORMATS`

完成判定：
- 批量页输出格式下拉框可见 `webm`
- 其他视频格式选项不受影响

验证：
- 打开批量页，确认 `mp4/mkv/webm` 可选
- 切换到 `audio_only` preset 时，视频格式列表仍会切回音频格式列表

### Step 2：只做 `V1a` 的命令层兼容
目标：
- 确认 `webm` 作为最终输出格式时，命令构建行为正确。

修改点：
- `core/ytdlp_builder.py`
  - 检查 `--merge-output-format webm`
  - 根据兼容性矩阵补限制或提示
- 如有必要：
  - `ui/input_validators.py`
  - `ui/pages/batch_source.py`
  - 增加冲突校验提示

完成判定：
- 选择 `webm` 后，命令摘要中能看到正确的输出容器
- 已知冲突组合被拦截或明确提示

优先验证组合：
- `webm`
- `webm + embed-thumbnail`
- `webm + embed-subs`
- `webm + h264_compat`

建议：
- 这一阶段不要引入手动策略任何代码

### Step 3：补 `V1a` 的文案与校验闭环
目标：
- 把 `webm` 相关冲突提示做完整，避免后续手动策略阶段再返工。

修改点：
- `ui/i18n.py`
  - 增加 `webm` 冲突提示文案
- `ui/pages/batch_source.py` 或 `ui/input_validators.py`
  - 增加对应的前置校验调用

完成判定：
- 冲突组合能在 UI 层被明确阻止
- 中英文文案齐全

验证：
- `webm + h264_compat`
- `webm + 不稳定嵌入型后处理`

### Step 4：新增纯策略模块，不接 UI
目标：
- 先把手动策略表达式生成做成可独立验证的纯函数模块。

修改点：
- 新增 `core/manual_format_policy.py`

第一批只实现：
- `ManualPresetSpec`
- `ManualBatchPolicy`
- `manual_policy_to_dict`
- `manual_policy_from_dict`
- `_vcodec_filter_token`
- `build_video_expr`
- `build_audio_expr`，仅支持 `default/no_audio`
- `build_expr_for_preset_strict`
- `build_ytdlp_format_expr`，仅组合 `preset1`

暂不实现：
- 预设2
- fallback 兜底链
- audio select

完成判定：
- 给定固定输入能稳定输出 `-f` 表达式
- 无 UI 依赖

验证样例建议：
- `1080 + h264 + mp4 + default`
- `720 + av1 + webm + no_audio`
- `height only`
- `codec only`

### Step 5：补策略模块校验与错误处理
目标：
- 在 UI 接入前先把策略层失败边界补齐。

修改点：
- `core/manual_format_policy.py`

新增能力：
- policy 基本校验
- preset1 必填校验
- 表达式为空时抛错
- 不支持组合时抛错

完成判定：
- 对非法输入能返回明确错误
- 不会生成空表达式或模糊表达式

建议：
- 这里如果有测试目录，优先补最小单测；如果当前仓库没有测试基建，也至少预留可手工调用的输入输出样例

### Step 6：接入批量页状态，不做弹窗细节
目标：
- 先在批量页里打通“手动状态会影响入队”的主链，但 UI 可以保持极简。

修改点：
- `ui/pages/batch_source.py`

第一批接入：
- `self.manual_policy_dict`
- `self.manual_enabled_var`
- `_apply_manual_policy_to_profile(profile)`
- `_build_batch_summary()` 中的手动策略状态显示

完成判定：
- 当 `manual_enabled_var=True` 且 policy 有效时，入队后 `profile.format` 被覆写
- `profile.preset_key="manual"`
- 摘要显示“手动策略”

验证：
- 同一批条目在手动开/关两种状态下，命令摘要不同

建议：
- 这一阶段可以先用硬编码 policy 或临时入口，不必马上做完整弹窗

### Step 7：补最小可用弹窗，只支持预设1
目标：
- 完成 `V1b` 的最小 UI 闭环。

修改点：
- `ui/pages/batch_source.py`
- `ui/i18n.py`

最小功能：
- 打开弹窗
- 输入样本 URL
- 获取格式
- 选择预设1：高度 / 编码 / 视频流容器偏好
- 选择音频模式：`default/no_audio`
- 保存 policy

不做：
- 预设2
- fallback 兜底链
- audio select

完成判定：
- 用户能通过 UI 完成一次手动策略配置并入队

验证：
- 保存后摘要变化
- 再次入队能看到 `-f <expr>`
- 手动关闭后恢复普通 preset 行为

### Step 8：补 `V1b` 的输入校验与日志
目标：
- 把手动策略最容易误用的地方补成明确阻断。

修改点：
- `ui/pages/batch_source.py`
- `ui/i18n.py`

必须补的点：
- 样本 URL 为空时不可获取格式
- 样本格式为空时不可保存
- 预设1为空时不可保存
- `manual_enabled_var=True` 但 policy 无效时不可入队
- 保存成功、保存失败、入队注入表达式都要有日志

完成判定：
- 误操作不会静默落到普通 preset

### Step 9：进入 `V2`，只补预设2
目标：
- 在不引入兜底链前，先把预设2接好。

修改点：
- `core/manual_format_policy.py`
- `ui/pages/batch_source.py`
- `ui/i18n.py`

完成判定：
- 最终表达式顺序是 `preset1 / preset2`
- UI 可选择开启或关闭预设2

验证：
- 预设2关闭时不出现在表达式里
- 预设2开启时按顺序参与匹配

### Step 10：进入 `V2`，补兜底链
目标：
- 最后再加 fallback，避免一开始把表达式复杂度拉太高。

修改点：
- `core/manual_format_policy.py`
- `ui/pages/batch_source.py`
- `ui/i18n.py`

新增能力：
- `build_expr_for_fallback`
- `fallback_enabled`
- 摘要与日志中的“启用兜底”

完成判定：
- 最终表达式顺序是 `preset1 / preset2 / fallback / best`

验证：
- 兜底关闭时，表达式不含 fallback 段
- 兜底开启时，摘要与日志可见

### Step 11：最后考虑 `V3`
目标：
- 只有在前面都稳定后，才进入音频 select 与逐条命中提示。

建议顺序：
1. 先补日志解析能力
2. 再补逐条命中回填
3. 最后补 audio select

原因：
- audio select 对格式元数据和后处理链要求更高，风险大于逐条命中提示

---

## 6.8 每步开发后的验证清单
建议每完成一步，都固定执行以下检查：

### 6.8.1 UI 检查
- 控件是否可见
- 状态切换是否正确
- 摘要是否同步更新
- 文案是否走 i18n

### 6.8.2 入队检查
- `build_profile_from_input(self)` 后 profile 是否被正确覆写
- `profile.preset_key` 是否正确
- `profile.format` 是否为空

### 6.8.3 命令检查
- 命令摘要是否反映最终输出格式
- 命令摘要是否反映手动策略表达式
- 冲突组合是否被阻止

### 6.8.4 回归检查
- 普通批量下载是否被破坏
- 单视频下载是否完全不受影响
- `audio_only` 预设是否仍正常

---

## 6.9 实施时的禁止事项
为减少返工，建议在开发时避免以下做法：

- 不要在 `batch_source.py` 里手写复杂表达式拼接逻辑。
- 不要让 UI 保存半成品 policy 后默认视为启用。
- 不要在手动策略失败时静默回落到普通 preset。
- 不要把 `webm` 兼容性问题拖到手动策略阶段一起处理。
- 不要先做 audio select，再去补基础表达式生成。

---

## 7. 回归与验收清单
### 7.1 全局输出格式 `webm`
- 批量页视频输出格式下拉框可选 `webm`。
- 选择 `webm` 后，生成的 yt-dlp 命令包含正确的输出容器参数。
- `webm` 与封面、字幕、元数据、H.264 兼容、保留中间视频等组合行为明确。

### 7.2 手动策略 V1
- 批量未启用手动：行为与现有完全一致。
- 批量启用手动：每个任务的 yt-dlp 命令包含 `-f <expr>`。
- 启用手动后，任务摘要/历史中的 `preset_key` 显示为 `manual`。
- 表达式中不含 fps 约束。
- 编码优先级体现为 h264 段优先。
- 音频：`default/no_audio` 行为正确。
- UI 明确提示“样本限制”与“实际命中以 yt-dlp 为准”。
- UI 明确区分“全局输出格式”与“视频流容器偏好”。

### 7.3 手动策略 V2/V3
- 预设2与兜底链表达式生效。
- 结果提示中能标出“启用兜底”。
- V3 可从运行日志回填逐条最终命中信息。

### 7.4 建议补成用例表执行
| 用例 | 预期 |
|---|---|
| 普通批量 + `mp4` | 行为与现有一致 |
| 普通批量 + `webm` | 基础下载成功 |
| 普通批量 + `webm + h264_compat` | 被阻止或明确提示 |
| 手动预设1 + `default` | 生成正确 `-f` 并成功入队 |
| 手动预设1 + `no_audio` | 不拼音频表达式 |
| 手动预设1 + 样本失效 | 不允许保存 |
| 手动启用 + policy 损坏 | 不允许入队 |
| V2 兜底链触发 | 日志或摘要可见兜底启用 |

### 7.5 i18n 清单
当前项目文本基本走 `get_text`，因此方案里应明确：
- 新增“手动策略”“视频流容器偏好”“手动策略已启用”“手动策略保存失败”“`webm` 与 H.264 兼容冲突”等文案键。
- 中英文一起补，避免只改中文后出现空文案或 fallback。

---

## 8. 后续增强（V3 以后）
若要继续增强“逐条最终命中说明”：
- 在下载运行日志中解析 yt-dlp 输出的最终 format，通常包含 format_id / 分辨率 / 编码。
- 将解析结果回填到任务历史/批量结果提示中，可挂到 `history_repo` 或任务状态字段。

若要继续增强“音频 select”：
- 先补齐格式元数据。
- 再决定是纯 selector 方案，还是增加音频提取/转码后处理方案。
