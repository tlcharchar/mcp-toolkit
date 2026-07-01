"""
Testes unitários para MCP Toolkit.
"""

import inspect
import json
import pytest
from typing import Optional
from pydantic import BaseModel, Field

from mcp_toolkit import (
    MCPServer,
    tool,
    resource,
    prompt,
    ToolDefinition,
    ToolParameter,
    ToolAnnotations,
    AuthConfig,
    AuthType,
    ResponseFormat,
)
from mcp_toolkit.types import ToolResult
from mcp_toolkit.adapters import RestApiAdapter
from mcp_toolkit.adapters.openapi import OpenAPIParser
from mcp_toolkit.auth import api_key, bearer, basic, validate_auth


# ============================================================================
# Test Decorators
# ============================================================================


class TestToolDecorator:
    """Testes para o decorator @tool."""
    
    def test_basic_tool(self):
        """Testa criação de tool básica."""
        @tool()
        def hello(name: str) -> str:
            """Retorna uma saudação."""
            return f"Hello, {name}!"
        
        assert hasattr(hello, "_mcp_tool")
        assert hello._mcp_tool.name == "hello"
        assert "saudação" in hello._mcp_tool.description
        assert len(hello._mcp_tool.parameters) == 1
        assert hello._mcp_tool.parameters[0].name == "name"
    
    def test_tool_with_custom_name(self):
        """Testa tool com nome customizado."""
        @tool(name="custom_hello")
        def hello(name: str) -> str:
            return f"Hello, {name}!"
        
        assert hello._mcp_tool.name == "custom_hello"
    
    def test_tool_with_annotations(self):
        """Testa tool com annotations."""
        @tool(annotations={"readOnlyHint": True, "destructiveHint": False})
        def get_data() -> dict:
            """Obtém dados."""
            return {}
        
        assert get_data._mcp_tool.annotations.read_only_hint is True
        assert get_data._mcp_tool.annotations.destructive_hint is False
    
    def test_tool_with_pydantic_model(self):
        """Testa tool que usa Pydantic model."""
        class UserInput(BaseModel):
            name: str = Field(..., description="Nome do usuário")
            age: int = Field(..., description="Idade", ge=0)
        
        @tool()
        def create_user(params: UserInput) -> dict:
            """Cria um usuário."""
            return {"name": params.name, "age": params.age}
        
        assert len(create_user._mcp_tool.parameters) == 2
        
        name_param = next(p for p in create_user._mcp_tool.parameters if p.name == "name")
        assert name_param.description == "Nome do usuário"
        
        age_param = next(p for p in create_user._mcp_tool.parameters if p.name == "age")
        assert age_param.type == "integer"
    
    def test_tool_with_optional_params(self):
        """Testa tool com parâmetros opcionais."""
        @tool()
        def search(query: str, limit: int = 10) -> list:
            """Busca itens."""
            return []
        
        params = search._mcp_tool.parameters
        
        query_param = next(p for p in params if p.name == "query")
        assert query_param.required is True
        
        limit_param = next(p for p in params if p.name == "limit")
        assert limit_param.required is False
        assert limit_param.default == 10


class TestResourceDecorator:
    """Testes para o decorator @resource."""
    
    def test_basic_resource(self):
        """Testa criação de resource básico."""
        @resource(uri="docs://{name}")
        def get_doc(name: str) -> str:
            """Retorna um documento."""
            return f"Document: {name}"
        
        assert hasattr(get_doc, "_mcp_resource")
        assert get_doc._mcp_resource.uri == "docs://{name}"
        assert get_doc._mcp_resource.name == "get_doc"
    
    def test_resource_with_mime_type(self):
        """Testa resource com mime type customizado."""
        @resource(uri="files://{path}", mime_type="application/json")
        def get_json(path: str) -> str:
            return "{}"
        
        assert get_json._mcp_resource.mime_type == "application/json"


