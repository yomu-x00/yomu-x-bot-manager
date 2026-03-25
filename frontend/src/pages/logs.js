import { api } from "../api.js";

export async function renderLogs(container) {
  container.innerHTML = `
    <h2>Execution Logs</h2>
    <div class="filter-bar">
      <select id="filter-status"><option value="">All Status</option><option value="success">Success</option><option value="failed">Failed</option><option value="skipped">Skipped</option></select>
      <select id="filter-action"><option value="">All Actions</option><option value="like">Like</option><option value="rt">RT</option><option value="reply">Reply</option><option value="follow">Follow</option><option value="unfollow">Unfollow</option></select>
      <button class="btn btn-sm btn-primary" id="apply-filter">Filter</button>
      <button class="btn btn-sm" id="load-more" style="background:var(--border)">Load More</button>
    </div>
    <div class="card"><table>
      <thead><tr><th>Time</th><th>Rule</th><th>Action</th><th>Tweet</th><th>Status</th><th>Reason</th></tr></thead>
      <tbody id="logs-body"><tr><td colspan="6" class="empty-state">Loading...</td></tr></tbody>
    </table></div>
  `;

  let offset = 0;
  const limit = 50;

  async function loadLogs(append = false) {
    const params = { limit, offset };
    const status = document.getElementById("filter-status").value;
    const action = document.getElementById("filter-action").value;
    if (status) params.status = status;
    if (action) params.action = action;

    try {
      const logs = await api.getLogs(params);
      const tbody = document.getElementById("logs-body");

      if (!append) tbody.innerHTML = "";

      if (logs.length === 0 && !append) {
        tbody.innerHTML = `<tr><td colspan="6" class="empty-state">No logs found</td></tr>`;
        return;
      }

      tbody.innerHTML += logs.map((l) => `
        <tr>
          <td style="white-space:nowrap">${new Date(l.executed_at).toLocaleString()}</td>
          <td>${l.rule_id}</td>
          <td><span class="badge badge-info">${l.action}</span></td>
          <td style="max-width:150px;overflow:hidden;text-overflow:ellipsis">${l.tweet_id || "-"}</td>
          <td><span class="badge badge-${l.status === "success" ? "success" : l.status === "failed" ? "danger" : "warning"}">${l.status}</span></td>
          <td style="color:var(--text-secondary);max-width:200px;overflow:hidden;text-overflow:ellipsis">${l.reason || ""}</td>
        </tr>
      `).join("");
    } catch {
      document.getElementById("logs-body").innerHTML =
        `<tr><td colspan="6" class="empty-state">Failed to load logs</td></tr>`;
    }
  }

  document.getElementById("apply-filter").onclick = () => {
    offset = 0;
    loadLogs();
  };

  document.getElementById("load-more").onclick = () => {
    offset += limit;
    loadLogs(true);
  };

  loadLogs();
}
