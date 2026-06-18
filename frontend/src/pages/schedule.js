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

const CSV_TEMPLATE = `account_id,content,scheduled_at,repeat_type
1,ツイート内容1,2026-06-01 09:00,none
1,ツイート内容2,2026-06-02 12:00,none
1,毎日投稿,2026-06-03 18:00,daily`;

function parseCsv(text) {
  const lines = text.trim().split(/\r?\n/);
  if (lines.length < 2) return { rows: [], error: "ヘッダー行とデータ行が必要です" };

  const headers = lines[0].split(",").map((h) => h.trim());
  const required = ["content", "scheduled_at"];
  for (const r of required) {
    if (!headers.includes(r)) return { rows: [], error: `必須カラム "${r}" がありません` };
  }

  const rows = [];
  for (let i = 1; i < lines.length; i++) {
    if (!lines[i].trim()) continue;
    // Simple CSV split (handles quoted fields with commas)
    const values = lines[i].match(/("(?:[^"]|"")*"|[^,]*)/g).filter((_, j) => j % 2 === 0);
    const row = {};
    headers.forEach((h, idx) => {
      row[h] = (values[idx] || "").replace(/^"|"$/g, "").replace(/""/g, '"').trim();
    });
    rows.push({ ...row, _line: i + 1 });
  }
  return { rows, error: null };
}

function normalizeScheduledAt(s) {
  // "2026-06-01 09:00" → "2026-06-01T09:00" so new Date() parses it reliably across browsers
  return s ? s.trim().replace(/\s+/, "T") : s;
}

function validateCsvRows(rows, accounts) {
  return rows.map((row) => {
    const errors = [];
    if (!row.content) errors.push("content が空");
    const normalized = normalizeScheduledAt(row.scheduled_at);
    const dt = new Date(normalized);
    if (!normalized || isNaN(dt)) errors.push("scheduled_at が無効な日時 (例: 2026-06-01 09:00)");
    const accountId = Number(row.account_id);
    if (row.account_id && !accounts.find((a) => a.id === accountId)) errors.push(`account_id=${row.account_id} が存在しない`);
    return { ...row, _errors: errors };
  });
}

