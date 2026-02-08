"""
CLI para MCP Toolkit.

Fornece comandos para scaffolding e gerenciamento de MCP Servers.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import List, Optional


# ============================================================================
# Templates
# ============================================================================


BASIC_SERVER_TEMPLATE = '''"""
MCP Server: {name}

{description}
"""

from mcp_toolkit import MCPServer, tool
from pydantic import BaseModel, Field


# Inicializa o server
server = MCPServer("{name}")


# ============================================================================
# Tools
# ============================================================================


@server.tool()
def hello_world(name: str = "World") -> str:
    """Retorna uma saudação personalizada."""
    return f"Hello, {{name}}!"


# ============================================================================
# Execução
# ============================================================================


if __name__ == "__main__":
    server.run()
'''


def _build_rest_template(name: str, base_url: str, no_auth: bool = False) -> str:
    """Monta o template REST com ou sem autenticação."""
    if no_auth:
        auth_section = '''from mcp_toolkit.auth import none

# Configuração (API local sem autenticação)
API_BASE_URL = "{base_url}"
AUTH = none()'''
    else:
        auth_section = '''from mcp_toolkit.auth import api_key

# Configuração
API_BASE_URL = "{base_url}"
AUTH = api_key(header_name="Authorization", env_var="API_TOKEN")'''

    return f'''"""
MCP Server: {name}

Server que expõe APIs REST como tools MCP.
Integrável por agentes externos via Streamable HTTP (transporte MCP).
"""

from mcp_toolkit import MCPServer
from mcp_toolkit.adapters import RestApiAdapter
from mcp_toolkit.types import ServerConfig, TransportType
{auth_section.format(base_url=base_url)}

# Server com Streamable HTTP (0.0.0.0 para aceitar conexões em k8s/pod)
server = MCPServer(
    ServerConfig(
        name="{name}",
        transport=TransportType.STREAMABLE_HTTP,
        host="0.0.0.0",
        port=9000,
    )
)

# Adapter REST (use http2=True se a API alvo suportar HTTP/2)
api = RestApiAdapter(
    base_url=API_BASE_URL,
    auth=AUTH,
    http2=False,
)

# Registra tools
# Exemplo: endpoint específico
# server.register_tool(
#     api.as_tool(
#         method="GET",
#         path="/users/{{id}}",
#         name="buscar_usuario",
#         description="Busca um usuário pelo ID",
#     )
# )

# Exemplo: CRUD completo
# server.register_tools(
#     api.crud_tools(
#         resource_name="usuario",
#         resource_path="/users",
#     )
# )


if __name__ == "__main__":
    server.run()
'''


def _build_openapi_template(
    name: str,
    openapi_url: str,
    openapi_base_url: str,
    no_auth: bool = False,
) -> str:
    """Monta o template OpenAPI com ou sem autenticação."""
    if no_auth:
        auth_section = """from mcp_toolkit.auth import none

# Configuração (API local sem autenticação)
OPENAPI_URL = "{openapi_url}"
OPENAPI_BASE_URL = {openapi_base_url}
AUTH = none()"""
    else:
        auth_section = """from mcp_toolkit.auth import api_key

# Configuração
OPENAPI_URL = "{openapi_url}"
# Opcional: use se a spec não tiver "servers" ou para sobrescrever a URL base da API
OPENAPI_BASE_URL = {openapi_base_url}
AUTH = api_key(header_name="Authorization", env_var="API_TOKEN")"""

    return f'''"""
MCP Server: {name}

Server gerado a partir de especificação OpenAPI.
Integrável por agentes externos via Streamable HTTP (transporte MCP).
"""

from mcp_toolkit import MCPServer
from mcp_toolkit.adapters import OpenAPIAdapter
from mcp_toolkit.types import ServerConfig, TransportType
{auth_section.format(openapi_url=openapi_url, openapi_base_url=openapi_base_url)}

# Server com Streamable HTTP (0.0.0.0 para aceitar conexões em k8s/pod)
server = MCPServer(
    ServerConfig(
        name="{name}",
        transport=TransportType.STREAMABLE_HTTP,
        host="0.0.0.0",
        port=9000,
    )
)

# Adapter OpenAPI (carrega a spec em tempo de execução e gera uma tool por operação)
adapter = OpenAPIAdapter.from_url(
    OPENAPI_URL,
    auth=AUTH,
    base_url=OPENAPI_BASE_URL,
)

# Registra todas as tools da spec OpenAPI (uma tool por endpoint)
server.register_tools(adapter.all_tools())

# Para registrar apenas algumas tags:
# server.register_tools(adapter.tools_matching(tags=["users", "orders"]))


if __name__ == "__main__":
    server.run()
'''


# ============================================================================
# IDE configs
# ============================================================================


# ---------------------------------------------------------------------------
# Docker & Kubernetes (deploy em k8s local, ex.: Docker Desktop)
# ---------------------------------------------------------------------------

DOCKERFILE_TEMPLATE = """# MCP Server - deploy em Kubernetes (Docker Desktop)
FROM python:3.12-slim
WORKDIR /app

