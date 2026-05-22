// chat.js — Message rendering, tool cards, image injection, thinking blocks.
// Depends on: utils.js (mkEl, escHtml, scrollBottom, TOOL_ZH, TOOL_ICON)
// Runtime deps: liveSess, activeSess, isLiveActive (sessions.js), _ws (app.js)

// ── Inline image injection ─────────────────────────────────────────────────────
// Finds local file paths ending in image extensions inside a rendered element
// and replaces them with <img> elements served via /file?path=...
const _IMG_PATH_RE = /([A-Za-z]:[\\\/][^\s"'<>\n]+\.(?:png|jpg|jpeg|gif|svg|webp)|(?:\/[^\s"'<>\n]+)\.(?:png|jpg|jpeg|gif|svg|webp))/gi;

function injectInlineImages(container) {
  const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
  const nodes = [];
  let n;
  while ((n = walker.nextNode())) nodes.push(n);

  for (const tn of nodes) {
    const text = tn.textContent;
    _IMG_PATH_RE.lastIndex = 0;
    if (!_IMG_PATH_RE.test(text)) continue;
    _IMG_PATH_RE.lastIndex = 0;

    const frag = document.createDocumentFragment();
    let last = 0, m;
    while ((m = _IMG_PATH_RE.exec(text)) !== null) {
      if (m.index > last) frag.appendChild(document.createTextNode(text.slice(last, m.index)));
      const img = document.createElement("img");
      img.src = "/file?path=" + encodeURIComponent(m[1]);
      img.className = "msg-inline-img";
      img.alt = m[1].split(/[\\\/]/).pop();
      img.title = m[1];
      img.onclick = () => window.open(img.src, "_blank");
      img.onerror = () => img.remove();
      frag.appendChild(img);
      last = m.index + m[0].length;
    }
    if (last < text.length) frag.appendChild(document.createTextNode(text.slice(last)));
    tn.parentNode.replaceChild(frag, tn);
  }
}

// ── Message building ───────────────────────────────────────────────────────────
function addUserMessage(text) {
  const s = activeSess();
  const el = mkEl("div", "msg user");
  const b = mkEl("div", "msg-bubble");
  b.textContent = text;
  el.appendChild(b);
  s.el.appendChild(el);
  s.history.push({ role: "user", content: text });
  scrollBottom();
}

function ensureLive() {
  const s = liveSess();
  if (!s || s.live) return;
  const el = mkEl("div", "msg assistant");
  const bubble = mkEl("div", "msg-bubble");
  const thinkingEl = mkEl("div", "thinking-indicator");
  thinkingEl.textContent = "思考中…";
  thinkingEl.style.display = "none";
  bubble.appendChild(thinkingEl);
  el.appendChild(bubble);
  s.el.appendChild(el);
  s.live = { el, bubble, thinkingEl, imagesEl: null, toolCards: {}, toolResults: [],
             turns: [], pendingThoughts: [], thoughtSteps: [] };
  scrollBottom();
}

function showThinking() {
  const s = liveSess();
  if (s?.live?.thinkingEl) s.live.thinkingEl.style.display = "block";
}
function hideThinking() {
  const s = liveSess();
  if (s?.live?.thinkingEl) s.live.thinkingEl.style.display = "none";
}

function addThought(text) {
  const s = liveSess();
  if (!s?.live) return;
  hideThinking();
  s.live.thoughtSteps = s.live.thoughtSteps || [];
  s.live.thoughtSteps.push(text);
  s.live.pendingThoughts = s.live.pendingThoughts || [];
  s.live.pendingThoughts.push(text);

  // Render thought as a <details> block
  let td = s.live._lastThoughtEl;
  if (!td) {
    td = document.createElement("details");
    td.className = "thought-block";
    td.open = true;
    td.innerHTML = `<summary>思考过程</summary><div class="thought-text"></div>`;
    s.live.bubble.insertBefore(td, s.live.thinkingEl.nextSibling || null);
    s.live._lastThoughtEl = td;
  }
  const body = td.querySelector(".thought-text");
  if (body) {
    if (body.children.length > 0) {
      body.insertAdjacentHTML("beforeend", `<hr class="thought-sep">`);
    }
    const step = document.createElement("div");
    step.className = "thought-step-text";
    step.textContent = text;
    body.appendChild(step);
  }
  scrollBottom();
}

function addToolCard(name, args) {
  const s = liveSess();
  if (!s?.live) return;

  // Finalize pending thoughts into a turn
  s.live.pendingThoughts = s.live.pendingThoughts || [];
  s.live.turns = s.live.turns || [];
  s.live.turns.push({ thoughts: [...s.live.pendingThoughts], toolName: name, args, result: null, elapsed: null });
  s.live.pendingThoughts = [];
  s.live._lastThoughtEl = null;  // next thought starts a new block

  const id = `tc-${Math.random().toString(36).slice(2, 8)}`;
  const label = TOOL_ZH[name] || name;
  const icon = TOOL_ICON[name] || "*";
  const argsStr = args && Object.keys(args).length ? JSON.stringify(args, null, 2) : "";

  // Exec panel card
  const card = mkEl("div", "tc-wrap");
  card.id = id;
  card.dataset.status = "running";
  card.innerHTML = `
    <div class="tc-header" onclick="toggleCard('${id}')">
      <span class="tc-icon">${icon}</span>
      <span class="tc-label">${label}</span>
      <span class="tc-status running" id="${id}-status">运行中</span>
      <span class="tc-chevron" id="${id}-chev">▶</span>
    </div>
    <div class="tc-body" id="${id}-body">
      <div id="${id}-progress"></div>
      ${argsStr ? `<div class="tc-section-label">参数</div><div class="tc-code">${escHtml(argsStr)}</div>` : ""}
      <div id="${id}-result"></div>
    </div>`;
  document.getElementById("exec-log").appendChild(card);

  // Chat inline tool card
  const ctc = mkEl("div", "chat-tc");
  const ctcId = `ctc-${id}`;
  ctc.innerHTML = `
    <div class="chat-tc-row" onclick="ctcToggle('${id}')">
      <span class="chat-tc-icon">${icon}</span>
      <span class="chat-tc-name">${label}</span>
      <span class="chat-tc-badge running" id="ctc-${id}-b">运行中</span>
      <span class="chat-tc-time" id="ctc-${id}-t"></span>
      <span class="chat-tc-arrow" id="${id}-a">▶</span>
    </div>
    <div class="chat-tc-body" id="${id}-chat-body" style="display:none">
      ${argsStr ? `<div class="tc-section-label">参数</div><pre class="chat-tc-pre">${escHtml(argsStr)}</pre>` : ""}
    </div>`;
  s.live.bubble.appendChild(ctc);
  s.live.toolCards[name] = { id, ctc: true };

  scrollBottom();
}

function ctcToggle(id) {
  const body = document.getElementById(`${id}-chat-body`);
  const arrow = document.getElementById(`${id}-a`);
  if (!body) return;
  const open = body.style.display !== "none";
  body.style.display = open ? "none" : "block";
  if (arrow) arrow.classList.toggle("open", !open);
}

function updateToolCard(name, result, elapsed) {
  const s = liveSess();
  const entry = s?.live?.toolCards[name];
  const id = entry ? (typeof entry === "string" ? entry : entry.id) : null;
  const ok = !(result?.error);
  const statusText = ok ? (elapsed ? `${elapsed}s` : "完成") : "失败";

  // Update exec panel card
  const card = id ? document.getElementById(id) : null;
  if (card) {
    card.dataset.status = ok ? "done" : "error";
    const st = document.getElementById(`${id}-status`);
    if (st) { st.className = `tc-status ${ok ? "done" : "error"}`; st.textContent = statusText; }
    const prog = document.getElementById(`${id}-progress`);
    if (prog) prog.innerHTML = "";
    const nse = result?.metrics?.NSE;
    if (typeof nse === "number") {
      const cls = nse >= .75 ? "nse-good" : nse >= .5 ? "nse-ok" : "nse-bad";
      const hdr = card.querySelector(".tc-header");
      const badge = mkEl("span", `tc-nse ${cls}`);
      badge.textContent = `NSE ${nse.toFixed(3)}`;
      hdr.insertBefore(badge, hdr.querySelector(".tc-chevron"));
    }
    const res = document.getElementById(`${id}-result`);
    if (res && result) res.innerHTML = `<div class="tc-section-label">执行结果</div><div class="tc-code">${escHtml(JSON.stringify(result, null, 2))}</div>`;
    const body = document.getElementById(`${id}-body`);
    const chev = document.getElementById(`${id}-chev`);
    if (body) body.classList.remove("open");
    if (chev) chev.classList.remove("open");
  }

  // Update chat badge and time
  const ctcEntry = entry && typeof entry === "object" ? entry.ctc : null;
  if (ctcEntry) {
    const badge = document.getElementById(`ctc-${id}-b`);
    const timeEl = document.getElementById(`ctc-${id}-t`);
    if (badge) { badge.textContent = ok ? "完成" : "失败"; badge.className = `chat-tc-badge ${ok ? "ok" : "err"}`; }
    if (timeEl) timeEl.textContent = elapsed ? `${elapsed}s` : "";
  }

  // Images: collect paths from multiple sources
  const _IMG_EXT = /\.(png|jpg|jpeg|gif|svg|webp)$/i;
  let _imgPaths = [];

  // 1. Explicit list fields
  const _explicit = result?.plot_files || result?.plot_paths || result?.figure_paths || [];
  if (Array.isArray(_explicit)) _imgPaths.push(..._explicit.map(String));

  // 2. inspect_dir: reconstruct full paths from dir path + file names
  if (name === "inspect_dir" && result?.path && Array.isArray(result?.files)) {
    const dirPath = String(result.path).replace(/[\\\/]+$/, "");
    const sep = dirPath.includes("\\") ? "\\" : "/";
    for (const f of result.files) {
      const fname = f?.name || f;
      if (_IMG_EXT.test(String(fname))) _imgPaths.push(`${dirPath}${sep}${fname}`);
    }
  }

  // 3. Recursive scan of any string values (catches run_code stdout etc.)
  if (_imgPaths.length === 0) {
    function _scanObj(obj, depth) {
      if (depth > 4 || !obj) return;
      if (typeof obj === "string") {
        if (_IMG_EXT.test(obj) && (obj.includes("/") || obj.includes("\\"))) _imgPaths.push(obj);
      } else if (Array.isArray(obj)) {
        obj.forEach(v => _scanObj(v, depth + 1));
      } else if (typeof obj === "object") {
        Object.values(obj).forEach(v => _scanObj(v, depth + 1));
      }
    }
    _scanObj(result, 0);
  }

  const imgs = [...new Set(_imgPaths)].slice(0, 8);
  if (imgs.length && s?.live) {
    if (!s.live.imagesEl) {
      s.live.imagesEl = mkEl("div", "msg-images");
      s.live.bubble.appendChild(s.live.imagesEl);
    }
    imgs.forEach(p => {
      const img = document.createElement("img");
      img.src = `/file?path=${encodeURIComponent(p)}`; img.alt = "plot";
      img.onerror = () => img.remove();
      img.onclick = () => openLightbox(img.src);
      s.live.imagesEl.appendChild(img);
    });
  }

  if (s?.live) {
    s.live.toolResults = s.live.toolResults || [];
    const tcEntry = s.live.toolCards[name];
    s.live.toolResults.push({ name, args: tcEntry?.args || {}, result: result || {}, elapsed });
    if (s.live.turns) {
      const turn = [...s.live.turns].reverse().find(t => t.toolName === name && t.result === null);
      if (turn) { turn.result = result || {}; turn.elapsed = elapsed; }
    }
  }
  if (isLiveActive()) scrollBottom();
}

function updateCalProgress(ev) {
  const s = liveSess();
  if (!s?.live) { console.log("[cal_progress] no live session"); return; }
  // Find the currently-running calibration card (calibrate_model or llm_calibrate).
  // Prefer an explicit match; fall back to any card whose DOM element is still "running".
  const CAL_TOOLS = ["calibrate_model", "llm_calibrate"];
  let id = null;
  for (const t of CAL_TOOLS) {
    const e = s.live.toolCards[t];
    if (e && typeof e === "object") { id = e.id; break; }
  }
  if (!id) {
    // last-resort: find the most-recently-added running card
    const running = Object.values(s.live.toolCards)
      .filter(e => e && typeof e === "object" &&
              document.getElementById(e.id)?.dataset.status === "running");
    id = running.length ? running[running.length - 1].id : null;
  }
  console.log("[cal_progress] toolCards=", Object.keys(s.live.toolCards), "id=", id);
  if (!id) { console.log("[cal_progress] no card id found"); return; }
  const prog = document.getElementById(`${id}-progress`);
  if (!prog) return;
  const pct = Math.round(ev.pct || 0);
  const label = ev.round_label ? `${ev.round_label} · ` : "";
  prog.innerHTML = `
    <div class="cal-progress-bar-wrap">
      <div class="cal-progress-bar" style="width:${pct}%"></div>
    </div>
    <div class="cal-progress-label">${label}${pct}% · ${ev.eval_count || 0} evals · ${ev.elapsed || 0}s</div>`;
}

function finalizeMessage(text) {
  const s = liveSess();
  if (!s?.live) return;
  hideThinking();

  // Finalize any trailing thought block
  s.live.pendingThoughts = s.live.pendingThoughts || [];
  s.live.turns = s.live.turns || [];
  if (s.live.pendingThoughts.length > 0) {
    s.live.turns.push({ thoughts: [...s.live.pendingThoughts], toolName: null, args: null, result: null, elapsed: null });
    s.live.pendingThoughts = [];
  }

  const ansEl = mkEl("div", "msg-answer");
  ansEl.innerHTML = marked.parse(text || "");
  injectInlineImages(ansEl);
  s.live.bubble.appendChild(ansEl);
  s.history.push({ role: "assistant", content: text, turns: s.live.turns, tools: s.live.toolResults || [], thoughts: s.live.thoughtSteps || [] });
  s.live = null;
  if (isLiveActive()) {
    scrollBottom();
    setTimeout(scrollBottom, 100);
  }
}

function appendError(msg) {
  const s = liveSess();
  if (!s) return;
  ensureLive();
  hideThinking();
  const el = mkEl("div", "msg-answer");
  el.style.color = "var(--err)";
  el.textContent = "[ERR] " + msg;
  s.live.bubble.appendChild(el);
  s.live = null;
  if (isLiveActive()) scrollBottom();
}

// ── Ask User ──────────────────────────────────────────────────────────────────
function showAskUser(question, context) {
  const bar = document.getElementById("ask-user-bar");
  document.getElementById("ask-user-q").textContent = (context ? context + "\n" : "") + question;
  bar.style.display = "block";
  document.getElementById("ask-user-input").focus();
}

document.getElementById("ask-user-submit").onclick = submitAnswer;
document.getElementById("ask-user-input").addEventListener("keydown", e => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submitAnswer(); }
});

function submitAnswer() {
  const inp = document.getElementById("ask-user-input");
  const ans = inp.value.trim();
  if (!ans) return;
  _ws.send(JSON.stringify({ type: "user_answer", text: ans }));
  inp.value = "";
  document.getElementById("ask-user-bar").style.display = "none";
}

// ── Tool card toggle (exec panel) ─────────────────────────────────────────────
function toggleCard(id) {
  const body = document.getElementById(`${id}-body`);
  const chev = document.getElementById(`${id}-chev`);
  if (!body) return;
  const open = body.classList.toggle("open");
  if (chev) chev.classList.toggle("open", open);
}
