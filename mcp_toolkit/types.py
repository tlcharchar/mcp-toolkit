"""
Tipos e modelos base do MCP Toolkit.

Este módulo define os modelos Pydantic usados em todo o SDK para
validação de entrada, configuração e estruturas de dados comuns.
"""

from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Literal, Optional, TypeVar, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ============================================================================
# Enums
# ============================================================================


class ResponseFormat(str, Enum):
    """Formato de resposta suportado pelas tools."""
    
    MARKDOWN = "markdown"
    JSON = "json"


class HttpMethod(str, Enum):
    """Métodos HTTP suportados."""
    
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"


class TransportType(str, Enum):
    """Tipos de transporte MCP suportados."""
    
    STDIO = "stdio"
    SSE = "sse"
    STREAMABLE_HTTP = "streamable_http"


class AuthType(str, Enum):
    """Tipos de autenticação suportados."""
    
    NONE = "none"
    API_KEY = "api_key"
    BEARER = "bearer"
    BASIC = "basic"
    OAUTH2 = "oauth2"


# ============================================================================
# Tool Annotations
# ============================================================================


class ToolAnnotations(BaseModel):
    """Anotações de comportamento para tools MCP."""
    
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    
    title: Optional[str] = Field(
        default=None,
        description="Título legível para humanos da tool"
    )
    read_only_hint: bool = Field(
        default=False,
        alias="readOnlyHint",
        description="Indica se a tool não modifica o ambiente"
    )
    destructive_hint: bool = Field(
        default=True,
        alias="destructiveHint",
        description="Indica se a tool pode realizar operações destrutivas"
    )
    idempotent_hint: bool = Field(
        default=False,
        alias="idempotentHint",
        description="Indica se chamadas repetidas não têm efeito adicional"
    )
    open_world_hint: bool = Field(
        default=True,
        alias="openWorldHint",
        description="Indica se a tool interage com entidades externas"
    )


# ============================================================================
# Tool Definition
# ============================================================================


class ToolParameter(BaseModel):
    """Definição de um parâmetro de tool."""
    
    model_config = ConfigDict(extra="forbid")
    
    name: str = Field(..., description="Nome do parâmetro")
    type: str = Field(..., description="Tipo do parâmetro (string, integer, etc.)")
    description: str = Field(..., description="Descrição do parâmetro")
    required: bool = Field(default=True, description="Se o parâmetro é obrigatório")
    default: Optional[Any] = Field(default=None, description="Valor padrão")
    enum: Optional[List[str]] = Field(default=None, description="Valores permitidos")
    minimum: Optional[float] = Field(default=None, description="Valor mínimo (números)")
    maximum: Optional[float] = Field(default=None, description="Valor máximo (números)")
    min_length: Optional[int] = Field(default=None, description="Tamanho mínimo (strings)")
    max_length: Optional[int] = Field(default=None, description="Tamanho máximo (strings)")
    pattern: Optional[str] = Field(default=None, description="Regex de validação (strings)")


class ToolDefinition(BaseModel):
    """Definição completa de uma tool MCP."""
    
    model_config = ConfigDict(extra="forbid")
    
    name: str = Field(..., description="Nome único da tool")
    description: str = Field(..., description="Descrição da tool")
    parameters: List[ToolParameter] = Field(
        default_factory=list,
        description="Parâmetros da tool"
    )
    annotations: ToolAnnotations = Field(
        default_factory=ToolAnnotations,
        description="Anotações de comportamento"
    )
    handler: Optional[Callable[..., Any]] = Field(
        default=None,
        exclude=True,
        description="Função handler da tool"
    )
    
    def to_json_schema(self) -> Dict[str, Any]:
        """Converte a definição para JSON Schema."""
        properties = {}
        required = []
        
        for param in self.parameters:
            prop: Dict[str, Any] = {
                "description": param.description
            }
            
            # Mapeia tipos Python para JSON Schema
            type_mapping = {
                "str": "string",
                "string": "string",
                "int": "integer",
                "integer": "integer",
                "float": "number",
                "number": "number",
                "bool": "boolean",
                "boolean": "boolean",
                "list": "array",
                "array": "array",
                "dict": "object",
                "object": "object",
            }
            
            prop["type"] = type_mapping.get(param.type.lower(), "string")
            
            if param.enum:
                prop["enum"] = param.enum
            if param.minimum is not None:
                prop["minimum"] = param.minimum
            if param.maximum is not None:
                prop["maximum"] = param.maximum
            if param.min_length is not None:
                prop["minLength"] = param.min_length
            if param.max_length is not None:
                prop["maxLength"] = param.max_length
            if param.pattern:
                prop["pattern"] = param.pattern
            if param.default is not None:
                prop["default"] = param.default
                
            properties[param.name] = prop
            
            if param.required:
                required.append(param.name)
        
        return {
            "type": "object",
            "properties": properties,
            "required": required
        }


