/**
 * Main application entry point.
 * SPA router and page loader for the Twitter Bot Manager.
 */

import { api } from "./api.js";
import { renderDashboard } from "./pages/dashboard.js";
import { renderAccounts } from "./pages/accounts.js";
import { renderRules } from "./pages/rules.js";
import { renderSchedule } from "./pages/schedule.js";
import { renderMonitor } from "./pages/monitor.js";
import { renderLogs } from "./pages/logs.js";

const routes = {
  dashboard: renderDashboard,
  accounts: renderAccounts,
  rules: renderRules,
  schedule: renderSchedule,
  monitors: renderMonitor,
  logs: renderLogs,
};

// Pages that don't filter by account
const globalPages = new Set(["accounts"]);

let currentPage = "dashboard";
let currentAccountId = null;

function navigate(page) {
  currentPage = page;
  const app = document.getElementById("app");
  const renderer = routes[page];
  if (!renderer) return;

  app.innerHTML = "";
  const accountId = globalPages.has(page) ? null : currentAccountId;
  renderer(app, accountId);

  document.querySelectorAll(".sidebar a").forEach((a) => {
    a.classList.toggle("active", a.dataset.page === page);
  });
}

async function initAccountSelector() {
  const selector = document.getElementById("account-selector");
  let accounts = [];
  try {
    accounts = await api.getAccounts();
  } catch {}

  if (accounts.length === 0) {
    selector.innerHTML = `<option value="">アカウントなし</option>`;
    currentAccountId = null;
  } else {
    selector.innerHTML = accounts
      .map((a) => `<option value="${a.id}">@${a.username}</option>`)
      .join("");
    currentAccountId = accounts[0].id;
    selector.value = currentAccountId;
  }

  selector.addEventListener("change", () => {
    currentAccountId = selector.value ? Number(selector.value) : null;
    navigate(currentPage);
  });
}

document.querySelectorAll(".sidebar a").forEach((link) => {
  link.addEventListener("click", (e) => {
    e.preventDefault();
    const page = link.dataset.page;
    window.location.hash = page;
    navigate(page);
  });
});

window.addEventListener("hashchange", () => {
  const page = window.location.hash.slice(1) || "dashboard";
  navigate(page);
});

// Init: load accounts first, then render initial page
(async () => {
  await initAccountSelector();
  const initialPage = window.location.hash.slice(1) || "dashboard";
  navigate(initialPage);
})();
