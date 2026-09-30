"""Importing the modules registers the 18 tools in core.REGISTRY."""

from mcp_server.core import REGISTRY
from mcp_server.tools import globals, pagamentos, pedidos, trocas  # noqa: F401

__all__ = ["REGISTRY"]
