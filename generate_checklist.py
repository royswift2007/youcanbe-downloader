import json
import os

def generate_markdown(json_path, output_path):
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    md = []
    md.append("# YouCanBe Downloader (YCB) 项目验收清单")
    md.append("\n本清单涵盖了程序界面的各项功能、各类下载策略的配置以及源码级别的函数与参数验收标准，用于保障项目交付质量与重构安全性。\n")
    
    md.append("## 一、 核心功能与业务逻辑验收\n")
    md.append("### 1.1 单视频下载功能")
    md.append("- [ ] YouTube 模式提取与解析能力验证")
    md.append("- [ ] Generic 模式通用 URL 下载验证")
    md.append("- [ ] 直接下载（自动策略匹配）的准确性")
    md.append("- [ ] “仅音频”策略的直接下载是否成功分离音频")
    md.append("- [ ] 添加到队列功能是否正确传递任务状态")

    md.append("\n### 1.2 批量下载（播放列表/频道）功能")
    md.append("- [ ] URL 提取与解析播放列表所有条目")
    md.append("- [ ] 批量勾选与过滤机制是否生效")
    md.append("- [ ] 全局输出格式（mp4/mkv/webm）生成准确性")
    md.append("- [ ] **手动设置策略验证**：")
    md.append("  - [ ] 样本视频格式提取与映射")
    md.append("  - [ ] 预设1 与 预设2 的精确回退机制")
    md.append("  - [ ] 兜底链（Fallback）确保最终可用性")

    md.append("\n### 1.3 媒体处理工具与组件管理")
    md.append("- [ ] remux、抽音频、裁剪、拼接、音量归一化等媒体功能")
    md.append("- [ ] 内嵌字幕与元数据写入测试")
    md.append("- [ ] yt-dlp, ffmpeg, deno 环境依赖的自动检测与无缝更新机制")
    md.append("- [ ] Cookies 与 PO Token 认证功能的有效性")

    md.append("\n---\n")
    md.append("## 二、 源码级 (函数与参数) 模块验收\n")
    md.append("以下为核心代码模块的逐级验收清单，验收各类类方法与函数的参数传递和逻辑。\n")

    for filepath, nodes in data.items():
        md.append(f"### 模块: `{filepath}`")
        for node in nodes:
            if node['type'] == 'class':
                md.append(f"- [ ] **类 `{node['name']}` 验收**")
                for method in node['methods']:
                    args_str = ", ".join(method['args'])
                    md.append(f"  - [ ] 方法 `{method['name']}({args_str})` 输入输出校验")
            elif node['type'] == 'function':
                args_str = ", ".join(node['args'])
                md.append(f"- [ ] **函数 `{node['name']}({args_str})` 验收**")
        md.append("")

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(md))

if __name__ == '__main__':
    generate_markdown('tmp_ast_out.json', os.path.join('plans', '项目验收清单.md'))
