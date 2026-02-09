/**
 * Remote Shell Module for Operator
 * 
 * Provides a terminal interface for executing commands on the client machine.
 * Commands are sent to the client and output is displayed locally.
 */
(() => {
  "use strict";

  const remdesk = window.remdesk || (window.remdesk = {});
  const { state } = remdesk;

  // Shell state
  const shellState = {
    sessions: {},
    activeSession: null,
    history: [],
    historyIndex: -1,
  };

  // DOM Elements
  let terminalContainer = null;
  let terminalOutput = null;
  let terminalInput = null;
  let terminalWindow = null;

  /**
   * Send shell action to client
   */
  function sendShellAction(action, payload = {}) {
    if (!state.dataChannel || state.dataChannel.readyState !== "open") {
      appendOutput("[Error] Not connected to client\n", "error");
      return false;
    }

    const message = {
      action: `shell_${action}`,
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
      console.error("Failed to send shell action:", err);
      appendOutput(`[Error] Failed to send command: ${err}\n`, "error");
      return false;
    }
  }

  /**
   * Execute a single command
   */
  function executeCommand(command, shell = "cmd") {
    if (!command.trim()) return;
    
    appendOutput(`> ${command}\n`, "command");
    
    // Add to history
    shellState.history.push(command);
    shellState.historyIndex = shellState.history.length;
    
    sendShellAction("exec", {
      command: command,
      shell: shell,
      timeout: 60
    });
  }

  /**
   * Start interactive session
   */
  function startSession(shell = "cmd") {
    appendOutput(`[Starting ${shell} session...]\n`, "info");
    sendShellAction("start", { shell: shell });
  }

  /**
   * Send input to interactive session
   */
  function sendInput(text) {
    if (!shellState.activeSession) {
      // No active session - execute as single command
      executeCommand(text);
      return;
    }
    
    appendOutput(`> ${text}\n`, "command");
    sendShellAction("input", {
      session_id: shellState.activeSession,
      text: text
    });
  }

  /**
   * Stop interactive session
   */
  function stopSession(sessionId) {
    sessionId = sessionId || shellState.activeSession;
    if (!sessionId) return;
    
    appendOutput(`[Stopping session ${sessionId}...]\n`, "info");
    sendShellAction("stop", { session_id: sessionId });
  }

  /**
   * Handle shell response from client
   */
  function handleShellResponse(payload) {
    const action = payload.action || "";

    switch (action) {
      case "shell_exec":
        if (payload.success) {
          if (payload.stdout) {
            appendOutput(payload.stdout, "stdout");
          }
          if (payload.stderr) {
            appendOutput(payload.stderr, "stderr");
          }
          if (payload.exit_code !== 0) {
            appendOutput(`[Exit code: ${payload.exit_code}]\n`, "info");
          }
        } else {
          appendOutput(`[Error] ${payload.error}\n`, "error");
        }
        break;

      case "shell_session_start":
        if (payload.success) {
          shellState.sessions[payload.session_id] = {
            id: payload.session_id,
            shell: payload.shell,
            created: Date.now()
          };
          shellState.activeSession = payload.session_id;
          appendOutput(`[Session ${payload.session_id} started (${payload.shell})]\n`, "info");
        } else {
          appendOutput(`[Error] Failed to start session: ${payload.error}\n`, "error");
        }
        break;

      case "shell_output":
        appendOutput(payload.output, "stdout");
        break;

      case "shell_session_stop":
        if (payload.success) {
          delete shellState.sessions[payload.session_id];
          if (shellState.activeSession === payload.session_id) {
            shellState.activeSession = null;
          }
          appendOutput(`[Session ${payload.session_id} stopped]\n`, "info");
        } else {
          appendOutput(`[Error] ${payload.error}\n`, "error");
        }
        break;

      case "shell_list":
        if (payload.success) {
          if (payload.sessions.length === 0) {
            appendOutput("[No active sessions]\n", "info");
          } else {
            appendOutput("[Active sessions:]\n", "info");
            payload.sessions.forEach(s => {
              appendOutput(`  ${s.session_id} (${s.shell})\n`, "info");
            });
          }
        }
        break;

      case "shell_input":
        // Input acknowledgment - no action needed
        break;

      default:
        if (action.startsWith("shell_")) {
          console.log("Unknown shell response:", payload);
        }
    }
    
    scrollToBottom();
  }

  /**
   * Append text to terminal output
   */
  function appendOutput(text, type = "stdout") {
    if (!terminalOutput) return;
    
    const span = document.createElement("span");
    span.className = `terminal-${type}`;
    span.textContent = text;
    terminalOutput.appendChild(span);
    scrollToBottom();
  }

  /**
   * Scroll terminal to bottom
   */
  function scrollToBottom() {
    if (terminalOutput) {
      terminalOutput.scrollTop = terminalOutput.scrollHeight;
    }
  }

  /**
   * Clear terminal output
   */
  function clearOutput() {
    if (terminalOutput) {
      terminalOutput.innerHTML = "";
    }
  }

  /**
   * Handle input keydown
   */
  function handleKeyDown(event) {
    if (event.key === "Enter") {
      const text = terminalInput.value.trim();
      if (text) {
        sendInput(text);
        terminalInput.value = "";
      }
    } else if (event.key === "ArrowUp") {
      // History navigation
      if (shellState.historyIndex > 0) {
        shellState.historyIndex--;
        terminalInput.value = shellState.history[shellState.historyIndex] || "";
      }
      event.preventDefault();
    } else if (event.key === "ArrowDown") {
      if (shellState.historyIndex < shellState.history.length - 1) {
        shellState.historyIndex++;
        terminalInput.value = shellState.history[shellState.historyIndex] || "";
      } else {
        shellState.historyIndex = shellState.history.length;
        terminalInput.value = "";
      }
      event.preventDefault();
    } else if (event.key === "c" && event.ctrlKey) {
      // Ctrl+C - stop session or clear input
      if (shellState.activeSession) {
        stopSession();
      } else {
        terminalInput.value = "";
      }
    } else if (event.key === "l" && event.ctrlKey) {
      // Ctrl+L - clear screen
      clearOutput();
      event.preventDefault();
    }
  }

  /**
   * Create terminal window
   */
  function createTerminalWindow() {
    if (terminalWindow) {
      terminalWindow.style.display = "flex";
      terminalInput.focus();
      return;
    }

    // Create window container
    terminalWindow = document.createElement("div");
    terminalWindow.id = "remoteTerminal";
    terminalWindow.className = "remote-terminal-window";
    terminalWindow.innerHTML = `
      <div class="terminal-header">
        <span class="terminal-title">Remote Shell</span>
        <div class="terminal-controls">
          <select id="shellTypeSelect" class="terminal-shell-select">
            <option value="cmd">CMD</option>
            <option value="powershell">PowerShell</option>
          </select>
          <button id="terminalStartSession" class="terminal-btn" title="Start Interactive Session">▶</button>
          <button id="terminalStopSession" class="terminal-btn" title="Stop Session">■</button>
          <button id="terminalClear" class="terminal-btn" title="Clear">⌫</button>
          <button id="terminalClose" class="terminal-btn terminal-close" title="Close">×</button>
        </div>
      </div>
      <div class="terminal-output" id="terminalOutput"></div>
      <div class="terminal-input-row">
        <span class="terminal-prompt">$</span>
        <input type="text" id="terminalInput" class="terminal-input" placeholder="Enter command..." autocomplete="off" spellcheck="false">
      </div>
    `;

    // Add styles
    const style = document.createElement("style");
    style.textContent = `
      .remote-terminal-window {
        position: fixed;
        bottom: 20px;
        right: 20px;
        width: 700px;
        height: 400px;
        background: #1e1e1e;
        border: 1px solid #333;
        border-radius: 8px;
        display: flex;
        flex-direction: column;
        z-index: 10000;
        font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
        box-shadow: 0 4px 20px rgba(0,0,0,0.5);
        resize: both;
        overflow: hidden;
      }
      .terminal-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 8px 12px;
        background: #2d2d2d;
        border-bottom: 1px solid #333;
        cursor: move;
      }
      .terminal-title {
        color: #0f0;
        font-weight: bold;
      }
      .terminal-controls {
        display: flex;
        gap: 8px;
        align-items: center;
      }
      .terminal-shell-select {
        background: #333;
        color: #fff;
        border: 1px solid #444;
        padding: 2px 6px;
        border-radius: 4px;
        font-size: 12px;
      }
      .terminal-btn {
        background: #333;
        color: #fff;
        border: none;
        padding: 4px 8px;
        border-radius: 4px;
        cursor: pointer;
        font-size: 14px;
      }
      .terminal-btn:hover {
        background: #444;
      }
      .terminal-close {
        color: #f55;
      }
      .terminal-close:hover {
        background: #f55;
        color: #fff;
      }
      .terminal-output {
        flex: 1;
        padding: 10px;
        overflow-y: auto;
        color: #ddd;
        font-size: 13px;
        line-height: 1.4;
        white-space: pre-wrap;
        word-wrap: break-word;
      }
      .terminal-stdout { color: #ddd; }
      .terminal-stderr { color: #f88; }
      .terminal-error { color: #f55; }
      .terminal-info { color: #5af; }
      .terminal-command { color: #0f0; }
      .terminal-input-row {
        display: flex;
        align-items: center;
        padding: 8px 10px;
        background: #2d2d2d;
        border-top: 1px solid #333;
      }
      .terminal-prompt {
        color: #0f0;
        margin-right: 8px;
        font-weight: bold;
      }
      .terminal-input {
        flex: 1;
        background: transparent;
        border: none;
        color: #fff;
        font-family: inherit;
        font-size: 13px;
        outline: none;
      }
      .terminal-input::placeholder {
        color: #666;
      }
    `;
    document.head.appendChild(style);
    document.body.appendChild(terminalWindow);

    // Get references
    terminalOutput = document.getElementById("terminalOutput");
    terminalInput = document.getElementById("terminalInput");

    // Event listeners
    terminalInput.addEventListener("keydown", handleKeyDown);
    
    document.getElementById("terminalStartSession").addEventListener("click", () => {
      const shell = document.getElementById("shellTypeSelect").value;
      startSession(shell);
    });
    
    document.getElementById("terminalStopSession").addEventListener("click", () => {
      stopSession();
    });
    
    document.getElementById("terminalClear").addEventListener("click", clearOutput);
    
    document.getElementById("terminalClose").addEventListener("click", () => {
      terminalWindow.style.display = "none";
    });

    // Make draggable
    makeDraggable(terminalWindow, terminalWindow.querySelector(".terminal-header"));

    // Initial message
    appendOutput("[Remote Shell Ready]\n", "info");
    appendOutput("[Type commands to execute on client]\n", "info");
    appendOutput("[Use Start (▶) button for interactive session]\n\n", "info");

    terminalInput.focus();
  }

  /**
   * Make element draggable
   */
  function makeDraggable(element, handle) {
    let offsetX = 0, offsetY = 0, startX = 0, startY = 0;

    handle.addEventListener("mousedown", dragStart);

    function dragStart(e) {
      e.preventDefault();
      startX = e.clientX;
      startY = e.clientY;
      document.addEventListener("mousemove", drag);
      document.addEventListener("mouseup", dragEnd);
    }

    function drag(e) {
      offsetX = startX - e.clientX;
      offsetY = startY - e.clientY;
      startX = e.clientX;
      startY = e.clientY;
      element.style.top = (element.offsetTop - offsetY) + "px";
      element.style.left = (element.offsetLeft - offsetX) + "px";
      element.style.bottom = "auto";
      element.style.right = "auto";
    }

    function dragEnd() {
      document.removeEventListener("mousemove", drag);
      document.removeEventListener("mouseup", dragEnd);
    }
  }

  /**
   * Toggle terminal visibility
   */
  function toggleTerminal() {
    if (!terminalWindow) {
      createTerminalWindow();
    } else if (terminalWindow.style.display === "none") {
      terminalWindow.style.display = "flex";
      terminalInput.focus();
    } else {
      terminalWindow.style.display = "none";
    }
  }

  /**
   * Initialize shell module
   */
  function initShell() {
    // Add keyboard shortcut (Ctrl+`)
    document.addEventListener("keydown", (e) => {
      if (e.key === "`" && e.ctrlKey) {
        toggleTerminal();
        e.preventDefault();
      }
    });

    // Add button handler
    const openBtn = document.getElementById("openTerminalBtn");
    if (openBtn) {
      openBtn.addEventListener("click", toggleTerminal);
    }

    console.log("Remote Shell module initialized (Ctrl+` to open)");
  }

  // Export
  remdesk.shell = {
    state: shellState,
    execute: executeCommand,
    startSession: startSession,
    stopSession: stopSession,
    sendInput: sendInput,
    handleResponse: handleShellResponse,
    toggle: toggleTerminal,
    clear: clearOutput,
    init: initShell,
  };

  // Auto-init
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initShell);
  } else {
    initShell();
  }
})();
