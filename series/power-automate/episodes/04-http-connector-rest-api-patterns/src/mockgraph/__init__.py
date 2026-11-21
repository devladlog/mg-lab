"""Local stand-in for the Entra token endpoint and Graph /v1.0/users (tests and CLI demo only)."""
from .server import Fault, MockGraph

__all__ = ["Fault", "MockGraph"]
