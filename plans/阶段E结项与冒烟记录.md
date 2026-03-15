# 阶段 E 结项与冒烟记录

## 1. 阶段目标

阶段 E 聚焦 **认证中心、历史数据库与稳定性增强**，目标是在 [`plans/阶段D结项与冒烟记录.md`](plans/阶段D结项与冒烟记录.md) 的基础上，补齐 YouTube 下载器在认证状态可观测性、历史结果可检索性、失败结果可追踪性方面的基础设施，并为阶段 F 的订阅同步与归档系统提供底座。

本阶段完成范围对应 [`plans/阶段E执行清单.md`](plans/阶段E执行清单.md)，覆盖：
- 认证状态模型与分类诊断
- SQLite 历史数据库主链路
- 成功 / 失败历史写入
- GUI 认证入口与历史入口
- 单视频 / 批量页历史级去重扩展点
- 阶段 E 冒烟验证与问题修复

---

## 2. 本阶段完成项

### 2.1 认证状态模型与统一诊断

已新增 [`core/auth_models.py`](core/auth_models.py)，统一承载：
- `AuthDiagnostic`
- `CookiesStatus`
- 认证级别常量
- 认证状态常量
- 认证原因常量

已在 [`core/youtube_metadata.py`](core/youtube_metadata.py) 中完成认证诊断重构：
- 新增 [`detect_auth_diagnostic()`](core/youtube_metadata.py:25)
- 保留兼容入口 [`detect_cookies_error()`](core/youtube_metadata.py:111)
- 元数据获取链路开始返回 `auth_diagnostic`
- 批量解析结果已可挂载认证诊断

已在 [`core/youtube_models.py`](core/youtube_models.py) 中扩展：
- [`YouTubeBatchParseResult`](core/youtube_models.py:132) 新增 `auth_diagnostic`

已在 [`ui/app_actions.py`](ui/app_actions.py) 中将 [`notify_cookies_error()`](ui/app_actions.py:50) 升级为可接受结构化诊断对象。

### 2.2 下载执行链路统一认证提示

已在 [`core/download_manager.py`](core/download_manager.py) 中完成统一接入：
- 标题拉取失败时复用 `auth_diagnostic`
- 下载失败时复用 [`detect_auth_diagnostic()`](core/youtube_metadata.py:25)
- 新增统一认证提示入口 `_notify_auth_issue`
- 日志输出不再只依赖布尔型 cookies 失效判断

应用层 [`JJH_download.pyw`](JJH_download.pyw) 已新增：
- `latest_auth_diagnostic`
- `latest_cookies_status`
- 带参 [`notify_cookies_error()`](JJH_download.pyw:347)

### 2.3 SQLite 历史数据库主链路

已将 [`core/history_repo.py`](core/history_repo.py) 从纯 JSON 仓储升级为：
- **SQLite 主写入链路**
- **JSON 兼容备份链路**

已新增 SQLite 文件：
- [`download_history_ytdlp.sqlite3`](download_history_ytdlp.sqlite3)

已建立最小历史表：
- `youtube_download_history`

核心覆盖字段包括：
- `video_id`
- `playlist_id`
- `channel_id`
- `url`
- `task_type`
- `status`
- `output_path`
- `format`
- `created_at`
- `final_title`
- `used_cookies`
- `failure_stage`
- `failure_summary`
- `return_code`

同时完成：
- 初始化
- 插入
- 查询
- 清空
- 成功历史去重检查

### 2.4 成功 / 失败历史写入增强

已在 [`core/download_manager.py`](core/download_manager.py) 中实现：
- 成功任务入库 [`_save_to_history()`](core/download_manager.py:285)
- 失败任务入库 [`_save_failed_history()`](core/download_manager.py:296)

失败记录最小分类已覆盖：
- `auth`
- `network`
- `download`
- `runtime`

失败历史保留字段包括：
- 失败阶段
- 失败摘要
- 退出码
- 时间戳
- `used_cookies`
- `final_title`
- 输出格式

### 2.5 GUI 认证入口与历史入口

已在 [`ui/app_shell.py`](ui/app_shell.py) 顶部工具栏新增：
- 认证状态摘要
- [`🔐 认证状态`](ui/app_shell.py:25) 按钮
- [`📜 历史记录`](ui/app_shell.py:32) 按钮

已在 [`ui/history_actions.py`](ui/history_actions.py) 新增：
- [`AuthStatusWindow`](ui/history_actions.py:7)
- [`show_auth_status()`](ui/history_actions.py:80)

已在 [`JJH_download.pyw`](JJH_download.pyw) 新增：
- [`show_history_window()`](JJH_download.pyw:322)
- [`show_auth_status()`](JJH_download.pyw:331)

### 2.6 单视频 / 批量页历史去重扩展点

