"""Importing the modules registers the 44 new large-profile tools in REGISTRY_LARGE."""

from mcp_server.large.data import REGISTRY_LARGE
from mcp_server.tools_large import (  # noqa: F401
    assinaturas,
    assistencia,
    cartao_loja,
    fidelidade,
    globals_large,
    marketplace,
    notas_fiscais,
    promocoes,
)

__all__ = ["REGISTRY_LARGE"]
