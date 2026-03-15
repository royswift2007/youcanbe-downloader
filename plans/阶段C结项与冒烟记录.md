# 阶段 C 结项与冒烟记录

## 1. 阶段范围

阶段 C 聚焦于 **单视频下载专业化增强**，目标是将当前 YouTube 下载 GUI 从基础的“输入 URL -> 获取格式 -> 下载”流程，提升为更适合专业使用的单视频工作台。

本阶段已完成的功能范围包括：

- 视频详情卡片
- 结构化格式表格
- 下载策略预设
- 输出格式联动
- 音频导出增强
- 视频/音频后处理增强
- 格式筛选与排序
- 命名预览
- H.264 兼容模式
- 下载前摘要
- 错误提示与交互收口

## 2. 本阶段完成情况

### 2.1 功能实现完成

阶段 C 的五批改造已全部完成：

1. 单视频工作台基础增强
2. 音频导出与视频后处理增强
3. 格式筛选与命名模板预览
4. H.264 兼容模式与下载前摘要
5. 错误提示与交互收口

相关实现已分布在以下核心文件中：

- [`core/youtube_models.py`](core/youtube_models.py)
- [`core/ytdlp_builder.py`](core/ytdlp_builder.py)
- [`core/youtube_metadata.py`](core/youtube_metadata.py)
- [`ui/input_validators.py`](ui/input_validators.py)
- [`ui/video_actions.py`](ui/video_actions.py)
- [`ui/pages/single_video.py`](ui/pages/single_video.py)

### 2.2 静态校验

已执行静态校验：

```bash
python -m py_compile JJH_download.pyw core\youtube_models.py core\ytdlp_builder.py core\youtube_metadata.py ui\input_validators.py ui\video_actions.py ui\pages\single_video.py
```

结果：通过。

### 2.3 GUI 最小冒烟

已执行 GUI 启动存活验证，结果：

```text
alive=True; returncode=None
```

说明当前程序在阶段 C 全部改造后，仍可正常启动。

## 3. 真实链路验证记录

### 3.1 测试样本

本轮使用用户提供的公开视频链接：

```text
https://www.youtube.com/watch?v=mmeLCAP74KA
```

### 3.2 元数据与格式获取验证

通过 [`core/youtube_metadata.py`](core/youtube_metadata.py) 中的 [`YouTubeMetadataService.fetch_formats()`](core/youtube_metadata.py:153) 执行真实格式获取验证，结果如下：

- `ok=True`
- `used_cookies=False`
- `cookies_error=False`
- 获取到 `26` 个格式
- 标题：`Cristiano Ronaldo 100 Legendary Goals Impossible To Forget`
- 频道：`kGZ`
- 时长：`1392`

结论：
- 真实 YouTube 链路下，格式获取成功
- 视频详情与结构化格式列表可以正常返回

### 3.3 预设下载命令验证：最佳兼容

基于 [`core/ytdlp_builder.py`](core/ytdlp_builder.py) 的 [`build_ytdlp_command()`](core/ytdlp_builder.py:6)，对“最佳兼容”路径执行了真实命令构建验证，并使用 `--skip-download --simulate` 做非落盘测试。

结果：
- 返回码：`0`
- 识别到下载格式：`399+140`

结论：
- “最佳兼容”预设对应的命令构建可正常执行
- 视频+音频合并路径工作正常

### 3.4 音频导出路径验证

对“仅音频 + mp3 + 192k + 写入信息 JSON”路径执行了真实命令构建验证。

验证过程中发现问题：
- 原逻辑在音频导出时仍无条件附加 `--merge-output-format`
- 当输出格式为 `mp3` 时，yt-dlp 报错：`invalid merge output format "mp3" given`

已修复 [`build_ytdlp_command()`](core/ytdlp_builder.py:6)：
- 音频模式下：
  - 若输出为 `m4a`，才使用 `--merge-output-format m4a`
  - 若输出为 `mp3 / opus / wav / flac`，改为仅使用 `-x --audio-format ... --audio-quality ...`
- 非音频模式下，仍保留 `--merge-output-format`

修复后重新验证结果：
- 返回码：`0`
- 生成命令包含：
  - `-f bestaudio[ext=m4a]/bestaudio`
  - `-x --audio-format mp3 --audio-quality 192`
  - `--write-info-json`

结论：
- 阶段 C 音频导出链路已通过真实命令验证
- 同时确认并修复了一个真实缺陷

### 3.5 H.264 兼容模式验证

对“H.264 兼容模式”路径执行了真实命令构建验证，并使用 `--skip-download --simulate` 进行非落盘测试。

结果：
- 返回码：`0`
- 命令中正确包含：
  - `--merge-output-format mp4`
  - `--recode-video mp4`
  - `--postprocessor-args ffmpeg:-c:v libx264 -c:a aac`

结论：
- H.264 兼容模式的命令层接线正确
- 该模式可成功进入 yt-dlp 模拟执行路径

## 4. 验证中观察到的环境性告警

在真实链路验证中，yt-dlp 输出了与 YouTube JS Challenge / `deno` 求解器相关的 warning，例如：

- `JS Challenge Provider "deno" returned an invalid response`
- `n challenge solving failed: Some formats may be missing`

该告警未阻断本轮验证：

- 元数据/格式获取仍成功
- 最佳兼容模拟执行成功
- 音频导出模拟执行成功
- H.264 兼容模式模拟执行成功

因此当前将其记录为 **环境侧告警**，不视为阶段 C 的功能阻塞项。但后续若追求更完整的高质量格式覆盖，建议继续关注 [`deno.exe`](deno.exe) / yt-dlp challenge solver 的兼容性。

## 5. 阶段结论

结论如下：

- 阶段 C 的五批功能开发已全部完成
- 静态校验通过
- GUI 最小冒烟通过
- 已完成真实 YouTube 样本上的关键链路验证
- 在真实验证过程中额外发现并修复了音频导出命令构建缺陷

因此，**阶段 C 现可认定为完成并结项**。

## 6. 后续建议

后续建议转入下一阶段或进入阶段 D / 产品化收尾工作，优先方向包括：

1. 扩展更多真实样本回归用例（普通视频 / Shorts / HDR / 直播回放）
2. 评估并优化 yt-dlp 与 [`deno.exe`](deno.exe) 的 challenge solver 兼容性
3. 继续完善命名模板系统与下载结果展示
4. 视需要补充自动化测试或批量回归脚本
