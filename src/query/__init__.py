# Re-export infrastructure helpers so mcp/ can import them without touching src.db directly.
from src.db.init import create_pool

__all__ = ["create_pool"]
