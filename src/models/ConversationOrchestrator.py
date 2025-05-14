import asyncio
import os
from typing import Optional
from lib.webrtc.Room import Room
from lib.webrtc.Peer import Peer
from lib.webrtc.SyntheticAudioTrack import SyntheticAudioTrack
from models.SpeechToText import SpeechToText
from models.TokenStreamingService import TokenStreamingService
from lib.sentence_stream import sentence_stream
from lib.text_to_speech_stream import text_to_speech_stream


class ConversationOrchestrator:

    # Constructor
    def __init__(self, context_id: str, allows_inturrptions: bool = False):
        self.context_id = context_id
        self.room: Optional[Room] = None
        self.token_streaming_service: Optional[TokenStreamingService] = None
        self.agent: Optional[object] = None
        self.peer_to_stt: dict[str, SpeechToText] = {}
        self.allows_inturrptions = allows_inturrptions
    
    # Initialize
    async def initialize(self):
        try:
            # Initialize and connect to WebRTC Room
            self.room = Room(
                room_id=self.context_id,
                signaling_server_url=os.environ["SIGNALING_SERVER_URL"],
                self_description="Agent",
                on_create_peer=self.on_create_peer,
            )
            await self.room.connect()

            # Initialize and connect to agent token streaming service
            self.token_streaming_service = TokenStreamingService(
                token_streaming_url=os.environ["TOKEN_STREAMING_SERVER_URL"],
                context_id=self.context_id,
            )
            await self.token_streaming_service.connect()
            asyncio.create_task(self.listen_to_token_stream())
        except Exception as e:
            print(f"Error initializing ConversationOrchestrator: {e}")
            raise e

    
    # Create Peer for Description - Callback used by the Room
    async def on_create_peer(self, peer_id: str, self_description: str):
        try:
            # Create a SpeechToText instance for the peer
            stt =  SpeechToText(
                on_speech_detected=lambda text: self.on_speach_detected(peer_id, text),
                silence_duration_ms=500,
            )
            await stt.connect_to_transcription_service()

            # Add to list
            self.peer_to_stt[peer_id] = stt

            # Create a new peer
            return Peer(
                peer_id=peer_id,
                self_description=self_description,
                create_data_channel=True,
                tracks=[SyntheticAudioTrack()],
                on_audio_data=self.on_audio_data, # Get data from audio stream
                on_message=lambda peer_id, message: print("WebRTC DataChanel Message", message, peer_id), # Get data from data channel
            )
        except Exception as e:
            print(f"Error creating peer {peer_id}: {e}")
            raise e
    
    # On Audio Data - Callback used by the Peers
    async def on_audio_data(self, peer_id, audio_data, sample_rate):
        try:
            # Add audio data to the SpeechToText instance
            await self.peer_to_stt[peer_id].add_audio_data(audio_data=audio_data, sample_rate=sample_rate)
        except Exception as e:
            print(f"Error processing audio data from peer {peer_id}: {e}")
            raise e

    # On Speech Detected - Callback used by the SpeechToText instance
    def on_speach_detected(self, peer_id: str, text: str):
        # Handle speech detected
        print(f"Speech detected from {peer_id}: {text}")
        
        # Send the text to the token streaming service
        asyncio.create_task(self.token_streaming_service.send_message(text))

    # Listen to the token stream
    async def listen_to_token_stream(self):
        async for full_sentence in sentence_stream(self.token_streaming_service.token_stream()):
            print(f"Full Sentence: {full_sentence}")

            # Process TTS chunks as they arrive
            async for chunk in text_to_speech_stream(full_sentence):
                for peer_id, peer in self.room.peers.items():
                    await peer.tracks[0].enqueue_audio_samples(chunk)