class TestPromptDecorator:
    """Testes para o decorator @prompt."""
    
    def test_basic_prompt(self):
        """Testa criação de prompt básico."""
        @prompt()
        def analysis(client_id: str) -> str:
            """Prompt para análise."""
            return f"Analise o cliente {client_id}"
        
        assert hasattr(analysis, "_mcp_prompt")
        assert analysis._mcp_prompt.name == "analysis"
        assert len(analysis._mcp_prompt.arguments) == 1


# ============================================================================
# Test MCPServer
# ============================================================================


class TestMCPServer:
    """Testes para MCPServer."""
    
    def test_server_creation(self):
        """Testa criação de server."""
        server = MCPServer("test_mcp")
        
        assert server.config.name == "test_mcp"
        assert len(server._tools) == 0
    
    def test_server_name_validation(self):
        """Testa validação de nome do server."""
        # Nome sem _mcp é ajustado automaticamente
        server = MCPServer("test")
        assert server.config.name == "test_mcp"
    
    def test_tool_registration_via_decorator(self):
        """Testa registro de tool via decorator."""
        server = MCPServer("test_mcp")
        
        @server.tool()
        def my_tool(x: int) -> int:
            return x * 2
        
        assert "my_tool" in server._tools
        assert server._tools["my_tool"].handler is not None
    
    def test_tool_registration_via_method(self):
        """Testa registro de tool via método."""
        server = MCPServer("test_mcp")
        
        tool_def = ToolDefinition(
            name="external_tool",
            description="Tool externa",
            parameters=[
                ToolParameter(
                    name="input",
                    type="string",
                    description="Input",
                    required=True,
                )
            ],
        )
        
        server.register_tool(tool_def)
        
        assert "external_tool" in server._tools
    
    def test_tool_registration_with_prefix(self):
        """Testa registro de tools com prefixo."""
        server = MCPServer("test_mcp")
        
        tools = [
            ToolDefinition(name="tool1", description="Tool 1", parameters=[]),
            ToolDefinition(name="tool2", description="Tool 2", parameters=[]),
        ]
        
        server.register_tools(tools, prefix="api_")
        
        assert "api_tool1" in server._tools
        assert "api_tool2" in server._tools
    
    @pytest.mark.asyncio
    async def test_tool_execution(self):
        """Testa execução de tool."""
        server = MCPServer("test_mcp")
        
        @server.tool()
        def add(a: int, b: int) -> int:
            return a + b
        
        result = await server.execute_tool("add", {"a": 2, "b": 3})
        
        assert result.success is True
        assert result.data == 5
    
    @pytest.mark.asyncio
    async def test_tool_execution_error(self):
        """Testa execução de tool com erro."""
        server = MCPServer("test_mcp")
        
        @server.tool()
        def fail() -> None:
            raise ValueError("Erro intencional")
        
        result = await server.execute_tool("fail", {})
        
        assert result.success is False
        assert "Erro intencional" in result.error
    
    @pytest.mark.asyncio
    async def test_tool_not_found(self):
        """Testa execução de tool inexistente."""
        server = MCPServer("test_mcp")
        
        result = await server.execute_tool("nonexistent", {})
        
        assert result.success is False
        assert "not found" in result.error


# ============================================================================
# Test REST Adapter
# ============================================================================


