const state = {
  platform: "boss",
  page: 1,
  size: 20,
  total: 0,
  tab: "configTab",
  progressSource: null,
};

const platformTitle = {
  boss: { title: "Boss直聘配置", icon: "💼" },
  liepin: { title: "猎聘配置", icon: "🎯" },
  zhilian: { title: "智联招聘配置", icon: "🧭" },
};

function el(id) {
  return document.getElementById(id);
}

function api(path, options = {}) {
  return fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
}

function setHealth(ok) {
  const dot = el("healthDot");
  const text = el("healthText");
  dot.className = `dot ${ok ? "ok" : "err"}`;
  text.textContent = ok ? "系统运行正常" : "服务不可达";
}

async function checkHealth() {
  try {
    const res = await api("/api/health");
    setHealth(res.ok);
  } catch (e) {
    setHealth(false);
  }
}

function appendProgress(line) {
  const area = el("progressLog");
  if (!area) return;
  const prev = area.value ? `${area.value}\n` : "";
  area.value = `${prev}${line}`;
  const maxLines = 120;
  const lines = area.value.split("\n");
  if (lines.length > maxLines) {
    area.value = lines.slice(lines.length - maxLines).join("\n");
  }
  area.scrollTop = area.scrollHeight;
}

function connectProgressStream() {
  if (state.progressSource) {
    state.progressSource.close();
    state.progressSource = null;
  }
  const src = new EventSource(`/api/tasks/progress/stream?platform=${encodeURIComponent(state.platform)}`);
  state.progressSource = src;

  src.addEventListener("connected", (ev) => {
    try {
      const data = JSON.parse(ev.data || "{}");
      appendProgress(`[${data.ts || "-"}] ${data.message || "connected"}`);
    } catch {
      appendProgress("connected");
    }
  });

  src.addEventListener("progress", (ev) => {
    try {
      const data = JSON.parse(ev.data || "{}");
      const msg = data.message || "";
      const ratio = data.current != null && data.total != null ? ` (${data.current}/${data.total})` : "";
      el("progressText").value = `${msg}${ratio}`;
      appendProgress(`[${data.ts || "-"}] ${msg}${ratio}`);
    } catch {
      // ignore
    }
  });

  src.onerror = () => {
    appendProgress("[SSE] 连接中断，等待自动重连...");
  };
}

function bindMenu() {
  document.querySelectorAll(".menu-item").forEach((item) => {
    item.addEventListener("click", async () => {
      const p = item.dataset.platform;
      if (!p) return;
      state.platform = p;
      state.page = 1;
      document.querySelectorAll(".menu-item").forEach((x) => x.classList.remove("active"));
      item.classList.add("active");
      applyPlatformDefaults();
      await loadOptions();
      await loadSavedConfig();
      connectProgressStream();
      refreshStatus();
      loadList();
      loadStats();
    });
  });
}

function bindTabs() {
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const tab = btn.dataset.tab;
      if (!tab) return;
      state.tab = tab;
      document.querySelectorAll(".tab-btn").forEach((x) => x.classList.remove("active"));
      btn.classList.add("active");
      document.querySelectorAll(".tab-pane").forEach((x) => x.classList.remove("active"));
      document.getElementById(tab).classList.add("active");
      if (tab === "analysisTab") loadStats();
    });
  });
}

function applyPlatformDefaults() {
  const defaults = {
    boss: { city: "101010100" },
    liepin: { city: "020" },
    zhilian: { city: "530" },
  };
  const d = defaults[state.platform] || defaults.boss;
  const titleMeta = platformTitle[state.platform] || { title: state.platform, icon: "💼" };
  el("cityCode").value = d.city;
  el("pageTitle").textContent = titleMeta.title;
  document.querySelector(".icon-badge").textContent = titleMeta.icon;
  ["boss", "liepin", "zhilian"].forEach((p) => {
    const sec = document.getElementById(`sec-${p}`);
    if (!sec) return;
    sec.style.display = p === state.platform ? "block" : "none";
  });
}

function parseExtraQueryText(text) {
  if (!text) return [];
  return text
    .split(",")
    .map((x) => x.trim())
    .filter((x) => x.includes("="));
}

function selectedValue(selectId, inputId) {
  const s = el(selectId);
  const custom = (el(inputId).value || "").trim();
  const val = s && s.value ? s.value : "";
  if (val && val !== "__custom__") return val;
  return custom;
}

function pushIfPresent(arr, key, value) {
  if (value && String(value).trim()) arr.push(`${key}=${String(value).trim()}`);
}

