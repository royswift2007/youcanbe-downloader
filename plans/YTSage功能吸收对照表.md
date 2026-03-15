# YTSage 功能吸收对照表

## 1. 文档目的

本文档用于把 [`YTSage_Analysis.md`](../YTSage_Analysis.md) 中提到的能力，逐项映射到当前 [`YCB.pyw`](../YCB.pyw) 项目的实施计划中，避免“分析已做、执行未对齐”。

使用方式：

- 作为 [`YCB全面增强分步开发方案_20260314.md`](./YCB全面增强分步开发方案_20260314.md) 的配套文档
- 每完成一个能力后同步更新“当前状态”和“备注”
- 后续阶段执行清单可直接从本表中抽取本阶段目标

状态标记：

- `已具备`：当前项目已稳定支持
- `部分具备`：已有基础，但未完整暴露或边界不足
- `待实现`：当前缺失
- `透传覆盖`：不做专门 UI，但可通过高级参数或脚本覆盖

---

## 2. 核心下载功能对照

| YTSage 功能 | 当前状态 | 目标状态 | 优先级 | 计划阶段 | 主要代码落点 | 备注 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 多质量视频下载 | 部分具备 | 完整支持，格式表格化 | P1 | 阶段 3 | [`ui/pages/single_video.py`](../ui/pages/single_video.py), [`core/youtube_metadata.py`](../core/youtube_metadata.py) | 当前已有格式获取与手动选择，但展示不够专业 |
| 智能音视频合并 | 已具备 | 保持并增强摘要展示 | P1 | 阶段 3 | [`core/ytdlp_builder.py`](../core/ytdlp_builder.py) | 当前已有 `--merge-output-format` |
| 音频提取 | 已具备 | 保持并补足更多音频格式与 UI 摘要 | P1 | 阶段 1 / 5 | [`core/ytdlp_builder.py`](../core/ytdlp_builder.py), [`ui/pages/single_video.py`](../ui/pages/single_video.py) | 当前已有音频模式与质量选择 |
| 视频裁剪下载 | 待实现 | `--download-sections` + FFmpeg fallback | P0 | 阶段 1 | [`core/ytdlp_builder.py`](../core/ytdlp_builder.py), [`ui/pages/single_video.py`](../ui/pages/single_video.py), [`ui/pages/batch_source.py`](../ui/pages/batch_source.py) | 优先能力 |
| 通用模式 Generic Mode | 待实现 | 新增 Generic 下载入口 | P1 | 阶段 1 | [`YCB.pyw`](../YCB.pyw), [`ui/pages/single_video.py`](../ui/pages/single_video.py), [`core/youtube_metadata.py`](../core/youtube_metadata.py) | 与 YouTube 专业模式分离 |
| 批量 / 列表处理 | 已具备 | 保持并增强 | P1 | 阶段 0 / 3 / 4 | [`ui/pages/batch_source.py`](../ui/pages/batch_source.py), [`core/download_manager.py`](../core/download_manager.py) | 当前已有播放列表与频道批量解析 |
| 断点续传与限速 | 部分具备 | 保持并补足 UI 摘要与诊断 | P1 | 阶段 0 / 1 | [`core/ytdlp_builder.py`](../core/ytdlp_builder.py), [`core/download_manager.py`](../core/download_manager.py) | 当前已有限速，续传主要依赖 yt-dlp 默认行为 |

---

## 3. 字幕与增强处理对照

| YTSage 功能 | 当前状态 | 目标状态 | 优先级 | 计划阶段 | 主要代码落点 | 备注 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 字幕抓取 | 部分具备 | 支持 manual/auto/both | P0 | 阶段 2 | [`core/ytdlp_builder.py`](../core/ytdlp_builder.py), [`core/youtube_models.py`](../core/youtube_models.py) | 当前仅简单 `--write-subs --embed-subs` |
| 多语言过滤 | 部分具备 | 支持多语言与正则 | P0 | 阶段 2 | [`core/ytdlp_builder.py`](../core/ytdlp_builder.py), [`ui/pages/single_video.py`](../ui/pages/single_video.py) | 当前仅单一 `sub_lang` 字段 |
| 字幕合并 / 内嵌 | 部分具备 | 外挂 / 内嵌 / 两者并存 | P0 | 阶段 2 | [`core/ytdlp_builder.py`](../core/ytdlp_builder.py) | 需考虑容器兼容性 |
| SponsorBlock 集成 | 待实现 | 开关 + 类别选择 | P0 | 阶段 1 | [`core/ytdlp_builder.py`](../core/ytdlp_builder.py), [`ui/pages/single_video.py`](../ui/pages/single_video.py) | 优先能力 |
| 章节嵌入 | 部分具备 | 明确区分嵌入与导出 | P1 | 阶段 1 | [`core/ytdlp_builder.py`](../core/ytdlp_builder.py), [`ui/pages/batch_source.py`](../ui/pages/batch_source.py) | 当前已有 `--embed-chapters` |

---

## 4. 元数据与附件功能对照

