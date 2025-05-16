import json
import asyncio
from lib.webrtc.JSONRPCPeer import JSONRPCPeer
from lib.webrtc.SimpleWebSocketClient import SimpleWebSocketClient


class TokenStreamingService:
    def __init__(
            self,
            token_streaming_url: str,
            context_id: str
        ):
        self.token_streaming_url = token_streaming_url
        self.context_id = context_id
        self.websocket = None
        self.token_streaming_service = None
        self.token_queue: asyncio.Queue[str] = asyncio.Queue()


    async def connect(self):
        # Create a WebSocket client
        self.websocket = SimpleWebSocketClient(self.token_streaming_url)

        # Create RPC peer to interface with the token streaming service
        self.token_streaming_service = JSONRPCPeer(sender=lambda msg: asyncio.create_task(self.websocket.send(msg)))

        # Register event handlers
        self.token_streaming_service.on("on_token", self._on_token)
        self.token_streaming_service.on("on_tool_call", self._on_tool_call)
        self.token_streaming_service.on("on_tool_response", self._on_tool_response)

        # Set the message handler for the WebSocket
        self.websocket.set_on_message(self.token_streaming_service.handle_message)

        # Connect to the token streaming service
        await self.websocket.connect()
        print(f"Connected to token streaming service at {self.token_streaming_url}")

        # Send connect_to_context message
        await self.token_streaming_service.call(
            method="connect_to_context",
            params={
                "context_id": self.context_id,
                "access_token": '',  # Assuming you'll fill this in
            },
            await_response=True
        )


    async def _on_token(self, token: str, response_id: str):
        self.token_queue.put_nowait(token)
        

    async def _on_tool_call(self, tool_call_id: str, tool_name: str, tool_input: str):
        print(f"Tool call: {tool_call_id}, Tool: {tool_name}, Input: {tool_input}")

    async def _on_tool_response(self, tool_call_id: str, tool_name: str, tool_output: str):
        print(f"Tool response: {tool_call_id}, Tool: {tool_name}, Output: {tool_output}")

    async def add_message(self, message: str):
        await self.token_streaming_service.call(
            method="add_message",
            params={
                "message": message,
            }
        )

    async def token_stream(self):
        """Async generator that yields tokens as they come in."""
        while True:
            token = await self.token_queue.get()
            yield token

    def close(self):
        if self.websocket:
            asyncio.create_task(self.websocket.close())
            print("Closed token streaming service connection")
