from __future__ import annotations

from html import escape
import json
import os
from pathlib import Path
import time
from urllib.parse import quote

from fastapi import HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from util import LOG_DIR
from util.Constant import _LOG_STREAM_ROUTE, _LOG_VIEW_ROUTE

_LOG_CHUNK_ROUTE = f"{_LOG_VIEW_ROUTE}/chunk"


def build_log_view_url(path: str) -> str:
    log_name = os.path.basename(path)
    return f"{_LOG_VIEW_ROUTE}?name={quote(log_name, safe='')}"


def _resolve_log_path(raw_path: str | None = None, log_name: str | None = None) -> Path:
    log_root = Path(LOG_DIR).resolve()

    if log_name:
        safe_name = os.path.basename(log_name.strip())
        if not safe_name:
            raise HTTPException(status_code=400, detail="missing log name")
        target = (log_root / safe_name).resolve()
    elif raw_path:
        target = Path(raw_path).resolve()
        try:
            target.relative_to(log_root)
        except ValueError as exc:
            raise HTTPException(
                status_code=403, detail="log path is outside log dir"
            ) from exc
    else:
        raise HTTPException(status_code=400, detail="missing log identifier")

    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="log file not found")

    return target


def _read_log_text(path: Path) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        return handle.read()


def _read_log_chunk_payload(
    path: Path,
    *,
    before: int | None = None,
    max_bytes: int = 512 * 1024,
):
    size = path.stat().st_size
    end = size if before is None else max(0, min(int(before), size))
    start = max(0, end - max(1, int(max_bytes)))
    if end <= 0:
        return {
            "text": "",
            "start": 0,
            "end": 0,
            "has_more": False,
            "file_size": size,
        }

    with open(path, "rb") as handle:
        handle.seek(start)
        content = handle.read(end - start)

    if start > 0:
        newline_index = content.find(b"\n")
        if newline_index >= 0:
            content = content[newline_index + 1 :]
            start += newline_index + 1
        else:
            content = b""
            start = end

    return {
        "text": content.decode("utf-8", errors="replace"),
        "start": start,
        "end": end,
        "has_more": start > 0,
        "file_size": size,
    }


