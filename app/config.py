import os
from typing import Optional
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

class Settings:
    # Set your Google API key - consider using environment variables
    GEMINI_API_KEY: Optional[str] = os.getenv('GEMINI_API_KEY')
    LLM: str = os.getenv('LLM')
    EMBEDDING_MODEL: str = os.getenv('EMBEDDING_MODEL')
    INDEX_PATH: str = './app/data/index'
    RESUME_PATH: str = './app/data/resume.md'

def get_settings():
    return Settings()