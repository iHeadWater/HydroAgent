// app.js — Core: WebSocket, event dispatch, send, running state, theme, init.
// Loaded LAST; all other modules (utils, chat, sessions, panels, toolbar) are
// already in scope when this file executes.

// ── Agent Mode ────────────────────────────────────────────────────────────────
// Three execution modes: pipeline / react / waypoint
let _agentMode = localStorage.getItem("hc_agent_mode") || "react";

function setAgentMode(mode) {
  _agentMode = mode;
  localStorage.setItem("hc_agent_mode", mode);
  ["pipeline", "react", "waypoint"].forEach(m => {
    document.getElementById("mode-" + m)?.classList.toggle("active", m === mode);
  });
}
// Restore persisted mode on load
document.addEventListener("DOMContentLoaded", () => setAgentMode(_agentMode));

// ── Theme ──────────────────────────────────────────────────────────────────────
const _theme = { val: localStorage.getItem("hc_theme") || "light" };
function setTheme(t) {
  _theme.val = t;
  document.body.dataset.theme = t;
  document.getElementById("theme-btn").textContent = t === "dark" ? "浅色" : "深色";
  localStorage.setItem("hc_theme", t);
}
setTheme(_theme.val);
document.getElementById("theme-btn").onclick = () => setTheme(_theme.val === "dark" ? "light" : "dark");

// ── Sidebar / exec-panel collapse ─────────────────────────────────────────────
function setSidebarCollapsed(v) {
  document.getElementById("sidebar").classList.toggle("collapsed", v);
  localStorage.setItem("hc_sb_collapsed", v ? "1" : "0");
}
setSidebarCollapsed(localStorage.getItem("hc_sb_collapsed") === "1");
document.getElementById("sidebar-collapse-btn").onclick = () =>
  setSidebarCollapsed(!document.getElementById("sidebar").classList.contains("collapsed"));

function setExecCollapsed(v) {
  document.getElementById("exec-panel").classList.toggle("collapsed", v);
  localStorage.setItem("hc_exec_collapsed", v ? "1" : "0");
}
setExecCollapsed(localStorage.getItem("hc_exec_collapsed") !== "0");
document.getElementById("exec-collapse-btn").onclick = () =>
  setExecCollapsed(!document.getElementById("exec-panel").classList.contains("collapsed"));

// ── WebSocket ──────────────────────────────────────────────────────────────────
let _ws = null;
function connect() {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  _ws = new WebSocket(`${proto}//${location.host}/ws`);
  _ws.onopen    = () => { setConn(true); _ws.send(JSON.stringify({ type: "ping" })); };
  _ws.onclose   = () => { setConn(false); setTimeout(connect, 3000); };
  _ws.onerror   = () => _ws.close();
  _ws.onmessage = e => { try { handleEvent(JSON.parse(e.data)); } catch (_) {} };
}
function setConn(ok) {
  document.getElementById("conn-dot").className = ok ? "connected" : "";
  document.getElementById("conn-label").textContent = ok ? "已连接" : "重连中...";
}

// ── Event handler ──────────────────────────────────────────────────────────────
function handleEvent(ev) {
  if (!["pong", "session_id"].includes(ev.type) && liveKey === null) return;
  switch (ev.type) {
    case "thinking_start":      setRunning(true); ensureLive(); showThinking(); break;
    case "thinking_end":        hideThinking(); break;
    case "thought":             addThought(ev.text); break;
    case "tool_start":          ensureLive(); addToolCard(ev.name, ev.args); setStatus(`工具: ${TOOL_ZH[ev.name] || ev.name}`); break;
    case "tool_end":            updateToolCard(ev.name, ev.result, ev.elapsed); break;
    case "calibration_progress":console.log("[cal_progress] received", ev); updateCalProgress(ev); break;
    case "answer":              finalizeMessage(ev.text); break;
    case "ask_user":            showAskUser(ev.question, ev.context); break;
    case "session_id":          if (liveSess()) liveSess().serverSid = ev.id; break;
    case "error":
      appendError(ev.msg);
      setRunning(false);
      if (/429|rate.?limit|quota/i.test(ev.msg))
        showToast("API 限速（429），Token 可能已耗尽，请稍后重试", 7000);
      else if (/5\d\d|timeout|connection|network/i.test(ev.msg))
        showToast("服务端错误，请检查网络或重试", 5000);
      break;
    case "done":     onDone(ev.tokens); break;
    case "stopping": setStatus("停止中，等待当前工具完成…"); break;
    case "pong":     break;
  }
}

// ── Send ───────────────────────────────────────────────────────────────────────
function sendQuery() {
  const input = document.getElementById("input");
  const text = input.value.trim();
  if (!text || !_ws || _ws.readyState !== 1) return;
  if (liveKey && liveKey !== activeKey) {
    showToast("后台任务执行中，请等待完成或先切换回该对话"); return;
  }
  if (!activeKey) createAndSwitchNew();
  liveKey = activeKey;
  addUserMessage(text);
  input.value = ""; input.style.height = "auto";
  const hint = getToolbarHint();
  const serverText = hint ? `${hint}\n\n用户输入：${text}` : text;
  _ws.send(JSON.stringify({ type: "query", text: serverText, prior_messages: buildPrior(), agent_mode: _agentMode }));
  setRunning(true);
  setExecCollapsed(false);
  const ls = liveSess();
  ls.runCount = (ls.runCount || 0) + 1;
  const log = document.getElementById("exec-log");
  document.getElementById("exec-empty")?.remove();
  const lbl = mkEl("div", "exec-run-label");
  lbl.textContent = `# 运行 ${ls.runCount}`;
  log.appendChild(lbl);
}

