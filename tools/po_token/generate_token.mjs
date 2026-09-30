// tools/po_token/generate_token.mjs
//
// 使用 bgutils-js + youtubei.js 动态生成 YouTube PO Token。
// 与旧版（youtube-po-token-generator 静态快照方案）不同，本方案每次运行都
// 从 YouTube 主页实时获取 BotGuard challenge，不依赖内置的播放器代码快照，
// 因此不会因 YouTube 更新播放器混淆代码而失效。
//
// 输出约定：
//   成功: stdout 输出 {"success": true, "po_token": "...", "visitor_data": "..."}
//   失败: stderr 输出 {"success": false, "stage": "...", "error": "...", "error_name": "..."}
//
// 环境要求：Node.js >= 20（ESM + 原生 fetch）

import { Innertube } from "youtubei.js";
import { JSDOM } from "jsdom";
import { BotGuardClient } from "bgutils-js/botguard";
import { WebPoMinter } from "bgutils-js/webpo";
import { buildURL, getHeaders, parseLooseJSON, USER_AGENT } from "bgutils-js/utils";

const OVERALL_TIMEOUT_MS = 90000;
const WATCHDOG_EXIT_DELAY_MS = 200;
// yt-dlp 生态多年不变的 GenerateIT 请求密钥（见 bgutil-ytdlp-pot-provider）
const REQUEST_KEY = "O43z0dpjhgX20SCx4KAo";

let forcedExitTimer = null;
let exitScheduled = false;

function serializeError(err, stage) {
    const details = {
        success: false,
        stage,
        error: err?.message || String(err),
        error_name: err?.name || "Error",
    };
    if (err?.cause !== undefined) {
        details.cause = String(err.cause?.message || err.cause);
    }
    return details;
}

function clearTimers() {
    if (forcedExitTimer) {
        clearTimeout(forcedExitTimer);
        forcedExitTimer = null;
    }
}

function scheduleExit(payload, code = 1) {
    if (exitScheduled) {
        return;
    }
    exitScheduled = true;
    process.exitCode = code;

    console.error(JSON.stringify(payload));
    if (payload.stack) {
        console.error(payload.stack);
    }

    forcedExitTimer = setTimeout(() => {
        process.exit(code);
    }, WATCHDOG_EXIT_DELAY_MS);
}

// 硬超时看门狗：BotGuard 的 snapshot 阶段存在同步重计算，可能长时间阻塞
// 事件循环，导致常规 setTimeout 回调迟迟无法执行；因此 unref + 强制退出
// 双保险，并由 Python 侧的 subprocess timeout 作为最终兜底。
const watchdogTimer = setTimeout(() => {
    const timeoutError = new Error(`PO token generation exceeded hard timeout of ${OVERALL_TIMEOUT_MS}ms`);
    timeoutError.name = "PoTokenHardTimeoutError";
    const payload = serializeError(timeoutError, "overall_timeout");
    payload.timeout_ms = OVERALL_TIMEOUT_MS;
    scheduleExit(payload, 1);
}, OVERALL_TIMEOUT_MS);
watchdogTimer.unref();

async function fetchChallengeFromHomepage() {
    // 从 YouTube 主页动态提取 (ytcfg, ytAtN challenge) 自洽对。
    // BotGuard 校验 challenge 与页面 EVENT_ID 的一致性，因此必须从同一页面
    // 提取两者（参照 bgutil 的 homepage 补丁做法）。
    const pageResponse = await fetch("https://www.youtube.com", {
        method: "GET",
        headers: {
            accept: "*/*",
            "accept-language": "en-US,en;q=0.7",
            "user-agent": USER_AGENT,
        },
    });
    if (!pageResponse.ok) {
        throw new Error(`homepage fetch failed: HTTP ${pageResponse.status}`);
    }
    const pageHtml = await pageResponse.text();

    const ytcfgMatch = pageHtml.match(/ytcfg\.set\(({.+?})\);/s);
    if (ytcfgMatch) {
        const ytObj = { config_: JSON.parse(ytcfgMatch[1]) };
        globalThis.yt = ytObj; // BotGuard 读取 yt.config_.EVENT_ID
        if (globalThis.window) globalThis.window.yt = ytObj;
    }

    const attMatch = pageHtml.match(/window\.ytAtN\(\s*({[\s\S]*?})\s*\)/);
    if (!attMatch) {
        throw new Error("homepage: no ytAtN challenge in page");
    }
    const attData = parseLooseJSON(attMatch[1]);
    const challenge = attData?.R?.bgChallenge;
    if (!challenge?.program || !challenge.interpreterUrl) {
        throw new Error("homepage: ytAtN payload missing bgChallenge");
    }
    return challenge;
}

