(() => {
  "use strict";

  const CONTROL_ACTION = "control";
  const CONTROL_TYPES = {
    mouseMove: "mouse_move",
    mouseClick: "mouse_click",
    keypress: "keypress"
  };
  const E2EE_STORAGE_KEY = "rc_e2ee_passphrase";
  const E2EE_PBKDF2_ITERS = 150000;
  const E2EE_SALT_PREFIX = "remote-controller:";
  const textEncoder = new TextEncoder();
  const textDecoder = new TextDecoder();

  const state = {
    operatorId:
      typeof crypto !== "undefined" && crypto.randomUUID
        ? crypto.randomUUID()
        : `operator-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    peerConnection: null,
    controlChannel: null,
    signalingWebSocket: null,
    connecting: false,
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
    cursorBounds: { width: 0, height: 0 }
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
    remotePathInput: document.getElementById("remotePathInput"),
    remoteFileList: document.getElementById("remoteFileList"),
    remoteStatus: document.getElementById("remoteStatus"),
    downloadStatus: document.getElementById("downloadStatus"),
    downloadList: document.getElementById("downloadList"),
    screenEl: document.getElementById("screen"),
    connectButton: document.getElementById("connectButton"),
    remoteGo: document.getElementById("remoteGo"),
    remoteUp: document.getElementById("remoteUp"),
    remoteRefresh: document.getElementById("remoteRefresh")
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
  }

  function applyUrlParams() {
    const params = new URLSearchParams(window.location.search);
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

  function setStatus(message, stateKey = "") {
    dom.statusEl.textContent = message;
    dom.statusEl.dataset.state = stateKey;
  }

  function setRemoteStatus(message, stateKey = "") {
    dom.remoteStatus.textContent = message;
    dom.remoteStatus.dataset.state = stateKey;
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

  function setModeLocked(locked) {
    state.modeLocked = locked;
    dom.interactionToggle.disabled = locked;
    dom.interactionToggle.setAttribute("aria-disabled", locked.toString());
  }

  function setConnected(connected) {
    state.isConnected = connected;
    if (!connected) {
      setRemoteStatus("Not connected", "warn");
    }
    updateAppLaunchAvailability();
  }

  function updateInteractionMode() {
    state.controlEnabled = dom.interactionToggle.checked;
    const label = state.controlEnabled ? "Managing" : "Viewing";
    dom.interactionState.textContent = label;
    dom.modeBadge.textContent = state.controlEnabled ? "Manage mode" : "View only";
    document.body.classList.toggle("manage-mode", state.controlEnabled);
    document.body.classList.toggle("view-mode", !state.controlEnabled);
    updateAppLaunchAvailability();
    if (!state.controlEnabled) {
      releasePointerLock();
    }
  }

  function releasePointerLock() {
    if (document.pointerLockElement === dom.screenEl) {
      document.exitPointerLock();
    }
  }

  function clamp(value, min, max) {
    return Math.min(Math.max(value, min), max);
  }

  function getVideoMetrics() {
    const rect = dom.screenEl.getBoundingClientRect();
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
  }

  function setCursorFromAbsolute(clientX, clientY) {
    const coords = mapClientToVideo(clientX, clientY);
    if (!coords) {
      return null;
    }
    state.cursorX = coords.x;
    state.cursorY = coords.y;
    state.cursorInitialized = true;
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
  }

  function getCursorPosition() {
    updateCursorBounds();
    return {
      x: Math.round(state.cursorX),
      y: Math.round(state.cursorY)
    };
  }

  function handlePointerLockChange() {
    state.cursorLocked = document.pointerLockElement === dom.screenEl;
    if (!state.cursorLocked) {
      updateCursorBounds();
    }
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
      textEncoder.encode(passphrase),
      { name: "PBKDF2" },
      false,
      ["deriveKey"]
    );
    const salt = textEncoder.encode(`${E2EE_SALT_PREFIX}${sessionId}`);
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
      textEncoder.encode(plaintext)
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
    return textDecoder.decode(plaintext);
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
      return textDecoder.decode(data);
    }
    if (ArrayBuffer.isView(data)) {
      const view = data;
      return textDecoder.decode(
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
      if (payload && Array.isArray(payload.iceServers)) {
        return { iceServers: payload.iceServers };
      }
    } catch (error) {
      console.warn("ICE config unavailable, using defaults.", error);
    }
    return { iceServers: [] };
  }

  function cleanupConnection() {
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
    releasePointerLock();
  }

  async function connect() {
    if (state.connecting) {
      return;
    }
    state.connecting = true;
    setStatus("Connecting...", "warn");
    setConnected(false);
    setModeLocked(true);
    cleanupConnection();

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

    state.rtcConfig = await loadIceConfig(apiBase, authToken);
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
      setStatus("Disconnected", "bad");
      setConnected(false);
      setModeLocked(false);
      state.connecting = false;
    };
    signalingSocket.onerror = () => {
      if (signalingSocket !== state.signalingWebSocket) {
        return;
      }
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
        await state.peerConnection.setRemoteDescription(payload);
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

      state.peerConnection.ontrack = (event) => {
        dom.screenEl.srcObject = event.streams[0];
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

    dom.screenEl.addEventListener("mousemove", (event) => {
      if (state.cursorLocked) {
        return;
      }
      const coords = setCursorFromAbsolute(event.clientX, event.clientY);
      if (!coords) {
        return;
      }
      void sendControl({
        type: CONTROL_TYPES.mouseMove,
        x: coords.x,
        y: coords.y
      });
    });

    dom.screenEl.addEventListener("mousedown", () => {
      if (!state.controlEnabled || !state.isConnected) {
        return;
      }
      if (!state.cursorLocked && dom.screenEl.requestPointerLock) {
        dom.screenEl.requestPointerLock();
      }
    });

    document.addEventListener("mousemove", (event) => {
      if (!state.cursorLocked) {
        return;
      }
      setCursorFromDelta(event.movementX || 0, event.movementY || 0);
      const coords = getCursorPosition();
      void sendControl({
        type: CONTROL_TYPES.mouseMove,
        x: coords.x,
        y: coords.y
      });
    });

    dom.screenEl.addEventListener("click", (event) => {
      let coords = null;
      if (state.cursorLocked) {
        coords = getCursorPosition();
      } else {
        coords = setCursorFromAbsolute(event.clientX, event.clientY);
      }
      if (!coords) {
        return;
      }
      void sendControl({
        type: CONTROL_TYPES.mouseClick,
        x: coords.x,
        y: coords.y,
        button: "left"
      });
    });

    window.addEventListener("keydown", (event) => {
      const activeTag = document.activeElement ? document.activeElement.tagName : "";
      if (activeTag === "INPUT" || activeTag === "TEXTAREA") {
        return;
      }
      void sendControl({
        type: CONTROL_TYPES.keypress,
        key: event.key
      });
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
    try {
      const message = await encodeOutgoing({
        action: "list_files",
        path: state.remoteCurrentPath
      });
      state.controlChannel.send(message);
    } catch (error) {
      setRemoteStatus(`E2EE error: ${error.message}`, "bad");
    }
  }

  async function requestDownload(path) {
    if (!ensureChannelOpen()) {
      setDownloadStatus("Data channel not ready", "warn");
      return;
    }
    state.pendingDownload = {
      path,
      name: getBaseName(path)
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
    const message = errorPayload.message || "Unknown error";
    if (state.pendingAppLaunch) {
      setAppStatus(message, "bad");
      state.pendingAppLaunch = null;
      return;
    }
    if (state.pendingDownload) {
      setDownloadStatus(message, "bad");
      state.pendingDownload = null;
    } else {
      setRemoteStatus(message, "bad");
    }
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
      if (state.pendingAppLaunch) {
        setAppStatus(reason, "bad");
        state.pendingAppLaunch = null;
      } else if (state.pendingDownload) {
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
    try {
      saveBase64File(message, state.pendingDownload.name);
      addDownloadEntry(state.pendingDownload.name);
      setDownloadStatus(`Saved ${state.pendingDownload.name}`, "ok");
    } catch (error) {
      setDownloadStatus("Failed to save file", "bad");
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
    document.addEventListener("pointerlockchange", handlePointerLockChange);
    dom.screenEl.addEventListener("loadedmetadata", updateCursorBounds);
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
    dom.connectButton.addEventListener("click", () => {
      void connect();
    });
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
  }

  initDefaults();
  const shouldConnect = applyUrlParams();
  updateInteractionMode();
  updateDrawerOffset();
  bindEvents();
  if (shouldConnect) {
    void connect();
  }
})();
