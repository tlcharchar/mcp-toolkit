"""
Provedores de autenticação para MCP Toolkit.

Este módulo fornece classes helper para configurar
diferentes tipos de autenticação.
"""

from __future__ import annotations

import os
from typing import List, Optional, Tuple

from ..types import AuthConfig, AuthType


# ============================================================================
# Auth Helpers
# ============================================================================


def api_key(
    header_name: str = "X-API-Key",
    env_var: Optional[str] = None,
    prefix: str = "",
) -> AuthConfig:
    """
    Cria configuração de autenticação via API Key.
    
    Args:
        header_name: Nome do header (ex: "X-API-Key", "Authorization")
        env_var: Nome da variável de ambiente (default: header_name normalizado)
        prefix: Prefixo do valor (ex: "Bearer ")
    
    Returns:
        AuthConfig configurado
    
    Exemplo:
        auth = api_key("X-API-Key", env_var="MY_API_KEY")
    """
    if env_var is None:
        env_var = header_name.upper().replace("-", "_")
    
    return AuthConfig(
        type=AuthType.API_KEY,
        header_name=header_name,
        env_var=env_var,
        token_prefix=prefix,
    )


def bearer(env_var: str = "API_TOKEN") -> AuthConfig:
    """
    Cria configuração de autenticação Bearer.
    
    Args:
        env_var: Nome da variável de ambiente com o token
    
    Returns:
        AuthConfig configurado
    
    Exemplo:
        auth = bearer("MY_TOKEN")
    """
    return AuthConfig(
        type=AuthType.BEARER,
        header_name="Authorization",
        env_var=env_var,
        token_prefix="Bearer ",
    )


def basic(
    username_env: str = "API_USERNAME",
    password_env: str = "API_PASSWORD",
) -> AuthConfig:
    """
    Cria configuração de autenticação Basic.
    
    Args:
        username_env: Variável de ambiente com username
        password_env: Variável de ambiente com password
    
    Returns:
        AuthConfig configurado
    
    Exemplo:
        auth = basic("MY_USER", "MY_PASS")
    """
    return AuthConfig(
        type=AuthType.BASIC,
        username_env=username_env,
        password_env=password_env,
    )


def oauth2(
    client_id_env: str = "OAUTH_CLIENT_ID",
    client_secret_env: str = "OAUTH_CLIENT_SECRET",
    token_url: str = "",
    scopes: Optional[List[str]] = None,
) -> AuthConfig:
    """
    Cria configuração de autenticação OAuth2.
    
    Args:
        client_id_env: Variável de ambiente com client ID
        client_secret_env: Variável de ambiente com client secret
        token_url: URL para obtenção de token
        scopes: Lista de escopos necessários
    
    Returns:
        AuthConfig configurado
    """
    return AuthConfig(
        type=AuthType.OAUTH2,
        client_id_env=client_id_env,
        client_secret_env=client_secret_env,
        token_url=token_url,
        scopes=scopes,
    )


def none() -> AuthConfig:
    """Retorna configuração sem autenticação."""
    return AuthConfig(type=AuthType.NONE)


# ============================================================================
# Auth Validation
# ============================================================================


def validate_auth(auth: AuthConfig) -> Tuple[bool, Optional[str]]:
    """
    Valida se as credenciais estão configuradas.
    
    Args:
        auth: Configuração de autenticação
    
    Returns:
        Tupla (is_valid, error_message)
    """
    if auth.type == AuthType.NONE:
        return True, None
    
    if auth.type == AuthType.API_KEY:
        if not auth.env_var:
            return False, "API Key auth requires env_var"
        if not os.environ.get(auth.env_var):
            return False, f"Environment variable '{auth.env_var}' not set"
        return True, None
    
    if auth.type == AuthType.BEARER:
        if not auth.env_var:
            return False, "Bearer auth requires env_var"
        if not os.environ.get(auth.env_var):
            return False, f"Environment variable '{auth.env_var}' not set"
        return True, None
    
    if auth.type == AuthType.BASIC:
        if not auth.username_env or not auth.password_env:
            return False, "Basic auth requires username_env and password_env"
        if not os.environ.get(auth.username_env):
            return False, f"Environment variable '{auth.username_env}' not set"
        if not os.environ.get(auth.password_env):
            return False, f"Environment variable '{auth.password_env}' not set"
        return True, None
    
    if auth.type == AuthType.OAUTH2:
        if not auth.token_url:
            return False, "OAuth2 auth requires token_url"
        if not auth.client_id_env or not auth.client_secret_env:
            return False, "OAuth2 auth requires client_id_env and client_secret_env"
        if not os.environ.get(auth.client_id_env):
            return False, f"Environment variable '{auth.client_id_env}' not set"
        if not os.environ.get(auth.client_secret_env):
            return False, f"Environment variable '{auth.client_secret_env}' not set"
        return True, None
    
    return False, f"Unknown auth type: {auth.type}"


__all__ = [
    "api_key",
    "basic",
    "bearer",
    "none",
    "oauth2",
    "validate_auth",
]