RUN useradd --create-home appuser && chown -R appuser /app
USER appuser

COPY --chown=appuser:appuser requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt
ENV PATH="/home/appuser/.local/bin:$PATH"

COPY --chown=appuser:appuser mcp_toolkit/ ./mcp_toolkit/
COPY --chown=appuser:appuser server.py .

EXPOSE 9000
CMD ["python", "server.py"]
"""

DOCKERIGNORE_TEMPLATE = """venv/
.venv/
__pycache__/
*.py[cod]
*$py.class
.git/
.gitignore
.cursor/
.vscode/
*.md
.env
.env.*
k8s/
"""

K8S_DEPLOYMENT_TEMPLATE = """apiVersion: apps/v1
kind: Deployment
metadata:
  name: {name}
  labels:
    app: {name}
spec:
  replicas: 1
  selector:
    matchLabels:
      app: {name}
  template:
    metadata:
      labels:
        app: {name}
    spec:
      containers:
        - name: mcp
          image: {name}:latest
          imagePullPolicy: IfNotPresent
          ports:
            - containerPort: 9000
          resources:
            requests:
              memory: "64Mi"
              cpu: "50m"
            limits:
              memory: "256Mi"
              cpu: "500m"
          livenessProbe:
            tcpSocket:
              port: 9000
            initialDelaySeconds: 10
            periodSeconds: 15
          readinessProbe:
            tcpSocket:
              port: 9000
            initialDelaySeconds: 5
            periodSeconds: 10
"""

K8S_SERVICE_TEMPLATE = """apiVersion: v1
kind: Service
metadata:
  name: {name}
  labels:
    app: {name}
spec:
  type: LoadBalancer
  selector:
    app: {name}
  ports:
    - port: 9000
      targetPort: 9000
      protocol: TCP
      name: http
"""


def _create_k8s_artifacts(project_dir: Path, server_name: str) -> None:
    """Cria Dockerfile, .dockerignore e manifestos k8s para deploy em pod (Docker Desktop)."""
    # Nome k8s: converte underscores para hífens (k8s não aceita _) e mantém
    # o sufixo -mcp para evitar conflito com outros deploys (ex: simple-api REST)
    k8s_name = server_name.replace("_", "-")

    (project_dir / "Dockerfile").write_text(DOCKERFILE_TEMPLATE)
    (project_dir / ".dockerignore").write_text(DOCKERIGNORE_TEMPLATE)

    k8s_dir = project_dir / "k8s"
    k8s_dir.mkdir(parents=True, exist_ok=True)
    (k8s_dir / "deployment.yaml").write_text(
        K8S_DEPLOYMENT_TEMPLATE.format(name=k8s_name)
    )
    (k8s_dir / "service.yaml").write_text(
        K8S_SERVICE_TEMPLATE.format(name=k8s_name)
    )


def _create_ide_configs(project_dir: Path, server_name: str) -> None:
    """Cria arquivos de configuração para IDEs enxergarem o MCP server."""
    stdio_config = {"command": "python", "args": ["server.py"]}

    # Cursor: .cursor/mcp.json
    cursor_dir = project_dir / ".cursor"
    cursor_dir.mkdir(parents=True, exist_ok=True)
    (cursor_dir / "mcp.json").write_text(
        json.dumps({"mcpServers": {server_name: stdio_config}}, indent=2)
    )

    # VS Code: .vscode/mcp.json (type stdio explícito)
    vscode_dir = project_dir / ".vscode"
    vscode_dir.mkdir(parents=True, exist_ok=True)
    vscode_mcp = {
        "servers": {
            server_name: {
                "type": "stdio",
                "command": stdio_config["command"],
                "args": stdio_config["args"],
            }
        }
    }
    (vscode_dir / "mcp.json").write_text(json.dumps(vscode_mcp, indent=2))


# ============================================================================
# Commands
# ============================================================================


def cmd_init(args: argparse.Namespace) -> int:
    """Cria um novo projeto MCP Server."""
    name = args.name
    template = args.template
    output_dir = Path(args.output or ".")
    
    # Valida nome
    if not name.endswith("_mcp"):
        name = f"{name}_mcp"
    
    # Cria diretório
    project_dir = output_dir / name
    project_dir.mkdir(parents=True, exist_ok=True)
    
    # Seleciona template
    if template == "basic":
        content = BASIC_SERVER_TEMPLATE.format(
            name=name,
            description=f"MCP Server {name}",
        )
    elif template == "rest":
        content = _build_rest_template(
            name=name,
            base_url=args.base_url or "https://api.example.com/v1",
            no_auth=getattr(args, "no_auth", False),
        )
    elif template == "openapi":
        openapi_base_url = f'"{args.base_url}"' if args.base_url else "None"
        content = _build_openapi_template(
            name=name,
            openapi_url=args.openapi_url or "https://api.example.com/openapi.json",
            openapi_base_url=openapi_base_url,
            no_auth=getattr(args, "no_auth", False),
        )
    else:
        print(f"Error: Unknown template '{template}'")
        return 1
    
    # Escreve arquivo principal
    server_file = project_dir / "server.py"
    server_file.write_text(content)
    
    # Cria requirements.txt (dependências do SDK — o pacote mcp_toolkit é
    # copiado diretamente para a imagem Docker, sem precisar de pip install)
    requirements = project_dir / "requirements.txt"
    requirements.write_text(
        "mcp>=1.0.0\n"
        "pydantic>=2.0.0\n"
        "httpx>=0.25.0\n"
        "pyyaml>=6.0\n"
        "structlog>=23.0.0\n"
    )
    
    # Cria README.md
    k8s_name = name.replace("_", "-")
    readme = project_dir / "README.md"
    readme.write_text(f"""# {name}