function showCsvImportModal(accounts, onImport) {
  const defaultAccountId = accounts[0]?.id ?? 1;
  const overlay = document.createElement("div");
  overlay.className = "modal-overlay";
  overlay.innerHTML = `
    <div class="modal" style="max-width:780px;width:90vw">
      <h3>CSV 一括インポート</h3>
      <div style="display:flex;gap:8px;margin-bottom:12px;align-items:center">
        <input id="csv-file" type="file" accept=".csv,text/csv" style="flex:1">
        <button class="btn" id="csv-template">テンプレDL</button>
      </div>
      <div class="form-group">
        <label style="font-size:12px;color:#888">
          CSVカラム: <code>account_id</code>（省略時=${defaultAccountId}）, <code>content</code>*, <code>scheduled_at</code>* (YYYY-MM-DD HH:MM), <code>repeat_type</code>（none/daily/weekly）
        </label>
      </div>
      <div id="csv-preview" style="display:none">
        <div id="csv-summary" style="margin-bottom:8px;font-size:13px"></div>
        <div style="max-height:300px;overflow-y:auto">
          <table style="font-size:12px;width:100%">
            <thead><tr><th>#</th><th>account</th><th>content</th><th>scheduled_at</th><th>repeat</th><th>状態</th></tr></thead>
            <tbody id="csv-rows"></tbody>
          </table>
        </div>
      </div>
      <div class="modal-actions">
        <button class="btn" id="csv-cancel">キャンセル</button>
        <button class="btn btn-primary" id="csv-import" disabled>インポート</button>
      </div>
    </div>`;
  document.body.appendChild(overlay);

  let parsedRows = [];

  overlay.querySelector("#csv-cancel").onclick = () => overlay.remove();
  overlay.addEventListener("click", (e) => { if (e.target === overlay) overlay.remove(); });

  overlay.querySelector("#csv-template").onclick = () => {
    const blob = new Blob([CSV_TEMPLATE], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "schedule_template.csv";
    a.click();
  };

  overlay.querySelector("#csv-file").onchange = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      const { rows, error } = parseCsv(ev.target.result);
      const preview = overlay.querySelector("#csv-preview");
      const summary = overlay.querySelector("#csv-summary");
      const tbody = overlay.querySelector("#csv-rows");
      const importBtn = overlay.querySelector("#csv-import");

      if (error) {
        preview.style.display = "none";
        importBtn.disabled = true;
        alert(`CSV エラー: ${error}`);
        return;
      }

      parsedRows = validateCsvRows(rows, accounts);
      const validCount = parsedRows.filter((r) => r._errors.length === 0).length;
      const errorCount = parsedRows.length - validCount;

      summary.innerHTML = `<strong>${parsedRows.length} 件</strong> 読み込み — ✅ ${validCount} 件登録可 ${errorCount ? `/ ⚠️ ${errorCount} 件エラー` : ""}`;
      tbody.innerHTML = parsedRows.map((row) => {
        const ok = row._errors.length === 0;
        const accountId = Number(row.account_id) || defaultAccountId;
        const acct = accounts.find((a) => a.id === accountId);
        return `<tr style="${ok ? "" : "color:#e55;background:#fff0f0"}">
          <td style="padding:2px 6px">${row._line}</td>
          <td style="padding:2px 6px">${acct ? `@${acct.username}` : row.account_id || defaultAccountId}</td>
          <td style="padding:2px 6px;max-width:240px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${row.content}</td>
          <td style="padding:2px 6px;white-space:nowrap">${row.scheduled_at}</td>
          <td style="padding:2px 6px">${row.repeat_type || "none"}</td>
          <td style="padding:2px 6px">${ok ? "✅" : "⚠️ " + row._errors.join(", ")}</td>
        </tr>`;
      }).join("");

      preview.style.display = "";
      importBtn.disabled = validCount === 0;
    };
    reader.readAsText(file);
  };

  overlay.querySelector("#csv-import").onclick = async () => {
    const defaultAccountId = accounts[0]?.id ?? 1;
    const validPosts = parsedRows
      .filter((r) => r._errors.length === 0)
      .map((r) => ({
        account_id: Number(r.account_id) || defaultAccountId,
        content: r.content,
        scheduled_at: normalizeScheduledAt(r.scheduled_at),
        repeat_type: r.repeat_type || "none",
        repeat_config: {},
        image_paths: [],
      }));
    await onImport(validPosts);
    overlay.remove();
  };
}

function showPostPreview(post) {
  const overlay = document.createElement("div");
  overlay.className = "modal-overlay";
  const images = (post.image_paths || []).map((p) => {
    const filename = p.split("/").pop();
    return `<img src="/api/uploads/${filename}" style="max-width:100%;border-radius:6px;margin-bottom:8px">`;
  }).join("");
  overlay.innerHTML = `
    <div class="modal" style="max-width:480px;width:90vw">
      <h3>投稿プレビュー</h3>
      <div style="white-space:pre-wrap;margin-bottom:12px">${post.content || "(本文なし)"}</div>
      ${images || `<div class="empty-state">画像なし</div>`}
      <div style="font-size:12px;color:#888;margin-top:8px">
        予定時刻: ${new Date(post.scheduled_at).toLocaleString()} / ステータス: ${post.status}
      </div>
      <div class="modal-actions">
        <button class="btn" id="preview-close">閉じる</button>
      </div>
    </div>`;
  document.body.appendChild(overlay);
  overlay.querySelector("#preview-close").onclick = () => overlay.remove();
  overlay.addEventListener("click", (e) => { if (e.target === overlay) overlay.remove(); });
}

