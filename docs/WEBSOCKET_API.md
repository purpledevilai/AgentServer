# Token Streaming Server WebSocket API Documentation

## Overview

The Token Streaming Server provides a WebSocket-based JSON-RPC API for connecting to AI agent contexts and streaming token-by-token responses. The server uses a JSON-RPC 2.0-like protocol for bidirectional communication.

**WebSocket Endpoint:** `wss://token-streaming-server.prod.token-streaming.ajentify.com/ws`

## Connection

### Establishing a WebSocket Connection

Connect to the WebSocket endpoint using any WebSocket client:

```javascript
const ws = new WebSocket('wss://token-streaming-server.prod.token-streaming.ajentify.com/ws');
```

Once connected, the server will accept the connection and assign a unique connection ID. The connection remains open until either the client or server closes it.

## Message Protocol

All messages are JSON strings sent over the WebSocket connection. The server uses a JSON-RPC-like protocol with the following structure:

### Request Format

```json
{
  "method": "method_name",
  "params": {
    "param1": "value1",
    "param2": "value2"
  },
  "id": "optional-request-id"
}
```

**Fields:**
- `method` (required): The method name to call
- `params` (required): An object containing the method parameters
- `id` (optional): A unique request ID. If provided, the server will send a response with the same ID. If omitted, the request is treated as a notification (no response expected)

### Response Format

When a request includes an `id`, the server will respond with:

```json
{
  "id": "same-request-id",
  "result": {
    "success": true,
    "data": {...}
  }
}
```

If an error occurs, the response will be:

```json
{
  "id": "same-request-id",
  "result": {
    "error": "Error message describing what went wrong"
  }
}
```

### Notification Format (Server to Client)

The server can send notifications to the client without a request. These messages do not include an `id` field:

```json
{
  "method": "notification_method",
  "params": {
    "data": "..."
  }
}
```

## Methods

### Client to Server Methods

#### 1. `connect_to_context`

Connects to a specific context and initializes the agent chat session. This must be called before sending messages.

**Request:**
```json
{
  "method": "connect_to_context",
  "params": {
    "context_id": "uuid-of-context",
    "access_token": "optional-jwt-token-or-api-key"
  },
  "id": "request-id-123"
}
```

**Parameters:**
- `context_id` (required): The UUID of the context to connect to
- `access_token` (optional): 
  - If provided, authenticates the user and allows access to private contexts
  - Can be either a JWT token (Cognito) or an API key
  - If omitted, only public contexts can be accessed

**Response:**
```json
{
  "id": "request-id-123",
  "result": {
    "success": true,
    "agent_speaks_first": false,
    "agent": {
      "agent_id": "uuid",
      "agent_name": "Agent Name",
      "agent_description": "Description",
      "prompt": "System prompt",
      "org_id": "organization-id",
      "is_public": true,
      "is_default_agent": false,
      "agent_speaks_first": false,
      "tools": ["tool1", "tool2"],
      "uses_prompt_args": false,
      "voice_id": null,
      "initialize_tool_id": null,
      "created_at": 1234567890,
      "updated_at": 1234567890
    }
  }
}
```

**Notes:**
- If `agent_speaks_first` is `true` and the context has no previous messages, the agent will automatically send its first message after connection
- The connection must be established before calling `add_message`
- If authentication fails or the context is not accessible, an error will be returned

**Error Response:**
```json
{
  "id": "request-id-123",
  "result": {
    "error": "No context_id provided"
  }
}
```

#### 2. `add_message`

Sends a message to the agent and triggers a response. The agent's response will be streamed token-by-token.

**Request:**
```json
{
  "method": "add_message",
  "params": {
    "message": "Hello, how are you?"
  },
  "id": "request-id-456"
}
```

**Parameters:**
- `message` (required): The text message to send to the agent

**Response:**
```json
{
  "id": "request-id-456",
  "result": {
    "success": true
  }
}
```

**Notes:**
- You must call `connect_to_context` first before sending messages
- The actual agent response is streamed via `on_token` notifications (see below)
- After the response is complete, you may receive `on_events` notifications if the agent generated any events

**Error Response:**
```json
{
  "id": "request-id-456",
  "result": {
    "error": "No context set for connection"
  }
}
```

#### 3. `stop_invocation`

Stops any currently running agent invocation. Use this to interrupt the agent while it's generating a response (e.g., when a user interrupts during voice conversation).

**Request:**
```json
{
  "method": "stop_invocation",
  "params": {},
  "id": "request-id-789"
}
```

