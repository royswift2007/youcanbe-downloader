/**
 * generate_token.js
 * 生成 YouTube PO Token，供 JJH Downloader 调用。
 * 成功时在 stdout 输出 JSON: {"visitor_data": "...", "po_token": "..."}
 * 失败时在 stderr 输出错误信息并以非零状态码退出。
 */

let generate;
try {
    ({ generate } = require('youtube-po-token-generator'));
} catch (e) {
    process.stderr.write('依赖未安装：npm install 尚未执行\n');
    process.exit(2);
}

generate()
    .then(result => {
        const output = {
            visitor_data: result.visitorData,
            po_token: result.poToken,
        };
        process.stdout.write(JSON.stringify(output) + '\n');
        process.exit(0);
    })
    .catch(err => {
        process.stderr.write('Token 生成失败: ' + (err && err.message ? err.message : String(err)) + '\n');
        process.exit(1);
    });
