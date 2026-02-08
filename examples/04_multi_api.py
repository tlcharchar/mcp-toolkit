"""
Exemplo 4: Múltiplas APIs Combinadas

Este exemplo demonstra como combinar múltiplas APIs REST
em um único MCP Server unificado.
"""

from mcp_toolkit import MCPServer, ToolParameter
from mcp_toolkit.adapters import RestApiAdapter
from mcp_toolkit.auth import api_key, bearer
from mcp_toolkit.observability import ToolkitLogger


# ============================================================================
# Configuração de Logging
# ============================================================================

logger = ToolkitLogger(
    name="multi_api_mcp",
    level="INFO",
    structured=True,
)


# ============================================================================
# Inicialização
# ============================================================================

server = MCPServer("operacoes_mcp")


# ============================================================================
# API 1: JSONPlaceholder (Usuários e Posts)
# ============================================================================

logger.info("Configurando API de usuários/posts...")

users_api = RestApiAdapter(
    base_url="https://jsonplaceholder.typicode.com",
    prefix="social_",  # Prefixo para identificar origem
    timeout=30.0,
)

# Registra tools de usuários
server.register_tools([
    users_api.as_tool(
        method="GET",
        path="/users",
        name="listar_usuarios",
        description="Lista todos os usuários da plataforma social",
    ),
    users_api.as_tool(
        method="GET",
        path="/users/{id}",
        name="buscar_usuario",
        description="Busca detalhes de um usuário específico",
    ),
    users_api.as_tool(
        method="GET",
        path="/users/{id}/posts",
        name="posts_do_usuario",
        description="Lista posts de um usuário específico",
    ),
])


# ============================================================================
# API 2: ReqRes (Simulação de API de RH)
# ============================================================================

logger.info("Configurando API de RH...")

hr_api = RestApiAdapter(
    base_url="https://reqres.in/api",
    prefix="rh_",
    timeout=30.0,
)

server.register_tools([
    hr_api.as_tool(
        method="GET",
        path="/users",
        name="listar_funcionarios",
        description="Lista funcionários cadastrados no sistema de RH",
        query_params=[
            ToolParameter(
                name="page",
                type="integer",
                description="Página de resultados",
                required=False,
                default=1,
            ),
            ToolParameter(
                name="per_page",
                type="integer",
                description="Itens por página",
                required=False,
                default=6,
            ),
        ],
    ),
    hr_api.as_tool(
        method="GET",
        path="/users/{id}",
        name="buscar_funcionario",
        description="Busca detalhes de um funcionário",
    ),
    hr_api.as_tool(
        method="POST",
        path="/users",
        name="cadastrar_funcionario",
        description="Cadastra um novo funcionário",
        body_params=[
            ToolParameter(name="name", type="string", description="Nome completo", required=True),
            ToolParameter(name="job", type="string", description="Cargo", required=True),
        ],
    ),
    hr_api.as_tool(
        method="PUT",
        path="/users/{id}",
        name="atualizar_funcionario",
        description="Atualiza dados de um funcionário",
        body_params=[
            ToolParameter(name="name", type="string", description="Nome completo", required=False),
            ToolParameter(name="job", type="string", description="Cargo", required=False),
        ],
    ),
])


# ============================================================================
# API 3: HTTPBin (Utilitários)
# ============================================================================

logger.info("Configurando API de utilitários...")

utils_api = RestApiAdapter(
    base_url="https://httpbin.org",
    prefix="util_",
    timeout=30.0,
)

server.register_tools([
    utils_api.as_tool(
        method="GET",
        path="/ip",
        name="meu_ip",
        description="Retorna o IP público do servidor",
    ),
    utils_api.as_tool(
        method="GET",
        path="/headers",
        name="meus_headers",
        description="Retorna os headers da requisição",
    ),
    utils_api.as_tool(
        method="GET",
        path="/uuid",
        name="gerar_uuid",
        description="Gera um UUID único",
    ),
    utils_api.as_tool(
        method="POST",
        path="/post",
        name="testar_post",
        description="Testa uma requisição POST (echo)",
        body_params=[
            ToolParameter(name="message", type="string", description="Mensagem de teste", required=True),
        ],
    ),
])