**Parameters:** None required.

**Response:**
```json
{
  "id": "request-id-789",
  "result": {
    "success": true
  }
}
```

**Notes:**
- Call this before `set_last_messages` to ensure any ongoing generation is stopped
- The agent will stop generating tokens as soon as possible
- Any partial response generated before stopping will be preserved in the message history
- Safe to call even if no generation is currently in progress

**Use Case - Voice Interruption:**
When building voice applications, users may interrupt the agent while it's speaking. Call `stop_invocation` immediately when an interruption is detected to stop token generation, then use `set_last_messages` to modify the conversation history.

#### 4. `set_last_messages`

Modifies the conversation history and re-invokes the agent. Designed for voice interruption scenarios where you need to adjust what was said and continue the conversation.

**Request:**
```json
{
  "method": "set_last_messages",
  "params": {
    "human_message": "The complete user message",
    "ai_message": "Optional: The AI's partial response"
  },
  "id": "request-id-101"
}
```

**Parameters:**
- `human_message` (required): The human message content
- `ai_message` (optional): The AI message content. If omitted, triggers Scenario 1. If provided, triggers Scenario 2.

**Response:**
The method will stream a new response via `on_token` notifications, followed by `on_stop_token` when complete.

**Scenario 1: Human Message Only (`ai_message` omitted)**

Use this when the user interrupts BEFORE the agent has spoken any audio to them.

The method will:
1. Find the last human message in the conversation
2. Check if any tool calls were completed after that message
3. **If NO completed tool calls:**
   - Replace the last human message content with `human_message`
   - Remove all AI-generated content after it
   - Re-invoke the agent
4. **If there ARE completed tool calls:**
   - Keep the original human message and all completed tool calls
   - Calculate the "delta" (new content): `human_message - original_human_message`
   - Add a NEW human message with the delta at the end
   - Re-invoke the agent

**Example - No Tool Calls:**
```
Before: [Human: "Hello"] → [AI: "Hi there!"]
Call: set_last_messages({ human_message: "Hello, what's the weather?" })
After: [Human: "Hello, what's the weather?"] → (new AI response streams)
```

**Example - With Completed Tool Calls:**
```
Before: [Human: "Check my email"] → [AI: tool_call] → [Tool: response] → [AI: "You have 3 emails"]
Call: set_last_messages({ human_message: "Check my email and tell me about the first one" })
After: [Human: "Check my email"] → [AI: tool_call] → [Tool: response] → [Human: "and tell me about the first one"] → (new AI response streams)
```

**Scenario 2: AI Message + Human Message (`ai_message` provided)**

Use this when the user interrupts AFTER the agent has spoken some audio to them.

The method will:
1. Find the last AI message with content
2. Replace its content with the provided `ai_message` (preserving any tool calls)
3. Append a new human message with `human_message` content
4. Re-invoke the agent

**Example:**
```
Before: [Human: "Tell me a story"] → [AI: "Once upon a time, there was a dragon who..."]
User interrupts after hearing "Once upon a time"
Call: set_last_messages({ 
  ai_message: "Once upon a time", 
  human_message: "Make it about a princess instead" 
})
After: [Human: "Tell me a story"] → [AI: "Once upon a time"] → [Human: "Make it about a princess instead"] → (new AI response streams)
```

**Notes:**
- Always call `stop_invocation` before `set_last_messages` to ensure any ongoing generation is stopped
- The context is automatically saved to the database after modifications and after the new response completes
- If no existing human/AI message is found, new messages are created
- The method streams the new response via `on_token` and signals completion with `on_stop_token`

**Error Response:**
```json
{
  "id": "request-id-101",
  "result": {
    "error": "No context set for connection"
  }
}
```

### Server to Client Notifications

The server sends these notifications to the client during agent interactions:

#### 1. `on_token`

Sent for each token as the agent generates its response. This allows for real-time streaming of the agent's response.

**Notification:**
```json
{
  "method": "on_token",
  "params": {
    "token": "Hello",
    "response_id": "uuid-of-response"
  }
}
```

**Parameters:**
- `token` (string): A single token from the agent's response
- `response_id` (string): A UUID that groups all tokens for a single response. Use this to associate tokens with the same response.

**Notes:**
- Tokens are sent sequentially as they are generated
- Multiple `on_token` notifications will be sent for a complete response
- The `response_id` remains constant for all tokens in a single response
- Tokens may be individual words, parts of words, or punctuation depending on the tokenization

