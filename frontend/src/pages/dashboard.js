import { api } from "../api.js";

export async function renderDashboard(container) {
  container.innerHTML = `<h2>Dashboard</h2><div class="card-grid" id="stats-grid"></div>
    <div class="card"><h3>Recent Logs</h3><div class="log-stream" id="log-stream"><div class="empty-state">Loading...</div></div></div>`;

  try {
    const stats = await api.getStats();
    document.getElementById("stats-grid").innerHTML = `
      <div class="stat-card"><div class="value">${stats.active_accounts}</div><div class="label">Active Accounts</div></div>
      <div class="stat-card"><div class="value">${stats.active_rules}</div><div class="label">Active Rules</div></div>
      <div class="stat-card"><div class="value">${stats.pending_posts}</div><div class="label">Pending Posts</div></div>
      <div class="stat-card"><div class="value">${stats.today_executions}</div><div class="label">Today Executions</div></div>
      <div class="stat-card"><div class="value">${stats.today_success}</div><div class="label">Success</div></div>
      <div class="stat-card"><div class="value">${stats.today_failed}</div><div class="label">Failed</div></div>
    `;
  } catch {
    document.getElementById("stats-grid").innerHTML = `<div class="empty-state">Failed to load stats</div>`;
  }

  try {
    const logs = await api.getLogs({ limit: 20 });
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
