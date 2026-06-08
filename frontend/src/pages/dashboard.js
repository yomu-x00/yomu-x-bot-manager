import { api } from "../api.js";

export async function renderDashboard(container, accountId) {
  container.innerHTML = `<h2>Dashboard</h2>
    <div id="cookie-alert"></div>
    <div class="card-grid" id="stats-grid"></div>
    <div class="card"><h3>Recent Logs</h3><div class="log-stream" id="log-stream"><div class="empty-state">Loading...</div></div></div>`;

  api.cookieHealth().then((results) => {
    const invalid = results.filter((r) => !r.valid);
    if (invalid.length === 0) return;
    const names = invalid.map((r) => `@${r.username}`).join(", ");
    document.getElementById("cookie-alert").innerHTML = `
      <div class="alert alert-danger" style="margin-bottom:1rem;padding:.75rem 1rem;border-radius:6px;background:#fee2e2;border:1px solid #fca5a5;color:#991b1b;">
        ⚠️ <strong>Cookie 失効:</strong> ${names} の Cookie が無効です。
        <a href="#accounts" style="margin-left:.5rem;color:#991b1b;font-weight:600;">アカウント設定で更新してください</a>
      </div>`;
  }).catch(() => {});


  try {
    const stats = await api.getStats(accountId);
    document.getElementById("stats-grid").innerHTML = `
      <div class="stat-card"><div class="value">${stats.active_rules}</div><div class="label">Active Rules</div></div>
      <div class="stat-card"><div class="value">${stats.pending_posts}</div><div class="label">Pending Posts</div></div>
      <div class="stat-card"><div class="value">${stats.today_executions}</div><div class="label">Today Executions</div></div>
      <div class="stat-card"><div class="value">${stats.today_success}</div><div class="label">Success</div></div>
      <div class="stat-card"><div class="value">${stats.today_failed}</div><div class="label">Failed</div></div>
      <div class="stat-card"><div class="value">${stats.today_skipped}</div><div class="label">Skipped</div></div>
    `;
  } catch {
    document.getElementById("stats-grid").innerHTML = `<div class="empty-state">Failed to load stats</div>`;
  }

  try {
    const params = { limit: 20 };
    if (accountId) params.account_id = accountId;
    const logs = await api.getLogs(params);
    const stream = document.getElementById("log-stream");
    if (logs.length === 0) {
      stream.innerHTML = `<div class="empty-state">No recent logs</div>`;
    } else {
      stream.innerHTML = logs.map((l) => `
        <div class="log-entry">
          <span class="time">${new Date(l.executed_at).toLocaleString()}</span>
          <span class="badge badge-${l.status === "success" ? "success" : l.status === "failed" ? "danger" : "warning"}">${l.status}</span>
          <span>${l.action}</span>
          ${l.tweet_id ? `<span style="color:var(--text-secondary)">tweet:${l.tweet_id}</span>` : ""}
        </div>
      `).join("");
    }
  } catch {
    document.getElementById("log-stream").innerHTML = `<div class="empty-state">Failed to load logs</div>`;
  }
}
