"""
MCP Toolkit - SDK para criação simplificada de MCP Servers em Python.

Este SDK permite criar MCP Servers de forma declarativa e pythônica,
com suporte especial para exposição de APIs REST existentes como tools MCP.

Exemplo básico:
    from mcp_toolkit import MCPServer, tool
    
    server = MCPServer("meu_mcp")
    
    @server.tool()
    def calcular_frete(cep_origem: str, cep_destino: str) -> dict:
        '''Calcula frete entre dois CEPs.'''
        return {"valor": 45.90, "prazo_dias": 3}
    
    server.run()

Exemplo com REST adapter:
    from mcp_toolkit import MCPServer
    from mcp_toolkit.adapters import RestApiAdapter
    
    server = MCPServer("vendas_mcp")
    
    api = RestApiAdapter(
        base_url="https://api.empresa.com/v1",
        auth=AuthConfig(type=AuthType.BEARER, env_var="API_TOKEN"),
    )
    
    server.register_tool(
        api.as_tool(
            method="GET",
            path="/clientes/{id}",
            name="buscar_cliente",
            description="Busca cliente pelo ID",
        )
    )
    
    server.run()
"""

__version__ = "1.0.0"
__author__ = "Empresa"

# Core
from .server import MCPServer
from .decorators import tool, resource, prompt

# Types
from .types import (
    # Enums
    AuthType,
    HttpMethod,
    ResponseFormat,
    TransportType,
    # Models
    AuthConfig,
    PromptArgument,
    PromptDefinition,
    ResourceDefinition,
    ServerConfig,
    ToolAnnotations,
    ToolDefinition,
    ToolParameter,
    ToolResult,
)

# Adapters (lazy import para performance)
def __getattr__(name: str):
    if name == "adapters":
        from . import adapters
        return adapters
    if name == "auth":
        from . import auth
        return auth
    if name == "observability":
        from . import observability
        return observability
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Version
    "__version__",
    # Core
    "MCPServer",
    "tool",
    "resource",
    "prompt",
    # Enums
    "AuthType",
    "HttpMethod",
    "ResponseFormat",
    "TransportType",
    # Models
    "AuthConfig",
    "PromptArgument",
    "PromptDefinition",
    "ResourceDefinition",
    "ServerConfig",
    "ToolAnnotations",
    "ToolDefinition",
    "ToolParameter",
    "ToolResult",
    # Submodules (lazy)
    "adapters",
    "auth",
    "observability",
]