# ============================================================================
# Resource Definition
# ============================================================================


class ResourceDefinition(BaseModel):
    """Definição de um resource MCP."""
    
    model_config = ConfigDict(extra="forbid")
    
    uri: str = Field(..., description="URI template do resource (ex: docs://{name})")
    name: str = Field(..., description="Nome do resource")
    description: str = Field(..., description="Descrição do resource")
    mime_type: str = Field(default="text/plain", description="MIME type do conteúdo")
    handler: Optional[Callable[..., Any]] = Field(
        default=None,
        exclude=True,
        description="Função handler do resource"
    )


# ============================================================================
# Prompt Definition
# ============================================================================


class PromptArgument(BaseModel):
    """Argumento de um prompt MCP."""
    
    model_config = ConfigDict(extra="forbid")
    
    name: str = Field(..., description="Nome do argumento")
    description: str = Field(..., description="Descrição do argumento")
    required: bool = Field(default=True, description="Se o argumento é obrigatório")


class PromptDefinition(BaseModel):
    """Definição de um prompt MCP."""
    
    model_config = ConfigDict(extra="forbid")
    
    name: str = Field(..., description="Nome único do prompt")
    description: str = Field(..., description="Descrição do prompt")
    arguments: List[PromptArgument] = Field(
        default_factory=list,
        description="Argumentos do prompt"
    )
    handler: Optional[Callable[..., str]] = Field(
        default=None,
        exclude=True,
        description="Função que gera o prompt"
    )


# ============================================================================
# REST API Configuration
# ============================================================================


class AuthConfig(BaseModel):
    """Configuração de autenticação para APIs REST."""
    
    model_config = ConfigDict(extra="forbid")
    
    type: AuthType = Field(default=AuthType.NONE, description="Tipo de autenticação")
    
    # API Key / Bearer
    header_name: Optional[str] = Field(
        default=None,
        description="Nome do header (ex: X-API-Key, Authorization)"
    )
    token_prefix: Optional[str] = Field(
        default=None,
        description="Prefixo do token (ex: Bearer)"
    )
    env_var: Optional[str] = Field(
        default=None,
        description="Nome da variável de ambiente com o token"
    )
    
    # Basic Auth
    username_env: Optional[str] = Field(
        default=None,
        description="Variável de ambiente com username"
    )
    password_env: Optional[str] = Field(
        default=None,
        description="Variável de ambiente com password"
    )
    
    # OAuth2
    client_id_env: Optional[str] = Field(default=None)
    client_secret_env: Optional[str] = Field(default=None)
    token_url: Optional[str] = Field(default=None)
    scopes: Optional[List[str]] = Field(default=None)


class RestEndpointConfig(BaseModel):
    """Configuração de um endpoint REST para conversão em tool."""
    
    model_config = ConfigDict(extra="forbid")
    
    method: HttpMethod = Field(..., description="Método HTTP")
    path: str = Field(..., description="Path do endpoint (suporta templates: /users/{id})")
    name: str = Field(..., description="Nome da tool resultante")
    description: str = Field(..., description="Descrição da tool")
    
    # Parâmetros
    path_params: List[ToolParameter] = Field(
        default_factory=list,
        description="Parâmetros de path"
    )
    query_params: List[ToolParameter] = Field(
        default_factory=list,
        description="Parâmetros de query string"
    )
    body_schema: Optional[Dict[str, Any]] = Field(
        default=None,
        description="JSON Schema do body"
    )
    
    # Comportamento
    annotations: ToolAnnotations = Field(
        default_factory=ToolAnnotations,
        description="Anotações de comportamento"
    )
    timeout: float = Field(default=30.0, description="Timeout em segundos")
    
    # Transformação de resposta
    response_path: Optional[str] = Field(
        default=None,
        description="JSON path para extrair da resposta (ex: data.items)"
    )