function buildStartPayload() {
  const city = selectedValue("citySelect", "cityCode");
  const salary = selectedValue("salarySelect", "salary");
  const extra = parseExtraQueryText(el("extraQuery").value || "");
  const stepWaitSec = Number(el("stepWaitSec").value || 0.2);

  if (state.platform === "boss") {
    pushIfPresent(extra, "industry", el("bossIndustry").value);
    pushIfPresent(extra, "experience", el("bossExperience").value);
    pushIfPresent(extra, "degree", el("bossDegree").value);
    pushIfPresent(extra, "jobType", el("bossJobType").value);
  }
  if (state.platform === "liepin") {
    pushIfPresent(extra, "dq", el("liepinDq").value);
  }

  return {
    platform: state.platform,
    keyword: (el("keyword").value || "").trim(),
    city_code: city,
    salary: salary || null,
    max_pages: Number(el("maxPages").value || 30),
    slow_mo: Math.max(0, Math.round(stepWaitSec * 1000)),
    step_wait_sec: Math.max(0, stepWaitSec),
    headless: Boolean(el("headless").checked),
    save_raw_json: Boolean(el("saveRaw").checked),
    extra_query: extra,
  };
}

function collectConfigSnapshot() {
  return {
    keyword: (el("keyword").value || "").trim(),
    city_code: (el("cityCode").value || "").trim(),
    salary: (el("salary").value || "").trim(),
    max_pages: Number(el("maxPages").value || 30),
    step_wait_sec: Number(el("stepWaitSec").value || 0.2),
    headless: Boolean(el("headless").checked),
    save_raw_json: Boolean(el("saveRaw").checked),
    extra_query_text: (el("extraQuery").value || "").trim(),
    bossIndustry: (el("bossIndustry").value || "").trim(),
    bossExperience: (el("bossExperience").value || "").trim(),
    bossDegree: (el("bossDegree").value || "").trim(),
    bossJobType: (el("bossJobType").value || "").trim(),
    liepinDq: (el("liepinDq").value || "").trim(),
  };
}

function setSelectOrCustom(selectId, inputId, value) {
  const s = el(selectId);
  const input = el(inputId);
  const val = (value || "").trim();
  if (!s || !input) return;
  if (!val) {
    s.value = "__custom__";
    input.value = "";
    return;
  }
  const hasOption = Array.from(s.options).some((opt) => opt.value === val);
  if (hasOption) {
    s.value = val;
    input.value = val;
  } else {
    s.value = "__custom__";
    input.value = val;
  }
}

function applyConfigSnapshot(cfg) {
  if (!cfg || typeof cfg !== "object") return;
  el("keyword").value = cfg.keyword || "";
  el("maxPages").value = cfg.max_pages ?? 30;
  el("stepWaitSec").value = cfg.step_wait_sec ?? ((cfg.slow_mo ?? 50) / 1000);
  el("headless").checked = Boolean(cfg.headless);
  el("saveRaw").checked = Boolean(cfg.save_raw_json);
  el("extraQuery").value = cfg.extra_query_text || "";
  el("bossIndustry").value = cfg.bossIndustry || "";
  el("bossExperience").value = cfg.bossExperience || "";
  el("bossDegree").value = cfg.bossDegree || "";
  el("bossJobType").value = cfg.bossJobType || "";
  el("liepinDq").value = cfg.liepinDq || "";
  setSelectOrCustom("citySelect", "cityCode", cfg.city_code || "");
  setSelectOrCustom("salarySelect", "salary", cfg.salary || "");
}

function setStatusText(text) {
  el("statusText").value = text;
}

function getTimeFilters() {
  return {
    createdFrom: (el("createdFrom").value || "").trim(),
    createdTo: (el("createdTo").value || "").trim(),
  };
}

async function startTask() {
  const payload = buildStartPayload();
  if (!payload.keyword) {
    setStatusText("请先输入关键词");
    return;
  }
  setStatusText("正在启动任务...");
  try {
    const res = await api("/api/tasks/start", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok || !data.ok) {
      setStatusText(`启动失败: ${data.detail || data.message || res.status}`);
      return;
    }
    setStatusText(`已启动: ${state.platform}`);
    appendProgress(`[${new Date().toLocaleTimeString()}] 已启动 ${state.platform}`);
    refreshStatus();
  } catch (e) {
    setStatusText(`启动异常: ${e.message}`);
  }
}

