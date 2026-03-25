import { api } from "../api.js";

const TRIGGER_TYPES = ["keyword", "user", "engagement", "schedule"];
const ACTION_TYPES = ["rt", "like", "reply", "follow", "unfollow"];

function ruleFormHtml(rule = null, accounts = []) {
  return `
    <div class="form-group"><label>Account</label>
      <select id="f-account">${accounts.map((a) => `<option value="${a.id}" ${rule?.account_id === a.id ? "selected" : ""}>${a.name} (@${a.username})</option>`).join("")}</select>
    </div>
    <div class="form-group"><label>Rule Name</label><input id="f-name" value="${rule?.name || ""}"></div>
    <div class="form-row">
      <div class="form-group"><label>Trigger Type</label>
        <select id="f-trigger-type">${TRIGGER_TYPES.map((t) => `<option value="${t}" ${rule?.trigger_type === t ? "selected" : ""}>${t}</option>`).join("")}</select>
      </div>
      <div class="form-group"><label>Action Type</label>
        <select id="f-action-type">${ACTION_TYPES.map((t) => `<option value="${t}" ${rule?.action_type === t ? "selected" : ""}>${t}</option>`).join("")}</select>
      </div>
    </div>
    <div class="form-group"><label>Trigger Config (JSON)</label>
      <textarea id="f-trigger-config" rows="3">${JSON.stringify(rule?.trigger_config || {}, null, 2)}</textarea>
    </div>
    <div class="form-group"><label>Action Config (JSON)</label>
      <textarea id="f-action-config" rows="3">${JSON.stringify(rule?.action_config || {}, null, 2)}</textarea>
    </div>
    <div class="form-row">
      <div class="form-group"><label>Cooldown (min)</label><input id="f-cooldown" type="number" value="${rule?.cooldown_minutes ?? 60}"></div>
      <div class="form-group"><label>Daily Limit</label><input id="f-daily-limit" type="number" value="${rule?.daily_limit ?? 50}"></div>
    </div>
  `;
}

function showModal(title, bodyHtml, onSave) {
  const overlay = document.createElement("div");
  overlay.className = "modal-overlay";
  overlay.innerHTML = `
    <div class="modal">
      <h3>${title}</h3>
      ${bodyHtml}
      <div class="modal-actions">
        <button class="btn" id="modal-cancel">Cancel</button>
        <button class="btn btn-primary" id="modal-save">Save</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);
  overlay.querySelector("#modal-cancel").onclick = () => overlay.remove();
  overlay.querySelector("#modal-save").onclick = async () => {
    await onSave();
    overlay.remove();
  };
  overlay.addEventListener("click", (e) => { if (e.target === overlay) overlay.remove(); });
}

export async function renderRules(container) {
  container.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px">
      <h2>Rules</h2>
      <button class="btn btn-primary" id="add-rule">+ Add Rule</button>
    </div>
    <div class="card"><table>
      <thead><tr><th>Name</th><th>Account</th><th>Trigger</th><th>Action</th><th>Limit</th><th>Status</th><th>Actions</th></tr></thead>
      <tbody id="rules-body"><tr><td colspan="7" class="empty-state">Loading...</td></tr></tbody>
    </table></div>
  `;

  let accounts = [];
  try { accounts = await api.getAccounts(); } catch {}

  async function loadRules() {
    try {
      const rules = await api.getRules();
      const tbody = document.getElementById("rules-body");
      if (rules.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" class="empty-state">No rules</td></tr>`;
        return;
      }
      const accountMap = Object.fromEntries(accounts.map((a) => [a.id, a]));
      tbody.innerHTML = rules.map((r) => `
        <tr>
          <td>${r.name}</td>
          <td>${accountMap[r.account_id]?.username || r.account_id}</td>
          <td><span class="badge badge-info">${r.trigger_type}</span></td>
          <td><span class="badge badge-info">${r.action_type}</span></td>
          <td>${r.daily_limit}/day</td>
          <td>
            <label class="toggle"><input type="checkbox" ${r.is_active ? "checked" : ""} data-id="${r.id}" class="toggle-rule"><span class="slider"></span></label>
          </td>
          <td>
            <button class="btn btn-sm btn-primary run-btn" data-id="${r.id}">Run</button>
            <button class="btn btn-sm edit-btn" data-id="${r.id}" style="background:var(--border)">Edit</button>
            <button class="btn btn-sm btn-danger delete-btn" data-id="${r.id}">Delete</button>
          </td>
        </tr>
      `).join("");

      tbody.querySelectorAll(".toggle-rule").forEach((input) => {
        input.onchange = async () => {
          await api.toggleRule(input.dataset.id);
        };
      });

      tbody.querySelectorAll(".run-btn").forEach((btn) => {
        btn.onclick = async () => {
          btn.textContent = "...";
          try {
            const result = await api.runRule(btn.dataset.id);
            btn.textContent = `Done (${result.executed})`;
          } catch {
            btn.textContent = "Error";
          }
        };
      });

      tbody.querySelectorAll(".delete-btn").forEach((btn) => {
        btn.onclick = async () => {
          if (confirm("Delete this rule?")) {
            await api.deleteRule(btn.dataset.id);
            loadRules();
          }
        };
      });

      tbody.querySelectorAll(".edit-btn").forEach((btn) => {
        btn.onclick = () => {
          const rule = rules.find((r) => r.id === Number(btn.dataset.id));
          showModal("Edit Rule", ruleFormHtml(rule, accounts), async () => {
            await api.updateRule(rule.id, {
              name: document.getElementById("f-name").value,
              trigger_type: document.getElementById("f-trigger-type").value,
              trigger_config: JSON.parse(document.getElementById("f-trigger-config").value || "{}"),
              action_type: document.getElementById("f-action-type").value,
              action_config: JSON.parse(document.getElementById("f-action-config").value || "{}"),
              cooldown_minutes: Number(document.getElementById("f-cooldown").value),
              daily_limit: Number(document.getElementById("f-daily-limit").value),
            });
            loadRules();
          });
        };
      });
    } catch {
      document.getElementById("rules-body").innerHTML =
        `<tr><td colspan="7" class="empty-state">Failed to load rules</td></tr>`;
    }
  }

  document.getElementById("add-rule").onclick = () => {
    if (accounts.length === 0) { alert("Please add an account first"); return; }
    showModal("Add Rule", ruleFormHtml(null, accounts), async () => {
      await api.createRule({
        account_id: Number(document.getElementById("f-account").value),
        name: document.getElementById("f-name").value,
        trigger_type: document.getElementById("f-trigger-type").value,
        trigger_config: JSON.parse(document.getElementById("f-trigger-config").value || "{}"),
        action_type: document.getElementById("f-action-type").value,
        action_config: JSON.parse(document.getElementById("f-action-config").value || "{}"),
        cooldown_minutes: Number(document.getElementById("f-cooldown").value),
        daily_limit: Number(document.getElementById("f-daily-limit").value),
      });
      loadRules();
    });
  };

  loadRules();
}
