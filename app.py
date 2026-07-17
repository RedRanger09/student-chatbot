"""
Student Support Services AI Chatbot — project entry helper.

The UI is Next.js. The API is FastAPI. Streamlit has been removed.

Start the backend:

    uvicorn backend.app.main:app --reload --port 8000

Start the frontend:

    cd frontend && npm run dev
"""

from __future__ import annotations


def main() -> None:
    print("Student Support Services AI Chatbot")
    print("Backend : uvicorn backend.app.main:app --reload --port 8000")
    print("Frontend: cd frontend && npm run dev")
    print("API docs: http://127.0.0.1:8000/docs")


if __name__ == "__main__":
    main()
