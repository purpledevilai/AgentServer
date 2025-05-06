from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from models.ConversationOrchestrator import ConversationOrchestrator


app = FastAPI()

# Optional: Add CORS if you expect to call from other domains
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health check
@app.get("/health")
async def health():
    return {"status": "ok"}

# Connect to Context
class RequestAgentConnect(BaseModel):
    context_id: str
@app.post("/invite-agent")
async def wake_agent(request_agent_connect: RequestAgentConnect):

    # Context ID from the request
    context_id = request_agent_connect.context_id

    # Start conversation orchestrator
    orchestrator = ConversationOrchestrator(context_id)
    await orchestrator.initialize()
    
    return {
        "message": "Initializing agent",
    }


