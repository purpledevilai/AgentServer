from typing import Callable, List
import asyncio
from aiortc import (
    RTCPeerConnection,
    RTCSessionDescription,
    RTCIceCandidate,
    RTCConfiguration,
    RTCIceServer,
    RTCDataChannel,
    MediaStreamTrack
)
from lib.webrtc.functions.parse_candidate_sdp import parse_candidate_sdp


class Peer:
    def __init__(
            self,
            peer_id: str,
            self_description: str,
            create_data_channel: bool = False,
            tracks: List[MediaStreamTrack] = [],
        ):
        self.peer_id = peer_id
        self.self_description = self_description
        self.pc: RTCPeerConnection | None = None
        self.create_data_channel = create_data_channel
        self.tracks = tracks
        self.data_channel: RTCDataChannel | None = None
        self.on_audio_data: Callable[[str, list, int], None] = lambda peer_id, samples, sample_rate: print(f"Audio data received from {peer_id}: {samples[:10]}... (sample rate: {sample_rate})")
        self.on_message: Callable[[str, str], None] = lambda peer_id, message: print(f"Message received: peer {peer_id}: message {message}")
        self.on_data_channel_connection_status: Callable[[str, str], None] = lambda peer_id: print(f"Data channel opened for peer {peer_id}")
        self.on_connection_status: Callable[[str, str], None] = lambda peer_id, status: print(f"Connection status for peer {peer_id}: {status}")


    ###########################
    # INITIALIZATION FOR ROOM #
    ###########################

    # Initialize Peer for Room
    def initialize_for_room(self, on_ice_candidate: Callable[[str, dict], None]):
        # WebRTC Peer Connection
        self.pc = RTCPeerConnection(configuration = RTCConfiguration(
            iceServers=[
                RTCIceServer(urls=["stun:stun.l.google.com:19302"]),
            ]
        ))
        print(f"Created RTCPeerConnection for Peer {self.peer_id}")

        # Data channel setup
        if self.create_data_channel:
            self.data_channel = self.pc.createDataChannel("chat")
            channel = self.pc.createDataChannel("chat")
            self.setup_data_channel(channel)
            print(f"Created data channel for Peer {self.peer_id}")

        # Receive data channel
        @self.pc.on("datachannel")
        def on_datachannel(channel: RTCDataChannel):
            self.setup_data_channel(channel)
            print(f"Received incoming data channel for Peer {self.peer_id}")

        # Track setup
        for track in self.tracks:
            self.pc.addTrack(track)
            print(f"Added track {track.kind} for Peer {self.peer_id}")

        # Receive audio track
        @self.pc.on("track")
        async def on_track(track):
            if track.kind == "audio" and self.on_audio_data:
                asyncio.create_task(self.tap_audio_stream(track))
            print(f"Received track {track.kind} for Peer {self.peer_id}")

        # Receive ICE candidates
        @self.pc.on("icecandidate")
        async def on_icecandidate(event):
            if event.candidate is not None:
                asyncio.create_task(on_ice_candidate(self.peer_id, event.candidate))
            print(f"Received ICE candidate for Peer {self.peer_id}")

        # ICE connection state changes
        @self.pc.on("iceconnectionstatechange")
        async def on_iceconnectionstatechange():
            print(f"ICE connection state changed: {self.pc.iceConnectionState} for Peer {self.peer_id}")

        # Connection state changes
        @self.pc.on("connectionstatechange")
        async def on_connectionstatechange():
            print(f"Connection state changed: {self.pc.connectionState} for Peer {self.peer_id}")
            await self.on_connection_status(self.peer_id, self.pc.connectionState)


    ##################
    # EVENT HANDLERS #
    ##################

    # Event handlers
    def on(self, event: str, callback: Callable):
        if event == "audio_data":
            self.on_audio_data = callback
        elif event == "data_channel_connection_status":
            self.on_data_channel_connection_status = callback
        elif event == "data_channel_message":
            self.on_message = callback
        elif event == "connection_status":
            self.on_connection_status = callback
        else:
            raise ValueError(f"Unknown event: {event}")


    ######################
    # DATA CHANNEL SETUP #
    ######################

    # Setup Data Channel
    def setup_data_channel(self, channel: RTCDataChannel):
        self.data_channel = channel
        channel.on("message", lambda msg: asyncio.create_task(self.on_message(msg)))

        def handle_open():
            print(f"Data channel opened for Peer {self.peer_id}")
            asyncio.create_task(self.on_data_channel_connection_status(self.peer_id, "connected"))

        channel.on("open", handle_open)

        # Check if already open
        if channel.readyState == "open":
            handle_open()

        def handle_close():
            print(f"Data channel closed for Peer {self.peer_id}")
            asyncio.create_task(self.on_data_channel_connection_status(self.peer_id, "disconnected"))

        channel.on("close", handle_close)

    # Send Message
    async def send_message(self, message: str):
        if self.data_channel and self.data_channel.readyState == "open":
            self.data_channel.send(message)
            print(f"Sent data channel message to peer {self.peer_id}: {message}")
        else:
            print(f"Cannot send message — data channel not open - peer id: {self.peer_id}")


    #############################
    # WEB RTC SIGNALING METHODS #
    #############################

    # Create Offer
    async def create_offer(self):
        offer = await self.pc.createOffer()
        await self.pc.setLocalDescription(offer)
        return {
            "sdp": self.pc.localDescription.sdp,
            "type": self.pc.localDescription.type
        }

    # Set Remote Description
    async def set_remote_description(self, description: dict):
        desc = RTCSessionDescription(sdp=description["sdp"], type=description["type"])
        await self.pc.setRemoteDescription(desc)

    # Create and Set Local Answer
    async def create_and_set_local_answer(self):
        answer = await self.pc.createAnswer()
        await self.pc.setLocalDescription(answer)
        return {
            "sdp": self.pc.localDescription.sdp,
            "type": self.pc.localDescription.type
        }

    # Add Ice Candidate
    async def add_ice_candidate(self, candidate: dict):
        # Null candidate to indicate end of candidates
        if candidate is None:
            await self.pc.addIceCandidate(None)
            return

        # Parse the candidate string into structured fields and add it to the peer connection
        parsed = parse_candidate_sdp(candidate["candidate"])
        await self.pc.addIceCandidate(RTCIceCandidate(
            component=parsed["component"],
            foundation=parsed["foundation"],
            ip=parsed["ip"],
            port=parsed["port"],
            priority=parsed["priority"],
            protocol=parsed["protocol"],
            type=parsed["type"],
            sdpMid=candidate.get("sdpMid"),
            sdpMLineIndex=candidate.get("sdpMLineIndex"),
        ))


    #################################
    # AUDIO STREAM HANDLING METHODS #
    #################################

    # Tap Audio Stream
    async def tap_audio_stream(self, track):
        while True:
            try:
                # Recieve the audio frame
                frame = await track.recv()

                # Extract PCM samples
                interleaved_samples = frame.to_ndarray()[0]
                samples = interleaved_samples[::2]

                # Call callback with audio data
                await self.on_audio_data(self.peer_id, samples, frame.sample_rate)
                
            except Exception as e:
                print(f"Error receiving audio frame: {e} - Peer id: {self.peer_id}")
                break   


    #########
    # CLOSE #
    #########
    
    # Close Peer
    def close(self):
        if self.pc:
            asyncio.create_task(self.pc.close())
            self.pc = None
             
