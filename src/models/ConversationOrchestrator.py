import asyncio
import os
from typing import Optional
from lib.webrtc.Room import Room
from lib.webrtc.Peer import Peer
from lib.webrtc.SyntheticAudioTrack import SyntheticAudioTrack
from models.SoundCalibrator import SoundCalibrator
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
        self.peer_to_calibration: dict[str, SoundCalibrator] = {}
        self.peer_to_media_stream: dict[str, SyntheticAudioTrack] = {}
        self.allows_inturrptions = allows_inturrptions
        self.has_calibrated = False
    
    # Initialize
    async def initialize(self):
        try:
            # Initialize and connect to WebRTC Room
            self.room = Room(
                room_id=self.context_id,
                signaling_server_url=os.environ["SIGNALING_SERVER_URL"],
                self_description="Agent",
                on_create_peer=self.on_create_peer,
                on_peer_disconnected=self.on_peer_disconnected,
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
                silence_duration_ms=1000,
                vad_threshold=0.001,
            )
            await stt.connect_to_transcription_service()
            self.peer_to_stt[peer_id] = stt

            # Create SoundCalibrator instance
            calibrator = SoundCalibrator(
                on_measurement=lambda energy: self.on_calibration_measurement(peer_id, energy),
            )
            self.peer_to_calibration[peer_id] = calibrator

            # Create a SyntheticAudioTrack instance for the peer
            audioTrack = SyntheticAudioTrack()
            self.peer_to_media_stream[peer_id] = audioTrack

            # Create a new peer
            return Peer(
                peer_id=peer_id,
                self_description=self_description,
                tracks=[audioTrack],
                on_audio_data=self.on_audio_data, # Get data from audio stream
                on_data_channel_open=self.on_peer_data_channel_open,
            )
        except Exception as e:
            print(f"Error creating peer {peer_id}: {e}")
            raise e
        
    # On Peer Data Channel Open 
    def on_peer_data_channel_open(self, peer_id: str):
        # Send calibrating message to the peer
        peer = self.room.peers[peer_id]
        print(f"Data channel opened for peer {peer_id}")
        asyncio.create_task(
            peer.rpc_peer.call("calibration_start", {
                "message": "Calibration started. Please speak for a few seconds."
            })
        )
        
    # On Peer Disconnected - Callback used by the Room
    def on_peer_disconnected(self, peer_id: str):
        # Handle peer disconnection
        print(f"Peer {peer_id} disconnected")
        
        # Remove the SpeechToText instance for the peer
        if peer_id in self.peer_to_stt:
            self.peer_to_stt[peer_id].close()
            del self.peer_to_stt[peer_id]
            print(f"Removed SpeechToText instance for peer {peer_id}")

        # Remove the SoundCalibrator instance for the peer
        if peer_id in self.peer_to_calibration:
            del self.peer_to_calibration[peer_id]
            print(f"Removed SoundCalibrator instance for peer {peer_id}")

        # Remove peer from the room
        self.room.remove_peer(peer_id)
        
        if len(self.room.peers) == 0:
            # No more peers in the room, close the room
            print(f"No more peers in room {self.room.room_id}, closing room")
            self.room.close()
            print(f"Room {self.room.room_id} closed")
            self.token_streaming_service.close()
            print("Closed token streaming service connection")
    
    # On Audio Data - Callback used by the Peers
    async def on_audio_data(self, peer_id, audio_data, sample_rate):
        try:
            # Add audio data to the SpeechToText instance
            self.peer_to_calibration[peer_id].add_audio_data(audio_data=audio_data)

            # If not calibrated, ignore the audio data
            if not self.has_calibrated:
                return
            
            # If interruption is disallowed, ignore the audio data
            if not self.allows_inturrptions and self.peer_to_media_stream[peer_id].is_speaking():
                return

            await self.peer_to_stt[peer_id].add_audio_data(audio_data=audio_data, sample_rate=sample_rate)
        except Exception as e:
            print(f"Error processing audio data from peer {peer_id}: {e}")
            raise e

    # On Speech Detected - Callback used by the SpeechToText instance
    def on_speach_detected(self, peer_id: str, text: str):
        # Handle speech detected
        print(f"Speech detected from {peer_id}: {text}")
        
        # Send the text to the token streaming service
        asyncio.create_task(self.token_streaming_service.add_message(text))

    # Listen to the token stream
    async def listen_to_token_stream(self):
        async for full_sentence in sentence_stream(self.token_streaming_service.token_stream()):
            print(f"Full Sentence: {full_sentence}")

            # Process TTS chunks as they arrive
            async for chunk in text_to_speech_stream(full_sentence):
                for peer_id, peer in self.room.peers.items():
                    await peer.tracks[0].enqueue_audio_samples(chunk)

    # On Calibration Measurement - Callback used by the SoundCalibrator instance
    def on_calibration_measurement(self, peer_id: str, energy: float):
        # print(f"Calibration measurement from {peer_id}: {energy}")

        # # Send the calibration measurement to the peer
        # peer = self.room.peers[peer_id]
        # peer.send_message(f"Calibration measurement: {energy}")

        # If already calibrated, ignore the measurement
        if (self.has_calibrated):
            return
        
        # Update the VAD threshold in the SpeechToText instance
        stt = self.peer_to_stt[peer_id]
        MAX_SAMPLE = 32767
        vad_threshold = (energy / (MAX_SAMPLE ** 2)) * 0.4
        stt.update_vad_threshold(vad_threshold)
        print(f"Calibrated VAD threshold for peer {peer_id}: {vad_threshold}")
        self.has_calibrated = True

        # Send calibration complete message to peer
        peer = self.room.peers[peer_id]
        asyncio.create_task(
            peer.rpc_peer.call("calibration_complete", {
                "message": "Calibration complete. You can now start speaking."
            })
        )
        
        



