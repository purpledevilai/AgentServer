import asyncio
from lib.webrtc.SimpleWebSocketClient import SimpleWebSocketClient
from lib.webrtc.JSONRPCPeer import JSONRPCPeer

class TranscriptionService:
    # Constructor
    def __init__(
            self,
            transcription_service_url: str,
        ):
        self.transcription_service_url = transcription_service_url
        self.transcription_service = None
        self.websocket = None
        
    # Connect
    async def connect(self):
        # Create a WebSocket client
        self.websocket = SimpleWebSocketClient(self.transcription_service_url)

        # Create RPC peer to interface with the signaling server
        self.transcription_service = JSONRPCPeer(sender=lambda msg: asyncio.create_task(self.websocket.send(msg)))

        # Register signaling event handlers
        # self.transcription_service.on("live_text", self.on_live_text)

        # Set the message handler for the WebSocket
        self.websocket.set_on_message(self.transcription_service.handle_message)
        
        # Connect to the signaling server
        await self.websocket.connect()

    # Add audio data
    async def add_audio_data(self, id, audio_data):
        # Send audio data to the transcription service
        await self.transcription_service.call(
            method="audio_data",
            params={
                "id": id,
                "data": audio_data.tolist(),
            }
        )

    # Cancel transcription
    async def cancel_transcription(self, id):
        # Send cancel request to the transcription service
        await self.transcription_service.call(
            method="cancel_transcription",
            params={
                "id": id,
            }
        )

    # Finalize transcription
    async def finalize_transcription(self, id, sample_rate):
        # Send finalize request to the transcription service
        transciptionResponse = await self.transcription_service.call(
            method="transcribe",
            params={
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


        
