import os
from typing import Optional
from lib.webrtc.Room import Room
from lib.webrtc.Peer import Peer
from lib.webrtc.SyntheticAudioTrack import SyntheticAudioTrack
from lib.vad import vad
from models.SpeechToText import SpeechToText
from models.DeepgramSTT import DeepgramSTT


class ConversationOrchestrator:

    # Constructor
    def __init__(self, context_id: str):
        self.context_id = context_id
        self.room: Optional[Room] = None
        self.agent: Optional[object] = None
        self.peer_to_stt: dict[str, DeepgramSTT] = {}
        
    # Initialize
    async def initialize(self):
        # Create the room
        self.room = Room(
            room_id=self.context_id,
            signaling_server_url=os.environ["SIGNALING_SERVER_URL"],
            self_description="Agent",
            on_create_peer=self.on_create_peer,
        )
        
        # Connect to the room
        await self.room.connect()
    
    # Create Peer for Description - Callback used by the Room
    def on_create_peer(self, peer_id: str, self_description: str):
        # Create a SpeechToText instance for the peer
        # stt =  SpeechToText(
        #     on_speech_detected=lambda text: print(f"Transcription for {peer_id}: {text}"),
        #     silence_duration_ms=1000,
        # )

        stt = DeepgramSTT(
            sample_rate=48000,
            on_text=lambda text: print(f"Transcription for {peer_id}: {text}"),
            vad_threshold=0.0001,
            silence_duration_ms=1000,
        )

        # Add to list
        self.peer_to_stt[peer_id] = stt

        # Create a new peer
        return Peer(
            peer_id=peer_id,
            self_description=self_description,
            create_data_channel=True,
            tracks=[SyntheticAudioTrack()],
            on_audio_data=self.on_audio_data,
            on_message=self.on_message,
        )
    
    # On Audio Data - Callback used by the Peers
    def on_audio_data(self, peer_id, audio_data, sample_rate):
        # Get peer's SpeechToText instance
        stt = self.peer_to_stt[peer_id]

        # Add audio data to the SpeechToText instance
        stt.add_audio_data(audio_data=audio_data)
    

    # On Message - Callback used by the Peers
    def on_message(peer_id: str, message: str):
        pass