async function checkLoginStatus() {
  try {
    const res = await api(`/api/tasks/login/status?platform=${encodeURIComponent(state.platform)}`);
    const data = await res.json();
    if (!res.ok || !data.ok) return null;
    return data.data || null;
  } catch {
    return null;
  }
}

async function loginAndSaveCookie() {
  const timeout = 180;
  const injectOldCookie = false;
  const manualLoginMode = true;
  const bossManualMode = false;
  const finishOnLogin = false;
  setStatusText("正在打开登录窗口，请在弹窗中完成登录...");
  appendProgress(`[${new Date().toLocaleTimeString()}] 已发起登录流程`);
  try {
    const res = await api(`/api/tasks/login/start?platform=${encodeURIComponent(state.platform)}&timeout_sec=${timeout}&inject_old_cookie=${injectOldCookie}&finish_on_login=${finishOnLogin}&boss_manual_mode=${bossManualMode}&manual_login_mode=${manualLoginMode}`, {
      method: "POST",
    });
    const data = await res.json();
    if (!res.ok || !data.ok) {
      setStatusText(`登录流程失败: ${data.detail || data.message || res.status}`);
      return;
    }
    const early = data.data?.finished_early ? "（已检测登录并提前结束）" : "";
    setStatusText(`登录流程完成${early}，已保存Cookie ${data.data?.saved_cookie_count || 0} 条`);
    const st = await checkLoginStatus();
    if (st) {
      appendProgress(`[${new Date().toLocaleTimeString()}] Cookie状态: active=${st.active_count}, total=${st.total_count}`);
    }
  } catch (e) {
    setStatusText(`登录流程异常: ${e.message}`);
  }
}

async function clearCookies() {
  try {
    const res = await api(`/api/tasks/login/clear?platform=${encodeURIComponent(state.platform)}`, {
      method: "POST",
    });
    const data = await res.json();
    if (!res.ok || !data.ok) {
      setStatusText(`清空Cookie失败: ${data.detail || data.message || res.status}`);
      return;
    }
    setStatusText("已清空Cookie");
    appendProgress(`[${new Date().toLocaleTimeString()}] 已清空 ${state.platform} Cookie`);
  } catch (e) {
    setStatusText(`清空Cookie异常: ${e.message}`);
  }
}

async function clearJobsData() {
  const ok = window.confirm("确认清空数据库中的全部岗位数据吗？该操作不可恢复。");
  if (!ok) return;

  setStatusText("正在清空岗位数据...");
  try {
    const res = await api("/api/tasks/data/clear?scope=all", {
      method: "POST",
    });
    const data = await res.json();
    if (!res.ok || !data.ok) {
      setStatusText(`清空岗位数据失败: ${data.detail || data.message || res.status}`);
      return;
    }
    const deleted = data.data?.deleted ?? 0;
    setStatusText(`清空完成，删除 ${deleted} 条岗位数据`);
    appendProgress(`[${new Date().toLocaleTimeString()}] 已清空岗位数据 ${deleted} 条`);
    state.page = 1;
    await loadList();
    await loadStats();
  } catch (e) {
    setStatusText(`清空岗位数据异常: ${e.message}`);
  }
}

async function saveCurrentConfig() {
  const payload = {
    platform: state.platform,
    config: collectConfigSnapshot(),
  };
  try {
    const res = await api("/api/tasks/config", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok || !data.ok) {
      setStatusText(`保存配置失败: ${data.detail || data.message || res.status}`);
      return;
    }
    setStatusText("配置已保存");
  } catch (e) {
    setStatusText(`保存配置异常: ${e.message}`);
  }
}

async function loadSavedConfig() {
  try {
    const res = await api(`/api/tasks/config?platform=${encodeURIComponent(state.platform)}`);
    const data = await res.json();
    if (!res.ok || !data.ok) return;
    applyConfigSnapshot(data.data || {});
  } catch {
    // ignore if no saved config
  }
}

async function stopTask() {
  setStatusText("正在发送停止指令...");
  try {
    const res = await api(`/api/tasks/stop?platform=${encodeURIComponent(state.platform)}`, { method: "POST" });
    const data = await res.json();
    if (!res.ok || !data.ok) {
      setStatusText(`停止失败: ${data.detail || data.message || res.status}`);
      return;
    }
    setStatusText(`已停止: ${state.platform}`);
    appendProgress(`[${new Date().toLocaleTimeString()}] 已停止 ${state.platform}`);
    refreshStatus();
  } catch (e) {
    setStatusText(`停止异常: ${e.message}`);
  }
}