class TestRestApiAdapter:
    """Testes para RestApiAdapter."""
    
    def test_adapter_creation(self):
        """Testa criação de adapter."""
        adapter = RestApiAdapter(
            base_url="https://api.example.com/v1",
        )
        
        assert adapter.base_url == "https://api.example.com/v1"
    
    def test_as_tool_basic(self):
        """Testa conversão de endpoint em tool."""
        adapter = RestApiAdapter(base_url="https://api.example.com")
        
        tool_def = adapter.as_tool(
            method="GET",
            path="/users/{id}",
            name="get_user",
            description="Busca usuário por ID",
        )
        
        assert tool_def.name == "get_user"
        assert tool_def.description == "Busca usuário por ID"
        assert len(tool_def.parameters) == 1
        assert tool_def.parameters[0].name == "id"
    
    def test_as_tool_with_query_params(self):
        """Testa tool com query parameters."""
        adapter = RestApiAdapter(base_url="https://api.example.com")
        
        tool_def = adapter.as_tool(
            method="GET",
            path="/users",
            name="list_users",
            description="Lista usuários",
            query_params=[
                ToolParameter(name="limit", type="integer", description="Limite", required=False),
                ToolParameter(name="offset", type="integer", description="Offset", required=False),
            ],
        )
        
        assert len(tool_def.parameters) == 2
    
    def test_crud_tools(self):
        """Testa geração de tools CRUD."""
        adapter = RestApiAdapter(base_url="https://api.example.com")
        
        tools = adapter.crud_tools(
            resource_name="usuario",
            resource_path="/users",
        )
        
        tool_names = [t.name for t in tools]
        
        assert "listar_usuarios" in tool_names
        assert "buscar_usuario" in tool_names
        assert "deletar_usuario" in tool_names
    
    def test_annotations_for_get(self):
        """Testa annotations padrão para GET."""
        adapter = RestApiAdapter(base_url="https://api.example.com")
        
        tool_def = adapter.as_tool(
            method="GET",
            path="/data",
            name="get_data",
            description="Get data",
        )
        
        assert tool_def.annotations.read_only_hint is True
        assert tool_def.annotations.destructive_hint is False
    
    def test_annotations_for_delete(self):
        """Testa annotations padrão para DELETE."""
        adapter = RestApiAdapter(base_url="https://api.example.com")
        
        tool_def = adapter.as_tool(
            method="DELETE",
            path="/data/{id}",
            name="delete_data",
            description="Delete data",
        )
        
        assert tool_def.annotations.destructive_hint is True

    def test_rest_tool_handler_wrapper_signature(self):
        """Testa que o wrapper para handlers **kwargs gera assinatura explícita.
        Necessário para FastMCP gerar schema correto (evita parâmetro 'kwargs').
        """
        import inspect

        server = MCPServer("test_wrapper_mcp")
        adapter = RestApiAdapter(base_url="https://api.example.com")

        tool_def = adapter.as_tool(
            method="GET",
            path="/users/{user_id}",
            name="buscar_usuario",
            description="Busca usuário por ID",
        )
        server.register_tool(tool_def)

        # O wrapper é criado em _register_tool_in_fastmcp; testamos _create_handler_wrapper
        handler = tool_def.handler
        wrapped = server._create_handler_wrapper(handler, tool_def.parameters)

        # Wrapper deve ter assinatura com user_id, não kwargs
        sig = inspect.signature(wrapped)
        params = list(sig.parameters.keys())
        assert "user_id" in params
        assert "kwargs" not in params
        assert len(params) == 1

    def test_rest_tool_handler_wrapper_no_params(self):
        """Testa que tools sem parâmetros (ex: listar_items) têm assinatura vazia.
        Evita o erro 'kwargs field required' em tools como GET /items.
        """
        import inspect

        server = MCPServer("test_no_params_mcp")
        adapter = RestApiAdapter(base_url="https://api.example.com")

        tool_def = adapter.as_tool(
            method="GET",
            path="/items",
            name="listar_items",
            description="Lista todos os items",
        )
        server.register_tool(tool_def)

        handler = tool_def.handler
        wrapped = server._create_handler_wrapper(handler, tool_def.parameters)

        # Wrapper deve ter assinatura vazia, sem kwargs
        sig = inspect.signature(wrapped)
        params = list(sig.parameters.keys())
        assert len(params) == 0
        assert "kwargs" not in params


# ============================================================================
# Test Auth
# ============================================================================