| YTSage 功能 | 当前状态 | 目标状态 | 优先级 | 计划阶段 | 主要代码落点 | 备注 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 封面保存 | 部分具备 | UI 完整暴露与摘要展示 | P1 | 阶段 1 | [`core/ytdlp_builder.py`](../core/ytdlp_builder.py), [`ui/pages/batch_source.py`](../ui/pages/batch_source.py) | 当前已支持写入与嵌入 |
| 描述文件保存 | 部分具备 | 单视频与批量都可控 | P1 | 阶段 1 | [`core/ytdlp_builder.py`](../core/ytdlp_builder.py) | 当前已有写描述开关 |
| 元数据展示 | 部分具备 | 展示更完整、字段更清晰 | P1 | 阶段 3 | [`core/youtube_metadata.py`](../core/youtube_metadata.py), [`ui/pages/single_video.py`](../ui/pages/single_video.py) | 当前已有标题与基础信息 |
| 自定义命名 | 已具备 | 保持并增强模板说明 | P1 | 阶段 1 / 7 | [`core/ytdlp_builder.py`](../core/ytdlp_builder.py), [`ui/input_validators.py`](../ui/input_validators.py) | 当前已有自定义文件名 |
| info.json 导出 | 部分具备 | 完整暴露与摘要展示 | P1 | 阶段 1 | [`core/ytdlp_builder.py`](../core/ytdlp_builder.py) | 当前仅部分 UI 暴露 |

---

## 5. 高级控制与网络对照

| YTSage 功能 | 当前状态 | 目标状态 | 优先级 | 计划阶段 | 主要代码落点 | 备注 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Cookie 导入 | 部分具备 | 文件模式 + 浏览器导入 | P1 | 阶段 4 | [`YCB.pyw`](../YCB.pyw), [`core/ytdlp_builder.py`](../core/ytdlp_builder.py) | 当前主要是 cookies 文件 |
| 代理支持 | 待实现 | 全局代理 + 任务级覆盖 | P0 | 阶段 1 | [`core/ytdlp_builder.py`](../core/ytdlp_builder.py), [`core/youtube_models.py`](../core/youtube_models.py) | 优先能力 |
| 自定义参数 | 待实现 | 高级参数透传 + 冲突检测 | P0 | 阶段 1 | [`core/ytdlp_builder.py`](../core/ytdlp_builder.py), [`ui/pages/single_video.py`](../ui/pages/single_video.py) | 优先能力 |
| 强制格式转换 | 部分具备 | 保持并扩展为 FFmpeg 工作台能力 | P1 | 阶段 5 | [`core/ytdlp_builder.py`](../core/ytdlp_builder.py), `core/ffmpeg_builder.py` | 当前已有 H.264/重编码路径 |

---

## 6. 系统与维护工具对照

| YTSage 功能 | 当前状态 | 目标状态 | 优先级 | 计划阶段 | 主要代码落点 | 备注 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 跨平台支持 | 部分具备 | 先做好 Windows 打包，再评估跨平台 | P2 | 阶段 7 | [`YCB.pyw`](../YCB.pyw), 打包配置文件 | 当前项目显然以 Windows 为主 |
| 组件更新程序 | 部分具备 | 组件中心统一管理 yt-dlp / ffmpeg / deno | P2 | 阶段 7 | [`ui/app_actions.py`](../ui/app_actions.py), [`YCB.pyw`](../YCB.pyw) | 当前已有 yt-dlp 更新入口 |
| 剪贴板监听 | 待实现 | 可开关监听 + 去重 | P1 | 阶段 3 | [`YCB.pyw`](../YCB.pyw), [`ui/pages/single_video.py`](../ui/pages/single_video.py) | 体验增强项 |
| 多语言界面 | 待实现 | 中英双语资源字典 | P2 | 阶段 7 | `ui/`, `core/` 文案抽取模块 | 当前先不追求复杂 i18n 体系 |

---

## 7. YTSage 吸收优先顺序

后续执行时，按以下顺序吸收，不建议打乱：

1. 区段下载
2. SponsorBlock
3. 代理支持
4. 高级参数透传
5. 字幕系统
6. 格式表格化
7. Browser Cookies 导入
8. Generic Mode
9. 剪贴板监听
10. 组件中心与多语言

原因：

- 1 到 4 直接影响下载成功率和可控性
- 5 到 8 直接提升专业能力与覆盖范围
- 9 到 10 属于产品化收尾

---

## 8. 当前不直接照搬的部分

YTSage 分析中部分实现思路基于 PySide6 / Qt，不应直接照搬到当前 Tkinter 项目，需按本项目实际替换：

- `Qt Signals` 替换为当前线程 + `after` 刷新机制
- `QClipboard` 替换为 Tkinter 剪贴板轮询或最小事件机制
- `Qt Linguist` 替换为轻量资源字典方案

---

## 9. 维护要求

每次完成一个 YTSage 能力吸收后，都应同步更新：

- “当前状态”
- “计划阶段”
- “备注”

并在对应阶段结项文档中引用本表，说明哪些项已经从 `部分具备/待实现` 变成 `已具备/透传覆盖`。

---

## 10. 阶段0更新记录

- 2026-03-15：阶段0补充测试骨架、结构化命令摘要与失败阶段分类；本表能力状态无变更。