已在 [`ui/pages/single_video.py`](ui/pages/single_video.py) 中接入：
- [`add_task()`](ui/pages/single_video.py:453) 历史成功记录检查
- [`add_direct_task()`](ui/pages/single_video.py:479) 历史成功记录检查

已在 [`ui/pages/batch_source.py`](ui/pages/batch_source.py) 中接入：
- [`add_selected_tasks()`](ui/pages/batch_source.py:345) 的历史级去重扩展点

当前最小去重策略：
- 队列中已存在：跳过
- 历史中已有成功记录：跳过
- 已失败记录：允许再次入队
- 优先基于 `video_id`，其次回退到 URL

---

## 3. 冒烟验证记录

### 3.1 静态编译校验

已执行 [`python -m py_compile`](JJH_download.pyw:1)，通过文件包括：
- [`core/auth_models.py`](core/auth_models.py)
- [`core/youtube_models.py`](core/youtube_models.py)
- [`core/youtube_metadata.py`](core/youtube_metadata.py)
- [`ui/app_actions.py`](ui/app_actions.py)
- [`core/download_manager.py`](core/download_manager.py)
- [`JJH_download.pyw`](JJH_download.pyw)
- [`core/history_repo.py`](core/history_repo.py)
- [`ui/app_shell.py`](ui/app_shell.py)
- [`ui/history_actions.py`](ui/history_actions.py)
- [`ui/pages/single_video.py`](ui/pages/single_video.py)
- [`ui/pages/batch_source.py`](ui/pages/batch_source.py)

### 3.2 SQLite 历史库验证

已通过命令验证：
- 仓储可初始化
- 数据库文件已存在
- `youtube_download_history` 表已创建
- [`load()`](core/history_repo.py:144) 可正常返回结果

验证结果：
- `db_available = True`
- `db_exists = True`
- `table_exists = 1`

### 3.3 GUI 入口级冒烟

已通过脚本实例化 [`DownloadApplication`](JJH_download.pyw:206)，验证：
- 顶部栏已创建
- 历史数据可加载
- 认证状态窗口可打开
- 历史窗口可打开
- `latest_auth_diagnostic` 状态槽存在
- cookies 路径可正常检测

验证结果：
- `history_loaded = True`
- `topbar_exists = True`
- `auth_diag_slot = True`
- `cookies_path_exists = True`

### 3.4 认证诊断样本验证

已对 [`detect_auth_diagnostic()`](core/youtube_metadata.py:25) 进行了样本文本级调用验证，覆盖示例：
- 年龄限制 / 登录要求
- `403 Forbidden`
- 网络连接中断

说明：
- 该项验证过程中终端输出未稳定回显，但函数调用链本身未阻塞，且后续 GUI 冒烟已证明模块可正常导入与实例化。

---

## 4. 验证中发现并修复的问题

在执行 GUI 级冒烟时，发现 [`YouTubeDownloadManager.__init__()`](core/download_manager.py:44) 中调用数据库初始化日志时机不合理，导致实例化初期访问未准备好的日志方法。

已在 [`core/download_manager.py`](core/download_manager.py) 中完成修复与收口：
- 补齐 [`log()`](core/download_manager.py:69)
- 补齐 [`process_log_queue()`](core/download_manager.py:73)
- 补齐 [`update_list()`](core/download_manager.py:85)
- 补齐：
  - `stop_all`
  - `clear_completed`
  - `retry_task`
  - `stop_selected`
  - `delete_selected`
  - `_find_task`
- 将初始化阶段日志改为先写入 `log_queue`

修复后再次执行 GUI 冒烟，验证通过。

---

## 5. 与旧 JSON 历史的兼容策略

本阶段未直接移除旧 JSON 历史，而是采用：
- SQLite 作为主历史结构
- JSON 作为兼容备份输出

当前策略：
- 写入时优先写 SQLite
- 同时保留 JSON 文件写入
- 读取时优先读 SQLite
- SQLite 不可用时自动回退 JSON
- 清空历史时同时清理 SQLite 与 JSON

该策略保证阶段 E 不破坏既有历史查看入口，也降低迁移风险。

---

## 6. 本阶段完成结论

对照 [`plans/阶段E执行清单.md`](plans/阶段E执行清单.md)，阶段 E 已完成：
- 认证状态统一建模
- cookies / 认证问题分类诊断
- SQLite 历史数据库主链路
- 成功 / 失败结果入库
- 单视频 / 批量页历史级去重扩展点
- GUI 认证入口与历史入口
- 阶段 E 冒烟验证与问题修复

阶段 E 结论：**完成并可结项**。

---

## 7. 留待阶段 F 的事项

以下能力明确留待后续阶段 F：
- 订阅同步
- 自动增量抓取
- 频道更新追踪
- 归档规则系统
- 更复杂的历史去重策略配置
- 更完整的历史检索 / 过滤 / 搜索中心
- 认证状态自动巡检与定时刷新
