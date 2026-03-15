# 阶段 C 当前进展记录

## 1. 阶段定位

当前项目已完成阶段 A（产品收口）与阶段 B（YouTube 领域模型与架构重构），目前进入阶段 C：**单视频下载专业化增强**。

阶段 C 的目标是把原有“输入 URL -> 获取格式 -> 下载”的轻量流程，升级为更适合 YouTube 专业下载场景的单视频工作台。

## 2. 已完成内容

### 2.1 第一批：单视频工作台基础增强

已完成以下能力落地：

- 视频详情卡片
  - 展示标题、视频 ID、频道、上传日期、时长、观看数、语言、Shorts、直播回放等信息
- 结构化格式表格
  - 用表格替代简单下拉框，展示 `format_id`、分辨率、`fps`、编解码、协议、大小、动态范围、音视频轨属性等
- 下载策略预设
  - 支持最佳画质、最佳兼容、最高 1080p、最高 4K、仅音频、最小体积、保留原始编码、HDR 优先、高帧率优先、手动模式
- 输出格式联动
  - 视频场景支持 `mp4 / mkv`
  - 音频场景支持 `m4a / mp3 / opus / wav / flac`

### 2.2 第二批：音频导出与视频后处理增强

已完成以下增强：

- 音频导出增强
  - 支持音质档位选择：`128 / 192 / 256 / 320`
- 视频/音频后处理增强
  - 嵌入封面
  - 嵌入元数据
  - 写入缩略图文件
  - 写入信息 JSON
  - 写入描述
  - 章节写入
  - 保留中间视频
- 命令构建增强
  - 已将上述选项接入 [`core/ytdlp_builder.py`](core/ytdlp_builder.py)
  - 支持 `--audio-quality`、`--embed-thumbnail`、`--embed-metadata`、`--write-thumbnail`、`--write-info-json`、`--write-description`、`--embed-chapters`、`--keep-video`
  - `mkv` 输出时增加 remux 支持

### 2.3 第三批：格式筛选与命名模板预览

已继续补齐阶段 C 规划中的工作台能力：

- 格式筛选增强
  - 支持在单视频页对格式表格进行快速筛选：
    - 仅 MP4
    - 仅带音频
    - 仅 60fps
    - 仅 4K+
    - 仅音频轨
- 格式排序增强
  - 支持按画质或大小排序：
    - `quality_desc`
    - `quality_asc`
    - `size_desc`
    - `size_asc`
- 命名预览增强
  - 在重命名输入框下方新增“命名预览”区域
  - 可根据当前自定义文件名、视频标题和输出格式实时显示预估文件名
- 格式视图刷新机制
  - 已支持在原始格式列表基础上进行筛选/排序并动态回填表格、下拉框和统计摘要

### 2.4 第四批：H.264 兼容模式与下载前摘要

已进一步增强阶段 C 的视频导出与可读性：

- H.264 兼容模式
  - 在单视频页新增“`H.264 兼容模式`”复选项
  - 已接入 [`core/youtube_models.py`](core/youtube_models.py) 的 [`YouTubeDownloadProfile`](core/youtube_models.py)
  - 已接入 [`ui/input_validators.py`](ui/input_validators.py) 的 profile 构建流程
  - 已接入 [`core/ytdlp_builder.py`](core/ytdlp_builder.py)
  - 视频任务启用该选项后，会附加 `--recode-video mp4 --postprocessor-args ffmpeg:-c:v libx264 -c:a aac` 以提升兼容性
- 下载前摘要
  - 在单视频页新增“下载摘要”区域
  - 可根据当前策略、输出格式、手动格式选择与后处理选项，实时汇总当前下载配置
  - 用户在正式加队列前可更直观看到本次下载的关键设置

### 2.5 第五批：错误提示与交互收口

已继续对单视频工作台的边界场景进行收口：

- 空状态与筛选无结果提示增强
  - 在尚未获取格式时，格式统计区域会明确提示先执行“获取分辨率/格式”
  - 在筛选后无结果时，摘要会显示“筛选后无可用格式”，并写入 warning 日志提示用户放宽筛选条件
- 下载摘要表达增强
  - 手动模式下如果尚未选择 `format_id`，摘要会明确提示“未选择（请先获取格式并选择一项）”
  - 非手动策略下若未指定格式，则摘要显示“自动按策略选择”
  - 已将“写入缩略图文件 / 写入信息 JSON / 写入描述”等后处理项纳入摘要展示
- 入队前校验增强
  - 标准下载与直接下载模式下，若当前处于手动模式且未选择 `format_id`，会阻止入队并写入 warning 日志
  - 直接下载任务创建失败时，会补充 error 日志，避免静默失败

## 3. 本阶段涉及的主要文件

- [`core/youtube_models.py`](core/youtube_models.py)
- [`core/ytdlp_builder.py`](core/ytdlp_builder.py)
- [`core/youtube_metadata.py`](core/youtube_metadata.py)
- [`ui/input_validators.py`](ui/input_validators.py)
- [`ui/video_actions.py`](ui/video_actions.py)
- [`ui/pages/single_video.py`](ui/pages/single_video.py)

## 4. 当前验证情况

### 4.1 静态校验

已执行：

```bash
python -m py_compile JJH_download.pyw core\youtube_models.py core\ytdlp_builder.py core\youtube_metadata.py ui\input_validators.py ui\video_actions.py ui\pages\single_video.py
```

结果：通过。

### 4.2 GUI 最小冒烟

已执行启动存活测试，结果：

```text
alive=True; returncode=None
```

说明当前程序在本轮改造后仍可正常启动，主界面未出现阻塞性初始化异常。

## 5. 当前遗留风险

阶段 C 虽已完成四批 UI 与命令层增强，但仍存在以下未完全覆盖项：

- 尚未完成真实视频上的完整链路验证：
  - 视频解析
  - 格式筛选
  - 预设选择
  - 下载启动
  - 后处理结果核验
- H.264 兼容模式当前已完成命令层接通，但仍需真实样本验证输出效果与耗时表现
- 命名预览目前为基础版，尚未扩展为更完整的模板系统
- 不同视频类型（普通视频 / Shorts / HDR / 直播回放）下的筛选效果仍需真实样本验证

## 6. 当前结论

当前状态应认定为：

- **阶段 C 进行中**
- 单视频工作台的专业化能力已经明显增强
- 第一批、第二批、第三批、第四批核心改造已完成首轮落地
- 在完成真实链路冒烟与剩余细节补齐前，暂不进入下一阶段

## 7. 下一步建议

下一轮开发建议直接进入阶段 C 的收口验证工作：

1. 对真实 YouTube 视频执行格式获取与筛选验证
2. 分别验证“最佳画质 / 最高 1080p / 仅音频 / H.264 兼容模式”等典型路径
3. 验证至少一项后处理能力（如封面嵌入、元数据写入、章节写入）
4. 根据验证结果修复阶段 C 遗留问题
5. 编写正式阶段 C 结项与冒烟记录文档