class TestAuth:
    """Testes para módulo de autenticação."""
    
    def test_api_key_config(self):
        """Testa configuração de API key."""
        auth = api_key("X-API-Key", env_var="MY_KEY")
        
        assert auth.type == AuthType.API_KEY
        assert auth.header_name == "X-API-Key"
        assert auth.env_var == "MY_KEY"
    
    def test_bearer_config(self):
        """Testa configuração de Bearer."""
        auth = bearer("MY_TOKEN")
        
        assert auth.type == AuthType.BEARER
        assert auth.env_var == "MY_TOKEN"
        assert auth.token_prefix == "Bearer "
    
    def test_basic_config(self):
        """Testa configuração de Basic."""
        auth = basic("USER", "PASS")
        
        assert auth.type == AuthType.BASIC
        assert auth.username_env == "USER"
        assert auth.password_env == "PASS"
    
    def test_validate_auth_missing_env(self, monkeypatch):
        """Testa validação com variável de ambiente faltando."""
        monkeypatch.delenv("MISSING_VAR", raising=False)
        
        auth = api_key("X-API-Key", env_var="MISSING_VAR")
        is_valid, error = validate_auth(auth)
        
        assert is_valid is False
        assert "MISSING_VAR" in error
    
    def test_validate_auth_with_env(self, monkeypatch):
        """Testa validação com variável de ambiente presente."""
        monkeypatch.setenv("PRESENT_VAR", "token123")
        
        auth = api_key("X-API-Key", env_var="PRESENT_VAR")
        is_valid, error = validate_auth(auth)
        
        assert is_valid is True
        assert error is None


# ============================================================================
# Test Types
# ============================================================================


class TestToolDefinition:
    """Testes para ToolDefinition."""
    
    def test_to_json_schema(self):
        """Testa conversão para JSON Schema."""
        tool_def = ToolDefinition(
            name="test",
            description="Test tool",
            parameters=[
                ToolParameter(name="name", type="string", description="Name", required=True),
                ToolParameter(name="age", type="integer", description="Age", required=False, default=18),
            ],
        )
        
        schema = tool_def.to_json_schema()
        
        assert schema["type"] == "object"
        assert "name" in schema["properties"]
        assert "age" in schema["properties"]
        assert "name" in schema["required"]
        assert "age" not in schema["required"]
        assert schema["properties"]["age"]["default"] == 18


class TestToolResult:
    """Testes para ToolResult."""
    
    def test_success_result(self):
        """Testa resultado de sucesso."""
        result = ToolResult(success=True, data={"key": "value"})
        
        assert result.success is True
        assert result.data == {"key": "value"}
    
    def test_error_result(self):
        """Testa resultado de erro."""
        result = ToolResult(success=False, error="Something went wrong")
        
        assert result.success is False
        assert result.error == "Something went wrong"
    
    def test_to_text_json(self):
        """Testa conversão para texto JSON."""
        result = ToolResult(success=True, data={"key": "value"})
        text = result.to_text(ResponseFormat.JSON)
        
        data = json.loads(text)
        assert data["key"] == "value"
    
    def test_to_text_error(self):
        """Testa conversão de erro para texto."""
        result = ToolResult(success=False, error="Error message")
        text = result.to_text()
        
        assert "Error: Error message" == text


# ============================================================================
# Integration Tests
# ============================================================================


class TestIntegration:
    """Testes de integração."""
    
    @pytest.mark.asyncio
    async def test_full_workflow(self):
        """Testa workflow completo de criação e execução."""
        # Cria server
        server = MCPServer("integration_mcp")
        
        # Registra tools
        @server.tool()
        def multiply(a: int, b: int) -> int:
            """Multiplica dois números."""
            return a * b
        
        @server.tool(annotations={"readOnlyHint": True})
        def get_config(key: str) -> str:
            """Obtém configuração."""
            configs = {"env": "production", "debug": "false"}
            return configs.get(key, "not_found")
        
        # Registra resource
        @server.resource(uri="data://{name}")
        def get_data(name: str) -> str:
            return f"data_{name}"
        
        # Valida registros
        assert len(server._tools) == 2
        assert len(server._resources) == 1
        
        # Executa tools
        result1 = await server.execute_tool("multiply", {"a": 3, "b": 4})
        assert result1.success is True
        assert result1.data == 12
        
        result2 = await server.execute_tool("get_config", {"key": "env"})
        assert result2.success is True
        assert result2.data == "production"
        
        # Lê resource
        data = await server.read_resource("data://test")
        assert data == "data_test"


# ============================================================================
# Test Parameter Deduplication & Ordering
# ============================================================================