**Example Flow:**
```json
{"method": "on_token", "params": {"token": "Hello", "response_id": "abc-123"}}
{"method": "on_token", "params": {"token": ",", "response_id": "abc-123"}}
{"method": "on_token", "params": {"token": " how", "response_id": "abc-123"}}
{"method": "on_token", "params": {"token": " are", "response_id": "abc-123"}}
{"method": "on_token", "params": {"token": " you", "response_id": "abc-123"}}
{"method": "on_token", "params": {"token": "?", "response_id": "abc-123"}}
{"method": "on_stop_token", "params": {"response_id": "abc-123"}}
```

#### 2. `on_stop_token`

Sent when the agent has finished generating its response. This signals that all tokens for a given `response_id` have been sent.

**Notification:**
```json
{
  "method": "on_stop_token",
  "params": {
    "response_id": "uuid-of-response"
  }
}
```

**Parameters:**
- `response_id` (string): The UUID that matches the `response_id` from the preceding `on_token` notifications

**Notes:**
- This notification is sent after the final `on_token` for a response
- Use this to know when it's safe to finalize the response (e.g., stop TTS generation, enable user input)
- Critical for voice applications to know when the agent has finished speaking
- Always sent after `add_message` or `set_last_messages` completes

**Use Case - Voice Applications:**
When building voice applications, use `on_stop_token` to:
1. Know when to stop waiting for more audio to generate
2. Re-enable user interruption detection
3. Update UI to show the agent is done speaking

#### 3. `on_tool_call`

Sent when the agent calls a tool during its response generation.

**Notification:**
```json
{
  "method": "on_tool_call",
  "params": {
    "tool_call_id": "uuid-of-tool-call",
    "tool_name": "tool_function_name",
    "tool_input": {
      "param1": "value1",
      "param2": "value2"
    }
  }
}
```

**Parameters:**
- `tool_call_id` (string): Unique identifier for this tool call
- `tool_name` (string): The name of the tool being called
- `tool_input` (object): The input parameters passed to the tool

**Notes:**
- Tool calls occur during agent response generation
- A corresponding `on_tool_response` notification will follow after the tool executes
- Multiple tool calls may occur in a single response

#### 4. `on_tool_response`

Sent after a tool call completes execution.

**Notification:**
```json
{
  "method": "on_tool_response",
  "params": {
    "tool_call_id": "uuid-of-tool-call",
    "tool_name": "tool_function_name",
    "tool_output": "Result from tool execution"
  }
}
```

**Parameters:**
- `tool_call_id` (string): The same ID from the corresponding `on_tool_call`
- `tool_name` (string): The name of the tool that was called
- `tool_output` (string): The result/output from the tool execution

**Notes:**
- This notification always follows a corresponding `on_tool_call` with the same `tool_call_id`
- The tool output is typically a string representation of the tool's result

#### 5. `on_events`

Sent after a response is complete if the agent generated any custom events during processing.

**Notification:**
```json
{
  "method": "on_events",
  "params": {
    "events": [
      {
        "type": "event_type",
        "data": "event_data"
      }
    ],
    "response_id": "uuid-of-response"
  }
}
```

**Parameters:**
- `events` (array): An array of event objects, each containing:
  - `type` (string): The type/category of the event
  - `data` (string): The event data/payload
- `response_id` (string): The UUID of the response that generated these events (matches the `response_id` from `on_token` notifications)

**Notes:**
- Events are optional and only sent if the agent generated them
- Events are sent after the response is complete
- The `response_id` links these events to the corresponding token stream
- Events are cleared after being sent, so they won't appear in subsequent responses

## Complete Example Flow

Here's a complete example of a client-server interaction:

### 1. Connect to WebSocket
```javascript
const ws = new WebSocket('wss://token-streaming-server.prod.token-streaming.ajentify.com/ws');
```

### 2. Connect to Context
**Client sends:**
```json
{
  "method": "connect_to_context",
  "params": {
    "context_id": "123e4567-e89b-12d3-a456-426614174000",
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
  },
  "id": "connect-1"
}
```

**Server responds:**
```json
{
  "id": "connect-1",
  "result": {
    "success": true,
    "agent_speaks_first": false,
    "agent": {
      "agent_id": "agent-uuid",
      "agent_name": "Assistant",
      "agent_description": "Helpful assistant",
      "prompt": "You are a helpful assistant.",
      "org_id": "org-123",
      "is_public": false,
      "is_default_agent": false,
      "agent_speaks_first": false,
      "tools": [],
      "uses_prompt_args": false,
      "voice_id": null,
      "initialize_tool_id": null,
      "created_at": 1234567890,
      "updated_at": 1234567890
    }
  }
}
```

