import { api } from "../api.js";

const CACHE_PREFIX = "timeline_cache_";
const CACHE_MAX = 200;

function cacheKey(accountId) {
  return `${CACHE_PREFIX}${accountId}`;
}

function loadCache(accountId) {
  try {
    const raw = localStorage.getItem(cacheKey(accountId));
    return raw ? JSON.parse(raw) : [];
  } catch { return []; }
}

function saveCache(accountId, tweets) {
  try {
    localStorage.setItem(cacheKey(accountId), JSON.stringify(tweets.slice(0, CACHE_MAX)));
  } catch {}
}

function mergeTweets(existing, incoming) {
  const map = new Map(existing.map((t) => [t.id, t]));
  for (const t of incoming) map.set(t.id, t);
  return [...map.values()].sort((a, b) => {
    const ta = a.createdAtISO || a.createdAt || "";
    const tb = b.createdAtISO || b.createdAt || "";
    return tb.localeCompare(ta);
  });
}

function showToast(msg, isError = false) {
  const t = document.createElement("div");
  t.textContent = msg;
  Object.assign(t.style, {
    position: "fixed", bottom: "24px", right: "24px", zIndex: "9999",
    padding: "12px 20px", borderRadius: "10px", fontWeight: "600", fontSize: "14px",
    background: isError ? "var(--danger)" : "var(--success)", color: "#fff",
    boxShadow: "0 4px 16px rgba(0,0,0,.4)", transition: "opacity .3s",
  });
  document.body.appendChild(t);
  setTimeout(() => { t.style.opacity = "0"; setTimeout(() => t.remove(), 300); }, 3000);
}

function tweetCardHtml(t, accountId) {
  const text = (t.text || t.full_text || "").replace(/\n/g, "<br>");
  const tweetId = t.id || t.id_str || "";
  const time = t.createdAtLocal || (t.createdAtISO ? new Date(t.createdAtISO).toLocaleString("ja-JP") : "");
  const metrics = t.metrics || {};
  const likes = metrics.likes ?? t.favorite_count ?? "";
  const rts = metrics.retweets ?? t.retweet_count ?? "";
  const replies = metrics.replies ?? "";
  const views = metrics.views || "";

  const mediaHtml = (t.media || []).map((m) => {
    if (m.type === "photo" || m.url) {
      const src = m.url || m.media_url_https || m.media_url || "";
      return src ? `<img src="${src}" style="max-width:100%;max-height:400px;border-radius:12px;display:block;margin-top:8px;object-fit:cover">` : "";
    }
    if (m.type === "video" || m.type === "animated_gif") {
      const src = m.url || (m.variants && m.variants[0]?.url) || "";
      return src ? `<video src="${src}" controls style="max-width:100%;border-radius:12px;margin-top:8px"></video>` : "";
    }
    return "";
  }).join("");

  const author = t.author || {};
  const avatar = author.profileImageUrl || "";
  const name = author.name || "";
  const screen = author.screenName || "";

  return `
    <div class="card tweet-card" data-tweet-id="${tweetId}" style="margin-bottom:12px;padding:16px">
      <div style="display:flex;gap:12px">
        ${avatar ? `<img src="${avatar}" style="width:40px;height:40px;border-radius:50%;flex-shrink:0;object-fit:cover">` : `<div style="width:40px;height:40px;border-radius:50%;background:var(--border);flex-shrink:0"></div>`}
        <div style="flex:1;min-width:0">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px">
            <div>
              ${name ? `<span style="font-weight:700;font-size:15px">${name}</span>` : ""}
              ${screen ? `<span style="color:var(--text-secondary);font-size:13px;margin-left:4px">@${screen}</span>` : ""}
            </div>
            <button class="btn btn-sm btn-danger del-tweet" data-tweet-id="${tweetId}" style="flex-shrink:0;font-size:11px;padding:3px 8px">削除</button>
          </div>
          <div style="margin-top:6px;line-height:1.6;word-break:break-word;white-space:pre-wrap;font-size:15px">${text}</div>
          ${mediaHtml}
          <div style="margin-top:10px;display:flex;gap:20px;color:var(--text-secondary);font-size:13px;flex-wrap:wrap">
            ${time ? `<span>${time}</span>` : ""}
            ${likes !== "" ? `<span>♥ ${likes}</span>` : ""}
            ${rts !== "" ? `<span>🔁 ${rts}</span>` : ""}
            ${replies !== "" ? `<span>💬 ${replies}</span>` : ""}
            ${views ? `<span>👁 ${views}</span>` : ""}
          </div>
        </div>
      </div>
    </div>`;
}

