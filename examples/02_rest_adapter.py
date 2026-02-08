"""
Exemplo 2: REST API Adapter

Este exemplo demonstra como expor uma API REST existente
como tools MCP usando o RestApiAdapter.
"""

from mcp_toolkit import MCPServer, ToolParameter
from mcp_toolkit.adapters import RestApiAdapter
from mcp_toolkit.auth import bearer


# ============================================================================
# Configuração
# ============================================================================

# URL base da API que queremos expor
API_BASE_URL = "https://jsonplaceholder.typicode.com"

# Autenticação (para este exemplo, a API é pública)
# Em produção, use: auth = bearer("API_TOKEN")
auth = None

# ============================================================================
# Inicialização
# ============================================================================

server = MCPServer("jsonplaceholder_mcp")

# Cria adapter para a API
api = RestApiAdapter(
    base_url=API_BASE_URL,
    auth=auth,
    timeout=30.0,
    max_retries=3,
)


# ============================================================================
# Registra endpoints específicos como tools
# ============================================================================

# GET /users - Lista usuários
server.register_tool(
    api.as_tool(
        method="GET",
        path="/users",
        name="listar_usuarios",
        description="Lista todos os usuários do sistema",
        query_params=[
            ToolParameter(
                name="_limit",
                type="integer",
                description="Número máximo de usuários a retornar",
                required=False,
                default=10,
                minimum=1,
                maximum=100,
            ),
        ],
    )
)

# GET /users/{id} - Busca usuário por ID
server.register_tool(
    api.as_tool(
        method="GET",
        path="/users/{id}",
        name="buscar_usuario",
        description="Busca um usuário específico pelo ID",
    )
)

# GET /posts - Lista posts
server.register_tool(
    api.as_tool(
        method="GET",
        path="/posts",
        name="listar_posts",
        description="Lista todos os posts",
        query_params=[
            ToolParameter(
                name="userId",
                type="integer",
                description="Filtrar posts por ID do usuário",
                required=False,
            ),
            ToolParameter(
                name="_limit",
                type="integer",
                description="Número máximo de posts",
                required=False,
                default=20,
            ),
        ],
    )
)

# GET /posts/{id} - Busca post por ID
server.register_tool(
    api.as_tool(
        method="GET",
        path="/posts/{id}",
        name="buscar_post",
        description="Busca um post específico pelo ID",
    )
)

# POST /posts - Cria novo post
server.register_tool(
    api.as_tool(
        method="POST",
        path="/posts",
        name="criar_post",
        description="Cria um novo post",
        body_params=[
            ToolParameter(
                name="title",
                type="string",
                description="Título do post",
                required=True,
            ),
            ToolParameter(
                name="body",
                type="string",
                description="Conteúdo do post",
                required=True,
            ),
            ToolParameter(
                name="userId",
                type="integer",
                description="ID do autor",
                required=True,
            ),
        ],
    )
)

# GET /comments - Lista comentários de um post
server.register_tool(
    api.as_tool(
        method="GET",
        path="/comments",
        name="listar_comentarios",
        description="Lista comentários, opcionalmente filtrados por post",
        query_params=[
            ToolParameter(
                name="postId",
                type="integer",
                description="Filtrar por ID do post",
                required=False,
            ),
        ],
    )
)


# ============================================================================
# Usando CRUD helper
# ============================================================================

# Gera automaticamente tools CRUD para o resource "todo"
todo_tools = api.crud_tools(
    resource_name="tarefa",
    resource_path="/todos",
    id_param="id",
    create_params=[
        ToolParameter(name="title", type="string", description="Título da tarefa", required=True),
        ToolParameter(name="completed", type="boolean", description="Se está completa", required=False),
        ToolParameter(name="userId", type="integer", description="ID do usuário", required=True),
    ],
    update_params=[
        ToolParameter(name="title", type="string", description="Título da tarefa", required=False),
        ToolParameter(name="completed", type="boolean", description="Se está completa", required=False),
    ],
)

# Registra todas as tools CRUD com prefixo para evitar conflito
server.register_tools(todo_tools, prefix="todo_")


# ============================================================================
# Execução
# ============================================================================

if __name__ == "__main__":
    print(f"Iniciando {server.config.name}...")
    print(f"\nTools disponíveis ({len(server.list_tools())}):")
    for tool_name in sorted(server.list_tools()):
        tool_def = server.get_tool(tool_name)
        print(f"  - {tool_name}: {tool_def.description[:60]}...")
    
    print("\nIniciando servidor...")
    server.run()
