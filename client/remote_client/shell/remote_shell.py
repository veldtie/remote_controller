"""Remote Shell Module.

Provides remote command execution capabilities for the operator.
Commands are executed on the client machine and output is sent back.

Supports:
- Single command execution (cmd /c, powershell -Command)
- Interactive shell sessions (PTY-like)
- Multiple concurrent shell sessions
"""
from __future__ import annotations

import asyncio
import logging
import os
import platform
import queue
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class ShellSession:
    """Represents an active shell session."""
    session_id: str
    shell_type: str  # "cmd" or "powershell"
    process: subprocess.Popen | None = None
    output_callback: Callable[[str, str], None] | None = None  # (session_id, output)
    _stop_event: threading.Event = field(default_factory=threading.Event)
    _output_thread: threading.Thread | None = None
    created_at: float = field(default_factory=time.time)
    
    @property
    def is_alive(self) -> bool:
        return self.process is not None and self.process.poll() is None


class RemoteShellManager:
    """Manages remote shell sessions and command execution."""
    
    def __init__(self):
        self._sessions: dict[str, ShellSession] = {}
        self._lock = threading.Lock()
        self._is_windows = platform.system() == "Windows"
    
    def _get_powershell_path(self) -> str:
        """Find the best available PowerShell executable.
        
        Prefers PowerShell Core (pwsh) if available, falls back to Windows PowerShell.
        """
        import shutil
        
        # Try PowerShell Core first (cross-platform, more features)
        pwsh = shutil.which("pwsh")
        if pwsh:
            return pwsh
        
        # Fall back to Windows PowerShell
        return "powershell.exe"
    
    def execute_command(self, command: str, shell_type: str = "cmd", 
                       timeout: float = 30.0, cwd: str | None = None) -> dict:
        """Execute a single command and return the result.
        
        Args:
            command: Command to execute
            shell_type: "cmd", "powershell", or "pwsh" (PowerShell Core)
            timeout: Command timeout in seconds
            cwd: Working directory
            
        Returns:
            Dict with stdout, stderr, exit_code, success
        """
        if not command:
            return {
                "action": "shell_exec",
                "success": False,
                "error": "Empty command"
            }
        
        try:
            if self._is_windows:
                if shell_type in ("powershell", "pwsh"):
                    # Get PowerShell executable
                    ps_exe = self._get_powershell_path() if shell_type == "pwsh" else "powershell.exe"
                    
                    # PowerShell execution with UTF-8 output
                    cmd = [ps_exe, "-NoProfile", "-NonInteractive", 
                           "-ExecutionPolicy", "Bypass", 
                           "-Command", f"[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; {command}"]
                else:
                    # CMD execution with UTF-8 codepage
                    cmd = ["cmd.exe", "/c", f"chcp 65001 >nul && {command}"]
                creationflags = subprocess.CREATE_NO_WINDOW
            else:
                # Linux/Unix - use PowerShell Core if requested and available
                if shell_type in ("powershell", "pwsh"):
                    import shutil
                    pwsh = shutil.which("pwsh")
                    if pwsh:
                        cmd = [pwsh, "-NoProfile", "-Command", command]
                    else:
                        # Fallback to bash
                        cmd = ["/bin/bash", "-c", command]
                else:
                    cmd = ["/bin/sh", "-c", command]
                creationflags = 0
            
            # Execute with timeout and UTF-8 encoding
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd,
                creationflags=creationflags,
                encoding='utf-8',
                errors='replace',
            )
            
            return {
                "action": "shell_exec",
                "success": True,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode,
                "command": command,
                "shell": shell_type,
            }
            
        except subprocess.TimeoutExpired:
            return {
                "action": "shell_exec",
                "success": False,
                "error": f"Command timed out after {timeout}s",
                "command": command,
            }
        except FileNotFoundError as e:
            return {
                "action": "shell_exec",
                "success": False,
                "error": f"Shell not found: {e}",
                "command": command,
            }
        except Exception as e:
            logger.error("Command execution failed: %s", e)
            return {
                "action": "shell_exec",
                "success": False,
                "error": str(e),
                "command": command,
            }
    
    def start_interactive_session(self, shell_type: str = "cmd",
                                   output_callback: Callable[[str, str], None] | None = None,
                                   cwd: str | None = None) -> dict:
        """Start an interactive shell session.
        
        Args:
            shell_type: "cmd", "powershell", or "pwsh" (PowerShell Core)
            output_callback: Callback for output (session_id, output_text)
            cwd: Working directory
            
        Returns:
            Dict with session_id and status
        """
        session_id = uuid.uuid4().hex[:8]
        
        try:
            env = os.environ.copy()
            if self._is_windows:
                if shell_type in ("powershell", "pwsh"):
                    # Get PowerShell executable
                    ps_exe = self._get_powershell_path() if shell_type == "pwsh" else "powershell.exe"
                    
                    # Set UTF-8 output encoding for PowerShell
                    cmd = [ps_exe, "-NoProfile", "-NoLogo", "-NoExit",
                           "-Command", "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; $Host.UI.RawUI.WindowTitle = 'RemDesk Shell'"]
                else:
                    # Set UTF-8 codepage for CMD
                    cmd = ["cmd.exe", "/k", "chcp 65001 >nul"]
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 0  # SW_HIDE
                creationflags = subprocess.CREATE_NO_WINDOW
            else:
                # Linux/Unix
                if shell_type in ("powershell", "pwsh"):
                    import shutil
                    pwsh = shutil.which("pwsh")
                    if pwsh:
                        cmd = [pwsh, "-NoProfile", "-NoLogo"]
                    else:
                        cmd = ["/bin/bash"]
                else:
                    cmd = ["/bin/bash"]
                startupinfo = None
                creationflags = 0
            
            # Start process with pipes and UTF-8 encoding
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=cwd,
                startupinfo=startupinfo,
                creationflags=creationflags,
                encoding='utf-8',
                errors='replace',
                env=env,
            )
            
            session = ShellSession(
                session_id=session_id,
                shell_type=shell_type,
                process=process,
                output_callback=output_callback,
            )
            
            # Start output reader thread
            session._output_thread = threading.Thread(
                target=self._read_output,
                args=(session,),
                daemon=True
            )
            session._output_thread.start()
            
            with self._lock:
                self._sessions[session_id] = session
            
            logger.info("Started interactive shell session: %s (%s)", session_id, shell_type)
            
            return {
                "action": "shell_session_start",
                "success": True,
                "session_id": session_id,
                "shell": shell_type,
            }
            
        except Exception as e:
            logger.error("Failed to start shell session: %s", e)
            return {
                "action": "shell_session_start",
                "success": False,
                "error": str(e),
            }
    
    def send_input(self, session_id: str, text: str) -> dict:
        """Send input to an interactive shell session.
        
        Args:
            session_id: Session ID
            text: Input text (will append newline if not present)
            
        Returns:
            Dict with status
        """
        with self._lock:
            session = self._sessions.get(session_id)
        
        if not session:
            return {
                "action": "shell_input",
                "success": False,
                "error": f"Session not found: {session_id}",
            }
        
        if not session.is_alive:
            return {
                "action": "shell_input",
                "success": False,
                "error": "Session has ended",
                "session_id": session_id,
            }
        
        try:
            # Ensure newline at end
            if not text.endswith("\n"):
                text += "\n"
            
            session.process.stdin.write(text)
            session.process.stdin.flush()
            
            return {
                "action": "shell_input",
                "success": True,
                "session_id": session_id,
            }
            
        except Exception as e:
            logger.error("Failed to send input to session %s: %s", session_id, e)
            return {
                "action": "shell_input",
                "success": False,
                "error": str(e),
                "session_id": session_id,
            }
    
    def stop_session(self, session_id: str) -> dict:
        """Stop an interactive shell session.
        
        Args:
            session_id: Session ID to stop
            
        Returns:
            Dict with status
        """
        with self._lock:
            session = self._sessions.pop(session_id, None)
        
        if not session:
            return {
                "action": "shell_session_stop",
                "success": False,
                "error": f"Session not found: {session_id}",
            }
        
        try:
            session._stop_event.set()
            
            if session.process and session.is_alive:
                session.process.terminate()
                try:
                    session.process.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    session.process.kill()
            
            logger.info("Stopped shell session: %s", session_id)
            
            return {
                "action": "shell_session_stop",
                "success": True,
                "session_id": session_id,
            }
            
        except Exception as e:
            logger.error("Failed to stop session %s: %s", session_id, e)
            return {
                "action": "shell_session_stop",
                "success": False,
                "error": str(e),
                "session_id": session_id,
            }
    
    def list_sessions(self) -> dict:
        """List all active shell sessions.
        
        Returns:
            Dict with list of sessions
        """
        with self._lock:
            sessions = []
            dead_sessions = []
            
            for session_id, session in self._sessions.items():
                if session.is_alive:
                    sessions.append({
                        "session_id": session_id,
                        "shell": session.shell_type,
                        "created_at": session.created_at,
                    })
                else:
                    dead_sessions.append(session_id)
            
            # Clean up dead sessions
            for session_id in dead_sessions:
                self._sessions.pop(session_id, None)
        
        return {
            "action": "shell_list",
            "success": True,
            "sessions": sessions,
        }
    
    def _read_output(self, session: ShellSession) -> None:
        """Background thread to read output from shell process."""
        try:
            while not session._stop_event.is_set() and session.is_alive:
                try:
                    # Read line with timeout simulation
                    line = session.process.stdout.readline()
                    if not line:
                        if not session.is_alive:
                            break
                        continue
                    
                    if session.output_callback:
                        session.output_callback(session.session_id, line)
                        
                except Exception as e:
                    if not session._stop_event.is_set():
                        logger.debug("Output read error for %s: %s", session.session_id, e)
                    break
                    
        except Exception as e:
            logger.debug("Output reader thread ended for %s: %s", session.session_id, e)
        
        # Send session ended notification
        if session.output_callback:
            try:
                session.output_callback(
                    session.session_id, 
                    f"\n[Session {session.session_id} ended]\n"
                )
            except Exception:
                pass
    
    def close_all(self) -> None:
        """Close all shell sessions."""
        with self._lock:
            session_ids = list(self._sessions.keys())
        
        for session_id in session_ids:
            self.stop_session(session_id)
        
        logger.info("Closed all shell sessions")
    
    def handle_action(self, action: str, payload: dict, 
                      output_callback: Callable[[str, str], None] | None = None) -> dict:
        """Handle shell action from operator.
        
        Args:
            action: Action name (without shell_ prefix)
            payload: Action payload
            output_callback: Callback for async output
            
        Returns:
            Response dict
        """
        handlers = {
            "exec": lambda: self.execute_command(
                payload.get("command", ""),
                payload.get("shell", "cmd"),
                payload.get("timeout", 30.0),
                payload.get("cwd"),
            ),
            "start": lambda: self.start_interactive_session(
                payload.get("shell", "cmd"),
                output_callback,
                payload.get("cwd"),
            ),
            "input": lambda: self.send_input(
                payload.get("session_id", ""),
                payload.get("text", ""),
            ),
            "stop": lambda: self.stop_session(
                payload.get("session_id", ""),
            ),
            "list": lambda: self.list_sessions(),
        }
        
        handler = handlers.get(action)
        if handler:
            return handler()
        
        return {
            "action": f"shell_{action}",
            "success": False,
            "error": f"Unknown shell action: {action}",
        }


# Global instance
_shell_manager: RemoteShellManager | None = None


def get_shell_manager() -> RemoteShellManager:
    """Get or create global shell manager instance."""
    global _shell_manager
    if _shell_manager is None:
        _shell_manager = RemoteShellManager()
    return _shell_manager


def handle_shell_action(action: str, payload: dict,
                        output_callback: Callable[[str, str], None] | None = None) -> dict:
    """Handle shell action - convenience function."""
    return get_shell_manager().handle_action(action, payload, output_callback)
