# Action Item Extractor

This project provides a simple web application for extracting action items from text notes, offering both heuristic-based and LLM-powered (via Ollama) extraction methods. It also allows saving and listing notes.

## Features

-   **Heuristic Action Item Extraction**: Extracts action items based on bullet points, numbered lists, checkboxes, and keyword prefixes (e.g., "todo:", "action:").
-   **LLM-Powered Action Item Extraction**: Leverages a local Ollama model (default `llama3.2`) for more intelligent action item identification from unstructured text.
-   **Note Management**: Save and retrieve notes via dedicated API endpoints.
-   **Simple Frontend**: A basic HTML/JavaScript frontend to interact with the API.

## Project Structure

-   `app/`: Backend FastAPI application.
    -   `config.py`: Application configuration.
    -   `db.py`: SQLite database operations.
    -   `main.py`: Main FastAPI application entry point.
    -   `routers/`: API route definitions (`action_items.py`, `notes.py`).
    -   `schemas/`: Pydantic models for API request/response validation.
    -   `services/extract.py`: Core logic for action item extraction (heuristic and LLM).
-   `data/`: Contains the SQLite database file (`app.db`).
-   `frontend/`: Static HTML/JavaScript frontend (`index.html`).
-   `tests/`: Unit and integration tests.

## Setup and Running

This project uses `poetry` for dependency management.

### Prerequisites

1.  **Python 3.9+**: Ensure you have Python installed.
2.  **Poetry**: Install Poetry if you haven't already:
    ```bash
    curl -sSL https://install.python-poetry.org | python -
    ```
3.  **Ollama**: For LLM-powered extraction, you need to have Ollama installed and a model pulled (e.g., `llama3.2`).
    -   [Download Ollama](https://ollama.com/download)
    -   Pull a model (e.g., `llama3.2`):
        ```bash
        ollama pull llama3.2
        ```

### Installation

Navigate to the project root directory (the parent of `week2/`) and install dependencies:

```bash
cd ../
poetry install
cd week2/
```

### Running the Application

From the `week2/` directory:

```bash
poetry run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The application will be accessible at `http://localhost:8000`.

### Environment Variables

You can configure the Ollama model and host using environment variables in a `.env` file:

-   `OLLAMA_MODEL`: Name of the Ollama model to use (default: `llama3.2`).
-   `OLLAMA_HOST`: URL of the Ollama host (default: `http://localhost:11434`).

## API Endpoints

-   **GET /**: Serves the `index.html` frontend.
-   **POST /action-items/extract**: Extracts action items using heuristic methods.
    -   Request: `{"text": "string", "save_note": boolean}`
    -   Response: `{"note_id": int | null, "items": [{"id": int, "text": "string"}]}`
-   **POST /action-items/extract-llm**: Extracts action items using the configured Ollama LLM.
    -   Request: `{"text": "string", "save_note": boolean}`
    -   Response: `{"note_id": int | null, "items": [{"id": int, "text": "string"}]}`
-   **GET /action-items**: Lists all action items, optionally filtered by `note_id`.
    -   Query: `note_id: int | null`
    -   Response: `[{"id": int, "note_id": int | null, "text": "string", "done": boolean, "created_at": "string"}]`
-   **POST /action-items/{action_item_id}/done**: Marks an action item as done or undone.
    -   Request: `{"done": boolean}`
    -   Response: `{"id": int, "done": boolean}`
-   **POST /notes**: Creates a new note.
    -   Request: `{"content": "string"}`
    -   Response: `{"id": int, "content": "string", "created_at": "string"}`
-   **GET /notes**: Lists all notes.
    -   Response: `[{"id": int, "content": "string", "created_at": "string"}]`
-   **GET /notes/{note_id}**: Retrieves a single note by ID.
    -   Response: `{"id": int, "content": "string", "created_at": "string"}`

## Testing

To run the tests (from the `week2/` directory):

```bash
poetry run pytest tests/
```

If you have a specific conda environment (e.g., `cs146s`) activated, you can run tests like this:

```bash
conda run -n cs146s poetry run pytest tests/
```
