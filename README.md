# Resume RAG API

This is an AI-powered API that allows you to query a personal resume using Persistent RAG (Retrieval Augmented Generation).

## Setup

1.  **Clone the repository:**

    ```bash
    git clone <repository_url>
    cd rag-resume-chatbot
    ```

2.  **Install dependencies:**

    ```bash
    pip install -r requirements.txt
    ```
    or if using Pipenv:
    ```bash
    pipenv install
    ```

3.  **Set up environment variables:**

    Create a `.env` file in the root directory with the following variables:

    ```env
    GOOGLE_API_KEY="YOUR_GEMINI_API_KEY"
    LLM="gemini-1.5-flash-latest" # Or your preferred Gemini model
    EMBEDDING_MODEL="publishers/google/models/text-embedding-004"
    ```

    Replace `"YOUR_GEMINI_API_KEY"` with your actual Gemini API key.

4.  **Build the vector index:**

    ```bash
    python app/rag/builder.py
    ```

## Running the Application

To run the FastAPI application, use the following command:

```bash
uvicorn main:app --reload
```

The API will be available at `http://127.0.0.1:8000`.

## API Endpoints

### `POST /query-resume/`

Endpoint to query the resume using natural language.

-   **Request Body:**

    ```json
    {
      "query": "Your question about the resume"
    }
    ```

-   **Response:**

    ```json
    {
      "query": "Your question about the resume",
      "message": "Relevant information from the resume"
    }
    ```

### `POST /feedback/`

Endpoint to receive feedback payload.

-   **Request Body:** Accepts any JSON object.

    ```json
    {
      "userMessage": "Your question about the resume",
      "botResponse": "Relevant information from the resume",
      "isPositive": true
    }
    ```

-   **Response:**

    ```json
    {
      "message": "Feedback received successfully"
    }
    ```

### `GET /`

Health check endpoint.

-   **Response:**

    ```json
    {
      "status": "healthy"
    }
