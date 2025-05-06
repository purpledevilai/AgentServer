import asyncio
import websockets
from typing import Callable, Optional

class SimpleWebSocketClient:
    def __init__(self, url: str):
        self.url = url
        self.on_message: Optional[Callable[[str], None]] = None
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.listen_task: Optional[asyncio.Task] = None

    def set_on_message(self, callback: Callable[[str], None]):
        self.on_message = callback

    async def connect(self):
        try:
            self.websocket = await websockets.connect(self.url)
            self.listen_task = asyncio.create_task(self.listen())
        except Exception as e:
            print(f"Connection failed: {e}")
            raise e

    async def listen(self):
        try:
            async for message in self.websocket:
                if self.on_message:
                    await self.on_message(message)
                else:
                    print(f"Received message: {message}")
        except websockets.exceptions.ConnectionClosed:
            print("WebSocket connection closed.")
        except asyncio.CancelledError:
            print("Listening task was cancelled.")

    async def send(self, message: str):
        if self.websocket:
            await self.websocket.send(message)
        else:
            print("WebSocket is not connected.")

    async def close(self):
        if self.listen_task:
            self.listen_task.cancel()
            try:
                await self.listen_task
            except asyncio.CancelledError:
                pass

        if self.websocket:
            await self.websocket.close()
            self.websocket = None
            print("WebSocket closed.")
