(() => {
  "use strict";

  const remdesk = window.remdesk;
  const { state, dom, constants } = remdesk;
  const { E2EE_STORAGE_KEY } = constants;

  let qtBridgeAttempts = 0;
  let qtScriptInjected = false;

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
      remdesk.applyStreamProfile(dom.streamProfile.value, false);
    }
    remdesk.ensureCursorOverlay();
    if (dom.cursorVisibilityToggle) {
      state.remoteCursorVisible = dom.cursorVisibilityToggle.checked;
    }
    remdesk.updateRemoteCursorVisibilityAvailability();
    remdesk.restorePanelState();
    remdesk.updatePanelToggleLabel();
    remdesk.updateFullscreenToggleLabel();
    remdesk.updateTopBar();
    remdesk.startTopClock();
    initQtBridge();
  }

  function initQtBridge() {
    if (window.remdeskHost) {
      return;
    }
    const hasQt = window.qt && window.qt.webChannelTransport;
    if (!hasQt) {
      if (qtBridgeAttempts < 20) {
        qtBridgeAttempts += 1;
        setTimeout(initQtBridge, 150);
      }
      return;
    }
    if (typeof QWebChannel === "undefined") {
      ensureQWebChannelScript();
      if (qtBridgeAttempts < 20) {
        qtBridgeAttempts += 1;
        setTimeout(initQtBridge, 150);
      }
      return;
    }
    try {
      new QWebChannel(window.qt.webChannelTransport, (channel) => {
        window.remdeskHost =
          channel.objects.remdeskHost || channel.objects.remdeskBridge || null;
      });
    } catch (error) {
      console.warn("Failed to init Qt bridge", error);
    }
  }

  function ensureQWebChannelScript() {
    if (qtScriptInjected) {
      return;
    }
    qtScriptInjected = true;
    const script = document.createElement("script");
    script.src = "qrc:///qtwebchannel/qwebchannel.js";
    script.onload = () => {
      initQtBridge();
    };
    document.head.appendChild(script);
  }

  function applyUrlParams() {
    const params = new URLSearchParams(window.location.search);
    const desktopFlag = (params.get("desktop") || params.get("embedded") || "").toLowerCase();
    if (desktopFlag === "1" || desktopFlag === "true" || desktopFlag === "yes" || desktopFlag === "on") {
      document.body.classList.add("desktop-mode");
    }
    const storageOnlyFlag = (params.get("storage_only") || params.get("storageOnly") || "").toLowerCase();
    if (storageOnlyFlag === "1" || storageOnlyFlag === "true" || storageOnlyFlag === "yes" || storageOnlyFlag === "on") {
      document.body.classList.add("storage-only");
      state.storageOnly = true;
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
    if (mode && remdesk.applySessionMode) {
      remdesk.applySessionMode(mode);
    } else if (mode === "view" && dom.interactionToggle) {
      dom.interactionToggle.checked = false;
    } else if (mode === "manage" && dom.interactionToggle) {
      dom.interactionToggle.checked = true;
    }

    const storage = (params.get("storage") || "").toLowerCase();
    state.storageAutostart =
      storage === "1" || storage === "true" || storage === "yes" || storage === "open";
    if (state.storageOnly) {
      state.storageAutostart = true;
    }

    const streamProfile = (params.get("stream") || params.get("quality") || "").toLowerCase();
    if (streamProfile && dom.streamProfile) {
      remdesk.applyStreamProfile(streamProfile, false);
    }

    const region = params.get("region") || params.get("geo") || "";
    if (region) {
      state.regionLabel = region;
    }
    const country = params.get("country") || params.get("country_name") || "";
    if (country) {
      state.countryLabel = country;
    }
    const countryCode = params.get("country_code") || params.get("cc") || "";
    if (countryCode) {
      state.countryCode = countryCode;
    }
    const flagsParam = params.get("flags") || params.get("countries") || "";
    if (flagsParam) {
      state.flagCodes = remdesk.parseFlagList(flagsParam);
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
    if (payload.storageOnly === true) {
      document.body.classList.add("storage-only");
      state.storageOnly = true;
    } else if (payload.storageOnly === false) {
      document.body.classList.remove("storage-only");
      state.storageOnly = false;
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
    if (payload.region) {
      state.regionLabel = String(payload.region);
    }
    if (payload.country) {
      state.countryLabel = String(payload.country);
    }
    if (payload.country_code) {
      state.countryCode = String(payload.country_code);
    }
    if (payload.flags || payload.countries) {
      state.flagCodes = remdesk.parseFlagList(payload.flags || payload.countries);
    }
    if (Object.prototype.hasOwnProperty.call(payload, "iceServers")) {
      if (Array.isArray(payload.iceServers)) {
        state.iceServersPreset = payload.iceServers;
        state.iceServersPresetSet = true;
      } else {
        state.iceServersPreset = null;
        state.iceServersPresetSet = false;
      }
    }
    if (
      Object.prototype.hasOwnProperty.call(payload, "availableBrowsers") &&
      remdesk.applyAvailableBrowsers
    ) {
      remdesk.applyAvailableBrowsers(payload.availableBrowsers);
    }
    remdesk.updateTopBar();
    if (payload.stream && dom.streamProfile) {
      remdesk.applyStreamProfile(payload.stream, false);
    }
    if (Object.prototype.hasOwnProperty.call(payload, "manage")) {
      const nextMode = payload.manage ? "manage" : "view";
      if (remdesk.applySessionMode) {
        remdesk.applySessionMode(nextMode);
      } else if (dom.interactionToggle) {
        dom.interactionToggle.checked = payload.manage;
        dom.interactionToggle.dispatchEvent(new Event("change", { bubbles: true }));
      }
    }
    if (payload.openStorage) {
      remdesk.toggleStorage(true);
    }
    if (payload.autoConnect) {
      setTimeout(() => void remdesk.connect(), 50);
    }
    remdesk.updateInteractionMode();
  }

  function bindEvents() {
    if (dom.interactionToggle) {
      dom.interactionToggle.addEventListener("change", remdesk.handleModeToggle);
    }
    if (dom.sessionModeButtons && dom.sessionModeButtons.length) {
      dom.sessionModeButtons.forEach((button) => {
        button.addEventListener("click", () => {
          remdesk.handleModeToggle(button.dataset.mode);
        });
      });
    }
    window.addEventListener("resize", () => remdesk.scheduleScreenLayout());
    document.addEventListener("pointerlockchange", remdesk.handlePointerLockChange);
    document.addEventListener("pointerlockerror", () => {
      state.cursorLocked = false;
      if (state.softLock) {
        remdesk.setSoftLock(false);
      } else {
        remdesk.updateCursorLockState();
      }
      remdesk.updateCursorOverlayVisibility();
    });
    document.addEventListener("fullscreenchange", () => {
      remdesk.updateFullscreenToggleLabel();
      remdesk.updateScreenLayout();
    });
    dom.screenEl.addEventListener("loadedmetadata", () => {
      remdesk.scheduleScreenLayout(true);
      remdesk.updateCursorBounds();
    });
    dom.screenEl.addEventListener("resize", () => {
      remdesk.scheduleScreenLayout();
      remdesk.updateCursorBounds();
    });
    if (dom.streamProfile) {
      dom.streamProfile.addEventListener("change", () => {
        remdesk.applyStreamProfile(dom.streamProfile.value, true);
      });
    }
    if (dom.sessionIdInput) {
      dom.sessionIdInput.addEventListener("input", remdesk.updateTopBar);
    }
    if (dom.serverUrlInput) {
      dom.serverUrlInput.addEventListener("input", remdesk.updateTopBar);
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
          remdesk.setStatus("E2EE key updated, reconnect", "warn");
        }
      });
    }
    dom.appButtons.forEach((button) => {
      button.addEventListener("click", () => {
        const appName = button.dataset.app;
        if (appName) {
          void remdesk.requestAppLaunch(appName);
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
        void remdesk.requestCookieExport(list);
      });
    });
    dom.connectButton.addEventListener("click", () => {
      void remdesk.connect();
    });
    if (dom.panelToggle) {
      dom.panelToggle.addEventListener("click", () => {
        remdesk.togglePanelCollapsed();
      });
    }
    if (dom.fullscreenToggle) {
      dom.fullscreenToggle.addEventListener("click", () => {
        remdesk.toggleFullscreen();
      });
    }
    if (dom.cursorVisibilityToggle) {
      dom.cursorVisibilityToggle.addEventListener("change", () => {
        remdesk.setRemoteCursorVisibility(dom.cursorVisibilityToggle.checked, true);
      });
    }
    // Hidden Desktop: Initialize input blocking toggle
    if (remdesk.initInputBlockingToggle) {
      remdesk.initInputBlockingToggle();
    }
    dom.storageToggle.addEventListener("click", () => {
      remdesk.updateDrawerOffset();
      remdesk.toggleStorage();
    });
    dom.storageClose.addEventListener("click", () => remdesk.toggleStorage(false));

    dom.remoteGo.addEventListener("click", () => {
      const nextPath = dom.remotePathInput.value.trim() || ".";
      void remdesk.requestRemoteList(nextPath);
    });

    dom.remoteUp.addEventListener("click", () => {
      void remdesk.requestRemoteList(remdesk.getParentPath(state.remoteCurrentPath));
    });

    dom.remoteRefresh.addEventListener("click", () => {
      void remdesk.requestRemoteList(state.remoteCurrentPath);
    });

    dom.remotePathInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        void remdesk.requestRemoteList(dom.remotePathInput.value.trim() || ".");
      }
    });

    window.addEventListener("resize", remdesk.updateDrawerOffset);
    window.addEventListener("resize", () => remdesk.scheduleScreenLayout());
    if (typeof ResizeObserver !== "undefined") {
      const resizeObserver = new ResizeObserver(() => {
        remdesk.scheduleScreenLayout();
      });
      resizeObserver.observe(dom.screenFrame);
    }
  }

  initDefaults();
  const shouldConnect = applyUrlParams();
  remdesk.updateTopBar();
  if (remdesk.applySessionMode) {
    remdesk.applySessionMode(state.sessionMode || "manage");
  } else {
    remdesk.updateInteractionMode();
  }
  remdesk.updateDrawerOffset();
  remdesk.updateScreenLayout();
  bindEvents();
  window.remdeskBootstrap = bootstrapFromPayload;
  window.__remdeskReady = true;
  if (window.__remdeskBootstrapPayload) {
    bootstrapFromPayload(window.__remdeskBootstrapPayload);
  }
  if (shouldConnect) {
    void remdesk.connect();
  }
})();
