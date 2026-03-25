/**
 * Main application entry point.
 * SPA router and page loader for the Twitter Bot Manager.
 */

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

function navigate(page) {
  const app = document.getElementById("app");
  const renderer = routes[page];
  if (!renderer) return;

  app.innerHTML = "";
  renderer(app);

  // Update active nav link
  document.querySelectorAll(".sidebar a").forEach((a) => {
    a.classList.toggle("active", a.dataset.page === page);
  });
}

// Handle navigation clicks
document.querySelectorAll(".sidebar a").forEach((link) => {
  link.addEventListener("click", (e) => {
    e.preventDefault();
    const page = link.dataset.page;
    window.location.hash = page;
    navigate(page);
  });
});

// Handle hash changes
window.addEventListener("hashchange", () => {
  const page = window.location.hash.slice(1) || "dashboard";
  navigate(page);
});

// Initial render
const initialPage = window.location.hash.slice(1) || "dashboard";
navigate(initialPage);
