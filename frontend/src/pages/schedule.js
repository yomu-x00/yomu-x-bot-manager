import { api } from "../api.js";

const DAY_LABELS = { mon: "月", tue: "火", wed: "水", thu: "木", fri: "金", sat: "土", sun: "日" };
const DAY_KEYS = Object.keys(DAY_LABELS);

function formatRepeat(p) {
  if (p.repeat_type === "random_window") {
    const cfg = p.repeat_config || {};
    const days = cfg.days && cfg.days.length ? cfg.days.map((d) => DAY_LABELS[d]).join("") : "毎日";
    return `ランダム ${cfg.window_start || "?"}-${cfg.window_end || "?"} (${days})`;
  }
  const map = { none: "なし", daily: "毎日", weekly: "毎週", custom: `${p.repeat_config?.interval_hours || "?"}h毎` };
  return map[p.repeat_type] || p.repeat_type;
}

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
          <td>${formatRepeat(p)}</td>
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
      <div class="form-group"><label>Images (max 4)</label><input id="f-images" type="file" accept="image/*" multiple></div>
      <div id="f-image-preview" style="display:flex;gap:8px;flex-wrap:wrap;margin-top:4px"></div>
      <div class="form-group"><label>Scheduled At</label><input id="f-scheduled-at" type="datetime-local"></div>
      <div class="form-group"><label>Repeat</label>
        <select id="f-repeat">
          <option value="none">なし</option>
          <option value="daily">毎日（同じ時刻）</option>
          <option value="weekly">毎週（同じ時刻）</option>
          <option value="custom">カスタム間隔</option>
          <option value="random_window">ランダム時間帯</option>
        </select>
      </div>
      <div id="f-custom-opts" style="display:none" class="form-group">
        <label>間隔（時間）</label>
        <input id="f-interval" type="number" min="1" value="24" style="width:80px">
      </div>
      <div id="f-window-opts" style="display:none">
        <div class="form-group" style="display:flex;gap:12px;align-items:center">
          <div><label>開始時刻</label><input id="f-win-start" type="time" value="09:00"></div>
          <div><label>終了時刻</label><input id="f-win-end" type="time" value="18:00"></div>
        </div>
        <div class="form-group">
          <label>投稿する曜日（未選択で毎日）</label>
          <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:4px">
            ${DAY_KEYS.map((d) => `<label style="display:flex;align-items:center;gap:4px"><input type="checkbox" class="f-day" value="${d}">${DAY_LABELS[d]}</label>`).join("")}
          </div>
        </div>
      </div>
    `, async () => {
      const repeatType = document.getElementById("f-repeat").value;
      const repeat_config = {};
      if (repeatType === "custom") {
        repeat_config.interval_hours = Number(document.getElementById("f-interval").value);
      } else if (repeatType === "random_window") {
        repeat_config.window_start = document.getElementById("f-win-start").value;
        repeat_config.window_end = document.getElementById("f-win-end").value;
        const days = Array.from(document.querySelectorAll(".f-day:checked")).map((el) => el.value);
        if (days.length) repeat_config.days = days;
      }

      const files = Array.from(document.getElementById("f-images").files).slice(0, 4);
      const image_paths = [];
      for (const file of files) {
        const { path } = await api.uploadImage(file);
        image_paths.push(path);
      }
      await api.createScheduledPost({
        account_id: Number(document.getElementById("f-account").value),
        content: document.getElementById("f-content").value,
        scheduled_at: new Date(document.getElementById("f-scheduled-at").value).toISOString(),
        repeat_type: repeatType,
        repeat_config,
        image_paths,
      });
      loadPosts(document.getElementById("filter-status").value);
    });

    // show/hide conditional fields
    document.getElementById("f-repeat").addEventListener("change", (e) => {
      document.getElementById("f-custom-opts").style.display = e.target.value === "custom" ? "" : "none";
      document.getElementById("f-window-opts").style.display = e.target.value === "random_window" ? "" : "none";
    });
  };

  loadPosts("");
}