MCP Server criado com MCP Toolkit.

## Instalação

```bash
pip install -r requirements.txt
```

## Execução local

```bash
python server.py
```

## Deploy no Kubernetes (Docker Desktop)

1. Ative o Kubernetes no Docker Desktop (Settings → Kubernetes → Enable).
2. **Template basic (stdio)**: para K8s edite `server.py` e use `ServerConfig` com `TransportType.STREAMABLE_HTTP`, `host="0.0.0.0"` e `port=9000`. Templates rest/openapi já vêm com Streamable HTTP.
3. Copie o SDK para o diretório do projeto (o Dockerfile espera a pasta `mcp_toolkit/`):
   ```bash
   cp -r /caminho/para/mcp_toolkit .
   ```
4. Build da imagem:
   ```bash
   docker build -t {k8s_name}:latest .
   ```
5. Aplique os manifestos:
   ```bash
   kubectl apply -f k8s/
   ```
6. Verifique o serviço (aguarde EXTERNAL-IP se necessário):
   ```bash
   kubectl get svc {k8s_name}
   ```
   Acesse em `http://localhost:9000` (agentes externos podem integrar via Streamable HTTP nessa URL).

## Configuração

Configure as variáveis de ambiente necessárias antes de executar:

```bash
export API_TOKEN="seu_token"
```

## IDE

- **Cursor**: foi gerado `.cursor/mcp.json`. Abra esta pasta no Cursor e ative
  o server em Settings > Features > MCP.
- **VS Code**: foi gerado `.vscode/mcp.json`. Abra esta pasta no VS Code;
  o Copilot Chat usará o server (confirme a confiança na primeira vez).
