const launcherId = "ctxh-demo-launcher";
const sidebarHostId = "ctxh-demo-sidebar-host";

function removeExistingSidebar() {
  const existing = document.getElementById(sidebarHostId);
  if (existing) {
    existing.remove();
  }
}

function mountSidebar() {
  removeExistingSidebar();

  const host = document.createElement("div");
  host.id = sidebarHostId;
  host.style.position = "fixed";
  host.style.top = "0";
  host.style.right = "0";
  host.style.width = "420px";
  host.style.height = "100vh";
  host.style.zIndex = "2147483646";
  host.style.boxShadow = "rgba(7, 14, 28, 0.55) 0 0 0 1px, rgba(7, 14, 28, 0.7) 0 18px 48px";

  const iframe = document.createElement("iframe");
  iframe.title = "ContextHub Demo Sidebar";
  iframe.src = chrome.runtime.getURL("sidebar.html");
  iframe.style.width = "100%";
  iframe.style.height = "100%";
  iframe.style.border = "0";
  iframe.style.background = "#0e1730";

  host.appendChild(iframe);
  document.body.appendChild(host);

  chrome.runtime.sendMessage({ type: "ctxh:sidebar:opened" });
}

function ensureLauncher() {
  if (document.getElementById(launcherId)) {
    return;
  }

  const launcher = document.createElement("button");
  launcher.id = launcherId;
  launcher.textContent = "ContextHub";
  launcher.style.position = "fixed";
  launcher.style.right = "16px";
  launcher.style.bottom = "16px";
  launcher.style.padding = "10px 14px";
  launcher.style.border = "none";
  launcher.style.borderRadius = "999px";
  launcher.style.background = "#3558c9";
  launcher.style.color = "white";
  launcher.style.fontWeight = "700";
  launcher.style.cursor = "pointer";
  launcher.style.zIndex = "2147483647";
  launcher.style.boxShadow = "0 8px 24px rgba(12, 24, 56, 0.5)";

  launcher.addEventListener("click", () => {
    const host = document.getElementById(sidebarHostId);
    if (host) {
      host.remove();
      return;
    }
    mountSidebar();
  });

  document.body.appendChild(launcher);
}

function isClaudeHost() {
  return window.location.hostname === "claude.ai" || window.location.hostname === "www.claude.ai";
}

function start() {
  if (!isClaudeHost()) {
    return;
  }

  if (document.body) {
    ensureLauncher();
    return;
  }

  window.addEventListener(
    "DOMContentLoaded",
    () => {
      ensureLauncher();
    },
    { once: true }
  );
}

start();
