
# Python YouTube 下载程序错误排查与修复需求文档

## 1. 任务目标

本任务旨在对 Python 编写的 YouTube 下载程序（基于 `yt-dlp` 后端）进行全面错误排查，并生成详细的修改报告，以便后续自动修复代码。具体目标如下：

1. **全面排查程序中可能的错误**，包括但不限于：
   - 语法错误（SyntaxError）
   - 运行时错误（RuntimeError）
   - 未初始化变量或空指针
   - 异常未处理（如网络中断、视频不可用）
   - 外部依赖错误（如 `yt-dlp` 调用失败）
   - 性能问题（如循环或下载任务阻塞）
   - 日志或输出错误
   - 代码逻辑错误或边界条件处理问题
   - 可选：代码风格和可维护性问题

2. **生成详细修改报告**，报告需结构化、可操作，便于 AI 或开发者直接修复代码。

3. 修改报告生成后，可用于 AI 自动执行代码修复。

---

## 2. 修改报告结构要求

每条错误记录必须包含以下字段：

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| **error_type** | 字符串 | 错误类型 | `"语法错误"`、`"未处理异常"`、`"性能问题"` |
| **location** | 字符串 | 文件名、行号或函数名 | `"main.py:45"`、`"downloader.py -> download_video"` |
| **description** | 字符串 | 简要说明问题 | `"变量未定义导致 NameError"` |
| **severity** | 字符串 | 严重级别，可选：`高`、`中`、`低` | `"高"` |
| **cause** | 字符串 | 错误的根本原因分析 | `"变量 x 在使用前未初始化"` |
| **suggestion** | 字符串 | 可操作的修复方案 | `"在函数开头初始化变量 x"` |
| **example_fix** | 字符串 | 修复示例代码，可直接替换或插入 | ```python x = 0``` |
| **alternative_fix** | 字符串，可选 | 其他可行修复方案 | ```python if 'x' not in locals(): x = 0``` |

> ⚠️ 每条记录只对应一个问题，确保修改报告可直接用于自动修复。

---

## 3. 输出格式要求

- **结构化格式**，推荐 **JSON** 或 **Markdown 表格**。
- **JSON 示例**：

```json
[
  {
    "error_type": "语法错误",
    "location": "main.py:45",
    "description": "变量未定义导致 NameError",
    "severity": "高",
    "cause": "变量 x 在使用前未初始化",
    "suggestion": "在函数开头初始化变量 x",
    "example_fix": "x = 0"
  },
  {
    "error_type": "未处理异常",
    "location": "downloader.py -> download_video",
    "description": "yt-dlp 下载失败未捕获异常",
    "severity": "高",
    "cause": "网络或视频问题导致 yt-dlp 抛出异常，但程序未处理",
    "suggestion": "为 yt-dlp 调用添加 try/except 异常处理，并记录错误",
    "example_fix": "try:\n    yt_dlp.download(url)\nexcept Exception as e:\n    log_error(e)"
  }
]
```

---

## 4. 开发流程建议

1. **代码扫描**  
   - AI 扫描整个程序，包括 `plans` 文件夹下的开发方案和步骤。
   
2. **生成修改报告**  
   - AI 根据扫描结果生成修改报告，每条记录严格遵守字段要求。

3. **代码修复**  
   - 将报告交给 AI，根据 `suggestion` 或 `example_fix` 执行修复。

4. **验证结果**  
   - 运行程序测试下载功能，确保修复有效。

---

## 5. 注意事项

- 每条记录只处理**一个问题**。  
- `example_fix` 代码片段必须**可直接替换或插入**。  
- 如果错误有多种修复方式，可使用 `alternative_fix` 字段。  
- 高严重级别问题优先修复。  
- 修改报告应完整覆盖程序中所有错误，包括 `yt-dlp` 调用和自定义逻辑问题。
