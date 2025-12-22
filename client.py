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
# Main WebRTC client
############################################

async def run():
    signaling = TcpSocketSignaling("localhost", 9999)
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

    await signaling.connect()

    offer = await signaling.receive()
    await pc.setRemoteDescription(offer)

    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)
    await signaling.send(pc.localDescription)

    while True:
        await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(run())