def attach_log_routes(app) -> None:
    if getattr(app.state, "btb_log_routes_ready", False):
        return

    @app.get(_LOG_VIEW_ROUTE, response_class=HTMLResponse)
    def view_log(
        request: Request,
        path: str | None = Query(default=None),
        name: str | None = Query(default=None),
    ) -> HTMLResponse:
        log_path = _resolve_log_path(raw_path=path, log_name=name)
        title = escape(log_path.name)
        stream_url = (
            f"{_LOG_STREAM_ROUTE}?name={quote(log_path.name, safe='')}"
        )
        chunk_url = f"{_LOG_CHUNK_ROUTE}?name={quote(log_path.name, safe='')}"
        initial_payload_json = json.dumps(
            _read_log_chunk_payload(log_path),
            ensure_ascii=False,
        )
        body = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #0c0c0c;
      --bar: #202020;
      --bar-strong: #292929;
      --panel: #0c0c0c;
      --panel-soft: #111111;
      --border: #3a3a3a;
      --border-strong: #505050;
      --text: #f2f2f2;
      --muted: #b7b7b7;
      --dim: #777777;
      --accent: #4cc2ff;
      --ok: #16c60c;
      --warn: #f9f1a5;
      --error: #f14c4c;
      --debug: #9cdcfe;
      --mono: "Cascadia Mono", "Cascadia Code", "JetBrains Mono", Consolas, ui-monospace, monospace;
    }}
    * {{
      box-sizing: border-box;
    }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 14px/1.5 "Segoe UI", "Microsoft YaHei UI", system-ui, sans-serif;
      overflow: hidden;
    }}
    .shell {{
      display: grid;
      grid-template-rows: auto 1fr;
      min-height: 100vh;
      height: 100vh;
      background:
        linear-gradient(180deg, rgba(255,255,255,0.035), transparent 88px),
        var(--bg);
    }}
    .bar {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 14px;
      align-items: center;
      padding: 10px 12px 10px 14px;
      border-bottom: 1px solid var(--border);
      background: linear-gradient(180deg, var(--bar-strong), var(--bar));
      box-shadow: 0 1px 0 rgba(255,255,255,0.06) inset;
    }}
    .identity {{
      min-width: 0;
    }}
    .title {{
      display: flex;
      align-items: center;
      gap: 9px;
      font-weight: 700;
      letter-spacing: 0;
    }}
    .title::before {{
      content: "";
      width: 9px;
      height: 9px;
      border-radius: 50%;
      background: var(--ok);
      box-shadow: 0 0 12px rgba(22, 198, 12, 0.75);
    }}
    .path {{
      margin-top: 4px;
      color: var(--muted);
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-size: 12px;
      font-family: var(--mono);
    }}
    .actions {{
      display: flex;
      flex-wrap: wrap;
      justify-content: flex-end;
      gap: 8px;
    }}
    button {{
      min-height: 32px;
      padding: 0 12px;
      border: 1px solid var(--border-strong);
      border-radius: 5px;
      background: #2d2d2d;
      color: var(--text);
      font: 12px/1 "Segoe UI", "Microsoft YaHei UI", system-ui, sans-serif;
      cursor: pointer;
    }}
    button:hover {{
      background: #383838;
      border-color: #6b6b6b;
    }}
    button.is-active {{
      color: #001018;
      background: var(--accent);
      border-color: var(--accent);
    }}
    .terminal {{
      min-height: 0;
      display: grid;
      grid-template-rows: 1fr auto;
      background: var(--panel);
    }}
    .viewport {{
      margin: 0;
      overflow: auto;
      padding: 14px 16px 18px;
      background:
        linear-gradient(rgba(255,255,255,0.025) 1px, transparent 1px) 0 0 / 100% 28px,
        var(--panel);
      scrollbar-color: #5c5c5c #161616;
    }}
    .log {{
      margin: 0;
      min-width: max-content;
      color: var(--text);
      background: transparent;
      white-space: pre;
      word-break: normal;
      overflow-wrap: normal;
      font: 13px/1.55 var(--mono);
      letter-spacing: 0;
      tab-size: 4;
    }}
    .log.is-wrap {{
      min-width: 0;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
    }}
    .line {{
      display: block;
      min-height: 1.55em;
      content-visibility: auto;
      contain-intrinsic-size: 20px;
    }}
    .line:hover {{
      background: rgba(255, 255, 255, 0.055);
    }}
    .line .time {{
      color: #6a9955;
    }}
    .line .message {{
      color: inherit;
    }}
    .line .sep,
    .line .meta {{
      color: var(--dim);
    }}
    .line.is-info .level {{
      color: #3bceac;
    }}
    .line.is-debug .level {{
      color: var(--debug);
    }}
    .line.is-warning .level {{
      color: var(--warn);
    }}
    .line.is-error .level,
    .line.is-critical .level {{
      color: var(--error);
      font-weight: 700;
    }}
    .line.is-error,
    .line.is-critical {{
      color: #ffd6d6;
    }}
    .line.is-payment,
    .line.is-success {{
      color: #b5f5a8;
    }}
    .line.is-warning {{
      color: #fff6c2;
    }}
    .line.is-risk,
    .line.is-rate-limit,
    .line.is-human-check,
    .line.is-unavailable {{
      color: #ffb86c;
    }}
    .line.is-sold-out {{
      color: #ff7b72;
      background: rgba(241, 76, 76, 0.1);
    }}
    .line.is-price {{
      color: #c586c0;
    }}
    .repeat-badge {{
      display: inline-flex;
      align-items: center;
      margin-left: 10px;
      padding: 0 7px;
      min-height: 18px;
      border: 1px solid rgba(76, 194, 255, 0.55);
      border-radius: 999px;
      color: #9cdcfe;
      background: rgba(76, 194, 255, 0.12);
      font-size: 11px;
      font-weight: 700;
      vertical-align: 1px;
    }}
    .history-loader {{
      position: sticky;
      top: 0;
      z-index: 2;
      display: flex;
      justify-content: center;
      padding: 0 0 10px;
      background: linear-gradient(180deg, var(--panel) 70%, transparent);
    }}
    .history-loader.is-hidden {{
      display: none;
    }}
    .history-loader button {{
      min-height: 30px;
      border-color: rgba(76, 194, 255, 0.45);
      color: #d8f3ff;
      background: rgba(76, 194, 255, 0.12);
    }}
    .footer {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      padding: 7px 12px;
      border-top: 1px solid var(--border);
      background: var(--bar);
      color: var(--muted);
      font-size: 12px;
    }}
    .status {{
      color: var(--accent);
    }}
    .counter {{
      color: var(--muted);
      font-family: var(--mono);
      white-space: nowrap;
    }}
    @media (max-width: 720px) {{
      body {{
        overflow: auto;
      }}
      .shell {{
        height: auto;
        min-height: 100vh;
      }}
      .bar {{
        grid-template-columns: 1fr;
      }}
      .actions {{
        justify-content: flex-start;
      }}
      .terminal {{
        min-height: 70vh;
      }}
      .log {{
        font-size: 12px;
      }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <div class="bar">
      <div class="identity">
        <div class="title">实时日志 - {title}</div>
        <div class="path" title="{escape(str(log_path))}">{escape(str(log_path))}</div>
      </div>
      <div class="actions">
        <button type="button" id="follow" class="is-active">跟随底部</button>
        <button type="button" id="wrap">自动换行</button>
        <button type="button" id="pause">暂停</button>
        <button type="button" id="copy">复制</button>
        <button type="button" id="clear">清空视图</button>
      </div>
    </div>
    <div class="terminal">
      <div class="viewport" id="viewport">
        <div class="history-loader" id="historyLoader">
          <button type="button" id="loadOlder">加载更早日志</button>
        </div>
        <pre class="log" id="log"></pre>
      </div>
      <div class="footer">
        <div class="status" id="status">已连接，等待新日志...</div>
        <div class="counter" id="counter">0 行</div>
      </div>
    </div>
  </div>
  <script>
    const initialPayload = {initial_payload_json};
    const chunkUrl = {json.dumps(chunk_url)};
    const logEl = document.getElementById("log");
    const viewportEl = document.getElementById("viewport");
    const historyLoaderEl = document.getElementById("historyLoader");
    const statusEl = document.getElementById("status");
    const counterEl = document.getElementById("counter");
    const followBtn = document.getElementById("follow");
    const wrapBtn = document.getElementById("wrap");
    const pauseBtn = document.getElementById("pause");
    const copyBtn = document.getElementById("copy");
    const clearBtn = document.getElementById("clear");
    const loadOlderBtn = document.getElementById("loadOlder");
    let follow = true;
    let paused = false;
    let buffer = "";
    let rawLines = [];
    let renderedEntries = [];
    let responseIndexes = new Map();
    let earliestOffset = initialPayload.start || 0;
    let hasMoreHistory = Boolean(initialPayload.has_more);
    let loadingHistory = false;
    let autoLoadArmed = true;
    let historyExpanded = false;
    let compactTimer = null;
    let lastInteractionAt = Date.now();
    let programmaticScroll = false;
    const MAX_RAW_LINES = 50000;
    const MAX_RENDERED_LINES = 50000;
    const PRUNE_RENDERED_TO = 45000;
    const AUTO_LOAD_TOP_PX = 120;
    const COMPACT_IDLE_MS = 60000;
    const COMPACT_MIN_LINES = 9000;
    const stream = new EventSource({json.dumps(stream_url)});

    function escapeHtml(value) {{
      return value
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;");
    }}

    function classForLine(line) {{
      if (/\\bCRITICAL\\b/.test(line)) return "is-critical";
      if (/\\b(ERROR|Traceback|Exception|失败|错误)\\b/.test(line)) return "is-error";
      if (/(\\[100009\\]|库存不足)/.test(line)) return "is-sold-out";
      if (/(HTTP 429|请求被限流|下单请求过多|下单过快|请求较多)/.test(line)) return "is-rate-limit";
      if (/(412 风控|412风控|触发 412|风控)/.test(line)) return "is-risk";
      if (/(人机验证|验证码)/.test(line)) return "is-human-check";
      if (/(暂无可售|不可售|活动收摊|\\[100001\\]|\\[900001\\])/.test(line)) return "is-unavailable";
      if (/(票价错误|更新票价)/.test(line)) return "is-price";
      if (/\\b(WARNING|WARN|警告)\\b/.test(line)) return "is-warning";
      if (/\\b(DEBUG)\\b/.test(line)) return "is-debug";
      if (/\\b(INFO)\\b/.test(line)) return "is-info";
      if (/(成功|完成|已下单|PAYMENT_QR_URL)/.test(line)) return "is-success";
      return "";
    }}

    function splitLogLine(line) {{
      const match = line.match(/^(\\[[^\\]]+\\])(\\|)([A-Z]+)(\\|)(.*)$/);
      if (!match) return null;
      return {{
        time: match[1],
        sep1: match[2],
        level: match[3],
        sep2: match[4],
        message: match[5] || ""
      }};
    }}

    function normalizedResponseMessage(message) {{
      let value = message.trim();
      value = value.replace(/^\\[\\d+(?:-\\d+)?\\/\\d+\\]\\s*/, "");
      value = value.replace(/^订单准备结果:\\s*/, "");
      if (/请求被限流\\(HTTP 429\\)/.test(value)) return "请求被限流(HTTP 429)";
      if (/触发 412 风控/.test(value)) return "触发 412 风控";
      const coded = value.match(/(\\[(?:\\d{{1,6}})\\].*)$/);
      if (coded) return coded[1].trim();
      return value;
    }}

    function responseMergeKey(line) {{
      const parsed = splitLogLine(line);
      const message = (parsed ? parsed.message : line).trim();
      if (!message) return "";
      const normalizedMessage = normalizedResponseMessage(message);
      const isResponse =
        /^\\[\\d+\\]/.test(normalizedMessage) ||
        /^(订单准备结果|创建订单接口|请求被限流|.*触发 412 风控)/.test(message) ||
        /(HTTP 429|412 风控|412风控|人机验证|库存不足|不可售|票价错误|token过期|下单请求过多|下单过快|请求较多)/.test(message);
      return isResponse ? `${{parsed ? parsed.level : ""}}|${{normalizedMessage}}` : "";
    }}

    function isOrderDomainBoundary(line) {{
      const parsed = splitLogLine(line);
      const message = (parsed ? parsed.message : line).trim();
      return /^(开始准备订单|开始创建订单)$/.test(message);
    }}

    function createLineElement(line, count) {{
      const safe = escapeHtml(line);
      const match = safe.match(/^(\\[[^\\]]+\\])(\\|)([A-Z]+)(\\|)(.*)$/);
      const cls = classForLine(line);
      const badge = count > 1 ? `<span class="repeat-badge">x${{count}}</span>` : "";
      const element = document.createElement("span");
      element.className = `line ${{cls}}`;
      if (!match) {{
        element.innerHTML = `${{safe || " "}}${{badge}}`;
        return element;
      }}
      element.innerHTML = [
        `<span class="time">${{match[1]}}</span>`,
        `<span class="sep">${{match[2]}}</span>`,
        `<span class="level">${{match[3]}}</span>`,
        `<span class="sep">${{match[4]}}</span>`,
        `<span class="message">${{match[5] || " "}}</span>`,
        badge
      ].join("");
      return element;
    }}

    function rebuildResponseIndex() {{
      responseIndexes = new Map();
      for (let index = 0; index < renderedEntries.length; index += 1) {{
        const entry = renderedEntries[index];
        if (isOrderDomainBoundary(entry.line)) {{
          responseIndexes = new Map();
          continue;
        }}
        if (entry.key) responseIndexes.set(entry.key, index);
      }}
    }}

    function pruneRenderedLines() {{
      if (renderedEntries.length <= MAX_RENDERED_LINES) return;
      const removeCount = renderedEntries.length - PRUNE_RENDERED_TO;
      renderedEntries.splice(0, removeCount);
      for (let index = 0; index < removeCount; index += 1) {{
        if (logEl.firstChild) logEl.removeChild(logEl.firstChild);
      }}
      rebuildResponseIndex();
    }}

    function pruneRawLines() {{
      if (rawLines.length <= MAX_RAW_LINES) return;
      rawLines.splice(0, rawLines.length - MAX_RAW_LINES);
    }}

    function updateCounter() {{
      const hidden = rawLines.length - renderedEntries.length;
      const capped = renderedEntries.length >= PRUNE_RENDERED_TO ? ` / 保留最近 ${{renderedEntries.length}} 行视图` : "";
      counterEl.textContent = hidden > 0
        ? `${{rawLines.length}} 行 / 合并 ${{hidden}} 行${{capped}}`
        : `${{rawLines.length}} 行${{capped}}`;
    }}

    function updateHistoryLoader() {{
      historyLoaderEl.classList.toggle("is-hidden", !hasMoreHistory);
      loadOlderBtn.disabled = loadingHistory || !hasMoreHistory;
      loadOlderBtn.textContent = loadingHistory ? "加载中..." : "加载更早日志";
    }}

    function markInteraction() {{
      lastInteractionAt = Date.now();
      scheduleCompactIfIdle();
    }}

    function appendRenderedLine(line) {{
      if (isOrderDomainBoundary(line)) {{
        responseIndexes = new Map();
      }}
      const key = responseMergeKey(line);
      if (key && responseIndexes.has(key)) {{
        const entry = renderedEntries[responseIndexes.get(key)];
        entry.count += 1;
        const replacement = createLineElement(entry.line, entry.count);
        entry.element.replaceWith(replacement);
        entry.element = replacement;
        return;
      }}
      const element = createLineElement(line, 1);
      const entry = {{ line, key, count: 1, element }};
      if (key) responseIndexes.set(key, renderedEntries.length);
      renderedEntries.push(entry);
      logEl.appendChild(element);
      pruneRenderedLines();
    }}

    function resetRenderedLines(lines) {{
      logEl.textContent = "";
      renderedEntries = [];
      responseIndexes = new Map();
      const fragment = document.createDocumentFragment();
      for (const line of lines) {{
        if (isOrderDomainBoundary(line)) {{
          responseIndexes = new Map();
        }}
        const key = responseMergeKey(line);
        if (key && responseIndexes.has(key)) {{
          const entry = renderedEntries[responseIndexes.get(key)];
          entry.count += 1;
          const replacement = createLineElement(entry.line, entry.count);
          entry.element.replaceWith(replacement);
          entry.element = replacement;
          continue;
        }}
        const element = createLineElement(line, 1);
        const entry = {{ line, key, count: 1, element }};
        if (key) responseIndexes.set(key, renderedEntries.length);
        renderedEntries.push(entry);
        fragment.appendChild(element);
      }}
      logEl.appendChild(fragment);
      pruneRenderedLines();
      rebuildResponseIndex();
      updateCounter();
    }}

    async function loadOlderLogs(source) {{
      if (loadingHistory || !hasMoreHistory) return;
      loadingHistory = true;
      updateHistoryLoader();
      const previousHeight = viewportEl.scrollHeight;
      try {{
        const response = await fetch(`${{chunkUrl}}&before=${{earliestOffset}}`);
        if (!response.ok) throw new Error(`HTTP ${{response.status}}`);
        const payload = await response.json();
        const olderLines = payload.text ? payload.text.split("\\n") : [];
        earliestOffset = payload.start || 0;
        hasMoreHistory = Boolean(payload.has_more);
        if (olderLines.length > 0) {{
          historyExpanded = true;
          rawLines = olderLines.concat(rawLines);
          resetRenderedLines(rawLines);
          viewportEl.scrollTop += viewportEl.scrollHeight - previousHeight;
        }}
        if (source !== "auto" || olderLines.length > 0) {{
          statusEl.textContent = olderLines.length > 0
            ? `已加载更早日志 ${{olderLines.length}} 行`
            : "没有更早的日志了";
        }}
      }} catch (error) {{
        statusEl.textContent = `加载更早日志失败: ${{error.message || error}}`;
      }} finally {{
        loadingHistory = false;
        autoLoadArmed = true;
        updateHistoryLoader();
      }}
    }}

    async function compactToTail() {{
      if (paused || loadingHistory || !stickToBottom()) return;
      if (!historyExpanded && rawLines.length < COMPACT_MIN_LINES) return;
      try {{
        const response = await fetch(chunkUrl);
        if (!response.ok) throw new Error(`HTTP ${{response.status}}`);
        const payload = await response.json();
        rawLines = payload.text ? payload.text.split("\\n") : [];
        earliestOffset = payload.start || 0;
        hasMoreHistory = Boolean(payload.has_more);
        historyExpanded = false;
        resetRenderedLines(rawLines);
        updateHistoryLoader();
        scrollBottom();
        statusEl.textContent = "已回到底部跟随模式，自动卸载远处日志以节省资源";
      }} catch (error) {{
        statusEl.textContent = `自动卸载远处日志失败: ${{error.message || error}}`;
      }}
    }}

    function scheduleCompactIfIdle() {{
      if (compactTimer !== null) clearTimeout(compactTimer);
      compactTimer = setTimeout(() => {{
        compactTimer = null;
        const idleMs = Date.now() - lastInteractionAt;
        if (follow && stickToBottom() && idleMs >= COMPACT_IDLE_MS) {{
          compactToTail();
        }}
      }}, COMPACT_IDLE_MS + 250);
    }}

    function maybeAutoLoadOlder() {{
      if (!autoLoadArmed || loadingHistory || !hasMoreHistory) return;
      if (viewportEl.scrollTop > AUTO_LOAD_TOP_PX) return;
      autoLoadArmed = false;
      loadOlderLogs("auto");
    }}

    function stickToBottom() {{
      const gap = viewportEl.scrollHeight - viewportEl.scrollTop - viewportEl.clientHeight;
      return gap < 80;
    }}
    function scrollBottom() {{
      programmaticScroll = true;
      viewportEl.scrollTop = viewportEl.scrollHeight;
      requestAnimationFrame(() => {{
        programmaticScroll = false;
      }});
    }}
    function appendText(text) {{
      const lines = text ? text.split("\\n") : [];
      for (const line of lines) {{
        rawLines.push(line);
        appendRenderedLine(line);
      }}
      pruneRawLines();
      updateCounter();
      if (follow) scrollBottom();
    }}
    function setFollow(value) {{
      follow = value;
      followBtn.classList.toggle("is-active", follow);
      if (follow) {{
        scrollBottom();
        scheduleCompactIfIdle();
      }}
    }}

    viewportEl.addEventListener("scroll", () => {{
      if (!programmaticScroll) markInteraction();
      if (!stickToBottom() && follow) setFollow(false);
      if (stickToBottom() && !follow) setFollow(true);
      maybeAutoLoadOlder();
    }});
    followBtn.addEventListener("click", () => {{
      markInteraction();
      setFollow(!follow);
    }});
    wrapBtn.addEventListener("click", () => {{
      markInteraction();
      logEl.classList.toggle("is-wrap");
      wrapBtn.classList.toggle("is-active", logEl.classList.contains("is-wrap"));
    }});
    pauseBtn.addEventListener("click", () => {{
      markInteraction();
      paused = !paused;
      pauseBtn.classList.toggle("is-active", paused);
      pauseBtn.textContent = paused ? "继续" : "暂停";
      if (!paused && buffer) {{
        const pending = buffer;
        buffer = "";
        appendText(pending);
      }}
    }});
    copyBtn.addEventListener("click", async () => {{
      markInteraction();
      await navigator.clipboard.writeText(rawLines.join("\\n"));
      copyBtn.textContent = "已复制";
      setTimeout(() => copyBtn.textContent = "复制", 1200);
    }});
    clearBtn.addEventListener("click", () => {{
      markInteraction();
      rawLines = [];
      earliestOffset = 0;
      hasMoreHistory = false;
      historyExpanded = false;
      resetRenderedLines([]);
      updateHistoryLoader();
      statusEl.textContent = "已清空当前视图，后续日志会继续显示";
    }});
    loadOlderBtn.addEventListener("click", () => {{
      markInteraction();
      loadOlderLogs("manual");
    }});
    document.addEventListener("keydown", markInteraction);
    viewportEl.addEventListener("pointerdown", markInteraction);

    stream.addEventListener("append", (event) => {{
      if (paused) {{
        buffer += event.data;
        statusEl.textContent = `已暂停，缓存 ${{buffer.length}} 个字符`;
        return;
      }}
      appendText(event.data);
      statusEl.textContent = "已连接，日志实时更新中";
    }});
    stream.addEventListener("reset", (event) => {{
      rawLines = event.data ? event.data.split("\\n") : [];
      earliestOffset = 0;
      hasMoreHistory = false;
      pruneRawLines();
      resetRenderedLines(rawLines);
      updateHistoryLoader();
      if (follow) scrollBottom();
      statusEl.textContent = "日志已重置，已重新加载";
    }});
    stream.onerror = () => {{
      statusEl.textContent = "连接中断，正在尝试重连...";
    }};
    rawLines = initialPayload.text ? initialPayload.text.split("\\n") : [];
    pruneRawLines();
    resetRenderedLines(rawLines);
    updateHistoryLoader();
    scrollBottom();
  </script>
</body>
</html>"""
        return HTMLResponse(body)

    @app.get(_LOG_CHUNK_ROUTE)
    def log_chunk(
        path: str | None = Query(default=None),
        name: str | None = Query(default=None),
        before: int | None = Query(default=None),
        max_bytes: int = Query(default=512 * 1024, ge=16 * 1024, le=1024 * 1024),
    ) -> JSONResponse:
        log_path = _resolve_log_path(raw_path=path, log_name=name)
        return JSONResponse(
            _read_log_chunk_payload(
                log_path,
                before=before,
                max_bytes=max_bytes,
            )
        )

    @app.get(_LOG_STREAM_ROUTE)
    def stream_log(
        path: str | None = Query(default=None),
        name: str | None = Query(default=None),
    ) -> StreamingResponse:
        log_path = _resolve_log_path(raw_path=path, log_name=name)

        def generate():
            position = log_path.stat().st_size
            last_ping = 0.0
            while True:
                try:
                    current_size = log_path.stat().st_size
                    if current_size < position:
                        content = _read_log_chunk_payload(log_path)["text"]
                        position = current_size
                        yield _sse("reset", content)
                    elif current_size > position:
                        with open(
                            log_path, "r", encoding="utf-8", errors="replace"
                        ) as handle:
                            handle.seek(position)
                            chunk = handle.read()
                        position = current_size
                        if chunk:
                            yield _sse("append", chunk)

                    now = time.time()
                    if now - last_ping >= 10:
                        last_ping = now
                        yield ": ping\n\n"
                    time.sleep(1)
                except FileNotFoundError:
                    yield _sse("append", "\n[日志文件已不存在]\n")
                    return

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    app.state.btb_log_routes_ready = True


def build_log_stream_url(path: str) -> str:
    log_name = os.path.basename(path)
    return f"{_LOG_STREAM_ROUTE}?name={quote(log_name, safe='')}"


def _sse(event: str, data: str) -> str:
    safe_data = data.replace("\r\n", "\n").replace("\r", "\n")
    return f"event: {event}\ndata: {safe_data.replace(chr(10), chr(10) + 'data: ')}\n\n"
