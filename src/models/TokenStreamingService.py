import asyncio
from typing import Callable
from lib.webrtc.JSONRPCPeer import JSONRPCPeer
from lib.webrtc.SimpleWebSocketClient import SimpleWebSocketClient


class TokenStreamingService:
    def __init__(
            self,
            token_streaming_url: str,
            context_id: str,
        ):
        self.token_streaming_url = token_streaming_url
        self.context_id = context_id
        self.websocket = None
        self.rpc_layer = None
        self.on_connection_status_callback: Callable[[str], None] = lambda status: print(f"Connection status: {status}")
        self.on_token: Callable[[str, str], None] = lambda token, response_id: print(f"Received token: {token}, Response ID: {response_id}")
        self.on_tool_call_callback: Callable[[str, str, dict], None] = lambda call_id, tool_name, tool_input: print(f"Tool call: {call_id}, Tool: {tool_name}, Input: {tool_input}")
        self.on_tool_response_callback: Callable[[str, str], None] = lambda call_id, response: print(f"Tool response: {call_id}, Response: {response}") 


    async def connect(self):
        # Create a WebSocket client
        self.websocket = SimpleWebSocketClient(self.token_streaming_url)

        # Create RPC peer to interface with the token streaming service
        self.rpc_layer = JSONRPCPeer(sender=lambda msg: asyncio.create_task(self.websocket.send(msg)))

        # Register event handlers
        self.rpc_layer.on("on_token", self.on_token)
        self.rpc_layer.on("on_tool_call", self.on_tool_call_callback)
        self.rpc_layer.on("on_tool_response", self.on_tool_response_callback)

        # Set the message handler for the WebSocket
        self.websocket.on("message", lambda msg: asyncio.create_task(self.rpc_layer.handle_message(msg)))
        self.websocket.on("connection_status", self.on_connection_status_callback)

        # Connect to the token streaming service
        await self.websocket.connect()
        print(f"Connected to token streaming service at {self.token_streaming_url}")

        # Send connect_to_context message
        await self.rpc_layer.call(
            method="connect_to_context",
            params={
                "context_id": self.context_id,
                "access_token": '',
            }
        )

    def on(self, event: str, callback: Callable):
        if event == "token":
            self.on_token = callback
        elif event == "tool_call":
            self.on_tool_call_callback = callback
        elif event == "tool_response":
            self.on_tool_response_callback = callback
        elif event == "connection_status":
            self.on_connection_status_callback = callback
        else:
            raise ValueError(f"Unknown event: {event}")

    async def add_message(self, message: str):
        await self.rpc_layer.call("add_message", {
            "message": message,
        })

    def close(self):
        if self.websocket:
            asyncio.create_task(self.websocket.close())
            print("Closed token streaming service connection")