function renderTweets(listEl, tweets, accountId, onDelete) {
  if (tweets.length === 0) {
    listEl.innerHTML = `<div class="empty-state">ツイートがありません</div>`;
    return;
  }
  listEl.innerHTML = tweets.map((t) => tweetCardHtml(t, accountId)).join("");
  listEl.querySelectorAll(".del-tweet").forEach((btn) => {
    btn.onclick = async () => {
      if (!confirm("このツイートを削除しますか？")) return;
      btn.disabled = true;
      btn.textContent = "...";
      try {
        await api.deleteTweet(accountId, btn.dataset.tweetId);
        btn.closest(".tweet-card").remove();
        onDelete(btn.dataset.tweetId);
        showToast("削除しました");
      } catch (err) {
        btn.disabled = false;
        btn.textContent = "削除";
        alert("削除に失敗しました: " + err.message);
      }
    };
  });
}

function showTestTweetModal(accountId, onPosted) {
  const overlay = document.createElement("div");
  overlay.className = "modal-overlay";
  overlay.innerHTML = `
    <div class="modal">
      <h3>テスト投稿</h3>
      <div class="form-group">
        <label>投稿テキスト</label>
        <textarea id="test-tweet-text" rows="4" placeholder="テスト投稿です" style="font-size:14px"></textarea>
      </div>
      <div class="modal-actions">
        <button class="btn" id="test-cancel">キャンセル</button>
        <button class="btn btn-primary" id="test-submit">投稿する</button>
      </div>
    </div>`;
  document.body.appendChild(overlay);
  overlay.querySelector("#test-tweet-text").focus();
  overlay.querySelector("#test-cancel").onclick = () => overlay.remove();
  overlay.addEventListener("click", (e) => { if (e.target === overlay) overlay.remove(); });
  overlay.querySelector("#test-submit").onclick = async () => {
    const text = overlay.querySelector("#test-tweet-text").value.trim();
    if (!text) { alert("テキストを入力してください"); return; }
    const btn = overlay.querySelector("#test-submit");
    btn.disabled = true;
    btn.textContent = "投稿中...";
    try {
      const result = await api.postTweet(accountId, text);
      overlay.remove();
      const tweetId = result?.tweet?.id || result?.tweet?.id_str || "";
      showToast(`投稿しました${tweetId ? `（tweet_id: ${tweetId}）` : ""}`);
      if (onPosted) onPosted();
    } catch (err) {
      btn.disabled = false;
      btn.textContent = "投稿する";
      alert("投稿に失敗しました: " + err.message);
    }
  };
}

export async function renderTimeline(container, accountId) {
  container.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px">
      <h2>Timeline</h2>
      <div style="display:flex;gap:8px;align-items:center">
        <span id="cache-status" style="font-size:12px;color:var(--text-secondary)"></span>
        <button class="btn" id="refresh-btn" style="background:var(--border)">更新</button>
        <button class="btn btn-primary" id="test-tweet-btn">テスト投稿</button>
      </div>
    </div>
    <div id="timeline-list"></div>`;

  const listEl = document.getElementById("timeline-list");
  const statusEl = document.getElementById("cache-status");

  document.getElementById("test-tweet-btn").onclick = () => {
    if (!accountId) { alert("アカウントを選択してください"); return; }
    showTestTweetModal(accountId, () => fetchAndMerge(20));
  };

  if (!accountId) {
    listEl.innerHTML = `<div class="empty-state">アカウントを選択してください</div>`;
    return;
  }

  let currentTweets = loadCache(accountId);

  function onDelete(tweetId) {
    currentTweets = currentTweets.filter((t) => t.id !== tweetId);
    saveCache(accountId, currentTweets);
  }

  // キャッシュがあれば即表示
  if (currentTweets.length > 0) {
    renderTweets(listEl, currentTweets, accountId, onDelete);
    statusEl.textContent = `キャッシュ ${currentTweets.length} 件`;
  } else {
    listEl.innerHTML = `<div class="empty-state">読み込み中...</div>`;
  }

  async function fetchAndMerge(count = 20) {
    statusEl.textContent = "取得中...";
    document.getElementById("refresh-btn").disabled = true;
    try {
      const resp = await api.getAccountTimeline(accountId, count);
      const raw = resp.tweets;
      const incoming = Array.isArray(raw) ? raw : (raw?.data ?? []);
      const before = currentTweets.length;
      currentTweets = mergeTweets(currentTweets, incoming);
      saveCache(accountId, currentTweets);
      renderTweets(listEl, currentTweets, accountId, onDelete);
      const added = currentTweets.length - before;
      statusEl.textContent = added > 0
        ? `${added} 件追加（計 ${currentTweets.length} 件）`
        : `最新（計 ${currentTweets.length} 件）`;
    } catch (err) {
      statusEl.textContent = "取得失敗";
      if (currentTweets.length === 0) {
        listEl.innerHTML = `<div class="empty-state">読み込みに失敗しました: ${err.message}</div>`;
      }
    } finally {
      document.getElementById("refresh-btn").disabled = false;
    }
  }

  document.getElementById("refresh-btn").onclick = () => fetchAndMerge(20);

  // 初回はバックグラウンドで最新20件取得（初訪問なら50件）
  fetchAndMerge(currentTweets.length === 0 ? 50 : 20);
}