async function main() {
    // 1. 建立 DOM 环境（BotGuard 运行时需要 window/document/navigator）
    const dom = new JSDOM(
        '<!DOCTYPE html><html lang="en"><head><title></title></head><body></body></html>',
        {
            url: "https://www.youtube.com/",
            referrer: "https://www.youtube.com/",
            resources: { userAgent: USER_AGENT },
        },
    );
    Object.assign(globalThis, {
        window: dom.window,
        document: dom.window.document,
        location: dom.window.location,
        origin: dom.window.origin,
    });
    if (!Reflect.has(globalThis, "navigator")) {
        Object.defineProperty(globalThis, "navigator", {
            value: dom.window.navigator,
        });
    }

    // 2. 通过 youtubei.js 获取 visitorData（作为 PO Token 的 contentBinding）
    const innertube = await Innertube.create({ retrieve_player: false });
    const visitorData = innertube.session.context.client.visitorData;
    if (!visitorData) {
        throw new Error("Unable to generate visitor data via Innertube");
    }

    // 3. 从主页动态获取 BotGuard challenge（无静态快照依赖）
    const challenge = await fetchChallengeFromHomepage();

    // 4. 下载并执行 challenge 解释器 VM
    const interpreterUrl =
        challenge.interpreterUrl.privateDoNotAccessOrElseTrustedResourceUrlWrappedValue;
    const interpreterResponse = await fetch(`https:${interpreterUrl}`);
    if (!interpreterResponse.ok) {
        throw new Error(`interpreter fetch failed: HTTP ${interpreterResponse.status}`);
    }
    const interpreterJS = await interpreterResponse.text();
    new Function(interpreterJS)();

    // 5. BotGuard 快照 → GenerateIT 换取 IntegrityToken
    const bgClient = await BotGuardClient.create({
        program: challenge.program,
        globalName: challenge.globalName,
        globalObject: globalThis,
    });
    const webPoSignalOutput = [];
    const botguardResponse = await bgClient.snapshot({ webPoSignalOutput });

    const integrityTokenResp = await fetch(buildURL("GenerateIT"), {
        method: "POST",
        headers: getHeaders(),
        body: JSON.stringify([REQUEST_KEY, botguardResponse]),
    });
    if (!integrityTokenResp.ok) {
        throw new Error(`GenerateIT failed: HTTP ${integrityTokenResp.status}`);
    }
    const [integrityToken, estimatedTtlSecs, mintRefreshThreshold, websafeFallbackToken] =
        await integrityTokenResp.json();
    if (!integrityToken) {
        throw new Error(
            `Unexpected empty integrity token: ${JSON.stringify({
                estimatedTtlSecs,
                mintRefreshThreshold,
                websafeFallbackToken,
            })}`,
        );
    }

    // 6. 用 WebPoMinter 以 visitorData 为 contentBinding 铸造 PO Token
    const minter = await WebPoMinter.create(
        { integrityToken, estimatedTtlSecs, mintRefreshThreshold, websafeFallbackToken },
        webPoSignalOutput,
    );
    const poToken = await minter.mintAsWebsafeString(visitorData);
    if (!poToken) {
        throw new Error("Unexpected empty POT");
    }

    clearTimers();
    console.log(
        JSON.stringify({
            success: true,
            po_token: poToken,
            visitor_data: visitorData,
        }),
    );
}

try {
    await main();
} catch (err) {
    clearTimers();
    scheduleExit(serializeError(err, "generate"), 1);
}
