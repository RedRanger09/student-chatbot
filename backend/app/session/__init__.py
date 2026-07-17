"""Re-export framework-independent session manager for the API package."""

from src.session.manager import SessionManager, get_session_manager

__all__ = ["SessionManager", "get_session_manager"]