function showBulkImageModal(accounts, accountId, onSubmit) {
  const overlay = document.createElement("div");
  overlay.className = "modal-overlay";
  overlay.innerHTML = `
    <div class="modal" style="max-width:560px;width:90vw">
      <h3>画像一括スケジュール</h3>
      <div class="form-group"><label>Account</label>
        <select id="bi-account">${accounts.map((a) => `<option value="${a.id}" ${a.id === accountId ? "selected" : ""}>${a.name} (@${a.username})</option>`).join("")}</select>
      </div>
      <div class="form-group"><label>画像（複数選択可）</label><input id="bi-images" type="file" accept="image/*" multiple></div>
      <div id="bi-count" style="font-size:12px;color:#888;margin-bottom:8px"></div>
      <div class="form-group"><label>キャプション（全件共通・空欄可）</label><textarea id="bi-caption" rows="3"></textarea></div>
      <div class="form-group"><label>投稿時刻（1日あたりの投稿数 = 時刻の数）</label>
        <div id="bi-times" style="display:flex;flex-direction:column;gap:6px"></div>
        <button class="btn btn-sm" id="bi-add-time" style="margin-top:6px">+ 時刻追加</button>
      </div>
      <div class="form-group"><label>開始日</label><input id="bi-start-date" type="date"></div>
      <div class="modal-actions">
        <button class="btn" id="bi-cancel">キャンセル</button>
        <button class="btn btn-primary" id="bi-submit">スケジュール作成</button>
      </div>
    </div>`;
  document.body.appendChild(overlay);

  const timesContainer = overlay.querySelector("#bi-times");
  function addTimeRow(value = "09:00") {
    const row = document.createElement("div");
    row.style.display = "flex";
    row.style.gap = "6px";
    row.innerHTML = `<input type="time" class="bi-time" value="${value}"><button class="btn btn-sm bi-remove-time">削除</button>`;
    row.querySelector(".bi-remove-time").onclick = () => row.remove();
    timesContainer.appendChild(row);
  }
  addTimeRow("09:00");
  addTimeRow("18:00");

  overlay.querySelector("#bi-add-time").onclick = () => addTimeRow("12:00");

  const todayStr = new Date().toISOString().slice(0, 10);
  overlay.querySelector("#bi-start-date").value = todayStr;

  overlay.querySelector("#bi-images").onchange = (e) => {
    overlay.querySelector("#bi-count").textContent = `${e.target.files.length} 枚選択中`;
  };

  overlay.querySelector("#bi-cancel").onclick = () => overlay.remove();
  overlay.addEventListener("click", (e) => { if (e.target === overlay) overlay.remove(); });

  overlay.querySelector("#bi-submit").onclick = async () => {
    const files = Array.from(overlay.querySelector("#bi-images").files);
    if (files.length === 0) { alert("画像を選択してください"); return; }
    const times = Array.from(overlay.querySelectorAll(".bi-time")).map((el) => el.value).filter(Boolean);
    if (times.length === 0) { alert("投稿時刻を1つ以上指定してください"); return; }

    const submitBtn = overlay.querySelector("#bi-submit");
    submitBtn.disabled = true;
    submitBtn.textContent = `アップロード中... 0/${files.length}`;

    const image_paths = [];
    for (let i = 0; i < files.length; i++) {
      const { path } = await api.uploadImage(files[i]);
      image_paths.push(path);
      submitBtn.textContent = `アップロード中... ${i + 1}/${files.length}`;
    }

    await onSubmit({
      account_id: Number(overlay.querySelector("#bi-account").value),
      image_paths,
      caption: overlay.querySelector("#bi-caption").value,
      times,
      start_date: overlay.querySelector("#bi-start-date").value,
    });
    overlay.remove();
  };
}