### 3. Send a Message
**Client sends:**
```json
{
  "method": "add_message",
  "params": {
    "message": "What is the weather like?"
  },
  "id": "msg-1"
}
```

**Server responds:**
```json
{
  "id": "msg-1",
  "result": {
    "success": true
  }
}
```

### 4. Receive Token Stream
**Server sends (multiple notifications):**
```json
{"method": "on_token", "params": {"token": "I", "response_id": "resp-abc"}}
{"method": "on_token", "params": {"token": " don", "response_id": "resp-abc"}}
{"method": "on_token", "params": {"token": "'t", "response_id": "resp-abc"}}
{"method": "on_token", "params": {"token": " have", "response_id": "resp-abc"}}
{"method": "on_token", "params": {"token": " access", "response_id": "resp-abc"}}
{"method": "on_token", "params": {"token": " to", "response_id": "resp-abc"}}
{"method": "on_token", "params": {"token": " real", "response_id": "resp-abc"}}
{"method": "on_token", "params": {"token": "-", "response_id": "resp-abc"}}
{"method": "on_token", "params": {"token": "time", "response_id": "resp-abc"}}
{"method": "on_token", "params": {"token": " weather", "response_id": "resp-abc"}}
{"method": "on_token", "params": {"token": " data", "response_id": "resp-abc"}}
{"method": "on_token", "params": {"token": ".", "response_id": "resp-abc"}}
```

### 5. Receive Events (if any)
**Server sends (optional):**
```json
{
  "method": "on_events",
  "params": {
    "events": [
      {
        "type": "custom_event",
        "data": "some event data"
      }
    ],
    "response_id": "resp-abc"
  }
}
```

## Error Handling

### Connection Errors

If the WebSocket connection fails or is closed:
- The connection will be terminated
- Any pending requests will not receive responses
- You must establish a new connection to continue

### Request Errors

If a request fails, the server will respond with an error in the `result.error` field:

```json
{
  "id": "request-id",
  "result": {
    "error": "Error message here"
  }
}
```

Common errors:
- `"No context_id provided"` - Missing required `context_id` parameter
- `"No context set for connection"` - Attempted to send message before connecting to context
- `"No agent_chat set for connection"` - Connection not properly initialized
- `"No message provided"` - Missing message parameter
- `"Context with id: {id} does not exist"` - Invalid context ID
- `"Context does not belong to user"` - User doesn't have access to this context
- `"Context is not public"` - Attempting to access private context without authentication
- `"Agent does not belong to user's orgs"` - User doesn't have access to the agent

### Timeout Handling

If you send a request with an `id` and don't receive a response within a reasonable time (typically 5-30 seconds depending on the operation), you should:
1. Consider the request failed
2. Check the connection status
3. Retry if appropriate

## Authentication

### Public Contexts

For public contexts, you can omit the `access_token` parameter:

```json
{
  "method": "connect_to_context",
  "params": {
    "context_id": "public-context-id"
  },
  "id": "connect-1"
}
```

### Private Contexts

For private contexts, you must provide an `access_token`:

**Using JWT (Cognito):**
```json
{
  "method": "connect_to_context",
  "params": {
    "context_id": "private-context-id",
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
  },
  "id": "connect-1"
}
```

**Using API Key:**
```json
{
  "method": "connect_to_context",
  "params": {
    "context_id": "private-context-id",
    "access_token": "api-key-string"
  },
  "id": "connect-1"
}
```

The server will:
1. First attempt to validate the token as an API key
2. If that fails, fall back to Cognito JWT validation
3. Extract the user ID and verify access to the context

## Best Practices

1. **Always connect to context first**: Call `connect_to_context` before sending any messages
2. **Handle token streaming**: Accumulate tokens with the same `response_id` to reconstruct the full response
3. **Monitor connection status**: Implement reconnection logic for dropped connections
4. **Use request IDs**: Include `id` in requests when you need to track responses
5. **Handle errors gracefully**: Check for `error` fields in responses and handle appropriately
6. **Clean up on disconnect**: Close connections properly and clean up any local state

## Implementation Example (JavaScript)

