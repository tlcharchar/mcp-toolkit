"""
Adapters para conversão de diferentes fontes em MCP tools.

Este módulo fornece adapters para:
- REST APIs (RestApiAdapter)
- OpenAPI specs (OpenAPIAdapter)
"""

from .openapi import OpenAPIAdapter, OpenAPIParser
from .rest import AsyncHttpClient, RestApiAdapter

__all__ = [
    "AsyncHttpClient",
    "OpenAPIAdapter",
    "OpenAPIParser",
    "RestApiAdapter",
]
