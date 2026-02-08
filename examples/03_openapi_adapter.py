"""
Exemplo 3: OpenAPI Adapter

Este exemplo demonstra como importar automaticamente
uma especificação OpenAPI e gerar tools MCP.
"""

from mcp_toolkit import MCPServer
from mcp_toolkit.adapters import OpenAPIAdapter, OpenAPIParser
from mcp_toolkit.auth import api_key


# ============================================================================
# Configuração
# ============================================================================

# URL de uma spec OpenAPI pública (Petstore é o exemplo clássico)
OPENAPI_URL = "https://petstore3.swagger.io/api/v3/openapi.json"

# ============================================================================
# Inicialização
# ============================================================================

server = MCPServer("petstore_mcp")


# ============================================================================
# Carrega OpenAPI spec
# ============================================================================

print("Carregando especificação OpenAPI...")

try:
    adapter = OpenAPIAdapter.from_url(
        OPENAPI_URL,
        auth=None,  # Petstore é público
        timeout=30.0,
        name_prefix="pet_",  # Prefixo para evitar conflitos
    )
    
    print(f"API: {adapter.parser.title}")
    print(f"Base URL: {adapter.parser.base_url}")
    
    # Lista tags disponíveis
    tags = adapter.list_available_tags()
    print(f"Tags disponíveis: {tags}")
    
    # Lista operações
    operations = adapter.list_available_operations()
    print(f"Total de operações: {len(operations)}")
    
except Exception as e:
    print(f"Erro ao carregar OpenAPI: {e}")
    print("Usando spec local de fallback...")
    
    # Fallback: spec inline para demonstração
    local_spec = {
        "openapi": "3.0.0",
        "info": {"title": "Demo API", "version": "1.0.0"},
        "servers": [{"url": "https://api.example.com"}],
        "paths": {
            "/pets": {
                "get": {
                    "operationId": "listPets",
                    "summary": "Lista todos os pets",
                    "tags": ["pets"],
                    "parameters": [
                        {
                            "name": "limit",
                            "in": "query",
                            "schema": {"type": "integer"},
                            "description": "Limite de resultados"
                        }
                    ],
                    "responses": {"200": {"description": "OK"}}
                },
                "post": {
                    "operationId": "createPet",
                    "summary": "Cria um novo pet",
                    "tags": ["pets"],
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string", "description": "Nome do pet"},
                                        "species": {"type": "string", "description": "Espécie"}
                                    },
                                    "required": ["name"]
                                }
                            }
                        }
                    },
                    "responses": {"201": {"description": "Criado"}}
                }
            },
            "/pets/{petId}": {
                "get": {
                    "operationId": "getPet",
                    "summary": "Busca um pet por ID",
                    "tags": ["pets"],
                    "parameters": [
                        {
                            "name": "petId",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                            "description": "ID do pet"
                        }
                    ],
                    "responses": {"200": {"description": "OK"}}
                }
            }
        }
    }
    
    parser = OpenAPIParser(local_spec)
    adapter = OpenAPIAdapter(parser, name_prefix="pet_")


# ============================================================================
# Registra tools
# ============================================================================

# Opção 1: Registrar TODAS as tools
# server.register_tools(adapter.all_tools())

# Opção 2: Filtrar por tags
if "pet" in adapter.list_available_tags():
    pet_tools = adapter.tools_matching(tags=["pet"])
    server.register_tools(pet_tools)
    print(f"Registradas {len(pet_tools)} tools da tag 'pet'")

# Opção 3: Filtrar por operationId
specific_tools = adapter.tools_matching(
    operation_ids=["listPets", "getPet", "createPet"]
)
if specific_tools:
    server.register_tools(specific_tools)
    print(f"Registradas {len(specific_tools)} tools específicas")

# Opção 4: Filtrar por método HTTP
# get_tools = adapter.tools_matching(methods=["GET"])
# server.register_tools(get_tools)

# Opção 5: Filtrar por padrão de path
# user_tools = adapter.tools_matching(path_pattern=r"/user.*")
# server.register_tools(user_tools)


# ============================================================================
# Adiciona tools customizadas
# ============================================================================

@server.tool()
def resumo_api() -> dict:
    """Retorna informações sobre a API carregada."""
    return {
        "titulo": adapter.parser.title,
        "base_url": adapter.parser.base_url,
        "tags": adapter.list_available_tags(),
        "total_operacoes": len(adapter.list_available_operations()),
        "tools_registradas": server.list_tools(),
    }


# ============================================================================
# Execução
# ============================================================================

if __name__ == "__main__":
    print(f"\n{'='*60}")
    print(f"Iniciando {server.config.name}")
    print(f"{'='*60}")
    
    print(f"\nTools registradas ({len(server.list_tools())}):")
    for tool_name in sorted(server.list_tools()):
        tool_def = server.get_tool(tool_name)
        print(f"  - {tool_name}")
        print(f"      {tool_def.description[:70]}...")
        if tool_def.parameters:
            print(f"      Params: {[p.name for p in tool_def.parameters]}")
    
    print("\nIniciando servidor...")
    server.run()
