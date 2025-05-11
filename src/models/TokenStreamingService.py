import json
import asyncio
from lib.webrtc.SimpleWebSocketClient import SimpleWebSocketClient


class TokenStreamingService:
    def __init__(self, token_streaming_url: str, context_id: str):
        self.token_streaming_url = token_streaming_url
        self.context_id = context_id
        self.websocket = None
        self.token_queue: asyncio.Queue[str] = asyncio.Queue()
        self._connected_event = asyncio.Event()

    async def connect(self):
        self.websocket = SimpleWebSocketClient(self.token_streaming_url)
        self.websocket.set_on_message(self._on_message)

        await self.websocket.connect()
        print(f"Connected to token streaming service at {self.token_streaming_url}")

        await self.websocket.send(json.dumps({
            "type": "connect_to_context",
            "context_id": self.context_id,
            "access_token": '',  # Assuming you'll fill this in
        }))

        await self._connected_event.wait()  # Wait until context_connected received

    async def _on_message(self, message):
        event = json.loads(message)

        if event.get("type") == "context_connected":
            print(f"Connected to context: {event}")
            self._connected_event.set()

        elif event.get("type") == "message":
            token = event.get("message")
            print(f"Token received: {token}")
            self.token_queue.put_nowait(token)

        elif event.get("type") == "error":
            print(f"Error: {event.get('message')}")

        elif event.get("type") == "events":
            print(f"Events: {event.get('events')}")

    async def send_message(self, message: str):
        await self.websocket.send(json.dumps({
            "type": "message",
            "message": message,
        }))

    async def token_stream(self):
        """Async generator that yields tokens as they come in."""
        while True:
            token = await self.token_queue.get()
            yield token