```javascript
class TokenStreamingClient {
  constructor(url) {
    this.url = url;
    this.ws = null;
    this.responseHandlers = new Map();
    this.tokenBuffers = new Map();
  }

  connect() {
    return new Promise((resolve, reject) => {
      this.ws = new WebSocket(this.url);
      
      this.ws.onopen = () => {
        console.log('Connected');
        resolve();
      };
      
      this.ws.onmessage = (event) => {
        this.handleMessage(JSON.parse(event.data));
      };
      
      this.ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        reject(error);
      };
      
      this.ws.onclose = () => {
        console.log('Connection closed');
      };
    });
  }

  handleMessage(msg) {
    // Handle responses to requests
    if (msg.id && this.responseHandlers.has(msg.id)) {
      const handler = this.responseHandlers.get(msg.id);
      this.responseHandlers.delete(msg.id);
      handler(msg.result);
      return;
    }

    // Handle notifications
    if (msg.method === 'on_token') {
      const { token, response_id } = msg.params;
      if (!this.tokenBuffers.has(response_id)) {
        this.tokenBuffers.set(response_id, '');
      }
      this.tokenBuffers.set(
        response_id,
        this.tokenBuffers.get(response_id) + token
      );
      // Emit token event
      this.onToken?.(token, response_id);
    } else if (msg.method === 'on_stop_token') {
      this.onStopToken?.(msg.params.response_id);
    } else if (msg.method === 'on_tool_call') {
      this.onToolCall?.(msg.params);
    } else if (msg.method === 'on_tool_response') {
      this.onToolResponse?.(msg.params);
    } else if (msg.method === 'on_events') {
      this.onEvents?.(msg.params);
    }
  }

  async call(method, params, awaitResponse = true) {
    return new Promise((resolve, reject) => {
      const id = awaitResponse ? `req-${Date.now()}-${Math.random()}` : null;
      
      const message = {
        method,
        params,
        ...(id && { id })
      };

      if (id) {
        this.responseHandlers.set(id, (result) => {
          if (result.error) {
            reject(new Error(result.error));
          } else {
            resolve(result);
          }
        });
      }

      this.ws.send(JSON.stringify(message));
      
      if (!awaitResponse) {
        resolve();
      }
    });
  }

  async connectToContext(contextId, accessToken = null) {
    const params = { context_id: contextId };
    if (accessToken) {
      params.access_token = accessToken;
    }
    return await this.call('connect_to_context', params);
  }

  async addMessage(message) {
    return await this.call('add_message', { message });
  }

  async stopInvocation() {
    return await this.call('stop_invocation', {});
  }

  async setLastMessages(humanMessage, aiMessage = null) {
    const params = { human_message: humanMessage };
    if (aiMessage) {
      params.ai_message = aiMessage;
    }
    return await this.call('set_last_messages', params);
  }

  getResponse(responseId) {
    return this.tokenBuffers.get(responseId) || '';
  }

  clearResponse(responseId) {
    this.tokenBuffers.delete(responseId);
  }
}

// Usage
const client = new TokenStreamingClient('wss://token-streaming-server.prod.token-streaming.ajentify.com/ws');

client.onToken = (token, responseId) => {
  console.log('Token:', token);
};

client.onStopToken = (responseId) => {
  console.log('Response complete:', responseId);
  console.log('Full response:', client.getResponse(responseId));
};

client.onToolCall = (params) => {
  console.log('Tool called:', params.tool_name);
};

client.onToolResponse = (params) => {
  console.log('Tool response:', params.tool_output);
};

client.onEvents = (params) => {
  console.log('Events:', params.events);
};

await client.connect();
await client.connectToContext('context-id', 'access-token');
await client.addMessage('Hello!');
```

## Summary

- **Endpoint**: `wss://token-streaming-server.prod.token-streaming.ajentify.com/ws`
- **Protocol**: JSON-RPC-like over WebSocket
- **Required Steps**: 
  1. Connect WebSocket
  2. Call `connect_to_context` with context ID
  3. Call `add_message` to send messages
  4. Receive `on_token` notifications for streaming responses
  5. Receive `on_stop_token` notification when response is complete
  6. Optionally receive `on_tool_call`, `on_tool_response`, and `on_events` notifications

### Voice Interruption Flow

For voice applications that need to handle user interruptions:

1. **User starts speaking (interruption detected)**
2. Call `stop_invocation` to stop the agent immediately
3. Call `set_last_messages` with appropriate parameters:
   - If agent hadn't spoken yet: `{ human_message: "aggregated user input" }`
   - If agent had spoken: `{ human_message: "user's new input", ai_message: "what agent said before interruption" }`
4. Receive new `on_token` stream for the agent's updated response
5. Receive `on_stop_token` when complete