# ============================================================================
# Server Configuration
# ============================================================================


class ServerConfig(BaseModel):
    """Configuração do MCP Server."""
    
    model_config = ConfigDict(extra="forbid")
    
    name: str = Field(..., description="Nome do server (ex: vendas_mcp)")
    version: str = Field(default="1.0.0", description="Versão do server")
    description: Optional[str] = Field(default=None, description="Descrição do server")
    
    # Transporte
    transport: TransportType = Field(
        default=TransportType.STDIO,
        description="Tipo de transporte"
    )
    host: str = Field(default="127.0.0.1", description="Host para HTTP")
    port: int = Field(default=9000, ge=1, le=65535, description="Porta para HTTP")
    
    # Logging
    log_level: str = Field(default="INFO", description="Nível de log")
    structured_logging: bool = Field(default=True, description="Usar JSON logs")
    
    # Métricas
    metrics_enabled: bool = Field(default=False, description="Habilitar métricas Prometheus")
    metrics_port: int = Field(default=9090, ge=1, le=65535, description="Porta das métricas")
    
    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Valida que o nome segue o padrão {service}_mcp."""
        import re
        if not re.match(r"^[a-z][a-z0-9_]*_mcp$", v):
            raise ValueError(
                f"Nome deve seguir o padrão '{{service}}_mcp' (ex: vendas_mcp). "
                f"Recebido: '{v}'"
            )
        return v


# ============================================================================
# Resultado de Tool
# ============================================================================


class ToolResult(BaseModel):
    """Resultado padronizado de execução de tool."""
    
    model_config = ConfigDict(extra="allow")
    
    success: bool = Field(..., description="Se a execução foi bem sucedida")
    data: Optional[Any] = Field(default=None, description="Dados retornados")
    error: Optional[str] = Field(default=None, description="Mensagem de erro")
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Metadados adicionais"
    )
    
    def to_text(self, format: ResponseFormat = ResponseFormat.JSON) -> str:
        """Converte o resultado para texto."""
        if not self.success:
            return f"Error: {self.error}"
        
        if format == ResponseFormat.JSON:
            return json.dumps(self.data, indent=2, default=str)
        
        # Markdown
        if isinstance(self.data, dict):
            return self._dict_to_markdown(self.data)
        elif isinstance(self.data, list):
            return self._list_to_markdown(self.data)
        else:
            return str(self.data)
    
    def _dict_to_markdown(self, data: Dict[str, Any], level: int = 1) -> str:
        """Converte dict para markdown."""
        lines = []
        for key, value in data.items():
            if isinstance(value, dict):
                lines.append(f"{'#' * (level + 1)} {key.replace('_', ' ').title()}")
                lines.append(self._dict_to_markdown(value, level + 1))
            elif isinstance(value, list):
                lines.append(f"**{key.replace('_', ' ').title()}**:")
                for item in value:
                    if isinstance(item, dict):
                        lines.append(f"- {json.dumps(item)}")
                    else:
                        lines.append(f"- {item}")
            else:
                lines.append(f"**{key.replace('_', ' ').title()}**: {value}")
        return "\n".join(lines)
    
    def _list_to_markdown(self, data: List[Any]) -> str:
        """Converte lista para markdown."""
        lines = []
        for i, item in enumerate(data, 1):
            if isinstance(item, dict):
                lines.append(f"### Item {i}")
                lines.append(self._dict_to_markdown(item, 2))
            else:
                lines.append(f"{i}. {item}")
        return "\n".join(lines)


# ============================================================================
# Type Aliases
# ============================================================================

ToolHandler = Callable[..., Any]
ResourceHandler = Callable[..., Union[str, bytes]]
PromptHandler = Callable[..., str]
