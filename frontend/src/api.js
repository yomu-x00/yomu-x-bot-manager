/**
 * API client for communicating with the FastAPI backend.
 */

const BASE = "/api";

async function request(path, options = {}) {
  const url = `${BASE}${path}`;
  const config = {
    headers: { "Content-Type": "application/json" },
    ...options,
  };

  if (config.body && typeof config.body === "object") {
    config.body = JSON.stringify(config.body);
  }

  const resp = await fetch(url, config);

  if (resp.status === 204) return null;

  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new Error(err.detail || "API error");
  }

  return resp.json();
}

export const api = {
  // Accounts
  getAccounts: () => request("/accounts"),
  createAccount: (data) => request("/accounts", { method: "POST", body: data }),
  updateAccount: (id, data) => request(`/accounts/${id}`, { method: "PUT", body: data }),
  deleteAccount: (id) => request(`/accounts/${id}`, { method: "DELETE" }),
  verifyAccount: (id) => request(`/accounts/${id}/verify`, { method: "POST" }),
  cookieHealth: () => request("/accounts/cookie-health"),
  getAccountTimeline: (accountId, count = 20) => request(`/accounts/${accountId}/timeline?count=${count}`),
  deleteTweet: (accountId, tweetId) => request(`/accounts/${accountId}/tweets/${tweetId}`, { method: "DELETE" }),
  pinTweet: (accountId, tweetId) => request(`/accounts/${accountId}/tweets/${tweetId}/pin`, { method: "POST" }),
  unpinTweet: (accountId, tweetId) => request(`/accounts/${accountId}/tweets/${tweetId}/pin`, { method: "DELETE" }),
  postTweet: (accountId, text) => request(`/accounts/${accountId}/tweet`, { method: "POST", body: { text } }),

  // Rules
  getRules: (accountId) => request(`/rules${accountId ? `?account_id=${accountId}` : ""}`),
  createRule: (data) => request("/rules", { method: "POST", body: data }),
  updateRule: (id, data) => request(`/rules/${id}`, { method: "PUT", body: data }),
  deleteRule: (id) => request(`/rules/${id}`, { method: "DELETE" }),
  toggleRule: (id) => request(`/rules/${id}/toggle`, { method: "POST" }),
  runRule: (id) => request(`/rules/${id}/run`, { method: "POST" }),

  // Schedule
  getScheduledPosts: (status) => request(`/schedule${status ? `?status=${status}` : ""}`),
  createScheduledPost: (data) => request("/schedule", { method: "POST", body: data }),
  bulkCreateScheduledPosts: (posts) => request("/schedule/bulk", { method: "POST", body: posts }),
  bulkScheduleImages: (data) => request("/schedule/bulk-images", { method: "POST", body: data }),
  deleteScheduledPost: (id) => request(`/schedule/${id}`, { method: "DELETE" }),
  postNow: (id) => request(`/schedule/${id}/post-now`, { method: "POST" }),
  retryPost: (id) => request(`/schedule/${id}/retry`, { method: "POST" }),
  uploadImage: async (file) => {
    const form = new FormData();
    form.append("file", file);
    const resp = await fetch("/api/uploads", { method: "POST", body: form });
    if (!resp.ok) throw new Error("Upload failed");
    return resp.json();
  },

  // Monitors
  getMonitors: () => request("/monitors"),
  createMonitor: (data) => request("/monitors", { method: "POST", body: data }),

  // Logs & Stats
  getLogs: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/logs${qs ? `?${qs}` : ""}`);
  },
  getStats: (accountId) => request(`/stats${accountId ? `?account_id=${accountId}` : ""}`),
};
