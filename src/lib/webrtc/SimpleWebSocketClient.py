import asyncio
import websockets
from typing import Callable, Optional

class SimpleWebSocketClient:
    def __init__(self, url: str):
        self.url = url
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.listen_task: Optional[asyncio.Task] = None
        self.on_message_callback: Optional[Callable[[str], None]] = lambda msg: print(f"Received message: {msg}")
        self.on_connection_status_callback: Optional[Callable[[str], None]] = lambda status: print(f"Connection status: {status}")


    async def connect(self):
        try:
            self.websocket = await websockets.connect(self.url)
            self.listen_task = asyncio.create_task(self.listen())
            await self.on_connection_status_callback("connected")
        except Exception as e:
            print(f"Connection failed: {e}")
            await self.on_connection_status_callback("failed")
            raise e
        
    def on(self, event: str, callback: Callable):
        if event == "message":
            self.on_message_callback = callback
        elif event == "connection_status":
            self.on_connection_status_callback = callback
        else:
            raise ValueError(f"Unknown event: {event}")

    async def listen(self):
        try:
            async for message in self.websocket:
                await self.on_message_callback(message)
        except websockets.exceptions.ConnectionClosed:
            print("WebSocket connection closed.")
            await self.on_connection_status_callback("disconnected")
        except asyncio.CancelledError:
            print("Listening task was cancelled.")
            await self.on_connection_status_callback("disconnected")

    async def send(self, message: str):
        if self.websocket:
            await self.websocket.send(message)
        
    async def close(self):
        if self.listen_task:
            self.listen_task.cancel()
            try:
                await self.listen_task
            except asyncio.CancelledError:
                pass

        if self.websocket:
            await self.websocket.close()
            await self.on_connection_status_callback("disconnected")
            self.websocket = None
            print("WebSocket closed.")
