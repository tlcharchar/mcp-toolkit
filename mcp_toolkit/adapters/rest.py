"""
Adapter para conversão de APIs REST em MCP tools.

Este módulo permite transformar endpoints REST existentes
em tools MCP de forma declarativa.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from urllib.parse import urljoin

import httpx
from pydantic import BaseModel, Field

from ..types import (
    AuthConfig,
    AuthType,
    HttpMethod,
    RestEndpointConfig,
    ToolAnnotations,
    ToolDefinition,
    ToolParameter,
    ToolResult,
)


# ============================================================================
# HTTP Client
# ============================================================================


class AsyncHttpClient:
    """Cliente HTTP async com suporte a autenticação, retry e opcionalmente HTTP/2."""

    def __init__(
        self,
        base_url: str,
        auth: Optional[AuthConfig] = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        headers: Optional[Dict[str, str]] = None,
        http2: bool = False,
    ):
        self.base_url = base_url.rstrip("/")
        self.auth = auth or AuthConfig()
        self.timeout = timeout
        self.max_retries = max_retries
        self.default_headers = headers or {}
        self.http2 = http2
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Obtém ou cria o cliente HTTP."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                headers=self._build_headers(),
                http2=self.http2,
            )
        return self._client
    
    def _build_headers(self) -> Dict[str, str]:
        """Constrói headers incluindo autenticação."""
        headers = self.default_headers.copy()
        
        if self.auth.type == AuthType.API_KEY:
            token = self._get_env_value(self.auth.env_var)
            if token and self.auth.header_name:
                prefix = self.auth.token_prefix or ""
                headers[self.auth.header_name] = f"{prefix}{token}".strip()
        
        elif self.auth.type == AuthType.BEARER:
            token = self._get_env_value(self.auth.env_var)
            if token:
                headers["Authorization"] = f"Bearer {token}"
        
        elif self.auth.type == AuthType.BASIC:
            username = self._get_env_value(self.auth.username_env)
            password = self._get_env_value(self.auth.password_env)
            if username and password:
                import base64
                credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
                headers["Authorization"] = f"Basic {credentials}"
        
        return headers
    
    def _get_env_value(self, var_name: Optional[str]) -> Optional[str]:
        """Obtém valor de variável de ambiente."""
        if var_name:
            return os.environ.get(var_name)
        return None
    
    async def request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> httpx.Response:
        """
        Faz uma requisição HTTP com retry.
        
        Args:
            method: Método HTTP
            path: Path do endpoint
            params: Query parameters
            json_body: Body JSON
            headers: Headers adicionais
        
        Returns:
            Response HTTP
        """
        client = await self._get_client()
        
        for attempt in range(self.max_retries):
            try:
                response = await client.request(
                    method=method,
                    url=path,
                    params=params,
                    json=json_body,
                    headers=headers,
                )
                
                # Retry em 429 (rate limit) e 5xx
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt < self.max_retries - 1:
                        wait_time = 2 ** attempt
                        await asyncio.sleep(wait_time)
                        continue
                
                return response
                
            except httpx.TimeoutException:
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise
        
        raise httpx.TimeoutException("Max retries exceeded")
    
    async def close(self) -> None:
        """Fecha o cliente HTTP."""
        if self._client:
            await self._client.aclose()
            self._client = None


# ============================================================================
# REST API Adapter
# ============================================================================


class RestApiAdapter:
    """
    Adapter para converter endpoints REST em MCP tools.

    Exemplo:
        adapter = RestApiAdapter(
            base_url="https://api.exemplo.com/v1",
            auth=AuthConfig(
                type=AuthType.BEARER,
                env_var="API_TOKEN"
            ),
            http2=True,  # use se a API suportar HTTP/2 (pip install mcp-toolkit[http2])
        )

        tool = adapter.as_tool(
            method="GET",
            path="/clientes/{id}",
            name="buscar_cliente",
            description="Busca um cliente pelo ID"
        )
    """

    def __init__(
        self,
        base_url: str,
        auth: Optional[AuthConfig] = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        headers: Optional[Dict[str, str]] = None,
        prefix: str = "",
        http2: bool = False,
    ):
        """
        Inicializa o adapter.

        Args:
            base_url: URL base da API
            auth: Configuração de autenticação
            timeout: Timeout padrão em segundos
            max_retries: Número máximo de retries
            headers: Headers padrão
            prefix: Prefixo para nomes de tools
            http2: Se True, usa HTTP/2 para chamadas à API (requer pip install mcp-toolkit[http2])
        """
        self.base_url = base_url
        self.auth = auth
        self.timeout = timeout
        self.max_retries = max_retries
        self.headers = headers
        self.prefix = prefix

        self._client = AsyncHttpClient(
            base_url=base_url,
            auth=auth,
            timeout=timeout,
            max_retries=max_retries,
            headers=headers,
            http2=http2,
        )
    
    def as_tool(
        self,
        method: Union[str, HttpMethod],
        path: str,
        name: str,
        description: str,
        path_params: Optional[List[ToolParameter]] = None,
        query_params: Optional[List[ToolParameter]] = None,
        body_params: Optional[List[ToolParameter]] = None,
        annotations: Optional[ToolAnnotations] = None,
        response_path: Optional[str] = None,
    ) -> ToolDefinition:
        """
        Converte um endpoint REST em uma MCP tool.
        
        Args:
            method: Método HTTP (GET, POST, etc.)
            path: Path do endpoint (suporta {param} para path params)
            name: Nome da tool
            description: Descrição da tool
            path_params: Parâmetros de path (extraídos automaticamente se não fornecidos)
            query_params: Parâmetros de query string
            body_params: Parâmetros do body (para POST/PUT/PATCH)
            annotations: Anotações de comportamento
            response_path: JSON path para extrair da resposta
        
        Returns:
            ToolDefinition pronta para registro
        """
        if isinstance(method, str):
            method = HttpMethod(method.upper())
        
        # Extrai path params automaticamente
        if path_params is None:
            path_params = self._extract_path_params(path)
        
        # Define annotations padrão baseado no método
        if annotations is None:
            annotations = self._default_annotations(method)
        
        # Combina todos os parâmetros
        all_params = list(path_params)
        if query_params:
            all_params.extend(query_params)
        if body_params and method in (HttpMethod.POST, HttpMethod.PUT, HttpMethod.PATCH):
            all_params.extend(body_params)
        
        # Nome com prefixo
        full_name = f"{self.prefix}{name}" if self.prefix else name
        
        # Cria handler
        handler = self._create_handler(
            method=method,
            path=path,
            path_params=[p.name for p in (path_params or [])],
            query_params=[p.name for p in (query_params or [])],
            body_params=[p.name for p in (body_params or [])],
            response_path=response_path,
        )
        
        return ToolDefinition(
            name=full_name,
            description=description,
            parameters=all_params,
            annotations=annotations,
            handler=handler,
        )
    
    def _extract_path_params(self, path: str) -> List[ToolParameter]:
        """Extrai parâmetros de path do template."""
        params = []
        matches = re.findall(r"\{(\w+)\}", path)
        
        for match in matches:
            params.append(ToolParameter(
                name=match,
                type="string",
                description=f"Path parameter: {match}",
                required=True,
            ))
        
        return params
    
    def _default_annotations(self, method: HttpMethod) -> ToolAnnotations:
        """Retorna annotations padrão baseado no método."""
        if method == HttpMethod.GET:
            return ToolAnnotations(
                read_only_hint=True,
                destructive_hint=False,
                idempotent_hint=True,
                open_world_hint=True,
            )
        elif method == HttpMethod.DELETE:
            return ToolAnnotations(
                read_only_hint=False,
                destructive_hint=True,
                idempotent_hint=True,
                open_world_hint=True,
            )
        elif method in (HttpMethod.POST, HttpMethod.PUT, HttpMethod.PATCH):
            return ToolAnnotations(
                read_only_hint=False,
                destructive_hint=method == HttpMethod.PUT,
                idempotent_hint=method == HttpMethod.PUT,
                open_world_hint=True,
            )
        
        return ToolAnnotations()
    
    def _create_handler(
        self,
        method: HttpMethod,
        path: str,
        path_params: List[str],
        query_params: List[str],
        body_params: List[str],
        response_path: Optional[str],
    ) -> Callable[..., Any]:
        """Cria handler async para a tool."""
        client = self._client
        
        async def handler(**kwargs: Any) -> str:
            # Substitui path params
            actual_path = path
            for param in path_params:
                if param in kwargs:
                    actual_path = actual_path.replace(f"{{{param}}}", str(kwargs[param]))
            
            # Separa query params
            query = {k: v for k, v in kwargs.items() if k in query_params and v is not None}
            
            # Separa body params
            body = None
            if body_params:
                body = {k: v for k, v in kwargs.items() if k in body_params and v is not None}
            
            try:
                response = await client.request(
                    method=method.value,
                    path=actual_path,
                    params=query if query else None,
                    json_body=body,
                )
                
                response.raise_for_status()
                
                # Parse response
                try:
                    data = response.json()
                except json.JSONDecodeError:
                    data = response.text
                
                # Extrai subpath se especificado
                if response_path and isinstance(data, dict):
                    for key in response_path.split("."):
                        if isinstance(data, dict) and key in data:
                            data = data[key]
                        else:
                            break
                
                return json.dumps(data, indent=2, default=str)
                
            except httpx.HTTPStatusError as e:
                return _format_http_error(e)
            except httpx.TimeoutException:
                return "Error: Request timed out. Please try again."
            except Exception as e:
                return f"Error: {type(e).__name__}: {str(e)}"
        
        return handler
    
    def crud_tools(
        self,
        resource_name: str,
        resource_path: str,
        id_param: str = "id",
        list_params: Optional[List[ToolParameter]] = None,
        create_params: Optional[List[ToolParameter]] = None,
        update_params: Optional[List[ToolParameter]] = None,
    ) -> List[ToolDefinition]:
        """
        Gera tools CRUD para um resource.
        
        Args:
            resource_name: Nome do resource (ex: "cliente")
            resource_path: Path base (ex: "/clientes")
            id_param: Nome do parâmetro de ID
            list_params: Parâmetros para listagem
            create_params: Parâmetros para criação
            update_params: Parâmetros para atualização
        
        Returns:
            Lista de ToolDefinitions para CRUD
        """
        tools = []
        
        # LIST
        tools.append(self.as_tool(
            method=HttpMethod.GET,
            path=resource_path,
            name=f"listar_{resource_name}s",
            description=f"Lista todos os {resource_name}s",
            query_params=list_params or [
                ToolParameter(
                    name="limit",
                    type="integer",
                    description="Número máximo de resultados",
                    required=False,
                    default=20,
                    minimum=1,
                    maximum=100,
                ),
                ToolParameter(
                    name="offset",
                    type="integer",
                    description="Offset para paginação",
                    required=False,
                    default=0,
                    minimum=0,
                ),
            ],
        ))
        
        # GET
        tools.append(self.as_tool(
            method=HttpMethod.GET,
            path=f"{resource_path}/{{{id_param}}}",
            name=f"buscar_{resource_name}",
            description=f"Busca um {resource_name} pelo ID",
        ))
        
        # CREATE
        if create_params:
            tools.append(self.as_tool(
                method=HttpMethod.POST,
                path=resource_path,
                name=f"criar_{resource_name}",
                description=f"Cria um novo {resource_name}",
                body_params=create_params,
            ))
        
        # UPDATE
        if update_params:
            tools.append(self.as_tool(
                method=HttpMethod.PUT,
                path=f"{resource_path}/{{{id_param}}}",
                name=f"atualizar_{resource_name}",
                description=f"Atualiza um {resource_name}",
                body_params=update_params,
            ))
        
        # DELETE
        tools.append(self.as_tool(
            method=HttpMethod.DELETE,
            path=f"{resource_path}/{{{id_param}}}",
            name=f"deletar_{resource_name}",
            description=f"Remove um {resource_name}",
        ))
        
        return tools
    
    async def close(self) -> None:
        """Fecha conexões."""
        await self._client.close()


# ============================================================================
# Error Formatting
# ============================================================================


def _format_http_error(error: httpx.HTTPStatusError) -> str:
    """Formata erro HTTP de forma amigável."""
    status = error.response.status_code
    
    messages = {
        400: "Bad Request - Verifique os parâmetros enviados.",
        401: "Unauthorized - Credenciais inválidas ou expiradas.",
        403: "Forbidden - Sem permissão para acessar este recurso.",
        404: "Not Found - Recurso não encontrado.",
        409: "Conflict - Conflito com o estado atual do recurso.",
        422: "Unprocessable Entity - Dados inválidos.",
        429: "Rate Limit - Muitas requisições. Aguarde um momento.",
        500: "Internal Server Error - Erro no servidor.",
        502: "Bad Gateway - Servidor indisponível.",
        503: "Service Unavailable - Serviço temporariamente indisponível.",
    }
    
    message = messages.get(status, f"HTTP Error {status}")
    
    # Tenta extrair mensagem do body
    try:
        body = error.response.json()
        if "message" in body:
            message += f" - {body['message']}"
        elif "error" in body:
            message += f" - {body['error']}"
    except Exception:
        pass
    
    return f"Error: {message}"
