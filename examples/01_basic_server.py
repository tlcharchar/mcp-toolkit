"""
Exemplo 1: MCP Server Básico

Este exemplo demonstra a criação de um MCP Server simples
com tools definidas usando decorators.
"""

from pydantic import BaseModel, Field

from mcp_toolkit import MCPServer, tool


# ============================================================================
# Inicialização
# ============================================================================

server = MCPServer("calculadora_mcp")


# ============================================================================
# Tools com parâmetros simples
# ============================================================================


@server.tool()
def somar(a: float, b: float) -> float:
    """Soma dois números."""
    return a + b


@server.tool()
def subtrair(a: float, b: float) -> float:
    """Subtrai b de a."""
    return a - b


@server.tool()
def multiplicar(a: float, b: float) -> float:
    """Multiplica dois números."""
    return a * b


@server.tool()
def dividir(a: float, b: float) -> float:
    """Divide a por b.
    
    Args:
        a: Dividendo
        b: Divisor (não pode ser zero)
    
    Returns:
        Resultado da divisão
    """
    if b == 0:
        raise ValueError("Divisão por zero não é permitida")
    return a / b


# ============================================================================
# Tool com Pydantic Model
# ============================================================================


class EquacaoQuadraticaInput(BaseModel):
    """Coeficientes de uma equação quadrática ax² + bx + c = 0."""
    
    a: float = Field(..., description="Coeficiente de x² (não pode ser zero)")
    b: float = Field(..., description="Coeficiente de x")
    c: float = Field(..., description="Termo constante")


@server.tool()
def resolver_equacao_quadratica(params: EquacaoQuadraticaInput) -> dict:
    """
    Resolve uma equação quadrática ax² + bx + c = 0.
    
    Retorna as raízes reais da equação, se existirem.
    """
    a, b, c = params.a, params.b, params.c
    
    if a == 0:
        raise ValueError("Coeficiente 'a' não pode ser zero (não seria equação quadrática)")
    
    delta = b**2 - 4*a*c
    
    if delta < 0:
        return {
            "delta": delta,
            "raizes_reais": False,
            "mensagem": "A equação não possui raízes reais"
        }
    elif delta == 0:
        x = -b / (2*a)
        return {
            "delta": delta,
            "raizes_reais": True,
            "raiz_dupla": x
        }
    else:
        import math
        x1 = (-b + math.sqrt(delta)) / (2*a)
        x2 = (-b - math.sqrt(delta)) / (2*a)
        return {
            "delta": delta,
            "raizes_reais": True,
            "x1": x1,
            "x2": x2
        }


# ============================================================================
# Tool com annotations customizadas
# ============================================================================


@server.tool(
    name="calcular_porcentagem",
    annotations={
        "title": "Calculadora de Porcentagem",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
    }
)
def porcentagem(valor: float, percentual: float) -> dict:
    """
    Calcula a porcentagem de um valor.
    
    Args:
        valor: Valor base
        percentual: Percentual a calcular (ex: 15 para 15%)
    
    Returns:
        Dicionário com o resultado e cálculos auxiliares
    """
    resultado = valor * (percentual / 100)
    return {
        "valor_original": valor,
        "percentual": percentual,
        "resultado": resultado,
        "valor_com_acrescimo": valor + resultado,
        "valor_com_desconto": valor - resultado,
    }


# ============================================================================
# Execução
# ============================================================================


if __name__ == "__main__":
    print(f"Iniciando {server.config.name}...")
    print(f"Tools disponíveis: {server.list_tools()}")
    server.run()
