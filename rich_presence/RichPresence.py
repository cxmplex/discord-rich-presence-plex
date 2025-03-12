import asyncio
import json
import os
import struct
import subprocess
import sys
import tempfile
import time


class RichPresence:
    is_linux = sys.platform in ["linux", "darwin"]

    def __init__(self, client_id, child):
        self.loop = asyncio.new_event_loop() if self.is_linux else asyncio.ProactorEventLoop()
        self.IPCPipe = ((os.environ.get("XDG_RUNTIME_DIR", None) or os.environ.get("TMPDIR", None) or os.environ.get(
            "TMP", None) or os.environ.get("TEMP",
                                           None) or "/tmp") + "/discord-ipc-0") if self.is_linux else "\\\\?\\pipe\\discord-ipc-0"
        self.clientID = client_id
        self.pipeReader = None
        self.pipeWriter = None
        self.process = None
        self.running = False
        self.child = child

    async def read(self):
        try:
            data = await self.pipeReader.read(1024)
            self.child.log("[READ] " + str(json.loads(data[8:].decode("utf-8"))))
        except Exception as e:
            self.child.log("[READ] " + str(e))
            self.stop()

    def write(self, op, payload):
        payload = json.dumps(payload)
        self.child.log("[WRITE] " + str(payload))
        data = self.pipeWriter.write(struct.pack("<ii", op, len(payload)) + payload.encode("utf-8"))

    async def handshake(self):
        try:
            if self.is_linux:
                self.pipeReader, self.pipeWriter = await asyncio.open_unix_connection(self.IPCPipe, loop=self.loop)
            else:
                self.pipeReader = asyncio.StreamReader(loop=self.loop)
                self.pipeWriter, _ = await self.loop.create_pipe_connection(
                    lambda: asyncio.StreamReaderProtocol(self.pipeReader, loop=self.loop), self.IPCPipe)
            self.write(0, {"v": 1, "client_id": self.clientID})
            await self.read()
            self.running = True
        except Exception as e:
            self.child.log("[HANDSHAKE] " + str(e))

    def start(self):
        self.child.log("Opening Discord IPC Pipe")
        empty_process_file_path = tempfile.gettempdir() + (
            "/" if self.is_linux else "\\") + "discordRichPresencePlex-emptyProcess.py"
        if not os.path.exists(empty_process_file_path):
            with open(empty_process_file_path, "w") as emptyProcessFile:
                emptyProcessFile.write("import time\n\ntry:\n\twhile (True):\n\t\ttime.sleep(3600)\nexcept:\n\tpass")
        self.process = subprocess.Popen(["python3" if self.is_linux else "pythonw", empty_process_file_path])
        self.loop.run_until_complete(self.handshake())

    def stop(self):
        self.child.log("Closing Discord IPC Pipe")
        self.child.lastState, self.child.lastSessionKey, self.child.lastRatingKey = None, None, None
        self.process.kill()

        if self.child.stopTimer:
            self.child.stopTimer.cancel()
            self.child.stopTimer = None

        if self.child.stopTimer2:
            self.child.stopTimer2.cancel()
            self.child.stopTimer2 = None

        if self.pipeWriter:
            try:
                self.pipeWriter.close()
            except:
                pass
            self.pipeWriter = None
        if self.pipeReader:
            try:
                self.loop.run_until_complete(self.pipeReader.read(1024))
            except:
                pass
            self.pipeReader = None
        try:
            self.loop.close()
        except:
            pass
        self.running = False

    def send(self, activity):
        payload = {
            "cmd": "SET_ACTIVITY",
            "args": {
                "activity": activity,
                "pid": self.process.pid
            },
            "nonce": "{0:.20f}".format(time.time())
        }
        self.write(1, payload)
        self.loop.run_until_complete(self.read())