""")
    
    # Configurações para IDEs enxergarem o MCP server
    _create_ide_configs(project_dir, name)
    # Artefatos para deploy em k8s (Docker Desktop)
    _create_k8s_artifacts(project_dir, name)
    
    print(f"✓ Projeto criado em: {project_dir}")
    print(f"  - server.py")
    print(f"  - requirements.txt")
    print(f"  - README.md")
    print(f"  - Dockerfile, .dockerignore, k8s/   (deploy K8s)")
    print(f"  - .cursor/mcp.json   (Cursor)")
    print(f"  - .vscode/mcp.json   (VS Code)")
    
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    """Valida um MCP Server."""
    server_path = Path(args.server)
    
    if not server_path.exists():
        print(f"Error: File not found: {server_path}")
        return 1
    
    # Importa e valida
    import importlib.util
    
    spec = importlib.util.spec_from_file_location("server", server_path)
    if spec is None or spec.loader is None:
        print(f"Error: Could not load module from {server_path}")
        return 1
    
    module = importlib.util.module_from_spec(spec)
    
    try:
        spec.loader.exec_module(module)
    except Exception as e:
        print(f"Error loading server: {e}")
        return 1
    
    # Procura MCPServer
    server = None
    for attr_name in dir(module):
        attr = getattr(module, attr_name)
        if hasattr(attr, "_tools") and hasattr(attr, "_resources"):
            server = attr
            break
    
    if server is None:
        print("Error: No MCPServer instance found")
        return 1
    
    print(f"✓ Server: {server.config.name}")
    print(f"  Tools: {len(server._tools)}")
    print(f"  Resources: {len(server._resources)}")
    print(f"  Prompts: {len(server._prompts)}")
    
    if args.verbose:
        print("\nTools:")
        for name, tool_def in server._tools.items():
            print(f"  - {name}: {tool_def.description[:50]}...")
    
    return 0


def cmd_list_tools(args: argparse.Namespace) -> int:
    """Lista tools de um MCP Server."""
    server_path = Path(args.server)
    
    if not server_path.exists():
        print(f"Error: File not found: {server_path}")
        return 1
    
    import importlib.util
    
    spec = importlib.util.spec_from_file_location("server", server_path)
    if spec is None or spec.loader is None:
        print(f"Error: Could not load module from {server_path}")
        return 1
    
    module = importlib.util.module_from_spec(spec)
    
    try:
        spec.loader.exec_module(module)
    except Exception as e:
        print(f"Error loading server: {e}")
        return 1
    
    # Procura MCPServer
    server = None
    for attr_name in dir(module):
        attr = getattr(module, attr_name)
        if hasattr(attr, "_tools"):
            server = attr
            break
    
    if server is None:
        print("Error: No MCPServer instance found")
        return 1
    
    if args.format == "json":
        tools_data = []
        for name, tool_def in server._tools.items():
            tools_data.append({
                "name": name,
                "description": tool_def.description,
                "parameters": [p.model_dump() for p in tool_def.parameters],
            })
        print(json.dumps(tools_data, indent=2))
    else:
        for name, tool_def in server._tools.items():
            print(f"\n{name}")
            print(f"  Description: {tool_def.description}")
            if tool_def.parameters:
                print("  Parameters:")
                for param in tool_def.parameters:
                    req = "*" if param.required else ""
                    print(f"    - {param.name}{req} ({param.type}): {param.description}")
    
    return 0


# ============================================================================
# Main
# ============================================================================


def main(argv: Optional[List[str]] = None) -> int:
    """Entry point da CLI."""
    parser = argparse.ArgumentParser(
        prog="mcp-toolkit",
        description="CLI para MCP Toolkit",
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Comandos disponíveis")
    
    # init
    init_parser = subparsers.add_parser("init", help="Cria novo projeto MCP Server")
    init_parser.add_argument("name", help="Nome do server (ex: vendas)")
    init_parser.add_argument(
        "-t", "--template",
        choices=["basic", "rest", "openapi"],
        default="basic",
        help="Template a usar",
    )
    init_parser.add_argument("-o", "--output", help="Diretório de saída")
    init_parser.add_argument("--base-url", help="URL base da API (templates rest e openapi)")
    init_parser.add_argument("--openapi-url", help="URL da spec OpenAPI (template openapi)")
    init_parser.add_argument("--no-auth", action="store_true", help="API sem autenticação (templates rest e openapi - ex.: APIs locais)")
    
    # validate
    validate_parser = subparsers.add_parser("validate", help="Valida um MCP Server")
    validate_parser.add_argument("server", help="Path do arquivo server.py")
    validate_parser.add_argument("-v", "--verbose", action="store_true", help="Saída detalhada")
    
    # list-tools
    list_parser = subparsers.add_parser("list-tools", help="Lista tools de um MCP Server")
    list_parser.add_argument("server", help="Path do arquivo server.py")
    list_parser.add_argument(
        "-f", "--format",
        choices=["text", "json"],
        default="text",
        help="Formato de saída",
    )
    
    args = parser.parse_args(argv)
    
    if args.command == "init":
        return cmd_init(args)
    elif args.command == "validate":
        return cmd_validate(args)
    elif args.command == "list-tools":
        return cmd_list_tools(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
