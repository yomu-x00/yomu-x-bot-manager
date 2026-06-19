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
import { renderTimeline } from "./pages/timeline.js";

const routes = {
  dashboard: renderDashboard,
  accounts: renderAccounts,
  rules: renderRules,
  schedule: renderSchedule,
  monitors: renderMonitor,
  logs: renderLogs,
  timeline: renderTimeline,
};

// Pages that don't filter by account
const globalPages = new Set(["accounts"]);

let currentPage = "dashboard";
let currentAccountId = null;

// ===== Mobile sidebar drawer =====
const sidebar = document.getElementById("sidebar");
const sidebarOverlay = document.getElementById("sidebar-overlay");
const mobileMenuBtn = document.getElementById("mobile-menu-btn");
const sidebarCloseBtn = document.getElementById("sidebar-close");

function openSidebar() {
  sidebar.classList.add("open");
  sidebarOverlay.classList.add("visible");
  document.body.style.overflow = "hidden";
}

function closeSidebar() {
  sidebar.classList.remove("open");
  sidebarOverlay.classList.remove("visible");
  document.body.style.overflow = "";
}

mobileMenuBtn?.addEventListener("click", openSidebar);
sidebarCloseBtn?.addEventListener("click", closeSidebar);
sidebarOverlay?.addEventListener("click", closeSidebar);

function navigate(page) {
  currentPage = page;
  closeSidebar();

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

// ===== Account selector (desktop sidebar + mobile header synced) =====
async function initAccountSelector() {
  const selector = document.getElementById("account-selector");
  const mobileSelector = document.getElementById("mobile-account-selector");

  let accounts = [];
  try { accounts = await api.getAccounts(); } catch {}

  const optionsHtml = accounts.length === 0
    ? `<option value="">アカウントなし</option>`
    : accounts.map((a) => `<option value="${a.id}">@${a.username}</option>`).join("");

  selector.innerHTML = optionsHtml;
  mobileSelector.innerHTML = optionsHtml;

  if (accounts.length > 0) {
    const saved = Number(localStorage.getItem("selectedAccountId"));
    currentAccountId = accounts.some((a) => a.id === saved) ? saved : accounts[0].id;
    selector.value = currentAccountId;
    mobileSelector.value = currentAccountId;
  } else {
    currentAccountId = null;
  }

  function onAccountChange(value) {
    currentAccountId = value ? Number(value) : null;
    if (currentAccountId) {
      localStorage.setItem("selectedAccountId", currentAccountId);
    } else {
      localStorage.removeItem("selectedAccountId");
    }
    selector.value = currentAccountId ?? "";
    mobileSelector.value = currentAccountId ?? "";
    navigate(currentPage);
  }

  selector.addEventListener("change", (e) => onAccountChange(e.target.value));
  mobileSelector.addEventListener("change", (e) => onAccountChange(e.target.value));
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
