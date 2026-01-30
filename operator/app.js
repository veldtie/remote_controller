(() => {
  "use strict";

  const CONTROL_ACTION = "control";
  const CONTROL_TYPES = {
    mouseMove: "mouse_move",
    mouseClick: "mouse_click",
    keypress: "keypress",
    text: "text"
  };
  const E2EE_STORAGE_KEY = "rc_e2ee_passphrase";
  const PANEL_COLLAPSED_KEY = "rc_panel_collapsed";
  const E2EE_PBKDF2_ITERS = 150000;
  const E2EE_SALT_PREFIX = "remote-controller:";
  const CONTROL_MOVE_INTERVAL_MS = 33;
  const STORAGE_TIMEOUT_MS = 10000;
  const STREAM_HINT_DEBOUNCE_MS = 250;
  const STREAM_HINT_THRESHOLD = 40;
  const NETWORK_STATS_INTERVAL_MS = 2000;
  const NETWORK_ADAPT_COOLDOWN_MS = 4000;
  const NETWORK_BPP = 0.1;
  const LOSS_DEGRADE = 0.12;
  const LOSS_UPGRADE = 0.01;
  const RTT_DEGRADE = 450;
  const RTT_UPGRADE = 180;
  const PROFILE_HEIGHT_DOWN_SCALE = 0.92;
  const PROFILE_HEIGHT_UP_SCALE = 1.15;
  const SIGNALING_PING_INTERVAL_MS = 20000;
  const DEFAULT_ICE_SERVERS = [
    { urls: ["stun:stun.l.google.com:19302"] },
    { urls: ["stun:stun1.l.google.com:19302"] },
    { urls: ["stun:stun.cloudflare.com:3478"] }
  ];
  const textEncoder = typeof TextEncoder !== "undefined" ? new TextEncoder() : null;
  const textDecoder = typeof TextDecoder !== "undefined" ? new TextDecoder() : null;

  function utf8Encode(value) {
    if (textEncoder) {
      return textEncoder.encode(value);
    }
    const encoded = unescape(encodeURIComponent(value));
    const bytes = new Uint8Array(encoded.length);
    for (let i = 0; i < encoded.length; i += 1) {
      bytes[i] = encoded.charCodeAt(i);
    }
    return bytes;
  }

  function utf8Decode(value) {
    if (textDecoder) {
      return textDecoder.decode(value);
    }
    let bytes = null;
    if (value instanceof ArrayBuffer) {
      bytes = new Uint8Array(value);
    } else if (ArrayBuffer.isView(value)) {
      bytes = new Uint8Array(value.buffer, value.byteOffset, value.byteLength);
    } else if (typeof value === "string") {
      return value;
    } else if (value === null || value === undefined) {
      return "";
    } else {
      return String(value);
    }
    let binary = "";
    for (let i = 0; i < bytes.length; i += 1) {
      binary += String.fromCharCode(bytes[i]);
    }
    try {
      return decodeURIComponent(escape(binary));
    } catch (error) {
      return binary;
    }
  }

  const STREAM_PROFILES = {
    speed: { minHeight: 720, maxHeight: 1080, minFps: 40, maxFps: 60 },
    balanced: { minHeight: 900, maxHeight: 1440, minFps: 30, maxFps: 60 },
    quality: { minHeight: 1080, maxHeight: 2160, minFps: 30, maxFps: 60 },
    reading: { minHeight: 1440, maxHeight: 2160, minFps: 10, maxFps: 20 }
  };

  const state = {
    operatorId:
      typeof crypto !== "undefined" && crypto.randomUUID
        ? crypto.randomUUID()
        : `operator-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    peerConnection: null,
    controlChannel: null,
    signalingWebSocket: null,
    connecting: false,
    storageAutostart: false,
    rtcConfig: { iceServers: [] },
    controlEnabled: true,
    modeLocked: false,
    controlsBound: false,
    remoteCurrentPath: ".",
    pendingDownload: null,
    pendingAppLaunch: null,
    isConnected: false,
    e2eeContext: null,
    cursorX: 0,
    cursorY: 0,
    cursorLocked: false,
    cursorInitialized: false,
    cursorBounds: { width: 0, height: 0 },
    pendingMove: null,
    pendingDelta: null,
    lastMoveSentAt: 0,
    moveTimer: null,
    lastSentPosition: null,
    storageTimer: null,
    streamProfile: "quality",
    streamHintTimer: null,
    lastStreamHint: null,
    statsTimer: null,
    netStats: null,
    netTargetHeight: null,
    netTargetFps: null,
    netLastAdaptAt: 0,
    networkHint: { height: null, fps: null },
    iceErrorCount: 0,
    iceFallbackTried: false,
    signalingPingTimer: null,
    panelCollapsed: false,
    textInputSupported: true,
    screenAspect: null
  };

  const dom = {
    statusEl: document.getElementById("status"),
    serverUrlInput: document.getElementById("serverUrl"),
    sessionIdInput: document.getElementById("sessionId"),
    authTokenInput: document.getElementById("authToken"),
    e2eeKeyInput: document.getElementById("e2eeKey"),
    interactionToggle: document.getElementById("interactionToggle"),
    interactionState: document.getElementById("interactionState"),
    modeBadge: document.getElementById("modeBadge"),
    storageToggle: document.getElementById("storageToggle"),
    storageClose: document.getElementById("storageClose"),
    storageDrawer: document.getElementById("storageDrawer"),
    appStatus: document.getElementById("appStatus"),
    appButtons: Array.from(document.querySelectorAll("[data-app]")),
    cookieStatus: document.getElementById("cookieStatus"),
    cookieButtons: Array.from(document.querySelectorAll("[data-cookie]")),
    remotePathInput: document.getElementById("remotePathInput"),
    remoteFileList: document.getElementById("remoteFileList"),
    remoteStatus: document.getElementById("remoteStatus"),
    downloadStatus: document.getElementById("downloadStatus"),
    downloadList: document.getElementById("downloadList"),
    screenFrame: document.getElementById("screenFrame"),
    screenEl: document.getElementById("screen"),
    panelToggle: document.getElementById("panelToggle"),
    fullscreenToggle: document.getElementById("fullscreenToggle"),
    connectButton: document.getElementById("connectButton"),
    remoteGo: document.getElementById("remoteGo"),
    remoteUp: document.getElementById("remoteUp"),
    remoteRefresh: document.getElementById("remoteRefresh"),
    manageOnly: Array.from(document.querySelectorAll("[data-requires-manage]")),
    streamProfile: document.getElementById("streamProfile"),
    cursorOverlay: null
  };

  const KEY_MAP = {
    Enter: "enter",
    Backspace: "backspace",
    Tab: "tab",
    Escape: "esc",
    " ": "space",
    ArrowLeft: "left",
    ArrowRight: "right",
    ArrowUp: "up",
    ArrowDown: "down",
    Delete: "delete",
    Home: "home",
    End: "end",
    PageUp: "pageup",
    PageDown: "pagedown",
    Insert: "insert"
  };

  function initDefaults() {
    if (!dom.serverUrlInput.value) {
      if (window.location.protocol.startsWith("http")) {
        dom.serverUrlInput.value = window.location.origin;
      } else {
        dom.serverUrlInput.value = "http://localhost:8000";
      }
    }
    if (dom.e2eeKeyInput) {
      const storedPassphrase = sessionStorage.getItem(E2EE_STORAGE_KEY);
      if (!dom.e2eeKeyInput.value && storedPassphrase) {
        dom.e2eeKeyInput.value = storedPassphrase;
      }
    }
    if (dom.streamProfile) {
      applyStreamProfile(dom.streamProfile.value, false);
    }
    ensureCursorOverlay();
    restorePanelState();
    updatePanelToggleLabel();
    updateFullscreenToggleLabel();
  }

  function applyUrlParams() {
    const params = new URLSearchParams(window.location.search);
    const desktopFlag = (params.get("desktop") || params.get("embedded") || "").toLowerCase();
    if (desktopFlag === "1" || desktopFlag === "true" || desktopFlag === "yes" || desktopFlag === "on") {
      document.body.classList.add("desktop-mode");
    }
    const serverUrl =
      params.get("server") ||
      params.get("server_url") ||
      params.get("api_url") ||
      params.get("url");
    if (serverUrl) {
      dom.serverUrlInput.value = serverUrl;
    }

    const sessionId =
      params.get("session_id") ||
      params.get("session") ||
      params.get("id");
    if (sessionId) {
      dom.sessionIdInput.value = sessionId;
    }

    const token =
      params.get("token") ||
      params.get("auth_token") ||
      params.get("api_token");
    if (token) {
      dom.authTokenInput.value = token;
    }

    const e2eeKey =
      params.get("e2ee") ||
      params.get("e2ee_key") ||
      params.get("key");
    if (e2eeKey && dom.e2eeKeyInput) {
      dom.e2eeKeyInput.value = e2eeKey;
      sessionStorage.setItem(E2EE_STORAGE_KEY, e2eeKey);
    }

    const mode = (params.get("mode") || "").toLowerCase();
    if (mode === "view") {
      dom.interactionToggle.checked = false;
    } else if (mode === "manage") {
      dom.interactionToggle.checked = true;
    }

    const storage = (params.get("storage") || "").toLowerCase();
    state.storageAutostart =
      storage === "1" || storage === "true" || storage === "yes" || storage === "open";

    const streamProfile = (params.get("stream") || params.get("quality") || "").toLowerCase();
    if (streamProfile && dom.streamProfile) {
      applyStreamProfile(streamProfile, false);
    }

    const autoConnect =
      params.get("autoconnect") ||
      params.get("connect") ||
      params.get("auto");
    if (!autoConnect) {
      return false;
    }
    const normalized = autoConnect.toLowerCase();
    return normalized !== "0" && normalized !== "false" && normalized !== "no";
  }

  function bootstrapFromPayload(payload) {
    if (!payload || typeof payload !== "object") {
      return;
    }
    if (payload.desktop) {
      document.body.classList.add("desktop-mode");
    }
    const setValue = (id, value) => {
      const el = document.getElementById(id);
      if (!el) return;
      if (value) {
        el.value = value;
        el.dispatchEvent(new Event("input", { bubbles: true }));
      }
    };
    setValue("serverUrl", payload.serverUrl);
    setValue("sessionId", payload.sessionId);
    setValue("authToken", payload.token);
    if (payload.stream && dom.streamProfile) {
      applyStreamProfile(payload.stream, false);
    }
    if (payload.manage && dom.interactionToggle && !dom.interactionToggle.checked) {
      dom.interactionToggle.checked = true;
      dom.interactionToggle.dispatchEvent(new Event("change", { bubbles: true }));
    }
    if (payload.openStorage) {
      toggleStorage(true);
    }
    if (payload.autoConnect) {
      setTimeout(() => void connect(), 50);
    }
  }

  function setStatus(message, stateKey = "") {
    dom.statusEl.textContent = message;
    dom.statusEl.dataset.state = stateKey;
  }

  function reportScriptError(message) {
    if (dom.statusEl) {
      setStatus(message, "bad");
    }
    console.error(message);
  }

  window.addEventListener("error", (event) => {
    if (!event) {
      return;
    }
    const message = event.message || "Unexpected script error";
    reportScriptError(`Script error: ${message}`);
  });

  window.addEventListener("unhandledrejection", (event) => {
    if (!event) {
      return;
    }
    const reason = event.reason && event.reason.message ? event.reason.message : event.reason;
    reportScriptError(`Script error: ${reason || "Unhandled rejection"}`);
  });

  function setRemoteStatus(message, stateKey = "") {
    dom.remoteStatus.textContent = message;
    dom.remoteStatus.dataset.state = stateKey;
  }

  function clearStorageTimeout() {
    if (state.storageTimer) {
      clearTimeout(state.storageTimer);
      state.storageTimer = null;
    }
  }

  function setDownloadStatus(message, stateKey = "") {
    dom.downloadStatus.textContent = message;
    dom.downloadStatus.dataset.state = stateKey;
  }

  function setAppStatus(message, stateKey = "") {
    if (!dom.appStatus) {
      return;
    }
    dom.appStatus.textContent = message;
    dom.appStatus.dataset.state = stateKey;
  }

  function setCookieStatus(message, stateKey = "") {
    if (!dom.cookieStatus) {
      return;
    }
    dom.cookieStatus.textContent = message;
    dom.cookieStatus.dataset.state = stateKey;
  }

  function updateAppLaunchAvailability() {
    const enabled = state.isConnected && state.controlEnabled;
    dom.appButtons.forEach((button) => {
      button.disabled = !enabled;
    });
    if (!enabled) {
      if (!state.isConnected) {
        setAppStatus("Connect to launch apps", "warn");
      } else {
        setAppStatus("Switch to manage mode to launch apps", "warn");
      }
    } else {
      setAppStatus("Ready", "");
    }
  }

  function updateCookieAvailability() {
    const enabled = state.isConnected && state.controlEnabled;
    dom.cookieButtons.forEach((button) => {
      button.disabled = !enabled;
    });
    if (!dom.cookieStatus) {
      return;
    }
    if (!enabled) {
      if (!state.isConnected) {
        setCookieStatus("Connect to export cookies", "warn");
      } else {
        setCookieStatus("Switch to manage mode to export cookies", "warn");
      }
    } else {
      setCookieStatus("Ready", "");
    }
  }

  function setModeLocked(locked) {
    state.modeLocked = locked;
    dom.interactionToggle.disabled = locked;
    dom.interactionToggle.setAttribute("aria-disabled", locked.toString());
  }

  function setConnected(connected) {
    state.isConnected = connected;
    if (!connected) {
      setRemoteStatus("Not connected", "warn");
      clearStorageTimeout();
      if (state.streamHintTimer) {
        clearTimeout(state.streamHintTimer);
        state.streamHintTimer = null;
      }
      state.lastStreamHint = null;
      stopStatsMonitor();
    }
    updateAppLaunchAvailability();
    updateCookieAvailability();
    updateCursorOverlayVisibility();
  }

  function applyStreamProfile(profile, shouldSend = true) {
    const normalized = (profile || "").toLowerCase();
    const allowed = new Set(["speed", "balanced", "quality", "reading"]);
    const next = allowed.has(normalized) ? normalized : "balanced";
    state.streamProfile = next;
    if (dom.streamProfile && dom.streamProfile.value !== next) {
      dom.streamProfile.value = next;
    }
    state.netTargetHeight = null;
    state.netTargetFps = null;
    state.netStats = null;
    state.networkHint = { height: null, fps: null };
    state.lastStreamHint = null;
    if (shouldSend && state.isConnected) {
      void sendStreamProfile(next);
      scheduleStreamHint();
    }
  }

  function updateInteractionMode() {
    state.controlEnabled = dom.interactionToggle.checked;
    const label = state.controlEnabled ? "Managing" : "Viewing";
    dom.interactionState.textContent = label;
    dom.modeBadge.textContent = state.controlEnabled ? "Manage mode" : "View only";
    document.body.classList.toggle("manage-mode", state.controlEnabled);
    document.body.classList.toggle("view-mode", !state.controlEnabled);
    updateAppLaunchAvailability();
    updateCookieAvailability();
    const disableManage = !state.controlEnabled;
    dom.manageOnly.forEach((section) => {
      section.classList.toggle("disabled", disableManage);
      section
        .querySelectorAll("button, input, select, textarea")
        .forEach((control) => {
          control.disabled = disableManage;
          control.setAttribute("aria-disabled", disableManage.toString());
        });
    });
    if (!state.controlEnabled) {
      releasePointerLock();
    }
    updateCursorOverlayVisibility();
  }

  function releasePointerLock() {
    if (document.pointerLockElement === dom.screenFrame) {
      document.exitPointerLock();
    }
  }

  function clamp(value, min, max) {
    return Math.min(Math.max(value, min), max);
  }

  function getProfileBounds(profile) {
    return STREAM_PROFILES[profile] || STREAM_PROFILES.balanced;
  }

  function computeExpectedBitrateKbps(height, fps, aspectRatio) {
    if (!height || !fps) {
      return null;
    }
    const width = Math.max(1, Math.round(height * aspectRatio));
    return (width * height * fps * NETWORK_BPP) / 1000;
  }

  function buildStreamHint() {
    const base = getStreamHintSize();
    if (!base) {
      return null;
    }
    let width = base.width;
    let height = base.height;
    if (state.networkHint && state.networkHint.height && height > state.networkHint.height) {
      const ratio = state.networkHint.height / height;
      height = state.networkHint.height;
      width = Math.round(width * ratio);
    }
    const fps = state.networkHint ? state.networkHint.fps : null;
    return { width, height, fps };
  }

  function getVideoMetrics() {
    const rect = dom.screenFrame.getBoundingClientRect();
    const videoWidth = dom.screenEl.videoWidth || rect.width;
    const videoHeight = dom.screenEl.videoHeight || rect.height;
    if (!videoWidth || !videoHeight || !rect.width || !rect.height) {
      return null;
    }
    const scale = Math.min(rect.width / videoWidth, rect.height / videoHeight);
    const renderWidth = videoWidth * scale;
    const renderHeight = videoHeight * scale;
    const offsetX = (rect.width - renderWidth) / 2;
    const offsetY = (rect.height - renderHeight) / 2;
    return {
      rect,
      videoWidth,
      videoHeight,
      renderWidth,
      renderHeight,
      offsetX,
      offsetY
    };
  }

  function updateScreenLayout() {
    updateScreenFrameBounds();
    const metrics = getVideoMetrics();
    if (!metrics) {
      dom.screenEl.style.width = "100%";
      dom.screenEl.style.height = "100%";
      return;
    }
    dom.screenEl.style.width = `${Math.floor(metrics.renderWidth)}px`;
    dom.screenEl.style.height = `${Math.floor(metrics.renderHeight)}px`;
    updateCursorOverlayPosition();
    scheduleStreamHint();
  }

  function getWorkspaceBounds() {
    const style = getComputedStyle(document.documentElement);
    const edgeGap = Number.parseFloat(style.getPropertyValue("--edge-gap")) || 16;
    const workspaceLeft =
      Number.parseFloat(style.getPropertyValue("--workspace-left")) || 320;
    const workspaceBottom =
      Number.parseFloat(style.getPropertyValue("--workspace-bottom")) || 120;
    const availableWidth = Math.max(0, window.innerWidth - workspaceLeft - edgeGap);
    const availableHeight = Math.max(
      0,
      window.innerHeight - workspaceBottom - edgeGap * 2
    );
    return {
      edgeGap,
      workspaceLeft,
      workspaceBottom,
      availableWidth,
      availableHeight
    };
  }

  function updateScreenFrameBounds() {
    if (!dom.screenFrame) {
      return;
    }
    if (document.fullscreenElement === dom.screenFrame) {
      dom.screenFrame.style.left = "0px";
      dom.screenFrame.style.top = "0px";
      dom.screenFrame.style.width = "100%";
      dom.screenFrame.style.height = "100%";
      dom.screenFrame.style.right = "0px";
      dom.screenFrame.style.bottom = "0px";
      return;
    }
    const { edgeGap, workspaceLeft, availableWidth, availableHeight } =
      getWorkspaceBounds();
    if (!availableWidth || !availableHeight) {
      return;
    }
    const aspect = state.screenAspect || 16 / 9;
    let width = availableWidth;
    let height = width / aspect;
    if (height > availableHeight) {
      height = availableHeight;
      width = height * aspect;
    }
    const left = workspaceLeft + (availableWidth - width) / 2;
    const top = edgeGap + (availableHeight - height) / 2;
    dom.screenFrame.style.left = `${Math.round(left)}px`;
    dom.screenFrame.style.top = `${Math.round(top)}px`;
    dom.screenFrame.style.width = `${Math.round(width)}px`;
    dom.screenFrame.style.height = `${Math.round(height)}px`;
    dom.screenFrame.style.right = "auto";
    dom.screenFrame.style.bottom = "auto";
  }

  function ensureCursorOverlay() {
    if (!dom.screenFrame) {
      return;
    }
    let cursor = dom.screenFrame.querySelector("#operatorCursor");
    if (!cursor) {
      cursor = document.createElement("div");
      cursor.id = "operatorCursor";
      cursor.setAttribute("aria-hidden", "true");
      dom.screenFrame.appendChild(cursor);
    }
    dom.cursorOverlay = cursor;
    updateCursorOverlayVisibility();
    updateCursorOverlayPosition();
  }

  function updatePanelToggleLabel() {
    if (!dom.panelToggle) {
      return;
    }
    dom.panelToggle.textContent = state.panelCollapsed ? "Restore" : "Minimize";
  }

  function updateFullscreenToggleLabel() {
    if (!dom.fullscreenToggle) {
      return;
    }
    const active = document.fullscreenElement === dom.screenFrame;
    dom.fullscreenToggle.textContent = active ? "Exit Fullscreen" : "Fullscreen";
  }

  function setPanelCollapsed(collapsed) {
    state.panelCollapsed = collapsed;
    document.body.classList.toggle("panel-collapsed", collapsed);
    updatePanelToggleLabel();
    updateScreenLayout();
  }

  function togglePanelCollapsed(force) {
    releasePointerLock();
    const next = typeof force === "boolean" ? force : !state.panelCollapsed;
    setPanelCollapsed(next);
    try {
      localStorage.setItem(PANEL_COLLAPSED_KEY, next ? "1" : "0");
    } catch (error) {
      /* ignore */
    }
  }

  function restorePanelState() {
    try {
      const stored = localStorage.getItem(PANEL_COLLAPSED_KEY);
      if (stored === "1") {
        setPanelCollapsed(true);
      }
    } catch (error) {
      /* ignore */
    }
  }

  function toggleFullscreen() {
    if (!dom.screenFrame) {
      return;
    }
    releasePointerLock();
    if (document.fullscreenElement === dom.screenFrame) {
      document.exitFullscreen?.();
      return;
    }
    if (dom.screenFrame.requestFullscreen) {
      dom.screenFrame.requestFullscreen().catch(() => {
        setStatus("Fullscreen blocked", "warn");
      });
    }
  }

  function updateCursorOverlayVisibility() {
    if (!dom.cursorOverlay) {
      return;
    }
    const shouldShow = state.isConnected && state.controlEnabled;
    dom.cursorOverlay.style.display = shouldShow ? "block" : "none";
  }

  function updateCursorOverlayPosition() {
    if (!dom.cursorOverlay || !state.cursorInitialized) {
      return;
    }
    const metrics = getVideoMetrics();
    if (!metrics) {
      return;
    }
    const x =
      metrics.offsetX + (state.cursorX / metrics.videoWidth) * metrics.renderWidth;
    const y =
      metrics.offsetY + (state.cursorY / metrics.videoHeight) * metrics.renderHeight;
    dom.cursorOverlay.style.left = `${Math.round(x)}px`;
    dom.cursorOverlay.style.top = `${Math.round(y)}px`;
  }

  function mapMouseButton(button) {
    if (button === 1) {
      return "middle";
    }
    if (button === 2) {
      return "right";
    }
    return "left";
  }

  function normalizeKeyEvent(event) {
    if (!event) {
      return null;
    }
    const key = event.key || "";
    if (!event.ctrlKey && !event.metaKey && !event.altKey && key.length === 1) {
      if (state.textInputSupported) {
        return { type: CONTROL_TYPES.text, text: key };
      }
      return { type: CONTROL_TYPES.keypress, key };
    }
    if (key === "Shift" || key === "Control" || key === "Alt" || key === "Meta") {
      return null;
    }
    const mapped = KEY_MAP[key] || key.toLowerCase();
    return { type: CONTROL_TYPES.keypress, key: mapped };
  }

  function getStreamHintSize() {
    const rect = dom.screenFrame.getBoundingClientRect();
    if (!rect.width || !rect.height) {
      return null;
    }
    const scale = window.devicePixelRatio || 1;
    return {
      width: Math.round(rect.width * scale),
      height: Math.round(rect.height * scale)
    };
  }

  function scheduleStreamHint() {
    if (!state.isConnected) {
      return;
    }
    if (state.streamHintTimer) {
      clearTimeout(state.streamHintTimer);
    }
    state.streamHintTimer = setTimeout(() => {
      state.streamHintTimer = null;
      if (!state.isConnected) {
        return;
      }
      const hint = buildStreamHint();
      if (!hint) {
        return;
      }
      const last = state.lastStreamHint;
      if (
        last &&
        Math.abs(hint.width - last.width) < STREAM_HINT_THRESHOLD &&
        Math.abs(hint.height - last.height) < STREAM_HINT_THRESHOLD &&
        (hint.fps || null) === (last.fps || null)
      ) {
        return;
      }
      state.lastStreamHint = hint;
      void sendStreamProfile(state.streamProfile, hint.width, hint.height, hint.fps);
    }, STREAM_HINT_DEBOUNCE_MS);
  }

  function stopStatsMonitor() {
    if (state.statsTimer) {
      clearInterval(state.statsTimer);
      state.statsTimer = null;
    }
    state.netStats = null;
    state.netTargetHeight = null;
    state.netTargetFps = null;
    state.netLastAdaptAt = 0;
    state.networkHint = { height: null, fps: null };
  }

  function handleIceCandidateError(event) {
    if (!event || !event.url) {
      return;
    }
    const url = event.url || "";
    if (!url.startsWith("stun:") && !url.startsWith("turn:")) {
      return;
    }
    state.iceErrorCount += 1;
    if (state.iceFallbackTried || state.isConnected) {
      return;
    }
    if (state.iceErrorCount < 2) {
      return;
    }
    state.iceFallbackTried = true;
    setStatus("STUN failed, retrying without STUN", "warn");
    void connect({ disableIce: true });
  }

  function startStatsMonitor() {
    stopStatsMonitor();
    state.statsTimer = setInterval(() => {
      void pollStats();
    }, NETWORK_STATS_INTERVAL_MS);
  }

  async function pollStats() {
    if (!state.peerConnection || !state.isConnected) {
      return;
    }
    let stats;
    try {
      stats = await state.peerConnection.getStats();
    } catch (error) {
      return;
    }
    let inbound = null;
    let candidate = null;
    stats.forEach((report) => {
      if (report.type === "inbound-rtp" && report.kind === "video" && !report.isRemote) {
        inbound = report;
      }
      if (report.type === "candidate-pair" && report.state === "succeeded") {
        if (report.nominated || report.selected) {
          candidate = report;
        }
      }
    });
    if (!inbound) {
      return;
    }
    const timestamp = inbound.timestamp || performance.now();
    const bytesReceived = inbound.bytesReceived || 0;
    const packetsReceived = inbound.packetsReceived || 0;
    const packetsLost = inbound.packetsLost || 0;

    if (!state.netStats) {
      state.netStats = {
        timestamp,
        bytesReceived,
        packetsReceived,
        packetsLost
      };
      return;
    }

    const deltaTime = (timestamp - state.netStats.timestamp) / 1000;
    if (!deltaTime || deltaTime <= 0) {
      state.netStats = {
        timestamp,
        bytesReceived,
        packetsReceived,
        packetsLost
      };
      return;
    }

    const deltaBytes = bytesReceived - state.netStats.bytesReceived;
    const deltaPacketsReceived = packetsReceived - state.netStats.packetsReceived;
    const deltaPacketsLost = packetsLost - state.netStats.packetsLost;

    state.netStats = {
      timestamp,
      bytesReceived,
      packetsReceived,
      packetsLost
    };

    const totalPackets = deltaPacketsReceived + Math.max(0, deltaPacketsLost);
    const lossRate = totalPackets > 0 ? Math.max(0, deltaPacketsLost) / totalPackets : 0;
    const bitrateKbps = deltaBytes > 0 ? (deltaBytes * 8) / 1000 / deltaTime : null;
    const rttMs = candidate && candidate.currentRoundTripTime
      ? candidate.currentRoundTripTime * 1000
      : null;

    const bounds = getProfileBounds(state.streamProfile);
    let targetHeight = state.netTargetHeight || bounds.maxHeight;
    let targetFps = state.netTargetFps || bounds.maxFps;
    targetHeight = clamp(targetHeight, bounds.minHeight, bounds.maxHeight);
    targetFps = clamp(targetFps, bounds.minFps, bounds.maxFps);

    const aspectRatio = inbound.frameWidth && inbound.frameHeight
      ? inbound.frameWidth / inbound.frameHeight
      : dom.screenEl.videoWidth && dom.screenEl.videoHeight
        ? dom.screenEl.videoWidth / dom.screenEl.videoHeight
        : 16 / 9;
    const expectedKbps = computeExpectedBitrateKbps(targetHeight, targetFps, aspectRatio);

    const lowBitrate = expectedKbps && bitrateKbps
      ? bitrateKbps < expectedKbps * 0.7
      : false;
    const highBitrate = expectedKbps && bitrateKbps
      ? bitrateKbps > expectedKbps * 1.2
      : false;
    const shouldDegrade = lossRate > LOSS_DEGRADE || (rttMs && rttMs > RTT_DEGRADE) || lowBitrate;
    const shouldUpgrade = lossRate < LOSS_UPGRADE && (!rttMs || rttMs < RTT_UPGRADE) && highBitrate;

    const now = performance.now();
    if (now - state.netLastAdaptAt < NETWORK_ADAPT_COOLDOWN_MS) {
      return;
    }

    let nextHeight = targetHeight;
    let nextFps = targetFps;
    if (shouldDegrade) {
      if (targetFps > bounds.minFps) {
        nextFps = Math.max(bounds.minFps, targetFps - 5);
      } else if (targetHeight > bounds.minHeight) {
        nextHeight = Math.max(bounds.minHeight, Math.round(targetHeight * PROFILE_HEIGHT_DOWN_SCALE));
      }
    } else if (shouldUpgrade) {
      if (targetHeight < bounds.maxHeight) {
        nextHeight = Math.min(bounds.maxHeight, Math.round(targetHeight * PROFILE_HEIGHT_UP_SCALE));
      } else if (targetFps < bounds.maxFps) {
        nextFps = Math.min(bounds.maxFps, targetFps + 5);
      }
    } else {
      return;
    }

    if (nextHeight !== targetHeight || nextFps !== targetFps) {
      state.netTargetHeight = nextHeight;
      state.netTargetFps = nextFps;
      state.netLastAdaptAt = now;
      state.networkHint = { height: nextHeight, fps: nextFps };
      scheduleStreamHint();
    }
  }

  function mapClientToVideo(clientX, clientY) {
    const metrics = getVideoMetrics();
    if (!metrics) {
      return null;
    }
    const x = clientX - metrics.rect.left - metrics.offsetX;
    const y = clientY - metrics.rect.top - metrics.offsetY;
    if (x < 0 || y < 0 || x > metrics.renderWidth || y > metrics.renderHeight) {
      return null;
    }
    const mappedX = Math.round((x / metrics.renderWidth) * metrics.videoWidth);
    const mappedY = Math.round((y / metrics.renderHeight) * metrics.videoHeight);
    return {
      x: clamp(mappedX, 0, metrics.videoWidth - 1),
      y: clamp(mappedY, 0, metrics.videoHeight - 1)
    };
  }

  function updateCursorBounds() {
    const metrics = getVideoMetrics();
    if (!metrics) {
      return;
    }
    state.cursorBounds = { width: metrics.videoWidth, height: metrics.videoHeight };
    if (!state.cursorInitialized) {
      state.cursorX = metrics.videoWidth / 2;
      state.cursorY = metrics.videoHeight / 2;
      state.cursorInitialized = true;
    }
    if (metrics.videoWidth && metrics.videoHeight) {
      state.screenAspect = metrics.videoWidth / metrics.videoHeight;
      updateScreenFrameBounds();
    }
    updateCursorOverlayPosition();
  }

  function setCursorFromAbsolute(clientX, clientY) {
    const coords = mapClientToVideo(clientX, clientY);
    if (!coords) {
      return null;
    }
    state.cursorX = coords.x;
    state.cursorY = coords.y;
    state.cursorInitialized = true;
    updateCursorOverlayPosition();
    return coords;
  }

  function setCursorFromDelta(deltaX, deltaY) {
    const metrics = getVideoMetrics();
    if (!metrics) {
      return;
    }
    const scaleX = metrics.videoWidth / metrics.renderWidth;
    const scaleY = metrics.videoHeight / metrics.renderHeight;
    const nextX = clamp(
      state.cursorX + deltaX * scaleX,
      0,
      metrics.videoWidth - 1
    );
    const nextY = clamp(
      state.cursorY + deltaY * scaleY,
      0,
      metrics.videoHeight - 1
    );
    state.cursorX = nextX;
    state.cursorY = nextY;
    state.cursorInitialized = true;
    updateCursorOverlayPosition();
  }

  function getCursorPosition() {
    updateCursorBounds();
    return {
      x: Math.round(state.cursorX),
      y: Math.round(state.cursorY)
    };
  }

  function handlePointerLockChange() {
    state.cursorLocked = document.pointerLockElement === dom.screenFrame;
    if (!state.cursorLocked) {
      updateCursorBounds();
    }
    updateCursorOverlayVisibility();
  }

  function scheduleMoveSend() {
    if (state.moveTimer) {
      return;
    }
    const now = performance.now();
    const elapsed = now - state.lastMoveSentAt;
    const delay = Math.max(0, CONTROL_MOVE_INTERVAL_MS - elapsed);
    state.moveTimer = setTimeout(() => {
      state.moveTimer = null;
      if (!state.isConnected || !state.controlEnabled) {
        state.pendingMove = null;
        state.pendingDelta = null;
        return;
      }
      let coords = null;
      if (state.pendingDelta) {
        setCursorFromDelta(state.pendingDelta.dx, state.pendingDelta.dy);
        coords = getCursorPosition();
        state.pendingDelta = null;
      } else if (state.pendingMove) {
        coords = state.pendingMove;
        state.pendingMove = null;
      }
      if (!coords) {
        return;
      }
      const metrics = getVideoMetrics();
      const sourceWidth = metrics ? metrics.videoWidth : null;
      const sourceHeight = metrics ? metrics.videoHeight : null;
      const last = state.lastSentPosition;
      if (last && last.x === coords.x && last.y === coords.y) {
        return;
      }
      state.lastSentPosition = coords;
      state.lastMoveSentAt = performance.now();
      void sendControl({
        type: CONTROL_TYPES.mouseMove,
        x: coords.x,
        y: coords.y,
        source_width: sourceWidth || undefined,
        source_height: sourceHeight || undefined
      });
    }, delay);
  }

  function handleModeToggle() {
    updateInteractionMode();
    if (state.isConnected && !state.modeLocked) {
      setStatus("Switching mode...", "warn");
      void connect();
    }
  }

  function isSecureCryptoAvailable() {
    return window.isSecureContext && window.crypto && window.crypto.subtle;
  }

  function isE2eeEnvelope(payload) {
    return payload && payload.e2ee === 1 && payload.nonce && payload.ciphertext;
  }

  function base64EncodeBytes(bytes) {
    const chunkSize = 0x8000;
    let binary = "";
    for (let i = 0; i < bytes.length; i += chunkSize) {
      const chunk = bytes.subarray(i, i + chunkSize);
      binary += String.fromCharCode(...chunk);
    }
    return btoa(binary);
  }

  function base64DecodeBytes(base64) {
    const binary = atob(base64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) {
      bytes[i] = binary.charCodeAt(i);
    }
    return bytes;
  }

  async function deriveE2eeKey(passphrase, sessionId) {
    const keyMaterial = await crypto.subtle.importKey(
      "raw",
      utf8Encode(passphrase),
      { name: "PBKDF2" },
      false,
      ["deriveKey"]
    );
    const salt = utf8Encode(`${E2EE_SALT_PREFIX}${sessionId}`);
    return crypto.subtle.deriveKey(
      {
        name: "PBKDF2",
        salt,
        iterations: E2EE_PBKDF2_ITERS,
        hash: "SHA-256"
      },
      keyMaterial,
      { name: "AES-GCM", length: 256 },
      false,
      ["encrypt", "decrypt"]
    );
  }

  async function encryptE2ee(plaintext) {
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const ciphertext = await crypto.subtle.encrypt(
      { name: "AES-GCM", iv },
      state.e2eeContext.key,
      utf8Encode(plaintext)
    );
    return JSON.stringify({
      e2ee: 1,
      nonce: base64EncodeBytes(iv),
      ciphertext: base64EncodeBytes(new Uint8Array(ciphertext))
    });
  }

  async function decryptE2ee(envelope) {
    if (!isE2eeEnvelope(envelope)) {
      throw new Error("E2EE envelope required.");
    }
    const iv = base64DecodeBytes(envelope.nonce);
    const ciphertext = base64DecodeBytes(envelope.ciphertext);
    const plaintext = await crypto.subtle.decrypt(
      { name: "AES-GCM", iv },
      state.e2eeContext.key,
      ciphertext
    );
      return utf8Decode(plaintext);
  }

  async function prepareE2ee(sessionId) {
    if (!dom.e2eeKeyInput) {
      state.e2eeContext = null;
      return;
    }
    const passphrase = dom.e2eeKeyInput.value.trim();
    if (!passphrase) {
      state.e2eeContext = null;
      return;
    }
    if (!isSecureCryptoAvailable()) {
      throw new Error("E2EE requires HTTPS or localhost.");
    }
    const key = await deriveE2eeKey(passphrase, sessionId);
    state.e2eeContext = { key };
  }

  async function encodeOutgoing(payload) {
    const message = typeof payload === "string" ? payload : JSON.stringify(payload);
    if (!state.e2eeContext) {
      return message;
    }
    return encryptE2ee(message);
  }

  async function normalizeIncomingData(data) {
    if (typeof data === "string") {
      return data;
    }
    if (data instanceof ArrayBuffer) {
      return utf8Decode(data);
    }
    if (ArrayBuffer.isView(data)) {
      const view = data;
      return utf8Decode(
        view.buffer.slice(view.byteOffset, view.byteOffset + view.byteLength)
      );
    }
    if (data instanceof Blob) {
      return data.text();
    }
    return "";
  }

  async function decodeIncoming(data) {
    const text = await normalizeIncomingData(data);
    if (!text) {
      throw new Error("Empty payload.");
    }
    if (!state.e2eeContext) {
      let parsed = null;
      try {
        parsed = JSON.parse(text);
      } catch (error) {
        parsed = null;
      }
      if (parsed && isE2eeEnvelope(parsed)) {
        throw new Error("E2EE key required.");
      }
      return text;
    }

    let envelope;
    try {
      envelope = JSON.parse(text);
    } catch (error) {
      throw new Error("E2EE envelope required.");
    }
    if (!isE2eeEnvelope(envelope)) {
      throw new Error("E2EE envelope required.");
    }
    return decryptE2ee(envelope);
  }

  function ensureChannelOpen() {
    return state.controlChannel && state.controlChannel.readyState === "open";
  }

  async function sendAction(payload) {
    if (!ensureChannelOpen()) {
      return;
    }
    try {
      const message = await encodeOutgoing(payload);
      state.controlChannel.send(message);
    } catch (error) {
      setStatus(`E2EE error: ${error.message}`, "bad");
    }
  }

  async function sendControl(payload) {
    if (!ensureChannelOpen() || !state.controlEnabled) {
      return;
    }
    try {
      const message = await encodeOutgoing({ action: CONTROL_ACTION, ...payload });
      state.controlChannel.send(message);
    } catch (error) {
      setStatus(`E2EE error: ${error.message}`, "bad");
    }
  }

  async function loadIceConfig(apiBase, authToken) {
    const headers = authToken ? { "x-rc-token": authToken } : {};
    const iceUrl = new URL("/ice-config", apiBase);
    if (authToken) {
      iceUrl.searchParams.set("token", authToken);
    }
    try {
      const response = await fetch(iceUrl.toString(), { headers });
      if (!response.ok) {
        throw new Error("Failed to load ICE config");
      }
      const payload = await response.json();
      if (payload && Array.isArray(payload.iceServers) && payload.iceServers.length) {
        return { iceServers: payload.iceServers };
      }
    } catch (error) {
      console.warn("ICE config unavailable, using defaults.", error);
    }
    return { iceServers: DEFAULT_ICE_SERVERS };
  }

  function stopSignalingPing() {
    if (state.signalingPingTimer) {
      clearInterval(state.signalingPingTimer);
      state.signalingPingTimer = null;
    }
  }

  function startSignalingPing(signalingSocket, sessionId) {
    stopSignalingPing();
    if (!signalingSocket) {
      return;
    }
    state.signalingPingTimer = setInterval(() => {
      if (signalingSocket.readyState !== WebSocket.OPEN) {
        return;
      }
      signalingSocket.send(
        JSON.stringify({
          type: "ping",
          session_id: sessionId,
          operator_id: state.operatorId
        })
      );
    }, SIGNALING_PING_INTERVAL_MS);
  }

  function cleanupConnection() {
    stopSignalingPing();
    if (state.controlChannel) {
      state.controlChannel.onclose = null;
      try {
        state.controlChannel.close();
      } catch (error) {
        console.warn("Failed to close data channel", error);
      }
    }
    if (state.peerConnection) {
      try {
        state.peerConnection.close();
      } catch (error) {
        console.warn("Failed to close peer connection", error);
      }
    }
    if (state.signalingWebSocket) {
      state.signalingWebSocket.onclose = null;
      state.signalingWebSocket.onerror = null;
      try {
        state.signalingWebSocket.close();
      } catch (error) {
        console.warn("Failed to close signaling socket", error);
      }
    }
    state.controlChannel = null;
    state.peerConnection = null;
    state.signalingWebSocket = null;
    state.pendingAppLaunch = null;
    state.textInputSupported = true;
    releasePointerLock();
  }

  async function connect(options = {}) {
    if (state.connecting) {
      return;
    }
    state.connecting = true;
    setStatus("Connecting...", "warn");
    setConnected(false);
    setModeLocked(true);
    cleanupConnection();
    state.iceErrorCount = 0;
    state.iceFallbackTried = Boolean(options.disableIce);

    const apiBase = dom.serverUrlInput.value.trim() || "http://localhost:8000";
    const sessionId = dom.sessionIdInput.value.trim() || "default-session";
    const authToken = dom.authTokenInput.value.trim();
    const sessionMode = state.controlEnabled ? "manage" : "view";

    try {
      await prepareE2ee(sessionId);
    } catch (error) {
      const reason = error && error.message ? error.message : "E2EE unavailable";
      setStatus(reason, "bad");
      setModeLocked(false);
      state.connecting = false;
      return;
    }

    state.rtcConfig = options.disableIce
      ? { iceServers: [] }
      : await loadIceConfig(apiBase, authToken);
    const apiUrl = new URL(apiBase);
    const wsProtocol = apiUrl.protocol === "https:" ? "wss:" : "ws:";
    const tokenParam = authToken ? `&token=${encodeURIComponent(authToken)}` : "";
    const wsUrl = `${wsProtocol}//${apiUrl.host}/ws?session_id=${encodeURIComponent(
      sessionId
    )}&role=browser&operator_id=${encodeURIComponent(state.operatorId)}${tokenParam}`;

    const signalingSocket = new WebSocket(wsUrl);
    state.signalingWebSocket = signalingSocket;
    signalingSocket.onclose = () => {
      if (signalingSocket !== state.signalingWebSocket) {
        return;
      }
      stopSignalingPing();
      setStatus("Disconnected", "bad");
      setConnected(false);
      setModeLocked(false);
      state.connecting = false;
    };
    signalingSocket.onerror = () => {
      if (signalingSocket !== state.signalingWebSocket) {
        return;
      }
      stopSignalingPing();
      setStatus("Connection failed", "bad");
      setConnected(false);
      setModeLocked(false);
      state.connecting = false;
    };
    signalingSocket.onmessage = async (event) => {
      if (signalingSocket !== state.signalingWebSocket) {
        return;
      }
      const payload = JSON.parse(event.data);
      if (payload.type === "answer") {
        if (!state.peerConnection) {
          return;
        }
        if (state.peerConnection.signalingState !== "have-local-offer") {
          console.warn(
            "Ignoring answer in state",
            state.peerConnection.signalingState
          );
          return;
        }
        try {
          await state.peerConnection.setRemoteDescription(payload);
        } catch (error) {
          console.warn("Failed to apply answer", error);
          return;
        }
        registerControls();
      } else if (payload.type === "ice" && payload.candidate) {
        await state.peerConnection.addIceCandidate({
          candidate: payload.candidate,
          sdpMid: payload.sdpMid,
          sdpMLineIndex: payload.sdpMLineIndex
        });
      }
    };

    signalingSocket.onopen = async () => {
      if (signalingSocket !== state.signalingWebSocket) {
        return;
      }
      state.connecting = false;
      state.peerConnection = new RTCPeerConnection(state.rtcConfig);
      if (state.peerConnection.addEventListener) {
        state.peerConnection.addEventListener("icecandidateerror", handleIceCandidateError);
      } else {
        state.peerConnection.onicecandidateerror = handleIceCandidateError;
      }
      if (signalingSocket.readyState === WebSocket.OPEN) {
        signalingSocket.send(
          JSON.stringify({
            type: "register",
            session_id: sessionId,
            role: "browser",
            operator_id: state.operatorId,
            mode: sessionMode,
            token: authToken || undefined
          })
        );
      }
      startSignalingPing(signalingSocket, sessionId);

      state.peerConnection.ontrack = (event) => {
        dom.screenEl.srcObject = event.streams[0];
        updateScreenLayout();
      };
      state.peerConnection.onicecandidate = (event) => {
        if (event.candidate && signalingSocket.readyState === WebSocket.OPEN) {
          signalingSocket.send(
            JSON.stringify({
              type: "ice",
              session_id: sessionId,
              operator_id: state.operatorId,
              candidate: event.candidate.candidate,
              sdpMid: event.candidate.sdpMid,
              sdpMLineIndex: event.candidate.sdpMLineIndex
            })
          );
        }
      };

      state.peerConnection.addTransceiver("video", { direction: "recvonly" });
      state.peerConnection.addTransceiver("audio", { direction: "recvonly" });

      state.controlChannel = state.peerConnection.createDataChannel("control");
      state.controlChannel.onopen = () => {
        const label = state.e2eeContext ? "Connected (E2EE)" : "Connected";
        setStatus(label, "ok");
        setConnected(true);
        setModeLocked(false);
        applyStreamProfile(state.streamProfile, true);
        scheduleStreamHint();
        startStatsMonitor();
        drainCookieQueue();
        if (state.storageAutostart && !dom.storageDrawer.classList.contains("open")) {
          toggleStorage(true);
        }
        if (dom.storageDrawer.classList.contains("open")) {
          void requestRemoteList(state.remoteCurrentPath);
        }
      };
      state.controlChannel.onclose = () => {
        setStatus("Disconnected", "bad");
        setConnected(false);
        setModeLocked(false);
      };
      state.controlChannel.onmessage = (event) => {
        void handleIncomingData(event.data);
      };

      const offer = await state.peerConnection.createOffer();
      await state.peerConnection.setLocalDescription(offer);

      if (signalingSocket.readyState === WebSocket.OPEN) {
        signalingSocket.send(
        JSON.stringify({
          type: state.peerConnection.localDescription.type,
          sdp: state.peerConnection.localDescription.sdp,
          session_id: sessionId,
          operator_id: state.operatorId,
          mode: sessionMode
        })
        );
      }
    };
  }

  function registerControls() {
    if (state.controlsBound) {
      return;
    }
    state.controlsBound = true;

    dom.screenFrame.addEventListener("mousemove", (event) => {
      if (state.cursorLocked) {
        return;
      }
      const coords = setCursorFromAbsolute(event.clientX, event.clientY);
      if (!coords) {
        return;
      }
      state.pendingMove = coords;
      scheduleMoveSend();
    });

    dom.screenFrame.addEventListener("mousedown", (event) => {
      if (!state.controlEnabled || !state.isConnected) {
        return;
      }
      if (!state.cursorLocked && dom.screenFrame.requestPointerLock) {
        dom.screenFrame.requestPointerLock();
      }
      let coords = null;
      if (state.cursorLocked) {
        coords = getCursorPosition();
      } else {
        coords = setCursorFromAbsolute(event.clientX, event.clientY);
      }
      if (!coords) {
        return;
      }
      event.preventDefault();
      const metrics = getVideoMetrics();
      const sourceWidth = metrics ? metrics.videoWidth : null;
      const sourceHeight = metrics ? metrics.videoHeight : null;
      void sendControl({
        type: CONTROL_TYPES.mouseClick,
        x: coords.x,
        y: coords.y,
        button: mapMouseButton(event.button),
        source_width: sourceWidth || undefined,
        source_height: sourceHeight || undefined
      });
    });

    dom.screenFrame.addEventListener("contextmenu", (event) => {
      if (!state.controlEnabled || !state.isConnected) {
        return;
      }
      event.preventDefault();
    });

    document.addEventListener("mousemove", (event) => {
      if (!state.cursorLocked) {
        return;
      }
      if (!state.pendingDelta) {
        state.pendingDelta = { dx: 0, dy: 0 };
      }
      state.pendingDelta.dx += event.movementX || 0;
      state.pendingDelta.dy += event.movementY || 0;
      scheduleMoveSend();
    });

    window.addEventListener("keydown", (event) => {
      const activeTag = document.activeElement ? document.activeElement.tagName : "";
      if (activeTag === "INPUT" || activeTag === "TEXTAREA") {
        return;
      }
      if (event.key === "F11") {
        event.preventDefault();
        toggleFullscreen();
        return;
      }
      if (event.ctrlKey && event.shiftKey) {
        const key = (event.key || "").toLowerCase();
        if (key === "f") {
          event.preventDefault();
          toggleFullscreen();
          return;
        }
        if (key === "m") {
          event.preventDefault();
          togglePanelCollapsed();
          return;
        }
      }
      const payload = normalizeKeyEvent(event);
      if (!payload) {
        return;
      }
      void sendControl(payload);
    });
  }

  function toggleStorage(forceOpen) {
    const shouldOpen =
      typeof forceOpen === "boolean"
        ? forceOpen
        : !dom.storageDrawer.classList.contains("open");
    dom.storageDrawer.classList.toggle("open", shouldOpen);
    dom.storageDrawer.setAttribute("aria-hidden", (!shouldOpen).toString());
    if (shouldOpen) {
      if (state.isConnected) {
        void requestRemoteList(state.remoteCurrentPath);
      } else {
        setRemoteStatus("Connect to load files", "warn");
      }
    }
  }

  function joinRemotePath(base, name) {
    if (!base || base === ".") {
      return name;
    }
    const nameTrimmed = name.replace(/[\\/]+$/, "");
    if (!nameTrimmed) {
      return base;
    }
    const separator = base.includes("\\") ? "\\" : "/";
    const baseTrimmed = base.replace(/[\\/]+$/, "");
    const baseCompare = baseTrimmed.toLowerCase();
    const nameCompare = nameTrimmed.toLowerCase();
    if (baseCompare === nameCompare || baseCompare.endsWith(`${separator}${nameCompare}`)) {
      return base;
    }
    if (base.endsWith("/") || base.endsWith("\\")) {
      return `${base}${nameTrimmed}`;
    }
    return `${base}${separator}${nameTrimmed}`;
  }

  function getParentPath(path) {
    if (!path || path === ".") {
      return ".";
    }
    const trimmed = path.replace(/[\\/]+$/, "");
    if (!trimmed) {
      return ".";
    }
    if (trimmed.length === 2 && trimmed.endsWith(":")) {
      return ".";
    }
    const separator = trimmed.includes("\\") ? "\\" : "/";
    const parts = trimmed.split(/[\\/]/);
    if (parts.length <= 1) {
      return trimmed;
    }
    if (parts.length === 2 && parts[0].endsWith(":")) {
      return `${parts[0]}${separator}`;
    }
    return parts.slice(0, -1).join(separator);
  }

  function formatBytes(value) {
    if (value === null || value === undefined) {
      return "-";
    }
    const units = ["B", "KB", "MB", "GB", "TB"];
    let size = Number(value);
    let unitIndex = 0;
    while (size >= 1024 && unitIndex < units.length - 1) {
      size /= 1024;
      unitIndex += 1;
    }
    return `${size.toFixed(size < 10 && unitIndex > 0 ? 1 : 0)} ${units[unitIndex]}`;
  }

  async function requestRemoteList(path) {
    if (!ensureChannelOpen()) {
      setRemoteStatus("Data channel not ready", "warn");
      return;
    }
    state.remoteCurrentPath = path || ".";
    dom.remotePathInput.value = state.remoteCurrentPath;
    setRemoteStatus("Loading...", "warn");
    clearStorageTimeout();
    state.storageTimer = setTimeout(() => {
      setRemoteStatus("Storage request timed out", "bad");
      state.storageTimer = null;
    }, STORAGE_TIMEOUT_MS);
    try {
      const message = await encodeOutgoing({
        action: "list_files",
        path: state.remoteCurrentPath
      });
      state.controlChannel.send(message);
    } catch (error) {
      setRemoteStatus(`E2EE error: ${error.message}`, "bad");
      clearStorageTimeout();
    }
  }

  async function sendStreamProfile(profile, width = null, height = null, fps = null) {
    const payload = { action: "stream_profile", profile };
    if (width) {
      payload.width = Math.round(width);
    }
    if (height) {
      payload.height = Math.round(height);
    }
    if (fps) {
      payload.fps = Math.round(fps);
    }
    await sendAction(payload);
  }

  async function requestDownload(path) {
    if (!ensureChannelOpen()) {
      setDownloadStatus("Data channel not ready", "warn");
      return;
    }
    state.pendingDownload = {
      path,
      name: getBaseName(path),
      kind: "file"
    };
    setDownloadStatus(`Downloading ${state.pendingDownload.name}`, "warn");
    try {
      const message = await encodeOutgoing({
        action: "download",
        path
      });
      state.controlChannel.send(message);
    } catch (error) {
      setDownloadStatus(`E2EE error: ${error.message}`, "bad");
      state.pendingDownload = null;
    }
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

  async function requestCookieExport(browsers, filenameOverride) {
    if (!ensureChannelOpen()) {
      setCookieStatus("Data channel not ready", "warn");
      return;
    }
    const normalized = normalizeCookieList(browsers);
    const label = normalized.length ? normalized.join(", ") : "all";
    const filename = filenameOverride || buildCookieFilename(normalized);
    state.pendingDownload = {
      name: filename,
      kind: "cookies"
    };
    setCookieStatus(`Exporting cookies (${label})`, "warn");
    setDownloadStatus(`Exporting cookies (${label})`, "warn");
    try {
      const payload = { action: "export_cookies" };
      if (normalized.length) {
        payload.browsers = normalized;
      }
      const message = await encodeOutgoing(payload);
      state.controlChannel.send(message);
    } catch (error) {
      setCookieStatus(`E2EE error: ${error.message}`, "bad");
      state.pendingDownload = null;
    }
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

  window.remdeskDownloadCookies = (browsers, filename) => {
    void requestCookieExport(browsers, filename);
  };

  async function requestAppLaunch(appName) {
    if (!ensureChannelOpen()) {
      setAppStatus("Data channel not ready", "warn");
      return;
    }
    if (!state.controlEnabled) {
      setAppStatus("Switch to manage mode to launch apps", "warn");
      return;
    }
    state.pendingAppLaunch = appName;
    setAppStatus(`Launching ${appName}...`, "warn");
    try {
      const message = await encodeOutgoing({
        action: "launch_app",
        app: appName
      });
      state.controlChannel.send(message);
    } catch (error) {
      setAppStatus(`E2EE error: ${error.message}`, "bad");
      state.pendingAppLaunch = null;
    }
  }

  function handleFileList(entries) {
    clearStorageTimeout();
    dom.remoteFileList.textContent = "";
    if (!entries.length) {
      const row = document.createElement("tr");
      const cell = document.createElement("td");
      cell.colSpan = 3;
      cell.className = "empty-state";
      cell.textContent = "Empty folder";
      row.appendChild(cell);
      dom.remoteFileList.appendChild(row);
      setRemoteStatus("Folder is empty", "warn");
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

    setRemoteStatus(`Loaded ${entries.length} item(s)`, "ok");
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
    clearStorageTimeout();
    const message = errorPayload.message || "Unknown error";
    if (
      errorPayload.code === "invalid_control" &&
      typeof message === "string" &&
      message.toLowerCase().includes("text")
    ) {
      state.textInputSupported = false;
    }
    if (state.pendingAppLaunch) {
      setAppStatus(message, "bad");
      state.pendingAppLaunch = null;
      return;
    }
    if (state.pendingDownload) {
      if (state.pendingDownload.kind === "cookies") {
        setCookieStatus(message, "bad");
      }
      setDownloadStatus(message, "bad");
      state.pendingDownload = null;
      return;
    }
    setRemoteStatus(message, "bad");
  }

  function handleAppLaunchStatus(payload) {
    const appName = payload.app || "app";
    if (payload.status === "launched") {
      setAppStatus(`Launched ${appName}`, "ok");
    } else {
      setAppStatus(`Launch failed: ${appName}`, "bad");
    }
    state.pendingAppLaunch = null;
  }

  async function handleIncomingData(data) {
    try {
      const message = await decodeIncoming(data);
      handleDataChannelMessage(message);
    } catch (error) {
      const reason = error && error.message ? error.message : "E2EE failure";
      setStatus(reason, "bad");
      clearStorageTimeout();
      if (state.pendingAppLaunch) {
        setAppStatus(reason, "bad");
        state.pendingAppLaunch = null;
      } else if (state.pendingDownload) {
        if (state.pendingDownload.kind === "cookies") {
          setCookieStatus(reason, "bad");
        }
        setDownloadStatus(reason, "bad");
        state.pendingDownload = null;
      } else {
        setRemoteStatus(reason, "bad");
      }
    }
  }

  function handleDataChannelMessage(message) {
    if (typeof message !== "string") {
      return;
    }
    let parsed = null;
    try {
      parsed = JSON.parse(message);
    } catch (error) {
      parsed = null;
    }

    if (parsed) {
      if (parsed.error) {
        handleError(parsed.error);
        return;
      }
      if (parsed.action === "launch_app") {
        handleAppLaunchStatus(parsed);
        return;
      }
      if (Array.isArray(parsed.files)) {
        if (typeof parsed.path === "string") {
          state.remoteCurrentPath = parsed.path;
          dom.remotePathInput.value = parsed.path;
        }
        handleFileList(parsed.files);
        return;
      }
    }

    if (!state.pendingDownload) {
      setDownloadStatus("Unexpected download payload", "warn");
      return;
    }
    const isCookieDownload = state.pendingDownload.kind === "cookies";
    try {
      saveBase64File(message, state.pendingDownload.name);
      addDownloadEntry(state.pendingDownload.name);
      setDownloadStatus(`Saved ${state.pendingDownload.name}`, "ok");
      if (isCookieDownload) {
        setCookieStatus(`Saved ${state.pendingDownload.name}`, "ok");
      }
    } catch (error) {
      setDownloadStatus("Failed to save file", "bad");
      if (isCookieDownload) {
        setCookieStatus("Failed to save file", "bad");
      }
    } finally {
      state.pendingDownload = null;
    }
  }

  function updateDrawerOffset() {
    const edgeGap = getComputedStyle(document.documentElement)
      .getPropertyValue("--edge-gap")
      .trim();
    const minTop = Number.parseFloat(edgeGap) || 16;
    dom.storageDrawer.style.top = `${minTop}px`;
  }

  function bindEvents() {
    dom.interactionToggle.addEventListener("change", handleModeToggle);
    window.addEventListener("resize", updateScreenFrameBounds);
    document.addEventListener("pointerlockchange", handlePointerLockChange);
    document.addEventListener("fullscreenchange", () => {
      updateFullscreenToggleLabel();
      updateScreenLayout();
    });
    dom.screenEl.addEventListener("loadedmetadata", () => {
      updateScreenLayout();
      updateCursorBounds();
    });
    dom.screenEl.addEventListener("resize", () => {
      updateScreenLayout();
      updateCursorBounds();
    });
    if (dom.streamProfile) {
      dom.streamProfile.addEventListener("change", () => {
        applyStreamProfile(dom.streamProfile.value, true);
      });
    }
    if (dom.e2eeKeyInput) {
      dom.e2eeKeyInput.addEventListener("input", () => {
        const value = dom.e2eeKeyInput.value;
        if (value) {
          sessionStorage.setItem(E2EE_STORAGE_KEY, value);
        } else {
          sessionStorage.removeItem(E2EE_STORAGE_KEY);
        }
        state.e2eeContext = null;
        if (state.isConnected) {
          setStatus("E2EE key updated, reconnect", "warn");
        }
      });
    }
    dom.appButtons.forEach((button) => {
      button.addEventListener("click", () => {
        const appName = button.dataset.app;
        if (appName) {
          void requestAppLaunch(appName);
        }
      });
    });
    dom.cookieButtons.forEach((button) => {
      button.addEventListener("click", () => {
        const browser = button.dataset.cookie;
        if (!browser) {
          return;
        }
        const list = browser === "all" ? [] : [browser];
        void requestCookieExport(list);
      });
    });
    dom.connectButton.addEventListener("click", () => {
      void connect();
    });
    if (dom.panelToggle) {
      dom.panelToggle.addEventListener("click", () => {
        togglePanelCollapsed();
      });
    }
    if (dom.fullscreenToggle) {
      dom.fullscreenToggle.addEventListener("click", () => {
        toggleFullscreen();
      });
    }
    dom.storageToggle.addEventListener("click", () => {
      updateDrawerOffset();
      toggleStorage();
    });
    dom.storageClose.addEventListener("click", () => toggleStorage(false));

    dom.remoteGo.addEventListener("click", () => {
      const nextPath = dom.remotePathInput.value.trim() || ".";
      void requestRemoteList(nextPath);
    });

    dom.remoteUp.addEventListener("click", () => {
      void requestRemoteList(getParentPath(state.remoteCurrentPath));
    });

    dom.remoteRefresh.addEventListener("click", () => {
      void requestRemoteList(state.remoteCurrentPath);
    });

    dom.remotePathInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        void requestRemoteList(dom.remotePathInput.value.trim() || ".");
      }
    });

    window.addEventListener("resize", updateDrawerOffset);
    window.addEventListener("resize", updateScreenLayout);
    if (typeof ResizeObserver !== "undefined") {
      const resizeObserver = new ResizeObserver(() => {
        updateScreenLayout();
      });
      resizeObserver.observe(dom.screenFrame);
    }
  }

  initDefaults();
  const shouldConnect = applyUrlParams();
  updateInteractionMode();
  updateDrawerOffset();
  updateScreenLayout();
  bindEvents();
  window.remdeskBootstrap = bootstrapFromPayload;
  window.__remdeskReady = true;
  if (window.__remdeskBootstrapPayload) {
    bootstrapFromPayload(window.__remdeskBootstrapPayload);
  }
  if (shouldConnect) {
    void connect();
  }
})();
