(() => {
  "use strict";

  const remdesk = window.remdesk;
  const { state, dom, constants, utf8Encode, utf8Decode } = remdesk;
  const {
    CONTROL_ACTION,
    E2EE_PBKDF2_ITERS,
    E2EE_SALT_PREFIX,
    SIGNALING_PING_INTERVAL_MS,
    RECONNECT_BASE_DELAY_MS,
    RECONNECT_MAX_DELAY_MS,
    RECONNECT_JITTER_MS,
    CONNECTION_READY_TIMEOUT_MS,
    CONNECTION_DROP_GRACE_MS,
    DEFAULT_ICE_SERVERS
  } = constants;

  let connectTimeoutId = null;
  let offerTimeoutId = null;

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

  function normalizeRemoteDescription(payload, expectedType = "") {
    if (!payload || typeof payload !== "object") {
      return null;
    }
    const type = payload.type;
    if (!type || (expectedType && type !== expectedType)) {
      return null;
    }
    let sdp = payload.sdp;
    if (typeof sdp !== "string") {
      return { type, sdp: "" };
    }
    sdp = sdp.trim();
    if (!sdp) {
      return { type, sdp: "" };
    }
    if (!sdp.includes("\r\n")) {
      sdp = sdp.replace(/\r?\n/g, "\r\n");
    }
    return { type, sdp };
  }

  function summarizeSdp(sdp) {
    if (!sdp || typeof sdp !== "string") {
      return { lines: 0, hasAudio: false, hasVideo: false, hasApp: false, hasSctpPort: false };
    }
    return {
      lines: sdp.split(/\r?\n/).length,
      hasAudio: /m=audio/i.test(sdp),
      hasVideo: /m=video/i.test(sdp),
      hasApp: /m=application/i.test(sdp),
      hasSctpPort: /a=sctp-port:/i.test(sdp)
    };
  }

  function formatLogDetails(details) {
    try {
      return JSON.stringify(details);
    } catch (error) {
      return String(details);
    }
  }

  function ensureChannelOpen() {
    return state.controlChannel && state.controlChannel.readyState === "open";
  }

  function clearConnectTimeout() {
    if (connectTimeoutId) {
      clearTimeout(connectTimeoutId);
      connectTimeoutId = null;
    }
  }

  function clearOfferTimeout() {
    if (offerTimeoutId) {
      clearTimeout(offerTimeoutId);
      offerTimeoutId = null;
    }
  }

  function clearConnectReadyTimeout() {
    if (state.connectReadyTimer) {
      clearTimeout(state.connectReadyTimer);
      state.connectReadyTimer = null;
    }
  }

  function clearConnectionDropTimer() {
    if (state.connectionDropTimer) {
      clearTimeout(state.connectionDropTimer);
      state.connectionDropTimer = null;
    }
  }

  async function logIceStats(reason) {
    const pc = state.peerConnection;
    if (!pc || typeof pc.getStats !== "function") {
      return;
    }
    const now = Date.now();
    if (state.lastIceStatsAt && now - state.lastIceStatsAt < 2000) {
      return;
    }
    state.lastIceStatsAt = now;
    let stats;
    try {
      stats = await pc.getStats();
    } catch (error) {
      console.warn("Failed to read ICE stats", error);
      return;
    }
    let localCount = 0;
    let remoteCount = 0;
    const candidatesById = {};
    const pairs = [];
    stats.forEach((report) => {
      if (report.type === "local-candidate") {
        localCount += 1;
        candidatesById[report.id] = report;
      } else if (report.type === "remote-candidate") {
        remoteCount += 1;
        candidatesById[report.id] = report;
      } else if (report.type === "candidate-pair") {
        pairs.push(report);
      }
    });
    const pairStates = {};
    for (const pair of pairs) {
      const key = pair.state || "unknown";
      pairStates[key] = (pairStates[key] || 0) + 1;
    }
    const selected = pairs.find((pair) => pair.nominated || pair.selected);
    const selectedLocal = selected ? candidatesById[selected.localCandidateId] : null;
    const selectedRemote = selected ? candidatesById[selected.remoteCandidateId] : null;
    console.warn("ICE stats", {
      reason,
      signaling: pc.signalingState,
      ice: pc.iceConnectionState,
      connection: pc.connectionState,
      localCandidates: localCount,
      remoteCandidates: remoteCount,
      candidatePairs: pairs.length,
      pairStates,
      selectedPair: selected
        ? {
            state: selected.state,
            nominated: selected.nominated,
            currentRoundTripTime: selected.currentRoundTripTime,
            totalRoundTripTime: selected.totalRoundTripTime,
            local: selectedLocal
              ? {
                  address: selectedLocal.address,
                  port: selectedLocal.port,
                  protocol: selectedLocal.protocol,
                  candidateType: selectedLocal.candidateType
                }
              : null,
            remote: selectedRemote
              ? {
                  address: selectedRemote.address,
                  port: selectedRemote.port,
                  protocol: selectedRemote.protocol,
                  candidateType: selectedRemote.candidateType
                }
              : null
          }
        : null
    });
  }

  function scheduleConnectionDrop(reason) {
    if (state.connectionDropTimer) {
      return;
    }
    state.connectionDropTimer = setTimeout(() => {
      state.connectionDropTimer = null;
      const pc = state.peerConnection;
      const channel = state.controlChannel;
      if (pc) {
        const connectionState = pc.connectionState;
        const iceState = pc.iceConnectionState;
        if (connectionState === "connected" || connectionState === "connecting") {
          return;
        }
        if (iceState === "connected" || iceState === "completed") {
          return;
        }
      }
      if (channel && channel.readyState === "open") {
        return;
      }
      void logIceStats(`connection_drop:${reason}`);
      remdesk.setStatus("Disconnected", "bad");
      remdesk.setConnected(false);
      remdesk.setModeLocked(false);
      state.connecting = false;
      cleanupConnection();
      scheduleReconnect(reason);
    }, CONNECTION_DROP_GRACE_MS);
  }

  function scheduleConnectReadyTimeout(signalingSocket) {
    clearConnectReadyTimeout();
    state.connectReadyTimer = setTimeout(() => {
      if (state.isConnected || state.connecting) {
        return;
      }
      if (signalingSocket !== state.signalingWebSocket) {
        return;
      }
      const shouldRetry = state.hadConnection;
      console.warn(
        "Connect ready timeout " +
          formatLogDetails({
            signalingState: state.peerConnection ? state.peerConnection.signalingState : "none",
            connectionState: state.peerConnection ? state.peerConnection.connectionState : "none",
            iceState: state.peerConnection ? state.peerConnection.iceConnectionState : "none",
            channelState: state.controlChannel ? state.controlChannel.readyState : "none"
          })
      );
      remdesk.setStatus(
        shouldRetry ? "Client not responding, retrying..." : "Client not responding",
        "warn"
      );
      void logIceStats("connect_ready_timeout");
      cleanupConnection();
      if (shouldRetry) {
        scheduleReconnect("No response");
      }
    }, CONNECTION_READY_TIMEOUT_MS);
  }

  function clearReconnectTimer() {
    if (state.reconnectTimer) {
      clearTimeout(state.reconnectTimer);
      state.reconnectTimer = null;
    }
  }

  function resetReconnectBackoff() {
    state.reconnectAttempt = 0;
    clearReconnectTimer();
  }

  function scheduleReconnect(reason = "", allowWithoutConnection = false) {
    if (!allowWithoutConnection && !state.hadConnection) {
      return;
    }
    if (state.connecting || state.isConnected) {
      return;
    }
    if (state.reconnectTimer) {
      return;
    }
    const attempt = Math.min(state.reconnectAttempt, 6);
    const baseDelay = RECONNECT_BASE_DELAY_MS * 2 ** attempt;
    const delay = Math.min(RECONNECT_MAX_DELAY_MS, baseDelay);
    const jitter = Math.floor(Math.random() * RECONNECT_JITTER_MS);
    const totalDelay = delay + jitter;
    const seconds = Math.max(1, Math.round(totalDelay / 1000));
    const prefix = reason ? `${reason}. ` : "";
    remdesk.setStatus(`${prefix}Reconnecting in ${seconds}s...`, "warn");
    state.reconnectAttempt += 1;
    state.reconnectTimer = setTimeout(() => {
      state.reconnectTimer = null;
      if (state.connecting || state.isConnected) {
        return;
      }
      void connect();
    }, totalDelay);
  }

  async function sendAction(payload) {
    if (!ensureChannelOpen()) {
      return;
    }
    try {
      const message = await encodeOutgoing(payload);
      state.controlChannel.send(message);
    } catch (error) {
      remdesk.setStatus(`E2EE error: ${error.message}`, "bad");
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
      remdesk.setStatus(`E2EE error: ${error.message}`, "bad");
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

  function buildBaseCandidates(apiBase) {
    let apiUrl;
    try {
      apiUrl = new URL(apiBase);
    } catch (error) {
      return [];
    }
    const baseOrigin = `${apiUrl.protocol}//${apiUrl.host}`;
    const path = apiUrl.pathname || "/";
    const baseWithPath = `${baseOrigin}${path.endsWith("/") ? path : `${path}/`}`;
    const baseRoot = `${baseOrigin}/`;
    if (baseWithPath === baseRoot) {
      return [baseRoot];
    }
    return [baseWithPath, baseRoot];
  }

  function buildSignalingUrls(apiBase, sessionId, operatorId, authToken) {
    let apiUrl;
    try {
      apiUrl = new URL(apiBase);
    } catch (error) {
      return [];
    }
    const wsProtocol = apiUrl.protocol === "https:" ? "wss:" : "ws:";
    const baseOrigin = `${wsProtocol}//${apiUrl.host}`;
    const path = apiUrl.pathname || "/";
    const baseWithPath = `${baseOrigin}${path.endsWith("/") ? path : `${path}/`}`;
    const baseRoot = `${baseOrigin}/`;
    const tokenParam = authToken ? `&token=${encodeURIComponent(authToken)}` : "";
    const query = `session_id=${encodeURIComponent(sessionId)}&role=browser&operator_id=${encodeURIComponent(
      operatorId
    )}${tokenParam}`;
    const primary = `${baseWithPath}ws?${query}`;
    const fallback = `${baseRoot}ws?${query}`;
    if (primary === fallback) {
      return [primary];
    }
    return [primary, fallback];
  }

  async function loadIceConfig(apiBase, authToken, preset) {
    if (Array.isArray(preset)) {
      return { iceServers: preset };
    }
    if (window.location.protocol === "file:") {
      return { iceServers: DEFAULT_ICE_SERVERS };
    }
    const headers = authToken ? { "x-rc-token": authToken } : {};
    const candidates = buildBaseCandidates(apiBase);
    for (const base of candidates) {
      const iceUrl = new URL("ice-config", base);
      if (authToken) {
        iceUrl.searchParams.set("token", authToken);
      }
      const controller = typeof AbortController !== "undefined" ? new AbortController() : null;
      const timeoutId = controller
        ? setTimeout(() => controller.abort(), 4000)
        : null;
      try {
        const response = await fetch(iceUrl.toString(), {
          headers,
          signal: controller ? controller.signal : undefined
        });
        if (!response.ok) {
          throw new Error("Failed to load ICE config");
        }
        const payload = await response.json();
        if (payload && Array.isArray(payload.iceServers)) {
          return { iceServers: payload.iceServers };
        }
      } catch (error) {
        console.warn("ICE config unavailable, trying fallback.", error);
      } finally {
        if (timeoutId) {
          clearTimeout(timeoutId);
        }
      }
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
    if (remdesk.stopMovePump) {
      remdesk.stopMovePump();
    }
    clearConnectTimeout();
    clearOfferTimeout();
    clearConnectReadyTimeout();
    clearConnectionDropTimer();
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
    state.pendingIce = [];
    if (remdesk.releasePointerLock) {
      remdesk.releasePointerLock();
    }
  }

  async function flushPendingIce() {
    if (!state.peerConnection || !state.pendingIce.length) {
      return;
    }
    const pending = state.pendingIce.slice();
    state.pendingIce.length = 0;
    for (const candidate of pending) {
      try {
        await state.peerConnection.addIceCandidate(candidate);
      } catch (error) {
        console.warn("Failed to apply queued ICE candidate", error);
      }
    }
  }

  async function connect(options = {}) {
    if (state.connecting) {
      return;
    }
    clearReconnectTimer();
    state.connecting = true;
    remdesk.setStatus("Connecting...", "warn");
    remdesk.setConnected(false);
    remdesk.setModeLocked(true);
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
      remdesk.setStatus(reason, "bad");
      remdesk.setModeLocked(false);
      state.connecting = false;
      return;
    }

    const presetIce = state.iceServersPresetSet ? state.iceServersPreset : null;
    state.allowIceFallback = false;
    state.rtcConfig = options.disableIce
      ? { iceServers: [] }
      : await loadIceConfig(apiBase, authToken, presetIce);
    const wsUrls = buildSignalingUrls(apiBase, sessionId, state.operatorId, authToken);
    const wsUrl = options.wsOverride || wsUrls[0];
    const fallbackWsUrl = options.wsOverride ? null : wsUrls[1] || null;
    if (!wsUrl) {
      remdesk.setStatus("Invalid server URL", "bad");
      remdesk.setModeLocked(false);
      state.connecting = false;
      return;
    }

    let fallbackTried = false;
    const attemptFallback = (reason) => {
      if (!state.connecting || fallbackTried || !fallbackWsUrl) {
        return false;
      }
      fallbackTried = true;
      console.warn("Signaling failed, retrying with fallback URL.", reason);
      remdesk.setStatus("Retrying connection...", "warn");
      state.connecting = false;
      void connect({ disableIce: options.disableIce, wsOverride: fallbackWsUrl });
      return true;
    };

    const signalingSocket = new WebSocket(wsUrl);
    state.signalingWebSocket = signalingSocket;
    clearConnectTimeout();
    connectTimeoutId = setTimeout(() => {
      if (signalingSocket.readyState === WebSocket.OPEN) {
        return;
      }
      if (signalingSocket !== state.signalingWebSocket) {
        return;
      }
      if (attemptFallback("timeout")) {
        return;
      }
      remdesk.setStatus("Connection timed out", "bad");
      remdesk.setConnected(false);
      remdesk.setModeLocked(false);
      state.connecting = false;
      try {
        signalingSocket.close();
      } catch (error) {
        console.warn("Failed to close signaling socket", error);
      }
    }, 8000);
    signalingSocket.onclose = (event) => {
      if (signalingSocket !== state.signalingWebSocket) {
        return;
      }
      if (event) {
        console.warn("Signaling socket closed", {
          code: event.code,
          reason: event.reason,
          wasClean: event.wasClean
        });
      }
      if (attemptFallback("close")) {
        return;
      }
      stopSignalingPing();
      clearConnectTimeout();
      clearOfferTimeout();
      clearConnectReadyTimeout();
      remdesk.setStatus("Disconnected", "bad");
      remdesk.setConnected(false);
      remdesk.setModeLocked(false);
      state.connecting = false;
      scheduleReconnect("Disconnected");
    };
    signalingSocket.onerror = (event) => {
      if (signalingSocket !== state.signalingWebSocket) {
        return;
      }
      console.warn("Signaling socket error", event);
      if (attemptFallback("error")) {
        return;
      }
      stopSignalingPing();
      clearConnectTimeout();
      clearOfferTimeout();
      clearConnectReadyTimeout();
      remdesk.setStatus("Connection failed", "bad");
      remdesk.setConnected(false);
      remdesk.setModeLocked(false);
      state.connecting = false;
      scheduleReconnect("Connection failed");
    };

    signalingSocket.onmessage = async (event) => {
      if (!state.peerConnection || signalingSocket !== state.signalingWebSocket) {
        return;
      }
      let payload;
      try {
        payload = JSON.parse(event.data);
      } catch (error) {
        payload = null;
      }
      if (!payload) {
        return;
      }
      if (payload.type === "offer") {
        console.info("Received offer", {
          hasSdp: Boolean(payload.sdp),
          session_id: payload.session_id,
          operator_id: payload.operator_id
        });
        try {
          await state.peerConnection.setRemoteDescription(payload);
        } catch (error) {
          remdesk.setStatus("Connection failed", "bad");
          console.warn("Failed to set remote offer", error);
          cleanupConnection();
          scheduleReconnect("Connection failed");
          return;
        }
        await flushPendingIce();
        const answer = await state.peerConnection.createAnswer();
        await state.peerConnection.setLocalDescription(answer);
        console.info("Sending answer", {
          hasSdp: Boolean(state.peerConnection.localDescription && state.peerConnection.localDescription.sdp)
        });
        if (signalingSocket.readyState === WebSocket.OPEN) {
          console.info(
            "Sending offer " +
              formatLogDetails(summarizeSdp(state.peerConnection.localDescription.sdp))
          );
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
        clearOfferTimeout();
        scheduleConnectReadyTimeout(signalingSocket);
        remdesk.registerControls();
      } else if (payload.type === "answer") {
        console.info("Received answer", {
          hasSdp: Boolean(payload.sdp),
          session_id: payload.session_id,
          operator_id: payload.operator_id
        });
        const normalized = normalizeRemoteDescription(payload, "answer");
        if (!normalized || !normalized.sdp) {
          console.warn("Answer missing SDP", {
            type: payload && payload.type,
            signalingState: state.peerConnection.signalingState
          });
          return;
        }
        if (state.peerConnection.signalingState !== "have-local-offer") {
          console.warn("Ignoring answer in unexpected state", {
            signalingState: state.peerConnection.signalingState
          });
          return;
        }
        try {
        console.info(
          "Applying answer " + formatLogDetails(summarizeSdp(normalized.sdp))
        );
        await state.peerConnection.setRemoteDescription(normalized);
      } catch (error) {
        const errorName = error && error.name ? error.name : "";
        const errorMessage = error && error.message ? error.message : "";
        const signalingState = state.peerConnection.signalingState;
        const sdpLength = normalized.sdp.length;
        const sdpHead = normalized.sdp.split(/\r?\n/, 1)[0] || "";
        console.warn(
          "Failed to set remote answer " +
            formatLogDetails({
              name: errorName,
              message: errorMessage,
              signalingState,
              sdpLength,
              sdpHead
            })
        );
        if (
          errorName === "InvalidStateError" ||
          /state|signaling|stable/i.test(errorMessage)
        ) {
            return;
          }
          remdesk.setStatus("Connection failed", "bad");
          cleanupConnection();
          scheduleReconnect("Connection failed");
          return;
        }
        await flushPendingIce();
        clearOfferTimeout();
        scheduleConnectReadyTimeout(signalingSocket);
        remdesk.registerControls();
      } else if (payload.type === "ice" && payload.candidate) {
        console.debug("Received ICE candidate", {
          sdpMid: payload.sdpMid,
          sdpMLineIndex: payload.sdpMLineIndex
        });
        const candidate = {
          candidate: payload.candidate,
          sdpMid: payload.sdpMid,
          sdpMLineIndex: payload.sdpMLineIndex
        };
        if (!state.peerConnection.remoteDescription) {
          state.pendingIce.push(candidate);
          return;
        }
        try {
          await state.peerConnection.addIceCandidate(candidate);
        } catch (error) {
          console.warn("Failed to add ICE candidate", error);
        }
      }
    };

    signalingSocket.onopen = async () => {
      if (signalingSocket !== state.signalingWebSocket) {
        return;
      }
      clearConnectTimeout();
      state.connecting = false;
      state.peerConnection = new RTCPeerConnection(state.rtcConfig);
      if (state.peerConnection.addEventListener) {
        state.peerConnection.addEventListener("icecandidateerror", remdesk.handleIceCandidateError);
      } else {
        state.peerConnection.onicecandidateerror = remdesk.handleIceCandidateError;
      }
      state.peerConnection.onconnectionstatechange = () => {
        if (!state.peerConnection) {
          return;
        }
        const connectionState = state.peerConnection.connectionState;
        console.info("WebRTC connection state:", connectionState, {
          ice: state.peerConnection.iceConnectionState,
          signaling: state.peerConnection.signalingState
        });
        if (connectionState === "failed") {
          void logIceStats("connection_failed");
          clearConnectionDropTimer();
          remdesk.setStatus("Connection failed", "bad");
          remdesk.setConnected(false);
          remdesk.setModeLocked(false);
          state.connecting = false;
          cleanupConnection();
          scheduleReconnect("Connection failed");
        } else if (connectionState === "disconnected") {
          remdesk.setStatus("Connection unstable, waiting...", "warn");
          scheduleConnectionDrop("Disconnected");
        } else if (connectionState === "connected") {
          clearConnectionDropTimer();
          if (state.controlChannel && state.controlChannel.readyState === "open") {
            const label = state.e2eeContext ? "Connected (E2EE)" : "Connected";
            remdesk.setStatus(label, "ok");
          }
        }
      };
      state.peerConnection.oniceconnectionstatechange = () => {
        if (!state.peerConnection) {
          return;
        }
        console.info("ICE connection state:", state.peerConnection.iceConnectionState);
        if (state.peerConnection.iceConnectionState === "failed") {
          void logIceStats("ice_failed");
        }
      };
      state.peerConnection.onicegatheringstatechange = () => {
        if (!state.peerConnection) {
          return;
        }
        console.info("ICE gathering state:", state.peerConnection.iceGatheringState);
      };
      state.peerConnection.onsignalingstatechange = () => {
        if (!state.peerConnection) {
          return;
        }
        console.info("Signaling state:", state.peerConnection.signalingState);
      };
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
        remdesk.updateScreenLayout();
      };
      state.peerConnection.onicecandidate = (event) => {
        if (event.candidate && signalingSocket.readyState === WebSocket.OPEN) {
          console.debug("Sending ICE candidate", {
            sdpMid: event.candidate.sdpMid,
            sdpMLineIndex: event.candidate.sdpMLineIndex
          });
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
        } else if (!event.candidate) {
          console.info("ICE gathering completed");
        }
      };

      state.peerConnection.addTransceiver("video", { direction: "recvonly" });
      state.peerConnection.addTransceiver("audio", { direction: "recvonly" });

      state.controlChannel = state.peerConnection.createDataChannel("control");
      state.controlChannel.onopen = () => {
        console.info(
          "Control channel open " +
            formatLogDetails({
              readyState: state.controlChannel ? state.controlChannel.readyState : "none",
              connectionState: state.peerConnection ? state.peerConnection.connectionState : "none",
              signalingState: state.peerConnection ? state.peerConnection.signalingState : "none"
            })
        );
        const label = state.e2eeContext ? "Connected (E2EE)" : "Connected";
        remdesk.setStatus(label, "ok");
        remdesk.setConnected(true);
        remdesk.setModeLocked(false);
        state.hadConnection = true;
        clearConnectionDropTimer();
        resetReconnectBackoff();
        clearOfferTimeout();
        clearConnectReadyTimeout();
        remdesk.applyStreamProfile(state.streamProfile, true);
        remdesk.scheduleStreamHint();
        remdesk.startStatsMonitor();
        remdesk.drainCookieQueue();
        remdesk.drainProxyQueue();
        void remdesk.retryPendingExport();
        remdesk.setRemoteCursorVisibility(state.remoteCursorVisible, true);
        if (state.controlEnabled) {
          void sendAction({ action: "session_config", cursor_mode: "independent" });
        } else {
          void sendAction({ action: "session_config", cursor_mode: "shared" });
        }
        if (state.storageAutostart && !dom.storageDrawer.classList.contains("open")) {
          remdesk.toggleStorage(true);
        }
        if (dom.storageDrawer.classList.contains("open")) {
          void remdesk.requestRemoteList(state.remoteCurrentPath);
        }
      };
      state.controlChannel.onclose = () => {
        console.warn(
          "Control channel closed " +
            formatLogDetails({
              connectionState: state.peerConnection ? state.peerConnection.connectionState : "none",
              signalingState: state.peerConnection ? state.peerConnection.signalingState : "none"
            })
        );
        remdesk.setStatus("Disconnected", "bad");
        remdesk.setConnected(false);
        remdesk.setModeLocked(false);
        clearConnectReadyTimeout();
        scheduleConnectionDrop("Disconnected");
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

      clearOfferTimeout();
      offerTimeoutId = setTimeout(() => {
        if (signalingSocket !== state.signalingWebSocket) {
          return;
        }
        remdesk.setStatus("Client did not answer", "bad");
        void logIceStats("offer_timeout");
        cleanupConnection();
        scheduleReconnect("No answer", true);
      }, 12000);
    };
  }

  async function handleIncomingData(data) {
    try {
      const message = await decodeIncoming(data);
      handleDataChannelMessage(message);
    } catch (error) {
      const reason = error && error.message ? error.message : "E2EE failure";
      remdesk.setStatus(reason, "bad");
      remdesk.clearStorageTimeout();
      if (state.pendingAppLaunch) {
        remdesk.setAppStatus(reason, "bad");
        state.pendingAppLaunch = null;
      } else if (state.pendingDownload) {
        if (state.pendingDownload.kind === "cookies") {
          remdesk.setCookieStatus(reason, "bad");
        }
        remdesk.setDownloadStatus(reason, "bad");
        state.pendingDownload = null;
      } else {
        remdesk.setRemoteStatus(reason, "bad");
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
        remdesk.handleError(parsed.error);
        return;
      }
      if (parsed.action === "launch_app") {
        remdesk.handleAppLaunchStatus(parsed);
        return;
      }
      if (Array.isArray(parsed.files)) {
        if (typeof parsed.path === "string") {
          state.remoteCurrentPath = parsed.path;
          dom.remotePathInput.value = parsed.path;
        }
        remdesk.handleFileList(parsed.files);
        return;
      }
    }

    if (!state.pendingDownload) {
      remdesk.setDownloadStatus("Unexpected download payload", "warn");
      return;
    }
    const isCookieDownload = state.pendingDownload.kind === "cookies";
    const completedKind = state.pendingDownload.kind;
    try {
      remdesk.saveBase64File(message, state.pendingDownload.name);
      remdesk.addDownloadEntry(state.pendingDownload.name);
      remdesk.setDownloadStatus(`Saved ${state.pendingDownload.name}`, "ok");
      if (isCookieDownload) {
        remdesk.setCookieStatus(`Saved ${state.pendingDownload.name}`, "ok");
      }
    } catch (error) {
      remdesk.setDownloadStatus("Failed to save file", "bad");
      if (isCookieDownload) {
        remdesk.setCookieStatus("Failed to save file", "bad");
      }
    } finally {
      if (
        state.pendingExport &&
        (completedKind === "cookies" || completedKind === "proxy")
      ) {
        state.pendingExport = null;
        state.pendingExportRetries = 0;
      }
      state.pendingDownload = null;
    }
  }

  remdesk.isSecureCryptoAvailable = isSecureCryptoAvailable;
  remdesk.isE2eeEnvelope = isE2eeEnvelope;
  remdesk.base64EncodeBytes = base64EncodeBytes;
  remdesk.base64DecodeBytes = base64DecodeBytes;
  remdesk.prepareE2ee = prepareE2ee;
  remdesk.encodeOutgoing = encodeOutgoing;
  remdesk.decodeIncoming = decodeIncoming;
  remdesk.ensureChannelOpen = ensureChannelOpen;
  remdesk.clearConnectTimeout = clearConnectTimeout;
  remdesk.clearOfferTimeout = clearOfferTimeout;
  remdesk.clearConnectReadyTimeout = clearConnectReadyTimeout;
  remdesk.clearConnectionDropTimer = clearConnectionDropTimer;
  remdesk.scheduleConnectionDrop = scheduleConnectionDrop;
  remdesk.scheduleConnectReadyTimeout = scheduleConnectReadyTimeout;
  remdesk.clearReconnectTimer = clearReconnectTimer;
  remdesk.resetReconnectBackoff = resetReconnectBackoff;
  remdesk.scheduleReconnect = scheduleReconnect;
  remdesk.sendAction = sendAction;
  remdesk.sendControl = sendControl;
  remdesk.sendStreamProfile = sendStreamProfile;
  remdesk.cleanupConnection = cleanupConnection;
  remdesk.connect = connect;
})();
