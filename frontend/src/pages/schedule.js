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

export async function renderSchedule(container) {
  container.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px">
      <h2>Scheduled Posts</h2>
      <button class="btn btn-primary" id="add-post">+ Schedule Post</button>
    </div>
    <div class="filter-bar">
      <select id="filter-status"><option value="">All</option><option value="pending">Pending</option><option value="posted">Posted</option><option value="failed">Failed</option></select>
    </div>
    <div class="card"><table>
      <thead><tr><th>Content</th><th>Scheduled At</th><th>Repeat</th><th>Status</th><th>Actions</th></tr></thead>
      <tbody id="posts-body"><tr><td colspan="5" class="empty-state">Loading...</td></tr></tbody>
    </table></div>
  `;

  let accounts = [];
  try { accounts = await api.getAccounts(); } catch {}

  async function loadPosts(status) {
    try {
      const posts = await api.getScheduledPosts(status || undefined);
      const tbody = document.getElementById("posts-body");
      if (posts.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" class="empty-state">No scheduled posts</td></tr>`;
        return;
      }
      tbody.innerHTML = posts.map((p) => `
        <tr>
          <td style="max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${p.content}</td>
          <td>${new Date(p.scheduled_at).toLocaleString()}</td>
          <td>${p.repeat_type}</td>
          <td><span class="badge ${p.status === "posted" ? "badge-success" : p.status === "failed" ? "badge-danger" : "badge-warning"}">${p.status}</span></td>
          <td>${p.status === "pending" ? `<button class="btn btn-sm btn-danger delete-post" data-id="${p.id}">Delete</button>` : ""}</td>
        </tr>
      `).join("");

      tbody.querySelectorAll(".delete-post").forEach((btn) => {
        btn.onclick = async () => {
          if (confirm("Delete this scheduled post?")) {
            await api.deleteScheduledPost(btn.dataset.id);
            loadPosts(document.getElementById("filter-status").value);
          }
        };
      });
    } catch {
      document.getElementById("posts-body").innerHTML =
        `<tr><td colspan="5" class="empty-state">Failed to load</td></tr>`;
    }
  }

  document.getElementById("filter-status").onchange = (e) => loadPosts(e.target.value);

  document.getElementById("add-post").onclick = () => {
    if (accounts.length === 0) { alert("Please add an account first"); return; }
    showModal("Schedule Post", `
      <div class="form-group"><label>Account</label>
        <select id="f-account">${accounts.map((a) => `<option value="${a.id}">${a.name} (@${a.username})</option>`).join("")}</select>
      </div>
      <div class="form-group"><label>Content</label><textarea id="f-content" rows="4"></textarea></div>
      <div class="form-group"><label>Scheduled At</label><input id="f-scheduled-at" type="datetime-local"></div>
      <div class="form-group"><label>Repeat</label>
        <select id="f-repeat"><option value="none">None</option><option value="daily">Daily</option><option value="weekly">Weekly</option><option value="custom">Custom</option></select>
      </div>
    `, async () => {
      await api.createScheduledPost({
        account_id: Number(document.getElementById("f-account").value),
        content: document.getElementById("f-content").value,
        scheduled_at: new Date(document.getElementById("f-scheduled-at").value).toISOString(),
        repeat_type: document.getElementById("f-repeat").value,
      });
      loadPosts(document.getElementById("filter-status").value);
    });
  };

  loadPosts("");
}