class TestParameterDeduplication:
    """Testes para deduplicação e ordenação de parâmetros."""

    def test_tool_definition_deduplicates_parameters(self):
        """ToolDefinition deve remover parâmetros com nomes duplicados."""
        tool_def = ToolDefinition(
            name="test_dedup",
            description="Tool com params duplicados",
            parameters=[
                ToolParameter(name="username", type="string", description="From path", required=True),
                ToolParameter(name="email", type="string", description="Email", required=True),
                ToolParameter(name="username", type="string", description="From body", required=False),
            ],
        )

        names = [p.name for p in tool_def.parameters]
        assert names.count("username") == 1
        # Primeira ocorrência (required) deve ser mantida
        username_param = next(p for p in tool_def.parameters if p.name == "username")
        assert username_param.required is True

    def test_tool_definition_orders_required_before_optional(self):
        """ToolDefinition deve ordenar required antes de optional."""
        tool_def = ToolDefinition(
            name="test_order",
            description="Tool com ordem misturada",
            parameters=[
                ToolParameter(name="user_id", type="string", description="Path param", required=True),
                ToolParameter(name="include_details", type="boolean", description="Query", required=False),
                ToolParameter(name="name", type="string", description="Body required", required=True),
                ToolParameter(name="email", type="string", description="Body optional", required=False),
            ],
        )

        params = tool_def.parameters
        # Required devem vir primeiro
        required_indices = [i for i, p in enumerate(params) if p.required]
        optional_indices = [i for i, p in enumerate(params) if not p.required]
        assert max(required_indices) < min(optional_indices)

    def test_rest_adapter_orders_mixed_required_optional(self):
        """RestApiAdapter deve ordenar required antes de optional mesmo com parâmetros misturados."""
        adapter = RestApiAdapter(base_url="https://api.example.com")

        tool_def = adapter.as_tool(
            method="POST",
            path="/users/{user_id}",
            name="update_user",
            description="Atualiza usuário",
            query_params=[
                ToolParameter(name="dry_run", type="boolean", description="Dry run", required=False, default=False),
            ],
            body_params=[
                ToolParameter(name="name", type="string", description="Nome", required=True),
                ToolParameter(name="bio", type="string", description="Bio", required=False),
            ],
        )

        params = tool_def.parameters
        required_names = [p.name for p in params if p.required]
        optional_names = [p.name for p in params if not p.required]

        # user_id e name devem ser required
        assert "user_id" in required_names
        assert "name" in required_names
        # dry_run e bio devem ser optional
        assert "dry_run" in optional_names
        assert "bio" in optional_names

        # Todos os required devem vir antes dos optional
        required_indices = [i for i, p in enumerate(params) if p.required]
        optional_indices = [i for i, p in enumerate(params) if not p.required]
        if required_indices and optional_indices:
            assert max(required_indices) < min(optional_indices)

    def test_rest_adapter_deduplicates_parameters(self):
        """RestApiAdapter deve remover parâmetros duplicados."""
        adapter = RestApiAdapter(base_url="https://api.example.com")

        tool_def = adapter.as_tool(
            method="PUT",
            path="/users/{username}",
            name="update_user",
            description="Atualiza usuário",
            body_params=[
                ToolParameter(name="username", type="string", description="Body username", required=False),
                ToolParameter(name="email", type="string", description="Email", required=True),
            ],
        )

        names = [p.name for p in tool_def.parameters]
        assert names.count("username") == 1

    def test_handler_wrapper_with_duplicate_params(self):
        """_create_handler_wrapper deve lidar com parâmetros duplicados sem crash."""
        server = MCPServer("test_dedup_wrapper_mcp")

        async def handler(**kwargs):
            return str(kwargs)

        params = [
            ToolParameter(name="username", type="string", description="Path", required=True),
            ToolParameter(name="email", type="string", description="Email", required=True),
            ToolParameter(name="username", type="string", description="Body dup", required=False),
        ]

        # Não deve lançar ValueError
        wrapped = server._create_handler_wrapper(handler, params)
        sig = inspect.signature(wrapped)
        param_names = list(sig.parameters.keys())

        # Deve ter username apenas uma vez
        assert param_names.count("username") == 1
        assert "email" in param_names

    def test_handler_wrapper_orders_required_before_optional(self):
        """_create_handler_wrapper deve criar assinatura com required antes de optional."""
        server = MCPServer("test_order_wrapper_mcp")

        async def handler(**kwargs):
            return str(kwargs)

        params = [
            ToolParameter(name="user_id", type="string", description="Path", required=True),
            ToolParameter(name="filter", type="string", description="Query", required=False),
            ToolParameter(name="name", type="string", description="Body", required=True),
        ]

        wrapped = server._create_handler_wrapper(handler, params)
        sig = inspect.signature(wrapped)
        sig_params = list(sig.parameters.values())

        # Verifica que required vêm antes de optional
        required_indices = [
            i for i, p in enumerate(sig_params) if p.default is inspect.Parameter.empty
        ]
        optional_indices = [
            i for i, p in enumerate(sig_params) if p.default is not inspect.Parameter.empty
        ]

        if required_indices and optional_indices:
            assert max(required_indices) < min(optional_indices)

    def test_openapi_parser_deduplicates_body_params(self):
        """OpenAPIParser deve deduplicar params que aparecem no path/query E no body."""
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "Test", "version": "1.0.0"},
            "servers": [{"url": "http://localhost:8000"}],
            "paths": {},
        }
        parser = OpenAPIParser(spec)

        operation = {
            "path": "/users/{username}",
            "method": "PUT",
            "operation_id": "updateUser",
            "summary": "Update user",
            "description": "Updates a user",
            "tags": [],
            "parameters": [
                {
                    "name": "username",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string"},
                }
            ],
            "request_body": {
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "properties": {
                                "username": {"type": "string", "description": "Username"},
                                "email": {"type": "string", "description": "Email"},
                            },
                            "required": ["email"],
                        }
                    }
                }
            },
            "responses": {},
        }

        tool_def = parser.operation_to_tool_definition(operation)
        names = [p.name for p in tool_def.parameters]

        # username deve aparecer apenas uma vez
        assert names.count("username") == 1
        # email deve estar presente
        assert "email" in names

    def test_openapi_parser_handles_xquik_search_contract(self):
        """OpenAPIParser deve preservar params, enum e limites em spec OpenAPI 3.1."""
        spec = {
            "openapi": "3.1.0",
            "info": {"title": "Xquik API", "version": "2.4.8"},
            "servers": [{"url": "https://xquik.com"}],
            "paths": {
                "/api/v1/x/tweets/search": {
                    "get": {
                        "operationId": "searchTweets",
                        "summary": "Search X posts",
                        "tags": ["X"],
                        "parameters": [
                            {
                                "name": "q",
                                "in": "query",
                                "required": True,
                                "schema": {"type": "string"},
                            },
                            {
                                "name": "queryType",
                                "in": "query",
                                "schema": {
                                    "type": "string",
                                    "enum": ["Latest", "Top"],
                                    "default": "Latest",
                                },
                            },
                            {
                                "name": "limit",
                                "in": "query",
                                "schema": {
                                    "type": "integer",
                                    "minimum": 1,
                                    "maximum": 200,
                                    "default": 20,
                                },
                            },
                        ],
                        "responses": {"200": {"description": "Search results"}},
                    }
                }
            },
        }
        parser = OpenAPIParser(spec)

        operations = parser.list_operations()
        tool_def = parser.operation_to_tool_definition(operations[0])
        params = {p.name: p for p in tool_def.parameters}

        assert parser.base_url == "https://xquik.com"
        assert parser.title == "Xquik API"
        assert tool_def.name == "search_tweets"
        assert tool_def.description == "Search X posts"
        assert tool_def.annotations.read_only_hint is True
        assert params["q"].required is True
        assert params["queryType"].enum == ["Latest", "Top"]
        assert params["queryType"].default == "Latest"
        assert params["limit"].type == "integer"
        assert params["limit"].default == 20
        assert params["limit"].minimum == 1
        assert params["limit"].maximum == 200
