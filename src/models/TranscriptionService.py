import asyncio
from typing import Callable
from lib.webrtc.SimpleWebSocketClient import SimpleWebSocketClient
from lib.webrtc.JSONRPCPeer import JSONRPCPeer

class TranscriptionService:
    # Constructor
    def __init__(
            self,
            transcription_service_url: str,
        ):
        self.transcription_service_url = transcription_service_url
        self.websocket: SimpleWebSocketClient = None
        self.rpc_layer: JSONRPCPeer = None
        self.on_connection_status_callback: Callable[[str], None] = lambda status: print(f"Connection status: {status}")
        
    # Connect
    async def connect(self):
        # Create a WebSocket client
        self.websocket = SimpleWebSocketClient(self.transcription_service_url)
        self.websocket.on("connection_status", self.on_connection_status_callback)

        # Create RPC peer to interface with the signaling server
        self.rpc_layer = JSONRPCPeer(sender=lambda msg: asyncio.create_task(self.websocket.send(msg)))

        # Set the message handler for the WebSocket
        self.websocket.on("message", self.rpc_layer.handle_message)
        
        # Connect to the signaling server
        await self.websocket.connect()

    # Event handler for connection status
    def on(self, event: str, callback: Callable):
        if event == "connection_status":
            self.on_connection_status_callback = callback
        else:
            raise ValueError(f"Unknown event: {event}")

    # Add audio data
    async def add_audio_data(self, id, audio_data):
        # Send audio data to the transcription service
        await self.rpc_layer.call("audio_data", {
            "id": id,
            "data": audio_data.tolist(),
        })

    # Cancel transcription
    async def cancel_transcription(self, id):
        # Send cancel request to the transcription service
        await self.rpc_layer.call("cancel_transcription", {
            "id": id,
        })

    # Finalize transcription
    async def finalize_transcription(self, id, sample_rate):
        # Send finalize request to the transcription service
        transciptionResponse = await self.rpc_layer.call("transcribe", {
                "id": id,
                "sample_rate": sample_rate,
            },
            await_response=True,
            timeout=10,
        )
        return transciptionResponse.get("text", None)

    def close(self):
        if self.websocket:
            asyncio.create_task(self.websocket.close())
            print("Closed token streaming service connection")


        
