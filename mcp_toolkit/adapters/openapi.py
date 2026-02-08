"""
Adapter para importação de OpenAPI specs como MCP tools.

Este módulo permite converter automaticamente uma spec OpenAPI
em múltiplas MCP tools.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Set, Tuple, Union
from urllib.parse import urljoin, urlparse

import httpx
import yaml

from ..types import (
    AuthConfig,
    AuthType,
    HttpMethod,
    ToolAnnotations,
    ToolDefinition,
    ToolParameter,
)
from .rest import RestApiAdapter


# ============================================================================
# OpenAPI Parser
# ============================================================================


class OpenAPIParser:
    """Parser para especificações OpenAPI 3.x."""
    
    def __init__(self, spec: Dict[str, Any]):
        """
        Inicializa o parser.
        
        Args:
            spec: Spec OpenAPI como dicionário
        """
        self.spec = spec
        self._components = spec.get("components", {})
        self._schemas = self._components.get("schemas", {})
    
    @classmethod
    def from_url(cls, url: str, headers: Optional[Dict[str, str]] = None) -> "OpenAPIParser":
        """Carrega spec de uma URL."""
        response = httpx.get(url, headers=headers, timeout=30.0)
        response.raise_for_status()
        
        content_type = response.headers.get("content-type", "")
        
        if "yaml" in content_type or url.endswith((".yaml", ".yml")):
            spec = yaml.safe_load(response.text)
        else:
            spec = response.json()
        
        return cls(spec)
    
    @classmethod
    def from_file(cls, path: str) -> "OpenAPIParser":
        """Carrega spec de um arquivo."""
        with open(path, "r") as f:
            if path.endswith((".yaml", ".yml")):
                spec = yaml.safe_load(f)
            else:
                spec = json.load(f)
        
        return cls(spec)
    
    @property
    def base_url(self) -> str:
        """Retorna a URL base da API."""
        servers = self.spec.get("servers", [])
        if servers:
            return servers[0].get("url", "")
        return ""
    
    @property
    def title(self) -> str:
        """Retorna o título da API."""
        info = self.spec.get("info", {})
        return info.get("title", "API")
    
    def list_operations(self) -> List[Dict[str, Any]]:
        """Lista todas as operações da spec."""
        operations = []
        
        paths = self.spec.get("paths", {})
        for path, path_item in paths.items():
            for method in ["get", "post", "put", "patch", "delete"]:
                if method in path_item:
                    operation = path_item[method]
                    operations.append({
                        "path": path,
                        "method": method.upper(),
                        "operation_id": operation.get("operationId"),
                        "summary": operation.get("summary", ""),
                        "description": operation.get("description", ""),
                        "tags": operation.get("tags", []),
                        "parameters": operation.get("parameters", []),
                        "request_body": operation.get("requestBody"),
                        "responses": operation.get("responses", {}),
                    })
        
        return operations
    
    def list_tags(self) -> List[str]:
        """Lista todas as tags únicas."""
        tags: Set[str] = set()
        for op in self.list_operations():
            tags.update(op.get("tags", []))
        return sorted(tags)
    
    def _resolve_ref(self, ref: str) -> Dict[str, Any]:
        """Resolve uma referência $ref."""
        # #/components/schemas/User -> components.schemas.User
        if not ref.startswith("#/"):
            return {}
        
        parts = ref[2:].split("/")
        result = self.spec
        
        for part in parts:
            if isinstance(result, dict) and part in result:
                result = result[part]
            else:
                return {}
        
        return result if isinstance(result, dict) else {}
    
    def _schema_to_parameters(
        self,
        schema: Dict[str, Any],
        prefix: str = "",
    ) -> List[ToolParameter]:
        """Converte um JSON Schema em lista de ToolParameter."""
        parameters = []
        
        # Resolve $ref
        if "$ref" in schema:
            schema = self._resolve_ref(schema["$ref"])
        
        if schema.get("type") != "object":
            return parameters
        
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))
        
        for name, prop in properties.items():
            # Resolve $ref em propriedades
            if "$ref" in prop:
                prop = self._resolve_ref(prop["$ref"])
            
            param_name = f"{prefix}{name}" if prefix else name
            
            # Tipo
            param_type = prop.get("type", "string")
            if param_type == "array":
                param_type = "array"
            elif param_type == "object":
                # Objetos aninhados são serializados como JSON string
                param_type = "object"
            
            parameters.append(ToolParameter(
                name=param_name,
                type=param_type,
                description=prop.get("description", f"Parameter {name}"),
                required=name in required,
                default=prop.get("default"),
                enum=prop.get("enum"),
                minimum=prop.get("minimum"),
                maximum=prop.get("maximum"),
                min_length=prop.get("minLength"),
                max_length=prop.get("maxLength"),
                pattern=prop.get("pattern"),
            ))
        
        return parameters
    
    def operation_to_tool_definition(
        self,
        operation: Dict[str, Any],
        name_prefix: str = "",
    ) -> ToolDefinition:
        """Converte uma operação OpenAPI em ToolDefinition."""
        # Nome da tool
        operation_id = operation.get("operation_id")
        if operation_id:
            tool_name = self._normalize_name(operation_id)
        else:
            # Gera nome a partir do path e método
            path_parts = operation["path"].strip("/").replace("/", "_").replace("{", "").replace("}", "")
            tool_name = f"{operation['method'].lower()}_{path_parts}"
        
        if name_prefix:
            tool_name = f"{name_prefix}_{tool_name}"
        
        tool_name = self._normalize_name(tool_name)
        
        # Descrição
        description = operation.get("summary") or operation.get("description") or f"API operation: {tool_name}"
        
        # Parâmetros
        parameters = []
        
        # Path e query parameters
        for param in operation.get("parameters", []):
            # Resolve $ref
            if "$ref" in param:
                param = self._resolve_ref(param["$ref"])
            
            param_in = param.get("in", "query")
            schema = param.get("schema", {})
            
            # Resolve $ref no schema
            if "$ref" in schema:
                schema = self._resolve_ref(schema["$ref"])
            
            parameters.append(ToolParameter(
                name=param.get("name", "param"),
                type=schema.get("type", "string"),
                description=param.get("description", ""),
                required=param.get("required", param_in == "path"),
                default=schema.get("default"),
                enum=schema.get("enum"),
                minimum=schema.get("minimum"),
                maximum=schema.get("maximum"),
            ))
        
        # Request body
        request_body = operation.get("request_body")
        if request_body:
            # Resolve $ref
            if "$ref" in request_body:
                request_body = self._resolve_ref(request_body["$ref"])
            
            content = request_body.get("content", {})
            json_content = content.get("application/json", {})
            schema = json_content.get("schema", {})
            
            body_params = self._schema_to_parameters(schema)
            parameters.extend(body_params)
        
        # Annotations
        method = operation["method"]
        annotations = ToolAnnotations(
            title=operation.get("summary", tool_name),
            read_only_hint=method == "GET",
            destructive_hint=method == "DELETE",
            idempotent_hint=method in ("GET", "PUT", "DELETE"),
            open_world_hint=True,
        )
        
        return ToolDefinition(
            name=tool_name,
            description=description,
            parameters=parameters,
            annotations=annotations,
        )
    
    def _normalize_name(self, name: str) -> str:
        """Normaliza nome para snake_case."""
        # Remove caracteres especiais
        name = re.sub(r"[^a-zA-Z0-9_]", "_", name)
        # CamelCase para snake_case
        name = re.sub(r"([a-z])([A-Z])", r"\1_\2", name)
        # Remove underscores duplicados
        name = re.sub(r"_+", "_", name)
        # Lowercase
        name = name.lower().strip("_")
        return name


# ============================================================================
# OpenAPI Adapter
# ============================================================================


class OpenAPIAdapter:
    """
    Adapter para converter OpenAPI specs em MCP tools.
    
    Exemplo:
        adapter = OpenAPIAdapter.from_url(
            "https://api.exemplo.com/openapi.json"
        )
        
        # Todas as tools
        tools = adapter.all_tools()
        
        # Apenas algumas tags
        tools = adapter.tools_matching(tags=["users", "orders"])
        
        # Apenas operações específicas
        tools = adapter.tools_matching(operation_ids=["getUser", "createUser"])
    """
    
    def __init__(
        self,
        parser: OpenAPIParser,
        auth: Optional[AuthConfig] = None,
        timeout: float = 30.0,
        name_prefix: str = "",
    ):
        """
        Inicializa o adapter.
        
        Args:
            parser: Parser OpenAPI com a spec carregada
            auth: Configuração de autenticação
            timeout: Timeout para requisições
            name_prefix: Prefixo para nomes de tools
        """
        self.parser = parser
        self.auth = auth
        self.timeout = timeout
        self.name_prefix = name_prefix
        
        base = parser.base_url.strip()
        if not base or not base.startswith(("http://", "https://")):
            raise ValueError(
                "OpenAPI spec precisa de URL base com protocolo (ex: http://localhost:8000). "
                "Adicione 'servers': [{'url': 'http://localhost:8000'}] na spec ou use "
                "OpenAPIAdapter.from_url(..., base_url='http://localhost:8000')."
            )
        
        self._rest_adapter = RestApiAdapter(
            base_url=base,
            auth=auth,
            timeout=timeout,
            prefix=name_prefix,
        )
    
    @classmethod
    def from_url(
        cls,
        url: str,
        auth: Optional[AuthConfig] = None,
        auth_header: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 30.0,
        name_prefix: str = "",
    ) -> "OpenAPIAdapter":
        """
        Cria adapter a partir de URL da spec.
        
        Args:
            url: URL da spec OpenAPI
            auth: Configuração de autenticação
            auth_header: Nome do header de autenticação (atalho)
            base_url: URL base da API (opcional). Se a spec não tiver "servers"
                e base_url não for passado, é derivado da URL da spec
                (ex: http://localhost:8000/openapi.json -> http://localhost:8000).
            timeout: Timeout para requisições
            name_prefix: Prefixo para nomes de tools
        """
        # Atalho para auth simples
        if auth is None and auth_header:
            auth = AuthConfig(
                type=AuthType.API_KEY,
                header_name=auth_header,
                env_var=auth_header.upper().replace("-", "_"),
            )
        
        parser = OpenAPIParser.from_url(url)
        resolved_base = (base_url or "").strip() or parser.base_url.strip()
        if not resolved_base:
            # Deriva da URL da spec (ex: http://localhost:8000/openapi.json -> http://localhost:8000)
            parsed = urlparse(url)
            if parsed.scheme and parsed.netloc:
                resolved_base = f"{parsed.scheme}://{parsed.netloc}"
        if resolved_base:
            parser.spec["servers"] = [{"url": resolved_base.rstrip("/")}]
        
        return cls(parser, auth=auth, timeout=timeout, name_prefix=name_prefix)
    
    @classmethod
    def from_file(
        cls,
        path: str,
        base_url: str,
        auth: Optional[AuthConfig] = None,
        timeout: float = 30.0,
        name_prefix: str = "",
    ) -> "OpenAPIAdapter":
        """Cria adapter a partir de arquivo local."""
        parser = OpenAPIParser.from_file(path)
        
        # Override base_url se fornecido
        if base_url:
            parser.spec["servers"] = [{"url": base_url}]
        
        return cls(parser, auth=auth, timeout=timeout, name_prefix=name_prefix)
    
    def all_tools(self) -> List[ToolDefinition]:
        """Retorna todas as operações como tools."""
        tools = []
        
        for operation in self.parser.list_operations():
            tool_def = self._operation_to_tool(operation)
            tools.append(tool_def)
        
        return tools
    
    def tools_matching(
        self,
        tags: Optional[List[str]] = None,
        operation_ids: Optional[List[str]] = None,
        methods: Optional[List[str]] = None,
        path_pattern: Optional[str] = None,
    ) -> List[ToolDefinition]:
        """
        Retorna tools que correspondem aos filtros.
        
        Args:
            tags: Lista de tags para filtrar
            operation_ids: Lista de operationIds para filtrar
            methods: Lista de métodos HTTP para filtrar
            path_pattern: Regex para filtrar paths
        """
        tools = []
        
        for operation in self.parser.list_operations():
            # Filtro por tags
            if tags:
                op_tags = set(operation.get("tags", []))
                if not op_tags.intersection(tags):
                    continue
            
            # Filtro por operation_id
            if operation_ids:
                if operation.get("operation_id") not in operation_ids:
                    continue
            
            # Filtro por método
            if methods:
                if operation["method"] not in [m.upper() for m in methods]:
                    continue
            
            # Filtro por path
            if path_pattern:
                if not re.search(path_pattern, operation["path"]):
                    continue
            
            tool_def = self._operation_to_tool(operation)
            tools.append(tool_def)
        
        return tools
    
    def _operation_to_tool(self, operation: Dict[str, Any]) -> ToolDefinition:
        """Converte operação em tool com handler."""
        # Usa o parser para definição base
        tool_def = self.parser.operation_to_tool_definition(
            operation,
            name_prefix=self.name_prefix,
        )
        
        # Cria handler via REST adapter
        path_params = []
        query_params = []
        body_params = []
        
        for param in operation.get("parameters", []):
            if "$ref" in param:
                param = self.parser._resolve_ref(param["$ref"])
            
            param_in = param.get("in", "query")
            if param_in == "path":
                path_params.append(param.get("name"))
            else:
                query_params.append(param.get("name"))
        
        # Body params
        if operation.get("request_body"):
            for p in tool_def.parameters:
                if p.name not in path_params and p.name not in query_params:
                    body_params.append(p.name)
        
        # Cria handler
        handler = self._rest_adapter._create_handler(
            method=HttpMethod(operation["method"]),
            path=operation["path"],
            path_params=path_params,
            query_params=query_params,
            body_params=body_params,
            response_path=None,
        )
        
        tool_def.handler = handler
        return tool_def
    
    def list_available_tags(self) -> List[str]:
        """Lista tags disponíveis na spec."""
        return self.parser.list_tags()
    
    def list_available_operations(self) -> List[Dict[str, str]]:
        """Lista operações disponíveis com metadata básico."""
        return [
            {
                "operation_id": op.get("operation_id"),
                "method": op["method"],
                "path": op["path"],
                "summary": op.get("summary", ""),
                "tags": op.get("tags", []),
            }
            for op in self.parser.list_operations()
        ]
