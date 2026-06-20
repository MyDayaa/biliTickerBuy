from __future__ import annotations

from html import escape
import json
import os
from pathlib import Path
import time
from urllib.parse import quote

from fastapi import HTTPException, Query, Request
from fastapi.responses import HTMLResponse, StreamingResponse

from util import LOG_DIR
from util.Constant import _LOG_STREAM_ROUTE, _LOG_VIEW_ROUTE


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
        initial_text_json = json.dumps(_read_log_text(log_path), ensure_ascii=False)
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
        <pre class="log" id="log"></pre>
      </div>
      <div class="footer">
        <div class="status" id="status">已连接，等待新日志...</div>
        <div class="counter" id="counter">0 行</div>
      </div>
    </div>
  </div>
  <script>
    let rawLog = {initial_text_json};
    const logEl = document.getElementById("log");
    const viewportEl = document.getElementById("viewport");
    const statusEl = document.getElementById("status");
    const counterEl = document.getElementById("counter");
    const followBtn = document.getElementById("follow");
    const wrapBtn = document.getElementById("wrap");
    const pauseBtn = document.getElementById("pause");
    const copyBtn = document.getElementById("copy");
    const clearBtn = document.getElementById("clear");
    let follow = true;
    let paused = false;
    let buffer = "";
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
      if (/\\b(WARNING|WARN|警告)\\b/.test(line)) return "is-warning";
      if (/\\b(DEBUG)\\b/.test(line)) return "is-debug";
      if (/\\b(INFO)\\b/.test(line)) return "is-info";
      if (/(成功|完成|PAYMENT_QR_URL)/.test(line)) return "is-success";
      return "";
    }}

    function paintLine(line) {{
      const safe = escapeHtml(line);
      const match = safe.match(/^(\\[[^\\]]+\\])(\\|)([A-Z]+)(\\|)(.*)$/);
      const cls = classForLine(line);
      if (!match) {{
        return `<span class="line ${{cls}}">${{safe || " "}}</span>`;
      }}
      return [
        `<span class="line ${{cls}}">`,
        `<span class="time">${{match[1]}}</span>`,
        `<span class="sep">${{match[2]}}</span>`,
        `<span class="level">${{match[3]}}</span>`,
        `<span class="sep">${{match[4]}}</span>`,
        `<span class="message">${{match[5] || " "}}</span>`,
        `</span>`
      ].join("");
    }}

    function renderLog() {{
      const lines = rawLog.split("\\n");
      logEl.innerHTML = lines.map(paintLine).join("");
      const count = rawLog.length ? lines.length : 0;
      counterEl.textContent = `${{count}} 行`;
    }}

    function stickToBottom() {{
      const gap = viewportEl.scrollHeight - viewportEl.scrollTop - viewportEl.clientHeight;
      return gap < 80;
    }}
    function scrollBottom() {{
      viewportEl.scrollTop = viewportEl.scrollHeight;
    }}
    function appendText(text) {{
      rawLog += text;
      renderLog();
      if (follow) scrollBottom();
    }}
    function setFollow(value) {{
      follow = value;
      followBtn.classList.toggle("is-active", follow);
      if (follow) scrollBottom();
    }}

    viewportEl.addEventListener("scroll", () => {{
      if (!stickToBottom() && follow) setFollow(false);
    }});
    followBtn.addEventListener("click", () => setFollow(!follow));
    wrapBtn.addEventListener("click", () => {{
      logEl.classList.toggle("is-wrap");
      wrapBtn.classList.toggle("is-active", logEl.classList.contains("is-wrap"));
    }});
    pauseBtn.addEventListener("click", () => {{
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
      await navigator.clipboard.writeText(rawLog);
      copyBtn.textContent = "已复制";
      setTimeout(() => copyBtn.textContent = "复制", 1200);
    }});
    clearBtn.addEventListener("click", () => {{
      rawLog = "";
      renderLog();
      statusEl.textContent = "已清空当前视图，后续日志会继续显示";
    }});

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
      rawLog = event.data;
      renderLog();
      if (follow) scrollBottom();
      statusEl.textContent = "日志已重置，已重新加载";
    }});
    stream.onerror = () => {{
      statusEl.textContent = "连接中断，正在尝试重连...";
    }};
    renderLog();
    scrollBottom();
  </script>
</body>
</html>"""
        return HTMLResponse(body)

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
                        content = _read_log_text(log_path)
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