async function refreshStatus() {
  try {
    const res = await api(`/api/tasks/status?platform=${encodeURIComponent(state.platform)}`);
    const data = await res.json();
    if (!res.ok || !data.ok) {
      setStatusText(`获取状态失败: ${data.detail || data.message || res.status}`);
      return;
    }
    const s = data.data || {};
    setStatusText(
      `平台=${s.platform} | 运行中=${s.running ? "是" : "否"} | 上次新增=${s.last_count || 0}` +
      `${s.last_error ? ` | 错误=${s.last_error}` : ""}`
    );
  } catch (e) {
    setStatusText(`获取状态异常: ${e.message}`);
  }
}

function renderTopList(listElId, rows, nameKey) {
  const ul = el(listElId);
  ul.innerHTML = "";
  const items = rows || [];
  if (items.length === 0) {
    ul.innerHTML = `<li><span class="muted">暂无数据</span><span></span></li>`;
    return;
  }
  for (const r of items) {
    const li = document.createElement("li");
    const name = r[nameKey] || "-";
    li.innerHTML = `<span>${name}</span><strong>${r.cnt || 0}</strong>`;
    ul.appendChild(li);
  }
}

async function loadStats() {
  const kw = (el("searchKeyword").value || "").trim();
  const tf = getTimeFilters();
  const q = new URLSearchParams({ platform: state.platform });
  if (kw) q.set("keyword", kw);
  if (tf.createdFrom) q.set("created_from", tf.createdFrom);
  if (tf.createdTo) q.set("created_to", tf.createdTo);
  try {
    const res = await api(`/api/tasks/stats?${q.toString()}`);
    const data = await res.json();
    if (!res.ok || !data.ok) return;
    const s = data.data || {};
    el("statTotal").textContent = String(s.total || 0);
    el("statCompanies").textContent = String(s.unique_companies || 0);
    el("statPlatform").textContent = state.platform;
    renderTopList("topCompanies", s.top_companies, "company_name");
    renderTopList("topLocations", s.top_locations, "location_name");
    drawBarChart("expChart", s.top_experience || [], "experience_name", "#6366f1");
    drawBarChart("degreeChart", s.top_degree || [], "degree_name", "#0ea5e9");
  } catch {
    // ignore stats errors
  }
}

function drawBarChart(canvasId, rows, nameKey, color) {
  const canvas = el(canvasId);
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const w = canvas.width;
  const h = canvas.height;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f8fafc";
  ctx.fillRect(0, 0, w, h);

  const items = (rows || []).slice(0, 8);
  if (items.length === 0) {
    ctx.fillStyle = "#64748b";
    ctx.font = "14px sans-serif";
    ctx.fillText("暂无数据", 18, 30);
    return;
  }
  const max = Math.max(...items.map((x) => Number(x.cnt || 0)), 1);
  const left = 42;
  const top = 18;
  const bottom = h - 28;
  const barAreaW = w - left - 18;
  const rowH = Math.floor((bottom - top) / items.length);

  ctx.strokeStyle = "#cbd5e1";
  ctx.beginPath();
  ctx.moveTo(left, top - 5);
  ctx.lineTo(left, bottom + 6);
  ctx.stroke();

  items.forEach((item, i) => {
    const y = top + i * rowH + 6;
    const val = Number(item.cnt || 0);
    const barW = Math.max(1, Math.floor((val / max) * (barAreaW - 90)));
    const name = String(item[nameKey] || "-").slice(0, 10);
    ctx.fillStyle = "#334155";
    ctx.font = "12px sans-serif";
    ctx.fillText(name, 8, y + 10);
    ctx.fillStyle = color;
    ctx.fillRect(left + 4, y, barW, 13);
    ctx.fillStyle = "#0f172a";
    ctx.fillText(String(val), left + 10 + barW, y + 11);
  });
}

function renderRows(items) {
  const tbody = el("rows");
  tbody.innerHTML = "";
  if (!items || items.length === 0) {
    tbody.innerHTML = `<tr><td colspan="8" class="muted">暂无数据</td></tr>`;
    return;
  }
  for (const it of items) {
    const tr = document.createElement("tr");
    const link = it.job_link
      ? `<a href="${it.job_link}" target="_blank" rel="noopener noreferrer">查看</a>`
      : "";
    tr.innerHTML = `
      <td>${it.id ?? ""}</td>
      <td>${it.job_name ?? ""}</td>
      <td>${link}</td>
      <td>${it.company_name ?? ""}</td>
      <td>${it.salary_desc ?? ""}</td>
      <td>${it.location_name ?? ""}</td>
      <td>${(it.experience_name ?? "") + " / " + (it.degree_name ?? "")}</td>
      <td>${it.created_at ?? ""}</td>
    `;
    tbody.appendChild(tr);
  }
}

