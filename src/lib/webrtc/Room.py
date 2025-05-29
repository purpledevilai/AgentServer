import asyncio
from typing import Callable
from lib.webrtc.SimpleWebSocketClient import SimpleWebSocketClient
from lib.webrtc.JSONRPCPeer import JSONRPCPeer
from lib.webrtc.Peer import Peer
from lib.webrtc.functions.till_true import till_true

class Room:
    # Constructor
    def __init__(
            self,
            room_id: str,
            signaling_server_url: str,
            self_description: str,
        ):
        self.room_id = room_id
        self.signaling_server_url = signaling_server_url
        self.self_description = self_description
        self.websocket = None
        self.rpc_layer: JSONRPCPeer = None
        self.peers: dict[str, Peer] = {}
        self.on_create_peer: Callable[[str, str], Peer] = lambda peer_id, self_description: None
        self.on_connection_status: Callable[[str], None] = lambda status: print(f"Connection status: {status}")
        
    # Connect
    async def connect(self):
        # Create a WebSocket client
        self.websocket = SimpleWebSocketClient(self.signaling_server_url)
        self.websocket.on("connection_status", self.on_connection_status)

        # Create RPC peer to interface with the signaling server
        self.rpc_layer = JSONRPCPeer(sender=self.websocket.send)

        # Register signaling event handlers
        self.rpc_layer.on("peer_added", self.peer_added)
        self.rpc_layer.on("connection_request", self.connection_request)
        self.rpc_layer.on("add_ice_candidate", self.add_ice_candidate)

        # Set the message handler for the WebSocket
        self.websocket.on("message", self.rpc_layer.handle_message)
        
        # Connect to the signaling server
        await self.websocket.connect()

        # Call to join the room
        await self.rpc_layer.call("join", {
            "room_id": self.room_id,
            "self_description": self.self_description
        })

    # Set event handlers
    def on(self, event: str, callback: Callable):
        if event == "create_peer":
            self.on_create_peer = callback
        elif event == "connection_status":
            self.on_connection_status = callback
        else:
            raise ValueError(f"Unknown event: {event}")


    ################################
    ## SIGNALING SERVER CALLBACKS ##
    ################################

    # Peer Added
    async def peer_added(self, peer_id: str, self_description: str):
        print(f"ROOM: peer was added: {peer_id} self_description: {self_description}")
        
        # Create a new peer
        peer: Peer = await self.on_create_peer(peer_id, self_description)
        if not peer:
            print(f"Did not create peer for {peer_id}")
            return
        
        # Initialize the peer
        peer.initialize_for_room(
            on_ice_candidate=lambda candidate: self.rpc_layer.call("relay_ice_candidate", {
                "peer_id": peer_id,
                "candidate": candidate
            })
        )

        # Connection exchange
        offer = await peer.create_offer()
        print(f"Created offer for peer {peer_id} offer: {offer}")
        answer = await self.rpc_layer.call("request_connection", {
            "peer_id": peer_id,
            "self_description": self.self_description,
            "offer": offer
        }, await_response=True)
        print(f"Received answer from peer {peer_id} answer: {answer}")
        if not answer or not answer.get("answer"):
            print(f"Peer {peer_id} did not respond with an answer")
            return
        await peer.set_remote_description(answer["answer"])

        # Add the peer to the list
        self.peers[peer_id] = peer

    # Connection Request
    async def connection_request(self, peer_id: str, self_description: str, offer):
        print(f"ROOM: connection request from peer {peer_id} self_description: {self_description}")

        # Check for handler
        if (self.on_create_peer is None):
            print("No handler for create_peer_for_description set")
            return
        
        # Create a new peer
        peer = await self.on_create_peer(peer_id, self_description)
        if not peer:
            print(f"Did not create peer for {peer_id}")
            return
        
        # Initialize the peer
        peer.initialize_for_room(
            on_ice_candidate=lambda candidate: self.rpc_layer.call("relay_ice_candidate", {
                "peer_id": peer_id,
                "candidate": candidate
            })
        )
        
        # Connection exchange
        print(f"Received offer from peer {peer_id} offer: {offer}")
        await peer.set_remote_description(offer)
        answer = await peer.create_and_set_local_answer()
        print(f"Created answer for peer {peer_id} answer: {answer}")
        self.peers[peer_id] = peer

        # Send the answer back to the peer
        return answer

    # Add ICE Candidate
    async def add_ice_candidate(self, peer_id: str, candidate):
        print(f"ROOM: request to add ice candidate for peer {peer_id}")

        # Wait for peer to be added if not already
        if not await till_true(lambda: peer_id in self.peers, timeout=5):
            print(f"Peer {peer_id} not added in time to add ice candidate")
            return
        
        # Add the ICE candidate to the peer
        await self.peers[peer_id].add_ice_candidate(candidate)

    def remove_peer(self, peer_id: str):
        # Remove the peer from the list
        if peer_id in self.peers:
            self.peers[peer_id].close()
            del self.peers[peer_id]
            print(f"Removed peer {peer_id} from room")
        else:
            print(f"Peer {peer_id} not found in room")

    def close(self):
        if self.websocket:
            asyncio.create_task(self.websocket.close())
            print("Closed signaling server connection")
        
        # Close all peers
        for peer in self.peers.values():
            peer.close()
        
        self.peers = {}
        print("Closed all peers")
