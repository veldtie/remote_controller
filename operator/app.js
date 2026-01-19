(() => {
  "use strict";

  const CONTROL_ACTION = "control";
  const CONTROL_TYPES = {
    mouseMove: "mouse_move",
    mouseClick: "mouse_click",
    keypress: "keypress"
  };

  const state = {
    operatorId:
      typeof crypto !== "undefined" && crypto.randomUUID
        ? crypto.randomUUID()
        : `operator-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    peerConnection: null,
    controlChannel: null,
    signalingWebSocket: null,
    rtcConfig: { iceServers: [] },
    controlEnabled: true,
    modeLocked: false,
    controlsBound: false,
    remoteCurrentPath: ".",
    pendingDownload: null,
    isConnected: false
  };

  const dom = {
    statusEl: document.getElementById("status"),
    serverUrlInput: document.getElementById("serverUrl"),
    sessionIdInput: document.getElementById("sessionId"),
    authTokenInput: document.getElementById("authToken"),
    interactionToggle: document.getElementById("interactionToggle"),
    interactionState: document.getElementById("interactionState"),
    modeBadge: document.getElementById("modeBadge"),
    storageToggle: document.getElementById("storageToggle"),
    storageClose: document.getElementById("storageClose"),
    storageDrawer: document.getElementById("storageDrawer"),
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
  }

  function updateInteractionMode() {
    state.controlEnabled = dom.interactionToggle.checked;
    const label = state.controlEnabled ? "Managing" : "Viewing";
    dom.interactionState.textContent = label;
    dom.modeBadge.textContent = state.controlEnabled ? "Manage mode" : "View only";
    document.body.classList.toggle("manage-mode", state.controlEnabled);
    document.body.classList.toggle("view-mode", !state.controlEnabled);
  }

  function handleModeToggle() {
    updateInteractionMode();
    if (state.isConnected && !state.modeLocked) {
      setStatus("Switching mode...", "warn");
      connect();
    }
  }

  function ensureChannelOpen() {
    return state.controlChannel && state.controlChannel.readyState === "open";
  }

  function sendControl(payload) {
    if (!ensureChannelOpen() || !state.controlEnabled) {
      return;
    }
    state.controlChannel.send(JSON.stringify({ action: CONTROL_ACTION, ...payload }));
  }

  async function loadIceConfig(apiBase, authToken) {
    const headers = authToken ? { "x-rc-token": authToken } : {};
    try {
      const response = await fetch(`${apiBase}/ice-config`, { headers });
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
  }

  async function connect() {
    setStatus("Connecting...", "warn");
    setConnected(false);
    setModeLocked(true);
    cleanupConnection();

    const apiBase = dom.serverUrlInput.value.trim() || "http://localhost:8000";
    const sessionId = dom.sessionIdInput.value.trim() || "default-session";
    const authToken = dom.authTokenInput.value.trim();
    const sessionMode = state.controlEnabled ? "manage" : "view";

    state.rtcConfig = await loadIceConfig(apiBase, authToken);
    const apiUrl = new URL(apiBase);
    const wsProtocol = apiUrl.protocol === "https:" ? "wss:" : "ws:";
    const tokenParam = authToken ? `&token=${encodeURIComponent(authToken)}` : "";
    const wsUrl = `${wsProtocol}//${apiUrl.host}/ws?session_id=${encodeURIComponent(
      sessionId
    )}&role=browser&operator_id=${encodeURIComponent(state.operatorId)}${tokenParam}`;

    state.signalingWebSocket = new WebSocket(wsUrl);
    state.signalingWebSocket.onclose = () => {
      setStatus("Disconnected", "bad");
      setConnected(false);
      setModeLocked(false);
    };
    state.signalingWebSocket.onerror = () => {
      setStatus("Connection failed", "bad");
      setConnected(false);
      setModeLocked(false);
    };
    state.signalingWebSocket.onmessage = async (event) => {
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

    state.signalingWebSocket.onopen = async () => {
      state.peerConnection = new RTCPeerConnection(state.rtcConfig);
      state.signalingWebSocket.send(
        JSON.stringify({
          type: "register",
          session_id: sessionId,
          role: "browser",
          operator_id: state.operatorId,
          mode: sessionMode,
          token: authToken || undefined
        })
      );

      state.peerConnection.ontrack = (event) => {
        dom.screenEl.srcObject = event.streams[0];
      };
      state.peerConnection.onicecandidate = (event) => {
        if (event.candidate) {
          state.signalingWebSocket.send(
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
        setStatus("Connected", "ok");
        setConnected(true);
        setModeLocked(false);
        if (dom.storageDrawer.classList.contains("open")) {
          requestRemoteList(state.remoteCurrentPath);
        }
      };
      state.controlChannel.onclose = () => {
        setStatus("Disconnected", "bad");
        setConnected(false);
        setModeLocked(false);
      };
      state.controlChannel.onmessage = (event) => {
        handleDataChannelMessage(event.data);
      };

      const offer = await state.peerConnection.createOffer();
      await state.peerConnection.setLocalDescription(offer);

      state.signalingWebSocket.send(
        JSON.stringify({
          type: state.peerConnection.localDescription.type,
          sdp: state.peerConnection.localDescription.sdp,
          session_id: sessionId,
          operator_id: state.operatorId,
          mode: sessionMode
        })
      );
    };
  }

  function registerControls() {
    if (state.controlsBound) {
      return;
    }
    state.controlsBound = true;

    dom.screenEl.addEventListener("mousemove", (event) => {
      sendControl({
        type: CONTROL_TYPES.mouseMove,
        x: event.offsetX,
        y: event.offsetY
      });
    });

    dom.screenEl.addEventListener("click", (event) => {
      sendControl({
        type: CONTROL_TYPES.mouseClick,
        x: event.offsetX,
        y: event.offsetY,
        button: "left"
      });
    });

    window.addEventListener("keydown", (event) => {
      const activeTag = document.activeElement ? document.activeElement.tagName : "";
      if (activeTag === "INPUT" || activeTag === "TEXTAREA") {
        return;
      }
      sendControl({
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
        requestRemoteList(state.remoteCurrentPath);
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

  function requestRemoteList(path) {
    if (!ensureChannelOpen()) {
      setRemoteStatus("Data channel not ready", "warn");
      return;
    }
    state.remoteCurrentPath = path || ".";
    dom.remotePathInput.value = state.remoteCurrentPath;
    setRemoteStatus("Loading...", "warn");
    state.controlChannel.send(
      JSON.stringify({
        action: "list_files",
        path: state.remoteCurrentPath
      })
    );
  }

  function requestDownload(path) {
    if (!ensureChannelOpen()) {
      setDownloadStatus("Data channel not ready", "warn");
      return;
    }
    state.pendingDownload = {
      path,
      name: getBaseName(path)
    };
    setDownloadStatus(`Downloading ${state.pendingDownload.name}`, "warn");
    state.controlChannel.send(
      JSON.stringify({
        action: "download",
        path
      })
    );
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
          requestRemoteList(entryPath);
        });
        nameCell.appendChild(nameButton);

        const openButton = document.createElement("button");
        openButton.type = "button";
        openButton.className = "ghost small";
        openButton.textContent = "Open";
        openButton.addEventListener("click", () => {
          requestRemoteList(entryPath);
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
          requestDownload(entryPath);
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
    if (state.pendingDownload) {
      setDownloadStatus(message, "bad");
      state.pendingDownload = null;
    } else {
      setRemoteStatus(message, "bad");
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
    const hud = document.getElementById("hud");
    if (!hud) {
      return;
    }
    const hudRect = hud.getBoundingClientRect();
    const gap = 12;
    const minTop = 16;
    const maxTop = Math.max(minTop, window.innerHeight - 220);
    const nextTop = Math.min(Math.max(minTop, hudRect.bottom + gap), maxTop);
    dom.storageDrawer.style.top = `${nextTop}px`;
  }

  function bindEvents() {
    dom.interactionToggle.addEventListener("change", handleModeToggle);
    dom.connectButton.addEventListener("click", connect);
    dom.storageToggle.addEventListener("click", () => {
      updateDrawerOffset();
      toggleStorage();
    });
    dom.storageClose.addEventListener("click", () => toggleStorage(false));

    dom.remoteGo.addEventListener("click", () => {
      const nextPath = dom.remotePathInput.value.trim() || ".";
      requestRemoteList(nextPath);
    });

    dom.remoteUp.addEventListener("click", () => {
      requestRemoteList(getParentPath(state.remoteCurrentPath));
    });

    dom.remoteRefresh.addEventListener("click", () => {
      requestRemoteList(state.remoteCurrentPath);
    });

    dom.remotePathInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        requestRemoteList(dom.remotePathInput.value.trim() || ".");
      }
    });

    window.addEventListener("resize", updateDrawerOffset);
  }

  initDefaults();
  updateInteractionMode();
  updateDrawerOffset();
  bindEvents();
})();