function sendStop() {
  if (!liveKey) return;
  if (_ws?.readyState === 1) _ws.send(JSON.stringify({ type: "stop" }));
  const s = liveSess();
  if (s) {
    ensureLive(); hideThinking();
    const note = mkEl("div", "msg-answer");
    note.innerHTML = "<em>*(任务已后台继续运行，率定将完成后自动保存)*</em>";
    if (s.live) {
      s.live.bubble.appendChild(note);
      s.history.push({ role: "assistant", content: "*(任务已后台继续运行)*",
        turns: s.live.turns || [], tools: s.live.toolResults || [], thoughts: s.live.thoughtSteps || [] });
      s.live = null;
    }
  }
  setStatus("任务挂后台，率定继续运行");
  onDone(null);
}

// ── Done / running state ───────────────────────────────────────────────────────
function onDone(tokens) {
  const s = liveSess();
  if (s && tokens) {
    s.tokens.total  += tokens.total_tokens      || 0;
    s.tokens.prompt += tokens.prompt_tokens     || 0;
    s.tokens.compl  += tokens.completion_tokens || 0;
  }
  const wasBackground = !isLiveActive();
  liveKey = null;
  setRunning(false);
  setStatus("待命");
  updateTokenDisplay();
  if (wasBackground) {
    document.querySelectorAll(".session-item").forEach(el => {
      if (el.dataset.sid === s?.serverSid) {
        el.querySelector(".running-dot")?.remove();
        const dot = mkEl("span", "");
        dot.style.cssText = "width:6px;height:6px;border-radius:50%;background:var(--ok);flex-shrink:0;display:inline-block;margin-left:auto";
        el.appendChild(dot);
      }
    });
    showToast("后台任务已完成，点击对话查看结果");
  }
  saveSnapshot().then(() => loadSessions());
}

let _runStart = 0;
let _timerInterval = null;

function setRunning(v) {
  document.getElementById("input").disabled = v && isLiveActive();
  document.getElementById("send-btn").disabled = v && isLiveActive();
  document.getElementById("status-dot").className = `status-dot${v ? " running" : ""}`;
  document.getElementById("stop-btn").classList.toggle("active", v);
  const timer = document.getElementById("elapsed-timer");
  if (v) {
    _runStart = Date.now();
    timer.style.display = "inline";
    _timerInterval = setInterval(() => {
      const s = Math.floor((Date.now() - _runStart) / 1000);
      timer.textContent = s < 60 ? `${s}s` : `${Math.floor(s/60)}m${s%60}s`;
    }, 1000);
  } else {
    clearInterval(_timerInterval);
    timer.style.display = "none";
  }
  document.querySelectorAll(".session-item .running-dot").forEach(el => el.remove());
  if (v && liveKey) {
    const s = SESS.get(liveKey);
    document.querySelectorAll(".session-item").forEach(el => {
      if (el.dataset.sid === s?.serverSid || el.dataset.key === liveKey)
        el.insertBefore(mkEl("span", "running-dot"), el.firstChild);
    });
  }
}

function setStatus(t) { document.getElementById("status-text").textContent = t; }

const TOKEN_MAX = 1_000_000;
let _tokenAlerted = false;
function updateTokenDisplay() {
  const t = activeSess()?.tokens?.total || 0;
  document.getElementById("token-display").textContent = `${fmtTokens(t)} / 1M`;
  document.getElementById("token-bar").style.width = Math.min(t / TOKEN_MAX * 100, 100) + "%";
  if (t >= TOKEN_MAX && !_tokenAlerted) {
    _tokenAlerted = true;
    showToast("Token 用量已达 1M 上限，后续请求可能失败", 6000);
  } else if (t >= TOKEN_MAX * 0.9 && !_tokenAlerted) {
    showToast("Token 用量已超过 90%，请注意剩余额度", 4000);
  }
}

// ── Prior messages ─────────────────────────────────────────────────────────────
function buildPrior() {
  const history = activeSess()?.history || [];
  return history.slice(-10).map(m => {
    if (m.role === "user") return { role: "user", content: m.content };
    const extras = (m.tools || []).flatMap(t => {
      const r = t.result || {}, out = [];
      if (r.calibration_dir) out.push(`calibration_dir=${r.calibration_dir}`);
      const nse = r.metrics?.NSE;
      if (typeof nse === "number") out.push(`NSE=${nse.toFixed(4)}`);
      return out;
    });
    const extra = extras.length ? `\n\n[Previous results: ${extras.join("; ")}]` : "";
    return { role: "assistant", content: (m.content || "") + extra };
  });
}

// ── Lightbox ───────────────────────────────────────────────────────────────────
function openLightbox(src) {
  document.getElementById("lightbox-img").src = src;
  document.getElementById("lightbox").classList.add("open");
}
function closeLightbox() { document.getElementById("lightbox").classList.remove("open"); }

// ── New chat button ────────────────────────────────────────────────────────────
document.getElementById("new-chat-btn").onclick = () => {
  closeCurrentPanel();
  createAndSwitchNew();
  updateTokenDisplay();
  setStatus("待命");
  if (!liveKey) {
    document.getElementById("exec-log").innerHTML = '<div id="exec-empty">暂无执行记录</div>';
  }
  document.querySelectorAll(".session-item").forEach(e => e.classList.remove("active"));
};

// ── Keyboard ───────────────────────────────────────────────────────────────────
document.getElementById("input").addEventListener("keydown", e => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendQuery(); }
});
document.getElementById("input").addEventListener("input", function () {
  this.style.height = "auto";
  this.style.height = Math.min(this.scrollHeight, 120) + "px";
});

// ── Init ───────────────────────────────────────────────────────────────────────
createAndSwitchNew();
connect();
loadSessions();
loadSystemPanels();