# ============================================================================
# Tools de Orquestração (combinam múltiplas APIs)
# ============================================================================

@server.tool()
async def status_geral() -> dict:
    """
    Verifica o status de todas as APIs integradas.
    
    Retorna informações de conectividade e latência de cada API.
    """
    import time
    import httpx
    
    apis = {
        "social": "https://jsonplaceholder.typicode.com/users/1",
        "rh": "https://reqres.in/api/users/1",
        "utils": "https://httpbin.org/ip",
    }
    
    results = {}
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        for name, url in apis.items():
            start = time.time()
            try:
                response = await client.get(url)
                latency = (time.time() - start) * 1000
                results[name] = {
                    "status": "online",
                    "http_status": response.status_code,
                    "latency_ms": round(latency, 2),
                }
            except Exception as e:
                results[name] = {
                    "status": "offline",
                    "error": str(e),
                }
    
    return {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "apis": results,
        "tools_disponiveis": len(server.list_tools()),
    }


@server.tool()
def listar_todas_tools() -> dict:
    """
    Lista todas as tools disponíveis agrupadas por origem.
    """
    tools_by_prefix = {
        "social": [],
        "rh": [],
        "util": [],
        "outros": [],
    }
    
    for tool_name in server.list_tools():
        tool_def = server.get_tool(tool_name)
        
        if tool_name.startswith("social_"):
            tools_by_prefix["social"].append({
                "name": tool_name,
                "description": tool_def.description,
            })
        elif tool_name.startswith("rh_"):
            tools_by_prefix["rh"].append({
                "name": tool_name,
                "description": tool_def.description,
            })
        elif tool_name.startswith("util_"):
            tools_by_prefix["util"].append({
                "name": tool_name,
                "description": tool_def.description,
            })
        else:
            tools_by_prefix["outros"].append({
                "name": tool_name,
                "description": tool_def.description,
            })
    
    return {
        "total": len(server.list_tools()),
        "por_categoria": {
            k: {"count": len(v), "tools": v}
            for k, v in tools_by_prefix.items()
            if v
        },
    }


# ============================================================================
# Resources
# ============================================================================

@server.resource(uri="docs://api/{api_name}")
def documentacao_api(api_name: str) -> str:
    """Retorna documentação da API especificada."""
    docs = {
        "social": """
# API Social (JSONPlaceholder)

API de demonstração para posts e usuários.

## Endpoints disponíveis:
- social_listar_usuarios: Lista todos os usuários
- social_buscar_usuario: Busca usuário por ID
- social_posts_do_usuario: Lista posts de um usuário
        """,
        "rh": """
# API de RH (ReqRes)

API de gestão de funcionários.

## Endpoints disponíveis:
- rh_listar_funcionarios: Lista funcionários com paginação
- rh_buscar_funcionario: Busca funcionário por ID
- rh_cadastrar_funcionario: Cadastra novo funcionário
- rh_atualizar_funcionario: Atualiza dados de funcionário
        """,
        "utils": """
# API de Utilitários (HTTPBin)

APIs utilitárias para debug e testes.

## Endpoints disponíveis:
- util_meu_ip: Retorna IP público
- util_meus_headers: Retorna headers da requisição
- util_gerar_uuid: Gera UUID único
- util_testar_post: Testa requisição POST
        """,
    }
    
    return docs.get(api_name, f"Documentação não encontrada para: {api_name}")


# ============================================================================
# Execução
# ============================================================================

if __name__ == "__main__":
    logger.info(
        "Servidor inicializado",
        server_name=server.config.name,
        total_tools=len(server.list_tools()),
    )
    
    print(f"\n{'='*60}")
    print(f"MCP Server: {server.config.name}")
    print(f"{'='*60}")
    
    print(f"\nAPIs integradas:")
    print(f"  - Social (JSONPlaceholder): 3 tools")
    print(f"  - RH (ReqRes): 4 tools")
    print(f"  - Utilitários (HTTPBin): 4 tools")
    print(f"  - Orquestração: 2 tools")
    
    print(f"\nTotal: {len(server.list_tools())} tools disponíveis")
    
    print("\nIniciando servidor...")
    server.run()
