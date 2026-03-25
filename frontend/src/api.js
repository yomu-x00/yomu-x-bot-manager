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
  deleteScheduledPost: (id) => request(`/schedule/${id}`, { method: "DELETE" }),

  // Monitors
  getMonitors: () => request("/monitors"),
  createMonitor: (data) => request("/monitors", { method: "POST", body: data }),

  // Logs & Stats
  getLogs: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/logs${qs ? `?${qs}` : ""}`);
  },
  getStats: () => request("/stats"),
};
