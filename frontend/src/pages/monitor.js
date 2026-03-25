import { api } from "../api.js";

function showModal(title, bodyHtml, onSave) {
  const overlay = document.createElement("div");
  overlay.className = "modal-overlay";
  overlay.innerHTML = `
    <div class="modal"><h3>${title}</h3>${bodyHtml}
      <div class="modal-actions">
        <button class="btn" id="modal-cancel">Cancel</button>
        <button class="btn btn-primary" id="modal-save">Save</button>
      </div>
    </div>`;
  document.body.appendChild(overlay);
  overlay.querySelector("#modal-cancel").onclick = () => overlay.remove();
  overlay.querySelector("#modal-save").onclick = async () => { await onSave(); overlay.remove(); };
  overlay.addEventListener("click", (e) => { if (e.target === overlay) overlay.remove(); });
}

export async function renderMonitor(container) {
  container.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px">
      <h2>Keyword Monitors</h2>
      <button class="btn btn-primary" id="add-monitor">+ Add Monitor</button>
    </div>
    <div class="card"><table>
      <thead><tr><th>Keyword</th><th>Account</th><th>Discord</th><th>Last Checked</th><th>Status</th></tr></thead>
      <tbody id="monitors-body"><tr><td colspan="5" class="empty-state">Loading...</td></tr></tbody>
    </table></div>
  `;

  let accounts = [];
  try { accounts = await api.getAccounts(); } catch {}

  async function loadMonitors() {
    try {
      const monitors = await api.getMonitors();
      const tbody = document.getElementById("monitors-body");
      if (monitors.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" class="empty-state">No monitors</td></tr>`;
        return;
      }
      const accountMap = Object.fromEntries(accounts.map((a) => [a.id, a]));
      tbody.innerHTML = monitors.map((m) => `
        <tr>
          <td>${m.keyword}</td>
          <td>${accountMap[m.account_id]?.username || m.account_id}</td>
          <td>${m.notify_discord ? '<span class="badge badge-success">On</span>' : '<span class="badge badge-danger">Off</span>'}</td>
          <td>${m.last_checked_at ? new Date(m.last_checked_at).toLocaleString() : "Never"}</td>
          <td><span class="badge ${m.is_active ? "badge-success" : "badge-danger"}">${m.is_active ? "Active" : "Inactive"}</span></td>
        </tr>
      `).join("");
    } catch {
      document.getElementById("monitors-body").innerHTML =
        `<tr><td colspan="5" class="empty-state">Failed to load</td></tr>`;
    }
  }

  document.getElementById("add-monitor").onclick = () => {
    if (accounts.length === 0) { alert("Please add an account first"); return; }
    showModal("Add Monitor", `
      <div class="form-group"><label>Account</label>
        <select id="f-account">${accounts.map((a) => `<option value="${a.id}">${a.name} (@${a.username})</option>`).join("")}</select>
      </div>
      <div class="form-group"><label>Keyword</label><input id="f-keyword"></div>
      <div class="form-group"><label><input type="checkbox" id="f-discord"> Notify Discord</label></div>
      <div class="form-group"><label>Discord Webhook URL</label><input id="f-webhook"></div>
    `, async () => {
      await api.createMonitor({
        account_id: Number(document.getElementById("f-account").value),
        keyword: document.getElementById("f-keyword").value,
        notify_discord: document.getElementById("f-discord").checked,
        discord_webhook: document.getElementById("f-webhook").value || null,
      });
      loadMonitors();
    });
  };

  loadMonitors();
}
