from llama_index.core import load_index_from_storage
from llama_index.core.tools import QueryEngineTool
from llama_index.core.agent import ReActAgent
from llama_index.llms.gemini import Gemini
from llama_index.embeddings.google import GeminiEmbedding
from llama_index.core.storage.storage_context import StorageContext
from llama_index.core.prompts import PromptTemplate
from app.config import Settings

class ResumeRAGAgent:
    def __init__(self, settings: Settings):
        # Initialize Gemini LLM
        self.llm = Gemini(
            model=settings.LLM, 
            api_key=settings.GEMINI_API_KEY,
            temperature=0,
            max_tokens=2**18
        )
        
        # Load the persisted index
        storage_context = StorageContext.from_defaults(persist_dir=settings.INDEX_PATH)
        index = load_index_from_storage(
            storage_context, 
            embed_model=GeminiEmbedding(
                model=settings.EMBEDDING_MODEL, 
                api_key=settings.GEMINI_API_KEY
            )
        )
        
        # Create query engine
        query_engine = index.as_query_engine(
            similarity_top_k=3,
            response_mode="compact"
        )
        
        # Create a tool from the query engine
        resume_tool = QueryEngineTool.from_defaults(
            query_engine=query_engine,
            name="resume_search",
            description="Useful for searching and retrieving information from the resume"
        )
        
        # Custom prompt template for more structured responses
        prompt_template = PromptTemplate("""
        You are an AI virtual assistant helping to answer questions about the person in resume. 
        Use the available tool to search for relevant information.
        Follow these guidelines:
        1. If the information is directly available in the resume, provide a concise and precise answer.
        2. If the information is not found, clearly state that.
        3. Format the response in a professional and helpful manner.
        4. If multiple pieces of information are relevant, synthesize them coherently.

        Query: {input}
        Thought: {agent_scratchpad}
        """)
        
        # Create ReAct Agent
        self.agent = ReActAgent.from_tools(
            tools=[resume_tool],
            llm=self.llm,
            prompt_template=prompt_template,
            verbose=True
        )
    
    def query_resume(self, query: str) -> str:
        """
        Query the resume using an agent-based approach
        
        :param query: User's query about the resume
        :return: Relevant information from the resume
        """
        try:
            # Use the agent to process the query
            response = self.agent.chat(query)
            return str(response)
        except Exception as e:
            return f"Error processing query: {str(e)}"