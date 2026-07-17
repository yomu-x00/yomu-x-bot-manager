import { api } from "../api.js";

function accountFormHtml(account = null) {
  const platform = account?.platform || "twitter";
  const isBluesky = platform === "bluesky";
  return `
    <div class="form-group">
      <label>プラットフォーム</label>
      <select id="f-platform" onchange="
        const bs = this.value === 'bluesky';
        document.getElementById('f-token-label').textContent = bs ? 'Identifier (handle / メールアドレス)' : 'auth_token';
        document.getElementById('f-ct0-label').textContent = bs ? 'App Password' : 'ct0';
        document.getElementById('f-username-group').style.display = bs ? 'none' : '';
      ">
        <option value="twitter" ${!isBluesky ? "selected" : ""}>X (Twitter)</option>
        <option value="bluesky" ${isBluesky ? "selected" : ""}>Bluesky</option>
      </select>
    </div>
    <div class="form-group"><label>Name</label><input id="f-name" value="${account?.name || ""}"></div>
    <div class="form-group" id="f-username-group" style="${isBluesky ? "display:none" : ""}">
      <label>Username (@)</label><input id="f-username" value="${account?.username || ""}">
    </div>
    <div class="form-group"><label id="f-token-label">${isBluesky ? "Identifier (handle / メールアドレス)" : "auth_token"}</label><input id="f-auth-token" type="password" value=""></div>
    <div class="form-group"><label id="f-ct0-label">${isBluesky ? "App Password" : "ct0"}</label><input id="f-ct0" type="password" value=""></div>
    <div class="form-group"><label>実行間隔（分）</label><input id="f-interval-minutes" type="number" min="1" value="${account?.interval_minutes ?? 5}"></div>
    <div class="form-group">
      <label>投稿末尾テキスト</label>
      <textarea id="f-tweet-suffix" rows="2" placeholder="例: &#10;#世界の祝日" style="font-family:monospace">${account?.tweet_suffix || ""}</textarea>
      <div style="font-size:11px;color:#888;margin-top:2px">全投稿の末尾に自動付与。空欄で無効。</div>
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
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) overlay.remove();
  });
}

export async function renderAccounts(container) {
  container.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px">
      <h2>Accounts</h2>
      <button class="btn btn-primary" id="add-account">+ Add Account</button>
    </div>
    <div class="card"><table>
      <thead><tr><th>Name</th><th>Username</th><th>Platform</th><th>Status</th><th>実行間隔</th><th>Created</th><th>Actions</th></tr></thead>
      <tbody id="accounts-body"><tr><td colspan="6" class="empty-state">Loading...</td></tr></tbody>
    </table></div>
  `;

  async function loadAccounts() {
    try {
      const accounts = await api.getAccounts();
      const tbody = document.getElementById("accounts-body");
      if (accounts.length === 0) {
        tbody.innerHTML = `<tr><td colspan="6" class="empty-state">No accounts</td></tr>`;
        return;
      }
      tbody.innerHTML = accounts.map((a) => `
        <tr>
          <td>${a.name}</td>
          <td>@${a.username}</td>
          <td><span class="badge badge-info" style="font-size:11px">${a.platform === "bluesky" ? "🦋 Bluesky" : "🐦 X"}</span></td>
          <td>
            <button class="btn btn-sm toggle-btn" data-id="${a.id}" data-active="${a.is_active}"
              style="background:${a.is_active ? "var(--success,#27ae60)" : "var(--danger,#e74c3c)"};color:#fff;min-width:64px">
              ${a.is_active ? "有効" : "停止中"}
            </button>
          </td>
          <td>${a.interval_minutes}分</td>
          <td>${new Date(a.created_at).toLocaleDateString()}</td>
          <td>
            <button class="btn btn-sm btn-primary verify-btn" data-id="${a.id}">Verify</button>
            <button class="btn btn-sm timeline-btn" data-id="${a.id}" data-username="${a.username}" style="background:var(--border)">Timeline</button>
            <button class="btn btn-sm edit-btn" data-id="${a.id}" style="background:var(--border)">Edit</button>
            <button class="btn btn-sm btn-danger delete-btn" data-id="${a.id}">Delete</button>
          </td>
        </tr>
      `).join("");

      tbody.querySelectorAll(".toggle-btn").forEach((btn) => {
        btn.onclick = async () => {
          const isActive = btn.dataset.active === "true";
          btn.textContent = "...";
          btn.disabled = true;
          try {
            await api.updateAccount(btn.dataset.id, { is_active: !isActive });
            loadAccounts();
          } catch {
            btn.textContent = isActive ? "有効" : "停止中";
            btn.disabled = false;
          }
        };
      });

      tbody.querySelectorAll(".verify-btn").forEach((btn) => {
        btn.onclick = async () => {
          btn.textContent = "...";
          try {
            const result = await api.verifyAccount(btn.dataset.id);
            btn.textContent = result.valid ? "Valid" : "Invalid";
          } catch {
            btn.textContent = "Error";
          }
        };
      });

      tbody.querySelectorAll(".timeline-btn").forEach((btn) => {
        btn.onclick = async () => {
          btn.textContent = "...";
          try {
            const { tweets } = await api.getAccountTimeline(btn.dataset.id);
            btn.textContent = "Timeline";
            const accountId = Number(btn.dataset.id);
            const username = btn.dataset.username;
            const tweetsHtml = tweets.length === 0
              ? `<div class="empty-state">ツイートがありません</div>`
              : tweets.map((t) => `
                <div style="padding:.6rem 0;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:flex-start;gap:.5rem">
                  <div style="flex:1;font-size:.9rem;word-break:break-all">${t.text || t.full_text || JSON.stringify(t)}</div>
                  <button class="btn btn-sm btn-danger del-tweet-btn" data-tweet-id="${t.id || t.id_str}" style="flex-shrink:0">削除</button>
                </div>`).join("");
            showModal(
              `@${username} のタイムライン`,
              `<div style="max-height:400px;overflow-y:auto">${tweetsHtml}</div>`,
              async () => {}
            );
            document.querySelectorAll(".del-tweet-btn").forEach((delBtn) => {
              delBtn.onclick = async (e) => {
                e.stopPropagation();
                if (!confirm("このツイートを削除しますか？")) return;
                delBtn.textContent = "...";
                try {
                  await api.deleteTweet(accountId, delBtn.dataset.tweetId);
                  delBtn.closest("div[style]").remove();
                } catch (err) {
                  alert("削除失敗: " + err.message);
                  delBtn.textContent = "削除";
                }
              };
            });
          } catch {
            btn.textContent = "Error";
          }
        };
      });

      tbody.querySelectorAll(".delete-btn").forEach((btn) => {
        btn.onclick = async () => {
          if (confirm("Delete this account?")) {
            await api.deleteAccount(btn.dataset.id);
            loadAccounts();
          }
        };
      });

      tbody.querySelectorAll(".edit-btn").forEach((btn) => {
        btn.onclick = () => {
          const account = accounts.find((a) => a.id === Number(btn.dataset.id));
          showModal("Edit Account", accountFormHtml(account), async () => {
            const data = {};
            const name = document.getElementById("f-name").value;
            const username = document.getElementById("f-username").value;
            const authToken = document.getElementById("f-auth-token").value;
            const ct0 = document.getElementById("f-ct0").value;
            const intervalMinutes = Number(document.getElementById("f-interval-minutes").value);
            const suffix = document.getElementById("f-tweet-suffix").value;
            if (name) data.name = name;
            if (username) data.username = username;
            if (authToken) data.auth_token = authToken;
            if (ct0) data.ct0 = ct0;
            data.interval_minutes = intervalMinutes > 0 ? intervalMinutes : 5;
            data.tweet_suffix = suffix || null;
            await api.updateAccount(account.id, data);
            loadAccounts();
          });
        };
      });
    } catch {
      document.getElementById("accounts-body").innerHTML =
        `<tr><td colspan="6" class="empty-state">Failed to load accounts</td></tr>`;
    }
  }

  document.getElementById("add-account").onclick = () => {
    showModal("Add Account", accountFormHtml(), async () => {
      const platform = document.getElementById("f-platform").value;
      const suffix = document.getElementById("f-tweet-suffix").value;
      const usernameEl = document.getElementById("f-username");
      await api.createAccount({
        name: document.getElementById("f-name").value,
        username: platform === "bluesky" ? document.getElementById("f-auth-token").value : (usernameEl?.value || ""),
        auth_token: document.getElementById("f-auth-token").value,
        ct0: document.getElementById("f-ct0").value,
        interval_minutes: Number(document.getElementById("f-interval-minutes").value) || 5,
        tweet_suffix: suffix || null,
        platform,
      });
      loadAccounts();
    });
  };

  loadAccounts();
}
