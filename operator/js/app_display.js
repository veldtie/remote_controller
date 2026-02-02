(() => {
  "use strict";

  const remdesk = window.remdesk;
  const { state, dom, KEY_MAP, constants } = remdesk;
  const {
    CONTROL_TYPES,
    STREAM_PROFILES,
    CONTROL_MOVE_INTERVAL_MS,
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
    ASPECT_UPDATE_COOLDOWN_MS
  } = constants;

  function applyStreamProfile(profile, shouldSend = true) {
    if (!STREAM_PROFILES[profile]) {
      return;
    }
    state.streamProfile = profile;
    if (dom.streamProfile && dom.streamProfile.value !== profile) {
      dom.streamProfile.value = profile;
    }
    if (shouldSend) {
      void remdesk.sendStreamProfile(state.streamProfile);
      scheduleStreamHint();
    }
  }

  function releasePointerLock() {
    if (document.pointerLockElement === dom.screenFrame) {
      document.exitPointerLock();
    }
    if (state.softLock) {
      setSoftLock(false);
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
    const pixels = width * height;
    const bits = pixels * fps * NETWORK_BPP;
    return Math.round(bits / 1000);
  }

  function buildStreamHint() {
    const metrics = getVideoMetrics();
    if (!metrics) {
      return null;
    }
    const screenWidth = metrics.renderWidth;
    const screenHeight = metrics.renderHeight;
    if (!screenWidth || !screenHeight) {
      return null;
    }
    const bounds = getProfileBounds(state.streamProfile);
    const screenAspect = screenWidth / screenHeight;
    const maxHeight = Math.min(bounds.maxHeight, screenHeight);
    const minHeight = Math.min(bounds.minHeight, maxHeight);
    const targetHeight = clamp(screenHeight, minHeight, maxHeight);
    const targetWidth = Math.round(targetHeight * screenAspect);
    const hint = {
      width: targetWidth,
      height: targetHeight,
      fps: null
    };
    if (state.networkHint.height && state.networkHint.fps) {
      hint.height = clamp(
        state.networkHint.height,
        minHeight,
        maxHeight
      );
      hint.width = Math.round(hint.height * screenAspect);
      hint.fps = clamp(state.networkHint.fps, bounds.minFps, bounds.maxFps);
    }
    return hint;
  }

  function getVideoMetrics() {
    if (!dom.screenEl) {
      return null;
    }
    if (state.metricsCache) {
      return state.metricsCache;
    }
    const rect = dom.screenEl.getBoundingClientRect();
    const renderWidth = rect.width || dom.screenEl.clientWidth || 0;
    const renderHeight = rect.height || dom.screenEl.clientHeight || 0;
    const videoWidth = dom.screenEl.videoWidth || 0;
    const videoHeight = dom.screenEl.videoHeight || 0;
    state.metricsCache = {
      renderWidth,
      renderHeight,
      videoWidth,
      videoHeight
    };
    return state.metricsCache;
  }

  function updateScreenAspect(nextAspect) {
    if (!nextAspect || !Number.isFinite(nextAspect)) {
      return;
    }
    const lastAspect = state.screenAspect;
    state.screenAspect = nextAspect;
    if (!lastAspect) {
      state.lastAspectUpdateAt = performance.now();
      return;
    }
    const diff = Math.abs(nextAspect - lastAspect) / lastAspect;
    const now = performance.now();
    if (diff < ASPECT_CHANGE_SOFT_THRESHOLD) {
      return;
    }
    if (diff < ASPECT_CHANGE_THRESHOLD && now - state.lastAspectUpdateAt < ASPECT_UPDATE_COOLDOWN_MS) {
      return;
    }
    state.lastAspectUpdateAt = now;
    scheduleScreenLayout();
  }

  function scheduleScreenLayout(urgent = false) {
    if (state.layoutTimer) {
      clearTimeout(state.layoutTimer);
      state.layoutTimer = null;
    }
    const delay = urgent ? 0 : SCREEN_LAYOUT_DEBOUNCE_MS;
    state.layoutTimer = setTimeout(() => {
      state.layoutTimer = null;
      updateScreenLayout();
    }, delay);
  }

  function updateScreenLayout() {
    if (!dom.screenFrame) {
      return;
    }
    state.metricsCache = null;
    updateScreenFrameBounds();
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
      dom.screenFrame.style.removeProperty("top");
      dom.screenFrame.style.removeProperty("left");
      dom.screenFrame.style.removeProperty("width");
      dom.screenFrame.style.removeProperty("height");
      return;
    }
    const { edgeGap, workspaceLeft, workspaceBottom, availableWidth, availableHeight } =
      getWorkspaceBounds();
    dom.screenFrame.style.top = `${edgeGap}px`;
    dom.screenFrame.style.left = `${workspaceLeft}px`;
    dom.screenFrame.style.width = `${availableWidth}px`;
    dom.screenFrame.style.height = `${availableHeight}px`;
  }

  function ensureCursorOverlay() {
    if (dom.cursorOverlay) {
      return;
    }
    const overlay = document.createElement("div");
    overlay.className = "cursor-overlay";
    dom.cursorOverlay = overlay;
    if (dom.screenFrame) {
      dom.screenFrame.appendChild(overlay);
    }
    updateCursorOverlayPosition();
  }

  function updateCursorOverlayVisibility() {
    if (!dom.cursorOverlay) {
      return;
    }
    const show = state.isConnected && state.controlEnabled && !state.remoteCursorVisible;
    dom.cursorOverlay.classList.toggle("visible", Boolean(show));
  }

  function setRemoteCursorVisibility(visible, shouldSend = true) {
    const next = Boolean(visible);
    state.remoteCursorVisible = next;
    if (dom.cursorVisibilityToggle && dom.cursorVisibilityToggle.checked !== next) {
      dom.cursorVisibilityToggle.checked = next;
    }
    if (remdesk.updateRemoteCursorVisibilityAvailability) {
      remdesk.updateRemoteCursorVisibilityAvailability();
    }
    updateCursorOverlayVisibility();
    if (shouldSend) {
      void remdesk.sendControl({
        type: "toggle_virtual_cursor",
        visible: next
      });
    }
  }

  function updateCursorOverlayPosition() {
    if (!dom.cursorOverlay || !state.cursorInitialized) {
      return;
    }
    const metrics = getVideoMetrics();
    if (!metrics) {
      return;
    }
    const scaleX = metrics.renderWidth / metrics.videoWidth;
    const scaleY = metrics.renderHeight / metrics.videoHeight;
    const x = Math.round(state.cursorX * scaleX);
    const y = Math.round(state.cursorY * scaleY);
    dom.cursorOverlay.style.transform = `translate(${x}px, ${y}px)`;
  }

  function setCursorFromAbsolute(event) {
    const metrics = getVideoMetrics();
    if (!metrics) {
      return;
    }
    const rect = dom.screenEl.getBoundingClientRect();
    const relativeX = event.clientX - rect.left;
    const relativeY = event.clientY - rect.top;
    const scaleX = metrics.videoWidth / metrics.renderWidth;
    const scaleY = metrics.videoHeight / metrics.renderHeight;
    state.cursorX = clamp(Math.round(relativeX * scaleX), 0, metrics.videoWidth - 1);
    state.cursorY = clamp(Math.round(relativeY * scaleY), 0, metrics.videoHeight - 1);
    state.cursorInitialized = true;
    updateCursorOverlayPosition();
  }

  function normalizeWheelDelta(value, mode) {
    if (!value) {
      return 0;
    }
    if (mode === 1) {
      return value * 16;
    }
    if (mode === 2) {
      return value * 120;
    }
    return value;
  }

  function mapMouseButton(button) {
    if (button === 2) {
      return "right";
    }
    if (button === 1) {
      return "middle";
    }
    if (button === 3) {
      return "x1";
    }
    if (button === 4) {
      return "x2";
    }
    return "left";
  }

  function normalizeKeyEvent(event) {
    if (!event || !event.key) {
      return null;
    }
    if (KEY_MAP[event.key]) {
      return KEY_MAP[event.key];
    }
    if (event.key.length === 1) {
      return event.key;
    }
    return event.key.toLowerCase();
  }

  function getStreamHintSize() {
    const metrics = getVideoMetrics();
    if (!metrics) {
      return null;
    }
    if (!metrics.renderWidth || !metrics.renderHeight) {
      return null;
    }
    return {
      width: metrics.renderWidth,
      height: metrics.renderHeight
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
      void remdesk.sendStreamProfile(state.streamProfile, hint.width, hint.height, hint.fps);
    }, STREAM_HINT_DEBOUNCE_MS);
  }

  function stopStatsMonitor() {
    if (state.statsTimer) {
      clearInterval(state.statsTimer);
      state.statsTimer = null;
    }
    state.netStats = null;
  }

  function handleIceCandidateError(event) {
    if (!event || !event.url) {
      return;
    }
    const url = event.url || "";
    if (!url.startsWith("stun:") && !url.startsWith("turn:") && !url.startsWith("turns:")) {
      return;
    }
    console.warn("ICE candidate error", {
      url: event.url,
      errorCode: event.errorCode,
      errorText: event.errorText,
      address: event.address,
      port: event.port
    });
    state.iceErrorCount += 1;
    if (state.iceFallbackTried || state.isConnected) {
      return;
    }
    if (!state.allowIceFallback) {
      return;
    }
    if (state.iceErrorCount < 2) {
      return;
    }
    state.iceFallbackTried = true;
    remdesk.setStatus("ICE failed, retrying without ICE", "warn");
    void remdesk.connect({ disableIce: true });
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

    if (lossRate > LOSS_DEGRADE || (rttMs && rttMs > RTT_DEGRADE)) {
      if (performance.now() - state.netLastAdaptAt > NETWORK_ADAPT_COOLDOWN_MS) {
        state.netLastAdaptAt = performance.now();
        if (targetFps > bounds.minFps) {
          targetFps = clamp(targetFps - 5, bounds.minFps, bounds.maxFps);
        } else {
          targetHeight = clamp(
            Math.round(targetHeight * PROFILE_HEIGHT_DOWN_SCALE),
            bounds.minHeight,
            bounds.maxHeight
          );
        }
      }
    } else if (lossRate < LOSS_UPGRADE && (!rttMs || rttMs < RTT_UPGRADE)) {
      if (performance.now() - state.netLastAdaptAt > NETWORK_ADAPT_COOLDOWN_MS) {
        state.netLastAdaptAt = performance.now();
        if (targetHeight < bounds.maxHeight) {
          targetHeight = clamp(
            Math.round(targetHeight * PROFILE_HEIGHT_UP_SCALE),
            bounds.minHeight,
            bounds.maxHeight
          );
        } else {
          targetFps = clamp(targetFps + 5, bounds.minFps, bounds.maxFps);
        }
      }
    }

    const ratio = expectedKbps ? bitrateKbps / expectedKbps : null;
    if (ratio && ratio < 0.8) {
      targetHeight = clamp(
        Math.round(targetHeight * PROFILE_HEIGHT_DOWN_SCALE),
        bounds.minHeight,
        bounds.maxHeight
      );
    } else if (ratio && ratio > 1.2) {
      targetHeight = clamp(
        Math.round(targetHeight * PROFILE_HEIGHT_UP_SCALE),
        bounds.minHeight,
        bounds.maxHeight
      );
    }

    state.netTargetHeight = targetHeight;
    state.netTargetFps = targetFps;
    state.networkHint = {
      height: targetHeight,
      fps: targetFps
    };
    scheduleStreamHint();
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
    const videoWidth = dom.screenEl.videoWidth;
    const videoHeight = dom.screenEl.videoHeight;
    if (videoWidth && videoHeight) {
      updateScreenAspect(videoWidth / videoHeight);
    }
    updateCursorOverlayPosition();
  }

  function getRelativeDelta(event) {
    const dx = event.movementX || 0;
    const dy = event.movementY || 0;
    if (dx || dy) {
      state.lastLocalX = event.clientX;
      state.lastLocalY = event.clientY;
      return { dx, dy };
    }
    if (state.lastLocalX === null || state.lastLocalY === null) {
      return { dx: 0, dy: 0 };
    }
    const deltaX = event.clientX - state.lastLocalX;
    const deltaY = event.clientY - state.lastLocalY;
    state.lastLocalX = event.clientX;
    state.lastLocalY = event.clientY;
    return { dx: deltaX, dy: deltaY };
  }

  function applyRelativeMove(event) {
    if (!state.isConnected) {
      return false;
    }
    const delta = getRelativeDelta(event);
    if (!delta.dx && !delta.dy) {
      return false;
    }
    if (!state.cursorInitialized) {
      updateCursorBounds();
    }
    setCursorFromDelta(delta.dx, delta.dy);
    scheduleMoveSend();
    return true;
  }

  function maybeStartDrag() {
    if (!state.dragState.active || state.dragState.dragging) {
      return;
    }
    const dx = state.cursorX - state.dragState.startX;
    const dy = state.cursorY - state.dragState.startY;
    const threshold = 3;
    if (Math.abs(dx) < threshold && Math.abs(dy) < threshold) {
      return;
    }
    state.dragState.dragging = true;
    void remdesk.sendControl({
      type: CONTROL_TYPES.mouseDown,
      x: Math.round(state.dragState.startX),
      y: Math.round(state.dragState.startY),
      button: state.dragState.button
    });
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
      if (state.softLock) {
        setSoftLock(false);
      }
    }
    updateCursorLockState();
    updateCursorOverlayVisibility();
  }

  function shouldUsePointerLock() {
    return !document.body.classList.contains("desktop-mode");
  }

  function updateCursorLockState() {
    const locked = state.cursorLocked || state.softLock;
    document.body.classList.toggle("cursor-locked", locked);
  }

  function setSoftLock(active) {
    state.softLock = Boolean(active);
    updateCursorLockState();
  }

  function startMovePump() {
    if (state.movePumpId) {
      return;
    }
    const pump = () => {
      state.movePumpId = requestAnimationFrame(pump);
      if (!state.isConnected || !state.controlEnabled) {
        state.cursorDirty = false;
        return;
      }
      if (!state.cursorDirty) {
        return;
      }
      const now = performance.now();
      if (now - state.lastMoveSentAt < CONTROL_MOVE_INTERVAL_MS) {
        return;
      }
      if (!state.cursorInitialized) {
        updateCursorBounds();
      }
      const coords = {
        x: Math.round(state.cursorX),
        y: Math.round(state.cursorY)
      };
      const last = state.lastSentPosition;
      if (last && last.x === coords.x && last.y === coords.y) {
        state.cursorDirty = false;
        return;
      }
      const metrics = getVideoMetrics();
      const sourceWidth = metrics ? metrics.videoWidth : null;
      const sourceHeight = metrics ? metrics.videoHeight : null;
      state.lastSentPosition = coords;
      state.lastMoveSentAt = now;
      state.cursorDirty = false;
      void remdesk.sendControl({
        type: CONTROL_TYPES.mouseMove,
        x: coords.x,
        y: coords.y,
        source_width: sourceWidth || undefined,
        source_height: sourceHeight || undefined
      });
    };
    state.movePumpId = requestAnimationFrame(pump);
  }

  function stopMovePump() {
    if (state.movePumpId) {
      cancelAnimationFrame(state.movePumpId);
      state.movePumpId = null;
    }
    state.cursorDirty = false;
  }

  function scheduleMoveSend() {
    state.cursorDirty = true;
    startMovePump();
  }

  function scheduleSingleClick(position, button) {
    if (state.clickTimer) {
      clearTimeout(state.clickTimer);
    }
    state.clickTimer = setTimeout(() => {
      state.clickTimer = null;
      void remdesk.sendControl({
        type: CONTROL_TYPES.mouseClick,
        x: position.x,
        y: position.y,
        button,
        count: 1
      });
    }, 240);
  }

  function handleModeToggle() {
    remdesk.updateInteractionMode();
    if (state.isConnected && !state.modeLocked) {
      remdesk.setStatus("Switching mode...", "warn");
      void remdesk.connect();
    }
  }

  function registerControls() {
    if (state.controlsBound) {
      return;
    }
    state.controlsBound = true;
    dom.screenFrame.setAttribute("tabindex", "0");

    dom.screenFrame.addEventListener("mousemove", (event) => {
      if (!state.controlEnabled || !state.isConnected) {
        return;
      }
      if (state.cursorLocked || state.softLock) {
        if (!applyRelativeMove(event)) {
          setCursorFromAbsolute(event);
          scheduleMoveSend();
        }
        maybeStartDrag();
        return;
      }
      setCursorFromAbsolute(event);
      scheduleMoveSend();
      maybeStartDrag();
    });

    dom.screenFrame.addEventListener("mousedown", (event) => {
      if (!state.controlEnabled || !state.isConnected) {
        return;
      }
      if (event.button === 0 && shouldUsePointerLock()) {
        dom.screenFrame.requestPointerLock();
      }
      const position = getCursorPosition();
      const button = mapMouseButton(event.button);
      state.mouseButtonsDown.add(button);
      state.dragState = {
        active: true,
        dragging: false,
        wasDrag: false,
        button,
        startX: position.x,
        startY: position.y
      };
    });

    const handleMouseUp = (event) => {
      if (!state.controlEnabled || !state.isConnected) {
        return;
      }
      const position = getCursorPosition();
      const button = mapMouseButton(event.button);
      if (!state.mouseButtonsDown.has(button)) {
        return;
      }
      state.mouseButtonsDown.delete(button);
      if (state.dragState.active && state.dragState.button === button && state.dragState.dragging) {
        state.dragState.wasDrag = true;
        void remdesk.sendControl({
          type: CONTROL_TYPES.mouseUp,
          x: position.x,
          y: position.y,
          button
        });
      } else if (state.dragState.active && state.dragState.button === button) {
        state.dragState.wasDrag = false;
      }
      state.dragState.active = false;
      state.dragState.dragging = false;
    };

    dom.screenFrame.addEventListener("mouseup", handleMouseUp);
    window.addEventListener("mouseup", handleMouseUp);

    dom.screenFrame.addEventListener("click", (event) => {
      if (!state.controlEnabled || !state.isConnected) {
        return;
      }
      if (state.dragState.wasDrag) {
        state.dragState.wasDrag = false;
        return;
      }
      if (event.detail && event.detail > 1) {
        return;
      }
      const position = getCursorPosition();
      const button = mapMouseButton(event.button);
      scheduleSingleClick(position, button);
    });

    dom.screenFrame.addEventListener("contextmenu", (event) => {
      if (!state.controlEnabled || !state.isConnected) {
        return;
      }
      event.preventDefault();
      const position = getCursorPosition();
      void remdesk.sendControl({
        type: CONTROL_TYPES.mouseClick,
        x: position.x,
        y: position.y,
        button: "right",
        count: 1
      });
    });

    dom.screenFrame.addEventListener("wheel", (event) => {
      if (!state.controlEnabled || !state.isConnected) {
        return;
      }
      event.preventDefault();
      const position = getCursorPosition();
      const deltaX = normalizeWheelDelta(event.deltaX, event.deltaMode);
      const deltaY = normalizeWheelDelta(event.deltaY, event.deltaMode);
      void remdesk.sendControl({
        type: CONTROL_TYPES.mouseScroll,
        x: position.x,
        y: position.y,
        delta_x: deltaX,
        delta_y: deltaY
      });
    }, { passive: false });

    dom.screenFrame.addEventListener("dblclick", (event) => {
      if (!state.controlEnabled || !state.isConnected) {
        return;
      }
      if (document.fullscreenElement === dom.screenFrame) {
        document.exitFullscreen();
        return;
      }
      if (event.shiftKey) {
        dom.screenFrame.requestFullscreen().catch(() => {
          remdesk.setStatus("Fullscreen failed", "bad");
        });
        return;
      }
      if (state.dragState.wasDrag) {
        state.dragState.wasDrag = false;
        return;
      }
      if (state.clickTimer) {
        clearTimeout(state.clickTimer);
        state.clickTimer = null;
      }
      const position = getCursorPosition();
      const button = mapMouseButton(event.button);
      void remdesk.sendControl({
        type: CONTROL_TYPES.mouseClick,
        x: position.x,
        y: position.y,
        button,
        count: 2
      });
    });

    dom.screenFrame.addEventListener("keydown", (event) => {
      if (!state.controlEnabled || !state.isConnected) {
        return;
      }
      const key = normalizeKeyEvent(event);
      if (!key) {
        return;
      }
      event.preventDefault();
      if (key.length === 1 && state.textInputSupported) {
        void remdesk.sendControl({
          type: CONTROL_TYPES.text,
          text: key
        });
        return;
      }
      void remdesk.sendControl({
        type: CONTROL_TYPES.keypress,
        key
      });
    });
  }

  remdesk.applyStreamProfile = applyStreamProfile;
  remdesk.releasePointerLock = releasePointerLock;
  remdesk.clamp = clamp;
  remdesk.getProfileBounds = getProfileBounds;
  remdesk.computeExpectedBitrateKbps = computeExpectedBitrateKbps;
  remdesk.buildStreamHint = buildStreamHint;
  remdesk.getVideoMetrics = getVideoMetrics;
  remdesk.updateScreenAspect = updateScreenAspect;
  remdesk.scheduleScreenLayout = scheduleScreenLayout;
  remdesk.updateScreenLayout = updateScreenLayout;
  remdesk.getWorkspaceBounds = getWorkspaceBounds;
  remdesk.updateScreenFrameBounds = updateScreenFrameBounds;
  remdesk.ensureCursorOverlay = ensureCursorOverlay;
  remdesk.updateCursorOverlayVisibility = updateCursorOverlayVisibility;
  remdesk.setRemoteCursorVisibility = setRemoteCursorVisibility;
  remdesk.updateCursorOverlayPosition = updateCursorOverlayPosition;
  remdesk.setCursorFromAbsolute = setCursorFromAbsolute;
  remdesk.normalizeWheelDelta = normalizeWheelDelta;
  remdesk.mapMouseButton = mapMouseButton;
  remdesk.normalizeKeyEvent = normalizeKeyEvent;
  remdesk.getStreamHintSize = getStreamHintSize;
  remdesk.scheduleStreamHint = scheduleStreamHint;
  remdesk.stopStatsMonitor = stopStatsMonitor;
  remdesk.handleIceCandidateError = handleIceCandidateError;
  remdesk.startStatsMonitor = startStatsMonitor;
  remdesk.updateCursorBounds = updateCursorBounds;
  remdesk.getRelativeDelta = getRelativeDelta;
  remdesk.applyRelativeMove = applyRelativeMove;
  remdesk.setCursorFromDelta = setCursorFromDelta;
  remdesk.getCursorPosition = getCursorPosition;
  remdesk.handlePointerLockChange = handlePointerLockChange;
  remdesk.shouldUsePointerLock = shouldUsePointerLock;
  remdesk.updateCursorLockState = updateCursorLockState;
  remdesk.setSoftLock = setSoftLock;
  remdesk.startMovePump = startMovePump;
  remdesk.stopMovePump = stopMovePump;
  remdesk.scheduleMoveSend = scheduleMoveSend;
  remdesk.handleModeToggle = handleModeToggle;
  remdesk.registerControls = registerControls;
})();
