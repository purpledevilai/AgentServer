import os
from typing import Optional
from lib.webrtc.Room import Room
from lib.webrtc.Peer import Peer
from lib.webrtc.SyntheticAudioTrack import SyntheticAudioTrack


class ConversationOrchestrator:

    # Constructor
    def __init__(self, context_id: str):
        self.context_id = context_id
        self.room: Optional[Room] = None
        self.agent: Optional[object] = None
        
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
    def on_audio_data(peer_id: str, data):
        print("recieved audio data")
        pass

    # On Message - Callback used by the Peers
    def on_message(peer_id: str, message: str):
        pass