from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from app.agent import ResumeRAGAgent
from app.config import get_settings
import os
import uvicorn
from dotenv import load_dotenv, find_dotenv
from llama_index.core import Settings
from llama_index.llms.gemini import Gemini

load_dotenv(find_dotenv())
settings = get_settings()
Settings.llm = Gemini(
    model=settings.LLM,
    temperature=0,
    api_key=settings.GEMINI_API_KEY
)

# Check if index exists, if not, provide guidance
if not os.path.exists(settings.INDEX_PATH):
    print("ERROR: Vector index not found!")
    print("Please run 'python app/rag/builder.py' to create the index before starting the API")
    raise SystemExit(1)

# Initialize the RAG agent
rag_agent = ResumeRAGAgent(settings=settings)

# FastAPI application
app = FastAPI(
    title="Resume RAG API",
    description="AI-powered API to query personal resume using Persistent RAG"
)

# Request model
class QueryRequest(BaseModel):
    query: str

# API endpoint
@app.post("/query-resume/")
async def query_resume(request: QueryRequest):
    """
    Endpoint to query the resume using natural language
    
    :param request: Query about the resume
    :return: Relevant information from the resume
    """
    try:
        response = rag_agent.query_resume(request.query)
        return {"query": request.query, "response": response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Optional: Health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "healthy"}

# Run with: uvicorn main:app --reload
if __name__ == "__main__":
    uvicorn.run(
        "main:app", host="0.0.0.0", port=8000, reload=True 
    )