export async function renderSchedule(container, accountId) {
  container.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px">
      <h2>Scheduled Posts</h2>
      <div style="display:flex;gap:8px">
        <button class="btn" id="import-csv">CSV インポート</button>
        <button class="btn" id="bulk-images">画像一括スケジュール</button>
        <button class="btn btn-primary" id="add-post">+ Schedule Post</button>
      </div>
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
      const allPosts = await api.getScheduledPosts(status || undefined);
      const posts = accountId ? allPosts.filter((p) => p.account_id === accountId) : allPosts;
      const tbody = document.getElementById("posts-body");
      if (posts.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" class="empty-state">No scheduled posts</td></tr>`;
        return;
      }
      tbody.innerHTML = posts.map((p) => `
        <tr class="post-row" data-id="${p.id}" style="cursor:pointer">
          <td style="max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${p.content}${p.image_paths?.length ? ` 📷${p.image_paths.length}` : ""}</td>
          <td>${new Date(p.scheduled_at).toLocaleString()}</td>
          <td>${formatRepeat(p)}</td>
          <td><span class="badge ${p.status === "posted" ? "badge-success" : p.status === "failed" ? "badge-danger" : "badge-warning"}">${p.status}</span></td>
          <td>${p.status === "pending" ? `
            <button class="btn btn-sm post-now" data-id="${p.id}">今すぐ投稿</button>
            <button class="btn btn-sm btn-danger delete-post" data-id="${p.id}">Delete</button>
          ` : ""}</td>
        </tr>
      `).join("");

      tbody.querySelectorAll(".post-row").forEach((row) => {
        row.onclick = (e) => {
          if (e.target.closest(".delete-post") || e.target.closest(".post-now")) return;
          const post = posts.find((p) => p.id === Number(row.dataset.id));
          showPostPreview(post);
        };
      });

      tbody.querySelectorAll(".delete-post").forEach((btn) => {
        btn.onclick = async () => {
          if (confirm("Delete this scheduled post?")) {
            await api.deleteScheduledPost(btn.dataset.id);
            loadPosts(document.getElementById("filter-status").value);
          }
        };
      });

      tbody.querySelectorAll(".post-now").forEach((btn) => {
        btn.onclick = async () => {
          if (!confirm("この内容を今すぐ投稿しますか？")) return;
          btn.disabled = true;
          btn.textContent = "投稿中...";
          try {
            await api.postNow(btn.dataset.id);
            loadPosts(document.getElementById("filter-status").value);
          } catch (err) {
            alert("投稿に失敗しました: " + err.message);
            btn.disabled = false;
            btn.textContent = "今すぐ投稿";
          }
        };
      });
    } catch {
      document.getElementById("posts-body").innerHTML =
        `<tr><td colspan="5" class="empty-state">Failed to load</td></tr>`;
    }
  }

  document.getElementById("filter-status").onchange = (e) => loadPosts(e.target.value);

  document.getElementById("bulk-images").onclick = () => {
    if (accounts.length === 0) { alert("Please add an account first"); return; }
    showBulkImageModal(accounts, accountId, async (data) => {
      try {
        const result = await api.bulkScheduleImages(data);
        const msg = `${result.created} 件登録しました${result.errors.length ? `（${result.errors.length} 件エラー）` : ""}`;
        alert(msg);
        loadPosts(document.getElementById("filter-status").value);
      } catch (e) {
        alert(`登録失敗: ${e.message}`);
      }
    });
  };

  document.getElementById("import-csv").onclick = () => {
    if (accounts.length === 0) { alert("Please add an account first"); return; }
    showCsvImportModal(accounts, async (posts) => {
      try {
        const result = await api.bulkCreateScheduledPosts(posts);
        const msg = `${result.created} 件登録しました${result.errors.length ? `（${result.errors.length} 件エラー）` : ""}`;
        alert(msg);
        loadPosts(document.getElementById("filter-status").value);
      } catch (e) {
        alert(`インポート失敗: ${e.message}`);
      }
    });
  };

  document.getElementById("add-post").onclick = () => {
    if (accounts.length === 0) { alert("Please add an account first"); return; }
    showModal("Schedule Post", `
      <div class="form-group"><label>Account</label>
        <select id="f-account">${accounts.map((a) => `<option value="${a.id}" ${a.id === accountId ? "selected" : ""}>${a.name} (@${a.username})</option>`).join("")}</select>
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
        scheduled_at: document.getElementById("f-scheduled-at").value,
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
