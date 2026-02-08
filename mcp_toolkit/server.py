"""
MCP Server principal do toolkit.

Este módulo fornece a classe MCPServer que é o ponto central
para criação de MCP Servers usando o SDK.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import sys
from contextlib import asynccontextmanager
from typing import (
    Any,
    AsyncGenerator,
    Callable,
    Dict,
    List,
    Optional,
    Sequence,
    Type,
    Union,
)

from pydantic import BaseModel

from .decorators import tool, resource, prompt
from .types import (
    PromptDefinition,
    ResourceDefinition,
    ResponseFormat,
    ServerConfig,
    ToolDefinition,
    ToolParameter,
    ToolResult,
    TransportType,
)


# ============================================================================
# Logging Setup
# ============================================================================


def _setup_logging(config: ServerConfig) -> logging.Logger:
    """Configura logging para o server."""
    logger = logging.getLogger(config.name)
    logger.setLevel(getattr(logging, config.log_level.upper()))
    
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)  # stderr para não interferir com stdio
        
        if config.structured_logging:
            # JSON logging
            class JsonFormatter(logging.Formatter):
                def format(self, record: logging.LogRecord) -> str:
                    log_data = {
                        "timestamp": self.formatTime(record),
                        "level": record.levelname,
                        "logger": record.name,
                        "message": record.getMessage(),
                    }
                    if record.exc_info:
                        log_data["exception"] = self.formatException(record.exc_info)
                    return json.dumps(log_data)
            
            handler.setFormatter(JsonFormatter())
        else:
            handler.setFormatter(
                logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
            )
        
        logger.addHandler(handler)
    
    return logger


# ============================================================================
# MCP Server
# ============================================================================


class MCPServer:
    """
    MCP Server principal do toolkit.
    
    Fornece uma interface simplificada para criar MCP Servers
    com suporte a tools, resources e prompts.
    
    Exemplo básico:
        server = MCPServer("meu_mcp")
        
        @server.tool()
        def minha_tool(param: str) -> str:
            return f"Resultado: {param}"
        
        server.run()
    
    Exemplo com configuração:
        config = ServerConfig(
            name="meu_mcp",
            transport=TransportType.STREAMABLE_HTTP,
            port=9000
        )
        server = MCPServer(config)
    """
    
    def __init__(
        self,
        name_or_config: Union[str, ServerConfig],
        version: str = "1.0.0",
        description: Optional[str] = None,
    ):
        """
        Inicializa o MCP Server.
        
        Args:
            name_or_config: Nome do server (formato: {service}_mcp) ou ServerConfig
            version: Versão do server
            description: Descrição do server
        """
        if isinstance(name_or_config, ServerConfig):
            self.config = name_or_config
        else:
            # Valida e cria config
            name = name_or_config
            if not name.endswith("_mcp"):
                name = f"{name}_mcp"
            
            self.config = ServerConfig(
                name=name,
                version=version,
                description=description
            )
        
        self._tools: Dict[str, ToolDefinition] = {}
        self._resources: Dict[str, ResourceDefinition] = {}
        self._prompts: Dict[str, PromptDefinition] = {}
        self._lifespan: Optional[Callable[[], AsyncGenerator[Dict[str, Any], None]]] = None
        self._lifespan_state: Dict[str, Any] = {}
        
        self.logger = _setup_logging(self.config)
        self.logger.info(f"Initializing MCP Server: {self.config.name}")
    
    # ========================================================================
    # Decorators
    # ========================================================================
    
    def tool(
        self,
        name: Optional[str] = None,
        description: Optional[str] = None,
        annotations: Optional[Dict[str, Any]] = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """
        Decorator para registrar uma tool no server.
        
        Exemplo:
            @server.tool()
            def buscar_cliente(cliente_id: str) -> dict:
                '''Busca um cliente pelo ID.'''
                return {"id": cliente_id, "nome": "João"}
        
            @server.tool(name="custom_name", annotations={"readOnlyHint": True})
            def outra_tool(param: str) -> str:
                return param
        """
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            # Aplica o decorator base
            decorated = tool(name=name, description=description, annotations=annotations)(func)
            
            # Registra no server
            tool_def: ToolDefinition = decorated._mcp_tool  # type: ignore
            self.register_tool(tool_def)
            
            return decorated
        
        return decorator
    
    def resource(
        self,
        uri: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        mime_type: str = "text/plain",
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """
        Decorator para registrar um resource no server.
        
        Exemplo:
            @server.resource(uri="docs://{name}")
            def get_doc(name: str) -> str:
                return open(f"docs/{name}.md").read()
        """
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            decorated = resource(uri=uri, name=name, description=description, mime_type=mime_type)(func)
            
            resource_def: ResourceDefinition = decorated._mcp_resource  # type: ignore
            self.register_resource(resource_def)
            
            return decorated
        
        return decorator
    
    def prompt(
        self,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Callable[[Callable[..., str]], Callable[..., str]]:
        """
        Decorator para registrar um prompt no server.
        
        Exemplo:
            @server.prompt(name="analise")
            def prompt_analise(cliente_id: str) -> str:
                return f"Analise o cliente {cliente_id}..."
        """
        def decorator(func: Callable[..., str]) -> Callable[..., str]:
            decorated = prompt(name=name, description=description)(func)
            
            prompt_def: PromptDefinition = decorated._mcp_prompt  # type: ignore
            self.register_prompt(prompt_def)
            
            return decorated
        
        return decorator
    
    # ========================================================================
    # Registration Methods
    # ========================================================================
    
    def register_tool(self, tool_def: ToolDefinition) -> None:
        """Registra uma tool no server."""
        if tool_def.name in self._tools:
            self.logger.warning(f"Tool '{tool_def.name}' already registered, overwriting")
        
        self._tools[tool_def.name] = tool_def
        self.logger.debug(f"Registered tool: {tool_def.name}")
    
    def register_tools(
        self,
        tools: Sequence[ToolDefinition],
        prefix: Optional[str] = None,
    ) -> None:
        """Registra múltiplas tools, opcionalmente com prefixo."""
        for tool_def in tools:
            if prefix:
                # Cria cópia com nome prefixado
                prefixed = ToolDefinition(
                    name=f"{prefix}{tool_def.name}",
                    description=tool_def.description,
                    parameters=tool_def.parameters,
                    annotations=tool_def.annotations,
                    handler=tool_def.handler
                )
                self.register_tool(prefixed)
            else:
                self.register_tool(tool_def)
    
    def register_resource(self, resource_def: ResourceDefinition) -> None:
        """Registra um resource no server."""
        if resource_def.uri in self._resources:
            self.logger.warning(f"Resource '{resource_def.uri}' already registered, overwriting")
        
        self._resources[resource_def.uri] = resource_def
        self.logger.debug(f"Registered resource: {resource_def.uri}")
    
    def register_prompt(self, prompt_def: PromptDefinition) -> None:
        """Registra um prompt no server."""
        if prompt_def.name in self._prompts:
            self.logger.warning(f"Prompt '{prompt_def.name}' already registered, overwriting")
        
        self._prompts[prompt_def.name] = prompt_def
        self.logger.debug(f"Registered prompt: {prompt_def.name}")
    
    # ========================================================================
    # Lifespan Management
    # ========================================================================
    
    def lifespan(
        self,
        func: Callable[[], AsyncGenerator[Dict[str, Any], None]]
    ) -> Callable[[], AsyncGenerator[Dict[str, Any], None]]:
        """
        Decorator para definir o lifespan do server.
        
        Exemplo:
            @server.lifespan
            @asynccontextmanager
            async def lifespan():
                db = await connect_db()
                yield {"db": db}
                await db.close()
        """
        self._lifespan = func
        return func
    
    # ========================================================================
    # Tool Execution
    # ========================================================================
    
    async def execute_tool(
        self,
        name: str,
        arguments: Dict[str, Any],
        response_format: ResponseFormat = ResponseFormat.JSON,
    ) -> ToolResult:
        """
        Executa uma tool pelo nome.
        
        Args:
            name: Nome da tool
            arguments: Argumentos para a tool
            response_format: Formato de resposta desejado
        
        Returns:
            ToolResult com o resultado da execução
        """
        if name not in self._tools:
            return ToolResult(
                success=False,
                error=f"Tool '{name}' not found. Available: {list(self._tools.keys())}"
            )
        
        tool_def = self._tools[name]
        handler = tool_def.handler
        
        if handler is None:
            return ToolResult(
                success=False,
                error=f"Tool '{name}' has no handler"
            )
        
        try:
            # Executa o handler
            if asyncio.iscoroutinefunction(handler):
                result = await handler(**arguments)
            else:
                result = handler(**arguments)
            
            return ToolResult(
                success=True,
                data=result,
                metadata={"tool": name, "format": response_format.value}
            )
            
        except Exception as e:
            self.logger.error(f"Error executing tool '{name}': {e}", exc_info=True)
            return ToolResult(
                success=False,
                error=str(e),
                metadata={"tool": name, "error_type": type(e).__name__}
            )
    
    # ========================================================================
    # Resource Access
    # ========================================================================
    
    async def read_resource(self, uri: str) -> Union[str, bytes]:
        """
        Lê um resource pelo URI.
        
        Args:
            uri: URI do resource
        
        Returns:
            Conteúdo do resource
        """
        # Encontra resource que match o URI pattern
        for pattern, resource_def in self._resources.items():
            match = self._match_uri(pattern, uri)
            if match is not None:
                handler = resource_def.handler
                if handler is None:
                    raise ValueError(f"Resource '{pattern}' has no handler")
                
                if asyncio.iscoroutinefunction(handler):
                    return await handler(**match)
                else:
                    return handler(**match)
        
        raise ValueError(f"Resource not found: {uri}")
    
    def _match_uri(self, pattern: str, uri: str) -> Optional[Dict[str, str]]:
        """Faz match de URI com pattern e extrai parâmetros."""
        import re
        
        # Converte pattern para regex
        # docs://{name} -> docs://(?P<name>[^/]+)
        regex_pattern = re.sub(r"\{(\w+)\}", r"(?P<\1>[^/]+)", pattern)
        regex_pattern = f"^{regex_pattern}$"
        
        match = re.match(regex_pattern, uri)
        if match:
            return match.groupdict()
        return None
    
    # ========================================================================
    # Server Lifecycle
    # ========================================================================
    
    def run(
        self,
        transport: Optional[TransportType] = None,
        host: Optional[str] = None,
        port: Optional[int] = None,
    ) -> None:
        """
        Inicia o MCP Server.
        
        Args:
            transport: Tipo de transporte (override do config)
            host: Host para HTTP (override do config)
            port: Porta para HTTP (override do config)
        """
        actual_transport = transport or self.config.transport
        actual_host = host or self.config.host
        actual_port = port or self.config.port
        
        self.logger.info(
            f"Starting MCP Server '{self.config.name}' "
            f"with transport={actual_transport.value}"
        )
        
        # Importa FastMCP para criar o server real
        try:
            from mcp.server.fastmcp import FastMCP
        except ImportError:
            self.logger.error(
                "MCP SDK not installed. Install with: pip install mcp"
            )
            raise
        
        # Cria server FastMCP (host/port usados por SSE e Streamable HTTP)
        mcp = FastMCP(
            self.config.name,
            host=actual_host,
            port=actual_port,
        )
        
        # Registra tools
        for name, tool_def in self._tools.items():
            self._register_tool_in_fastmcp(mcp, tool_def)
        
        # Registra resources
        for uri, resource_def in self._resources.items():
            self._register_resource_in_fastmcp(mcp, resource_def)
        
        # Registra prompts
        for name, prompt_def in self._prompts.items():
            self._register_prompt_in_fastmcp(mcp, prompt_def)
        
        # Executa (FastMCP usa "stdio" | "sse" | "streamable-http")
        if actual_transport == TransportType.STREAMABLE_HTTP:
            mcp.run(transport="streamable-http")
        elif actual_transport == TransportType.SSE:
            mcp.run(transport="sse")
        else:
            mcp.run(transport="stdio")
    
    def _create_handler_wrapper(
        self,
        handler: Callable[..., Any],
        parameters: List[ToolParameter],
    ) -> Callable[..., Any]:
        """
        Cria um wrapper com assinatura explícita para handlers que usam **kwargs.
        O FastMCP infere o input schema da assinatura da função; handlers com
        **kwargs geram um parâmetro genérico 'kwargs' que causa erro de validação.
        Este wrapper expõe os parâmetros reais (ou nenhum) para que o schema seja correto.
        """
        is_async = asyncio.iscoroutinefunction(handler)

        # Tools sem parâmetros: wrapper com assinatura vazia (evita kwargs obrigatório)
        if not parameters:
            async def async_no_param_wrapper() -> Any:
                return await handler()

            def sync_no_param_wrapper() -> Any:
                return handler()

            wrapper = async_no_param_wrapper if is_async else sync_no_param_wrapper
            wrapper.__name__ = handler.__name__
            wrapper.__doc__ = handler.__doc__
            wrapper.__signature__ = inspect.Signature([])
            wrapper.__annotations__ = {}
            return wrapper

        # Mapeia tipos do schema para tipos Python
        type_mapping = {
            "string": str,
            "integer": int,
            "number": float,
            "boolean": bool,
            "array": list,
            "object": dict,
        }

        param_names = {p.name for p in parameters}

        async def async_wrapper(**kwargs: Any) -> Any:
            filtered = {k: v for k, v in kwargs.items() if k in param_names}
            return await handler(**filtered)

        def sync_wrapper(**kwargs: Any) -> Any:
            filtered = {k: v for k, v in kwargs.items() if k in param_names}
            return handler(**filtered)

        wrapper = async_wrapper if is_async else sync_wrapper
        wrapper.__name__ = handler.__name__
        wrapper.__doc__ = handler.__doc__

        # Define assinatura explícita para o FastMCP gerar o schema correto.
        # Deduplica nomes (primeira ocorrência vence) e ordena:
        # required (sem default) primeiro, optional (com default) depois.
        # Isso evita ValueError do inspect.Signature.
        required_sig_params = []
        optional_sig_params = []
        annotations: Dict[str, Any] = {}
        seen_names: set = set()
        for p in parameters:
            if p.name in seen_names:
                continue
            seen_names.add(p.name)
            py_type = type_mapping.get(p.type.lower(), str)
            annotations[p.name] = py_type
            if p.required:
                required_sig_params.append(
                    inspect.Parameter(
                        p.name,
                        inspect.Parameter.POSITIONAL_OR_KEYWORD,
                        annotation=py_type,
                    )
                )
            else:
                # Usa default real (incluindo False, 0, "") - não só None
                default_val = p.default
                optional_sig_params.append(
                    inspect.Parameter(
                        p.name,
                        inspect.Parameter.POSITIONAL_OR_KEYWORD,
                        default=default_val,
                        annotation=py_type,
                    )
                )

        sig_params = required_sig_params + optional_sig_params
        wrapper.__signature__ = inspect.Signature(sig_params)
        wrapper.__annotations__ = annotations
        return wrapper

    def _handler_uses_kwargs(self, handler: Callable[..., Any]) -> bool:
        """Verifica se o handler usa **kwargs (ex.: handlers do RestApiAdapter)."""
        try:
            sig = inspect.signature(handler)
            return any(
                p.kind == inspect.Parameter.VAR_KEYWORD
                for p in sig.parameters.values()
            )
        except (ValueError, TypeError):
            return False

    def _register_tool_in_fastmcp(self, mcp: Any, tool_def: ToolDefinition) -> None:
        """Registra uma tool no FastMCP."""
        handler = tool_def.handler
        if handler is None:
            return

        # Handlers do RestApiAdapter/OpenAPIAdapter usam **kwargs; criamos wrapper
        # com assinatura explícita (ou vazia) para gerar schema correto
        if self._handler_uses_kwargs(handler):
            handler = self._create_handler_wrapper(handler, tool_def.parameters)

        # Converte annotations para dict
        annotations_dict = {
            "title": tool_def.annotations.title,
            "readOnlyHint": tool_def.annotations.read_only_hint,
            "destructiveHint": tool_def.annotations.destructive_hint,
            "idempotentHint": tool_def.annotations.idempotent_hint,
            "openWorldHint": tool_def.annotations.open_world_hint,
        }

        # Registra no FastMCP (description importante para clientes MCP)
        mcp.tool(
            name=tool_def.name,
            description=tool_def.description,
            annotations=annotations_dict,
        )(handler)
    
    def _register_resource_in_fastmcp(self, mcp: Any, resource_def: ResourceDefinition) -> None:
        """Registra um resource no FastMCP."""
        handler = resource_def.handler
        if handler is None:
            return
        
        mcp.resource(resource_def.uri)(handler)
    
    def _register_prompt_in_fastmcp(self, mcp: Any, prompt_def: PromptDefinition) -> None:
        """Registra um prompt no FastMCP."""
        handler = prompt_def.handler
        if handler is None:
            return
        
        # FastMCP não tem decorator de prompt direto, usamos a API interna
        # Por hora, prompts serão gerenciados pelo toolkit
        self.logger.debug(f"Prompt '{prompt_def.name}' registered (toolkit-managed)")
    
    # ========================================================================
    # Introspection
    # ========================================================================
    
    @property
    def tools(self) -> Dict[str, ToolDefinition]:
        """Retorna todas as tools registradas."""
        return self._tools.copy()
    
    @property
    def resources(self) -> Dict[str, ResourceDefinition]:
        """Retorna todos os resources registrados."""
        return self._resources.copy()
    
    @property
    def prompts(self) -> Dict[str, PromptDefinition]:
        """Retorna todos os prompts registrados."""
        return self._prompts.copy()
    
    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        """Retorna uma tool pelo nome."""
        return self._tools.get(name)
    
    def list_tools(self) -> List[str]:
        """Lista nomes de todas as tools."""
        return list(self._tools.keys())
    
    def __repr__(self) -> str:
        return (
            f"MCPServer(name='{self.config.name}', "
            f"tools={len(self._tools)}, "
            f"resources={len(self._resources)}, "
            f"prompts={len(self._prompts)})"
        )