function updatePager() {
  const totalPage = Math.max(1, Math.ceil((state.total || 0) / state.size));
  el("pagerInfo").textContent = `第 ${state.page} / ${totalPage} 页，共 ${state.total} 条`;
  el("btnPrev").disabled = state.page <= 1;
  el("btnNext").disabled = state.page >= totalPage;
}

async function loadList() {
  const kw = (el("searchKeyword").value || "").trim();
  const tf = getTimeFilters();
  const q = new URLSearchParams({
    platform: state.platform,
    page: String(state.page),
    size: String(state.size),
  });
  if (kw) q.set("keyword", kw);
  if (tf.createdFrom) q.set("created_from", tf.createdFrom);
  if (tf.createdTo) q.set("created_to", tf.createdTo);

  try {
    const res = await api(`/api/tasks/list?${q.toString()}`);
    const data = await res.json();
    state.total = data.total || 0;
    renderRows(data.items || []);
    updatePager();
    if (state.tab === "analysisTab") {
      loadStats();
    }
  } catch (e) {
    renderRows([]);
    setStatusText(`加载列表失败: ${e.message}`);
  }
}

function fillSelect(selectId, options, defaultCode) {
  const s = el(selectId);
  if (!s) return;
  const current = s.value;
  s.innerHTML = "";
  const custom = document.createElement("option");
  custom.value = "__custom__";
  custom.textContent = "自定义输入";
  s.appendChild(custom);
  (options || []).forEach((opt) => {
    const option = document.createElement("option");
    option.value = opt.code || "";
    option.textContent = `${opt.name || opt.code} (${opt.code || ""})`;
    s.appendChild(option);
  });
  const finalVal = current || defaultCode || "__custom__";
  s.value = finalVal;
}

function bindSelectInputs() {
  el("citySelect").addEventListener("change", () => {
    const v = el("citySelect").value;
    if (v && v !== "__custom__") {
      el("cityCode").value = v;
    }
  });
  el("salarySelect").addEventListener("change", () => {
    const v = el("salarySelect").value;
    if (v && v !== "__custom__") {
      el("salary").value = v;
    }
  });
}

async function loadOptions() {
  try {
    const res = await api(`/api/tasks/options?platform=${encodeURIComponent(state.platform)}`);
    const data = await res.json();
    if (!res.ok || !data.ok) return;
    const o = data.data || {};
    fillSelect("citySelect", o.city || [], o.defaults?.city_code);
    fillSelect("salarySelect", o.salary || [], null);
    if (o.defaults?.city_code) {
      el("cityCode").value = o.defaults.city_code;
    }
    if (o.defaults?.max_pages) {
      el("maxPages").value = o.defaults.max_pages;
    }
  } catch {
    // keep existing manual inputs
  }
}

function bindActions() {
  el("btnSaveConfig").addEventListener("click", saveCurrentConfig);
  el("btnLogin").addEventListener("click", loginAndSaveCookie);
  el("btnClearCookie").addEventListener("click", clearCookies);
  el("btnClearJobs").addEventListener("click", clearJobsData);
  el("btnStart").addEventListener("click", startTask);
  el("btnStop").addEventListener("click", stopTask);
  el("btnRefreshStatus").addEventListener("click", refreshStatus);
  el("btnSearch").addEventListener("click", () => {
    state.page = 1;
    loadList();
    loadStats();
  });
  el("btnPrev").addEventListener("click", () => {
    if (state.page > 1) {
      state.page -= 1;
      loadList();
    }
  });
  el("btnNext").addEventListener("click", () => {
    const totalPage = Math.max(1, Math.ceil((state.total || 0) / state.size));
    if (state.page < totalPage) {
      state.page += 1;
      loadList();
    }
  });
}

async function init() {
  bindMenu();
  bindTabs();
  bindActions();
  bindSelectInputs();
  applyPlatformDefaults();
  await loadOptions();
  await loadSavedConfig();
  connectProgressStream();
  await checkHealth();
  const loginState = await checkLoginStatus();
  if (loginState) {
    appendProgress(`[init] Cookie active=${loginState.active_count}, total=${loginState.total_count}`);
  }
  await refreshStatus();
  await loadList();
  await loadStats();
  setInterval(checkHealth, 30000);
  setInterval(refreshStatus, 10000);
}

init();
