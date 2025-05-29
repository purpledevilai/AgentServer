import json
import uuid
from typing import Callable, Dict, Any, Optional
from lib.webrtc.functions.till_true import till_true


class JSONRPCResponse:
    def __init__(self, id: str, result: Dict[str, Any]):
        self.id = id
        self.result = result


class JSONRPCPeer:
    def __init__(self, sender: Callable[[str], None]):
        self.sender = sender
        self.response_queue: Dict[str, Optional[JSONRPCResponse]] = {}
        self.handler_registry: Dict[str, Callable[[Dict[str, Any]], Any]] = {}

    def on(self, method: str, handler: Callable[[Dict[str, Any]], Any]):
        self.handler_registry[method] = handler

    async def call(
        self,
        method: str,
        params: Dict[str, Any],
        await_response: bool = False,
        timeout: int = 5
    ) -> Optional[Dict[str, Any]]:

        msg_id = str(uuid.uuid4()) if await_response else None

        message = json.dumps({
            "method": method,
            "params": params,
            "id": msg_id
        })

        await self.sender(message)

        if not await_response or msg_id is None:
            return

        self.response_queue[msg_id] = None

        if not await till_true(lambda: self.response_queue[msg_id] is not None, timeout=timeout):
            raise TimeoutError(f"Timeout waiting for response to {method}")
        
        response = self.response_queue.pop(msg_id)

        if response.result.get("error"):
            raise Exception(f"Error in response to {method}: {response.result['error']}")

        return response.result

    async def handle_message(self, message: str):
        try:
            parsed_message = json.loads(message)
        except Exception as e:
            print("Error parsing message", e)
            return

        # Request
        if "method" in parsed_message and "params" in parsed_message:
            handler = self.handler_registry.get(parsed_message["method"])
            if not handler:
                print("Error: no handler for message", parsed_message)
                return

            if not parsed_message["id"]:
                await handler(**parsed_message["params"])
                return

            try:
                result = await handler(**parsed_message["params"])
                await self.sender(json.dumps({
                    "id": parsed_message["id"],
                    "result": result
                }))
            except Exception as e:
                print("Error handling message", e)
                await self.sender(json.dumps({
                    "id": parsed_message["id"],
                    "result": {
                        "error": str(e)
                    }
                }))
            return

        # Response
        if "id" not in parsed_message or parsed_message["id"] not in self.response_queue:
            print("Error: message is not a response or unknown ID", parsed_message)
            print("Response Queue", self.response_queue)
            return

        self.response_queue[parsed_message["id"]] = JSONRPCResponse(
            id=parsed_message["id"],
            result=parsed_message.get("result", {})
        )
