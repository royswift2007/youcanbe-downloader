const { generate } = require('youtube-po-token-generator');

const OVERALL_TIMEOUT_MS = 60000;
const WATCHDOG_EXIT_DELAY_MS = 200;

let watchdogTimer = null;
let forcedExitTimer = null;
let exitScheduled = false;

function serializeError(err, stage) {
    const message = err?.message || String(err);
    const stack = typeof err?.stack === 'string' ? err.stack : null;
    const details = {
        success: false,
        stage,
        error: message,
        error_name: err?.name || 'Error',
    };

    if (err?.cause !== undefined) {
        details.cause = err.cause;
    }
    if (stack) {
        details.stack = stack;
    }

    return details;
}

function clearTimers() {
    if (watchdogTimer) {
        clearTimeout(watchdogTimer);
        watchdogTimer = null;
    }
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

function armWatchdog() {
    watchdogTimer = setTimeout(() => {
        const timeoutError = new Error(`PO token generation exceeded hard timeout of ${OVERALL_TIMEOUT_MS}ms`);
        timeoutError.name = 'PoTokenHardTimeoutError';
        const payload = serializeError(timeoutError, 'overall_timeout');
        payload.timeout_ms = OVERALL_TIMEOUT_MS;
        scheduleExit(payload, 1);
    }, OVERALL_TIMEOUT_MS);
}

async function main() {
    armWatchdog();

    try {
        const result = await generate();

        if (exitScheduled) {
            return;
        }

        if (!result?.poToken || !result?.visitorData) {
            throw new Error('Generator returned incomplete token payload');
        }

        clearTimers();
        console.log(JSON.stringify({
            success: true,
            po_token: result.poToken,
            visitor_data: result.visitorData,
        }));
    } catch (err) {
        if (exitScheduled) {
            return;
        }
        clearTimers();
        const payload = serializeError(err, 'generate');
        scheduleExit(payload, 1);
    }
}

main().catch((err) => {
    if (exitScheduled) {
        return;
    }
    clearTimers();
    const payload = serializeError(err, 'main');
    scheduleExit(payload, 1);
});
