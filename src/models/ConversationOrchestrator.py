import asyncio
import os
from typing import Optional
from lib.webrtc.JSONRPCPeer import JSONRPCPeer
from lib.webrtc.Room import Room
from lib.webrtc.Peer import Peer
from lib.webrtc.SyntheticAudioTrack import SyntheticAudioTrack
from models.SoundCalibrator import SoundCalibrator
from models.SpeechToText import SpeechToText
from models.TokenStreamingService import TokenStreamingService
from lib.sentence_stream import sentence_stream, TokenObject
from lib.text_to_speech_stream import text_to_speech_stream


class ConversationOrchestrator:

    # Constructor
    def __init__(self, context_id: str, auth_token: Optional[str] = None):
        self.context_id = context_id
        self.auth_token = auth_token
        self.has_calibrated = False
        self.room: Optional[Room] = None
        self.token_streaming_service: Optional[TokenStreamingService] = None
        self.voice_id: Optional[str] = None
        self.token_queue = asyncio.Queue()
        self.peer_to_stt: dict[str, SpeechToText] = {}
        self.peer_to_calibration: dict[str, SoundCalibrator] = {}
        self.peer_to_media_stream: dict[str, SyntheticAudioTrack] = {}
        self.peer_to_data_channel_rpc_layer: dict[str, JSONRPCPeer] = {}
        self.sentence_counter = 0
        
        # Interruption state
        self.last_human_message: Optional[str] = None    # Last text sent to token streaming
        self.sentence_id_to_text: dict[int, str] = {}    # sentence_id → text
        self.in_interruption_window: bool = False        # True from add_message/set_last_messages until last audio played
    

    ##################
    # INITIALIZATION #
    ##################

    # Initialize
    async def initialize(self):
        try:
            # WEBRTC ROOM
            self.room = Room(
                room_id=self.context_id,
                signaling_server_url=os.environ["SIGNALING_SERVER_URL"],
                self_description="Agent",
            )
            self.room.on("create_peer", self.on_create_peer)
            self.room.on("connection_status", self.on_room_connection_status)
            await self.room.connect()

            # TOKEN STREAMING SERVICE
            self.token_streaming_service = TokenStreamingService(
                token_streaming_url=os.environ["TOKEN_STREAMING_SERVER_URL"],
                context_id=self.context_id,
                auth_token=self.auth_token,
            )
            self.token_streaming_service.on("token", self.on_token)
            self.token_streaming_service.on("stop_token", self.on_stop_token)
            self.token_streaming_service.on("tool_call", self.on_tool_call)
            self.token_streaming_service.on("tool_response", self.on_tool_response)
            self.token_streaming_service.on("connection_status", self.on_token_streaming_service_connection_status)
            connection_request = await self.token_streaming_service.connect()

            if connection_request.get("success", False):
                self.voice_id = connection_request["agent"]["voice_id"] # Connection returns the agent and we can get the voice ID

            # Create thread to run speech generation
            asyncio.create_task(self.start_speech_generator())
        except Exception as e:
            print(f"Error initializing ConversationOrchestrator: {e}")
            raise e


    #########################
    # WEBRTC ROOM CALLBACKS #
    #########################

    # Create Peer for Description - Callback used by the Room
    async def on_create_peer(self, peer_id: str, self_description: str):
        print(f"Create Peer Called: {self_description}")
        try:
            # SPEECH TO TEXT
            stt =  SpeechToText(
                transcription_service_url=os.environ["TRANSCRIPTION_SERVER_URL"],
                silence_duration_ms=1000,
                vad_threshold=0.001,
            )
            stt.on("connection_status", lambda status: asyncio.create_task(self.on_transcription_service_connection_status(peer_id, status)))
            stt.on("is_speaking_status", lambda is_speaking: asyncio.create_task(self.on_is_speaking_status(peer_id, is_speaking)))
            stt.on("speech_detected", lambda text: asyncio.create_task(self.on_speech_detected(peer_id, text)))
            await stt.connect()
            self.peer_to_stt[peer_id] = stt

            # SOUND CALIBRATOR
            calibrator = SoundCalibrator()
            calibrator.on("measurement", lambda energy: asyncio.create_task(self.on_calibration_measurement(peer_id, energy)))
            self.peer_to_calibration[peer_id] = calibrator

            # SYNTHETIC AUDIO TRACK
            audioTrack = SyntheticAudioTrack()
            audioTrack.on("is_speaking_sentence", lambda sentence_id: asyncio.create_task(self.on_is_speaking_sentence(peer_id, sentence_id)))
            audioTrack.on("stoped_speaking", lambda: asyncio.create_task(self.on_stoped_speaking(peer_id)))
            audioTrack.on("invocation_audio_complete", lambda: asyncio.create_task(self.on_invocation_audio_complete(peer_id)))
            self.peer_to_media_stream[peer_id] = audioTrack

            # WEBRTC PEER
            peer = Peer(
                peer_id=peer_id,
                self_description=self_description,
                tracks=[audioTrack],
            )
            peer.on("audio_data", self.on_audio_data)
            peer.on("data_channel_connection_status", self.on_peer_data_channel_connection_status)
            peer.on("connection_status", self.on_peer_connection_status)

            # JSON RPC Layer with peer
            data_channel_rpc_layer = JSONRPCPeer(sender=peer.send_message)
            peer.on("data_channel_message", data_channel_rpc_layer.handle_message)
            self.peer_to_data_channel_rpc_layer[peer_id] = data_channel_rpc_layer

            # Return peer
            return peer
        except Exception as e:
            print(f"Error creating peer {peer_id}: {e}")
            raise e

    # On Room Connection Status - The room's connection status to the signaling server 
    async def on_room_connection_status(self, status: str):
        print(f"Room connection status: {status}")
        await self.send_call_to_all_peers("room_connection_status", {
            "status": status,
        })


    #########################
    # WEBRTC PEER CALLBACKS #
    #########################

    # On Audio Data - Audio packets received from the remote peer
    async def on_audio_data(self, peer_id, audio_data, sample_rate):
        try:
            # Add audio data to the SpeechToText instance
            self.peer_to_calibration[peer_id].add_audio_data(audio_data=audio_data)

            # If not calibrated, ignore the audio data
            if not self.has_calibrated:
                return

            await self.peer_to_stt[peer_id].add_audio_data(audio_data=audio_data, sample_rate=sample_rate)
        except Exception as e:
            print(f"Error processing audio data from peer {peer_id}: {e}")
            raise e
    
    # On Peer Data Channel Connection Status - When the data channel connection status changes
    async def on_peer_data_channel_connection_status(self, peer_id: str, status: str):
        print(f"Data channel connection status for peer {peer_id}: {status}")
        await self.send_call_to_peer(peer_id, "data_channel_connection_status", {
            "status": status,
        })
        if status == "connected":
            await self.send_call_to_peer(peer_id, "calibration_status", {
                "status": "started",
            })

    # On Peer Connection Status - When the peer's webrtc connection status changes
    async def on_peer_connection_status(self, peer_id: str, status: str):
        print(f"Peer {peer_id} connection status changed: {status}")
        # If the peer is disconnected, remove it from the room
        if status in ["disconnected", "failed", "closed"]:
            self.on_peer_disconnected(peer_id)
            return
        
        # If the peer is connected, send a message to the peer
        await self.send_call_to_peer(peer_id, "connection_status", {
            "status": status,
        })

    # On Peer Disconnected
    def on_peer_disconnected(self, peer_id: str):
        # Remove the SpeechToText instance for the peer
        if peer_id in self.peer_to_stt:
            self.peer_to_stt[peer_id].close()
            del self.peer_to_stt[peer_id]
            print(f"Removed SpeechToText instance for peer {peer_id}")

        # Remove the SoundCalibrator instance for the peer
        if peer_id in self.peer_to_calibration:
            del self.peer_to_calibration[peer_id]
            print(f"Removed SoundCalibrator instance for peer {peer_id}")

        # Remove the SyntheticAudioTrack instance for the peer
        if peer_id in self.peer_to_media_stream:
            del self.peer_to_media_stream[peer_id]
            print(f"Removed SyntheticAudioTrack instance for peer {peer_id}")

        # Remove the JSON RPC layer for the peer
        if peer_id in self.peer_to_data_channel_rpc_layer:
            del self.peer_to_data_channel_rpc_layer[peer_id]
            print(f"Removed JSON RPC layer for peer {peer_id}")

        # Remove peer from the room
        self.room.remove_peer(peer_id)
        
        if len(self.room.peers) == 0:
            # No more peers in the room, close the room
            print(f"No more peers in room {self.room.room_id}, closing room")
            self.room.close()
            print(f"Room {self.room.room_id} closed")
            self.token_streaming_service.close()
            print("Closed token streaming service connection")
    
    

    ######################################
    ## TOKEN STREAMING SERVICE CALLBACKS #
    ######################################

    # On Token - When the agent receives a token from the token streaming service
    async def on_token(self, token: str, response_id: str):
        # Enqueue token object with is_last=False
        await self.token_queue.put(TokenObject(token=token, is_last=False))

    # On Stop Token - When the token streaming service has finished generating tokens
    async def on_stop_token(self, response_id: str):
        print(f"Stop token received for response: {response_id}")
        # Enqueue is_last marker
        await self.token_queue.put(TokenObject(token="", is_last=True))

    # Generator to stream token objects
    async def token_stream(self):
        while True:
            token_obj = await self.token_queue.get()
            yield token_obj

    # Speech Generator - Generates speech from the token stream and enqueues it to the media stream
    async def start_speech_generator(self):
        async for sentence_obj in sentence_stream(self.token_stream()):
            sentence = sentence_obj["sentence"]
            is_last = sentence_obj["is_last"]
            
            if is_last:
                # This is the is_last marker - don't increment counter or call TTS
                # Just enqueue the is_last marker to all tracks
                for synthetic_audio_track in self.peer_to_media_stream.values():
                    synthetic_audio_track.enqueue_audio_samples([], None, is_last=True)
            else:
                # Normal sentence processing
                sentence_id = self.sentence_counter
                self.sentence_counter += 1
                
                # Store sentence text for interruption handling
                self.sentence_id_to_text[sentence_id] = sentence
                
                await self.send_call_to_all_peers("ai_sentence", {
                    "sentence": sentence,
                    "sentence_id": sentence_id,
                })

                async for pcm_data in text_to_speech_stream(sentence, voice_id=self.voice_id):
                    for synthetic_audio_track in self.peer_to_media_stream.values():
                        synthetic_audio_track.enqueue_audio_samples(pcm_data, sentence_id, is_last=False)


    # On Tool Call - When the agent calls a tool
    async def on_tool_call(self, tool_call_id: str, tool_name: str, tool_input: dict):
        print(f"Tool call: {tool_call_id}, Tool: {tool_name}, Input: {tool_input}")
        await self.send_call_to_all_peers("tool_call", {
            "tool_id": tool_call_id,
            "tool_name": tool_name,
            "tool_input": tool_input,
        })
    
    # On Tool Response - When the agent receives a tool response
    async def on_tool_response(self, tool_call_id: str, tool_name: str, tool_output: dict):
        print(f"Tool response: {tool_call_id}, Tool: {tool_name}, Output: {tool_output}")
        await self.send_call_to_all_peers("tool_response", {
            "tool_id": tool_call_id,
            "tool_name": tool_name,
            "tool_output": tool_output,
        })

    # On Token Streaming Service Connection Status - When the token streaming service connection status changes
    async def on_token_streaming_service_connection_status(self, status: str):
        print(f"Token streaming service connection status: {status}")
        await self.send_call_to_all_peers("token_streaming_service_connection_status", {
            "status": status,
        })


    ############################
    # SPEECH TO TEXT CALLBACKS #
    ############################

    # On Speech Detected - Callback used by the SpeechToText instance
    async def on_speech_detected(self, peer_id: str, text: str):
        # Handle speech detected
        print(f"Speech detected from {peer_id}: {text}")

        # Send detected speech to the peer
        await self.send_call_to_peer(peer_id, "speech_detected", {
            "text": text
        })
        
        if self.in_interruption_window:
            # This is an interruption!
            await self.handle_interruption(text)
        else:
            # Normal flow - new conversation turn
            self.last_human_message = text
            self.in_interruption_window = True
            self.sentence_id_to_text.clear()
            for track in self.peer_to_media_stream.values():
                track.reset_completed_sentences()
            asyncio.create_task(self.token_streaming_service.add_message(text))

    # On Is Speaking Status - Callback used by the SpeechToText instance
    async def on_is_speaking_status(self, peer_id: str, is_speaking: bool):
        print(f"Is speaking status for peer {peer_id}: {is_speaking}")

        # Send is speaking status to the peer
        await self.send_call_to_peer(peer_id, "is_speaking_status", {
            "is_speaking": is_speaking
        })
        
        # Pause/resume all audio tracks (global)
        for track in self.peer_to_media_stream.values():
            if is_speaking:
                track.pause()
            else:
                track.resume()

    # On transcription service connection status - Callback used by the SpeechToText instance
    async def on_transcription_service_connection_status(self, peer_id: str, status: str):
        print(f"Transcription service connection status for peer {peer_id}: {status}")
        await self.send_call_to_peer(peer_id, "transcription_service_connection_status", {
            "status": status
        })

    
    ###################################
    # SYNTHETIC AUDIO TRACK CALLBACKS #
    ###################################

    # On Is Speaking Sentence - Callback used by the SyntheticAudioTrack instance
    async def on_is_speaking_sentence(self, peer_id: str, sentence_id: int):
        print(f"Peer {peer_id} is speaking sentence {sentence_id}")

        # Send is speaking sentence to the peer
        await self.send_call_to_peer(peer_id, "is_speaking_sentence", {
            "sentence_id": sentence_id
        })

    # On Stoped Speaking - Callback used by the SyntheticAudioTrack instance
    async def on_stoped_speaking(self, peer_id: str):
        print(f"Peer {peer_id} stopped speaking")

        # Send stoped speaking to the peer
        await self.send_call_to_peer(peer_id, "stoped_speaking", {})

    # On Invocation Audio Complete - Called when the last audio packet of an invocation has been played
    async def on_invocation_audio_complete(self, peer_id: str):
        print(f"Invocation audio complete for peer {peer_id}")
        
        # Close the interruption window
        self.in_interruption_window = False
        
        # Notify peers
        await self.send_call_to_all_peers("agent_finished_speaking", {})


    #########################
    # CALIBRATION CALLBACKS #
    #########################

    # On Calibration Measurement - Callback used by the SoundCalibrator instance
    async def on_calibration_measurement(self, peer_id: str, energy: float):
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
        await self.send_call_to_peer(peer_id, "calibration_status", {
            "status": "complete"
        })        


    ########################
    # INTERRUPTION HANDLING #
    ########################

    async def handle_interruption(self, user_text: str):
        """Handle an interruption from the user during agent speech."""
        print(f"Handling interruption with user text: {user_text}")
        
        # 1. Stop token generation
        await self.token_streaming_service.stop_invocation()
        
        # 2. Get completed sentences before clearing
        completed_ids: set[int] = set()
        for track in self.peer_to_media_stream.values():
            completed_ids.update(track.get_completed_sentence_ids())
        
        # 3. Clear all audio queues
        for track in self.peer_to_media_stream.values():
            track.clear_queue()
            track.reset_completed_sentences()
        
        # 4. Build AI message from completed sentences (in order)
        ai_sentences = [
            self.sentence_id_to_text[sid]
            for sid in sorted(completed_ids)
            if sid in self.sentence_id_to_text
        ]
        ai_message = " ".join(ai_sentences) if ai_sentences else None
        
        # 5. Build human message
        if ai_message:
            # Agent said something - user_text is new input
            human_message = user_text
        else:
            # Agent said nothing - append to previous message
            human_message = f"{self.last_human_message} {user_text}".strip()
        
        print(f"Interruption - AI said: {ai_message}")
        print(f"Interruption - Human message: {human_message}")
        
        # 6. Notify peers of the interruption
        await self.send_call_to_all_peers("interruption", {
            "ai_said": ai_message,
            "human_said": human_message,
        })
        
        # 7. Call set_last_messages (triggers new token stream)
        # This also keeps in_interruption_window = True since new invocation is starting
        await self.token_streaming_service.set_last_messages(
            human_message=human_message,
            ai_message=ai_message
        )
        
        # 8. Reset state for new invocation
        self.last_human_message = human_message
        self.sentence_id_to_text.clear()
        # in_interruption_window stays True - new invocation starting


    ####################
    # HELPER FUNCTIONS #
    ####################

    # Send call to peer - helper function to make RPC calls
    async def send_call_to_peer(self, peer_id: str, method: str, params: dict):
        if peer_id in self.peer_to_data_channel_rpc_layer:
            await self.peer_to_data_channel_rpc_layer[peer_id].call(method, params)
    
    # Send call to all peers - helper function to make RPC calls to all peers
    async def send_call_to_all_peers(self, method: str, params: dict):
        for peer_id in self.peer_to_data_channel_rpc_layer.keys():
            await self.send_call_to_peer(peer_id, method, params)
        
        
