"""
Decorators para definição de tools, resources e prompts.

Este módulo fornece decorators pythônicos para registrar tools,
resources e prompts em um MCP Server de forma declarativa.
"""

from __future__ import annotations

import functools
import inspect
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Type,
    TypeVar,
    Union,
    get_type_hints,
)

from pydantic import BaseModel

from .types import (
    PromptArgument,
    PromptDefinition,
    ResourceDefinition,
    ToolAnnotations,
    ToolDefinition,
    ToolParameter,
)


F = TypeVar("F", bound=Callable[..., Any])


# ============================================================================
# Schema Generation
# ============================================================================


def _python_type_to_json_type(python_type: Any) -> str:
    """Converte tipo Python para tipo JSON Schema."""
    type_str = str(python_type)
    
    # Tipos primitivos
    if python_type in (str, "str"):
        return "string"
    elif python_type in (int, "int"):
        return "integer"
    elif python_type in (float, "float"):
        return "number"
    elif python_type in (bool, "bool"):
        return "boolean"
    elif python_type in (list, "list") or "List" in type_str:
        return "array"
    elif python_type in (dict, "dict") or "Dict" in type_str:
        return "object"
    elif hasattr(python_type, "__origin__"):
        # Tipos genéricos (List[str], Dict[str, Any], etc.)
        origin = python_type.__origin__
        if origin is list:
            return "array"
        elif origin is dict:
            return "object"
        elif origin is Union:
            # Optional[X] é Union[X, None]
            args = [a for a in python_type.__args__ if a is not type(None)]
            if args:
                return _python_type_to_json_type(args[0])
    
    return "string"  # Default


def _extract_parameters_from_function(func: Callable[..., Any]) -> List[ToolParameter]:
    """Extrai parâmetros de uma função para ToolParameter."""
    parameters = []
    sig = inspect.signature(func)
    
    try:
        hints = get_type_hints(func)
    except Exception:
        hints = {}
    
    # Parse docstring para descrições
    descriptions = _parse_docstring_params(func.__doc__ or "")
    
    for name, param in sig.parameters.items():
        # Pula parâmetros especiais
        if name in ("self", "cls", "ctx", "context"):
            continue
        
        # Determina o tipo
        python_type = hints.get(name, str)
        json_type = _python_type_to_json_type(python_type)
        
        # Determina se é obrigatório
        required = param.default is inspect.Parameter.empty
        default = None if required else param.default
        
        # Descrição do docstring ou gerada
        description = descriptions.get(name, f"Parâmetro {name}")
        
        parameters.append(ToolParameter(
            name=name,
            type=json_type,
            description=description,
            required=required,
            default=default
        ))
    
    return parameters


def _extract_parameters_from_pydantic(model: Type[BaseModel]) -> List[ToolParameter]:
    """Extrai parâmetros de um modelo Pydantic."""
    parameters = []
    
    for field_name, field_info in model.model_fields.items():
        # Tipo
        annotation = model.__annotations__.get(field_name, str)
        json_type = _python_type_to_json_type(annotation)
        
        # Required
        required = field_info.is_required()
        
        # Default
        default = None
        if not required and field_info.default is not None:
            default = field_info.default
        
        # Descrição
        description = field_info.description or f"Parâmetro {field_name}"
        
        # Constraints
        constraints: Dict[str, Any] = {}
        
        if hasattr(field_info, "metadata"):
            for meta in field_info.metadata:
                if hasattr(meta, "ge"):
                    constraints["minimum"] = meta.ge
                if hasattr(meta, "le"):
                    constraints["maximum"] = meta.le
                if hasattr(meta, "min_length"):
                    constraints["min_length"] = meta.min_length
                if hasattr(meta, "max_length"):
                    constraints["max_length"] = meta.max_length
                if hasattr(meta, "pattern"):
                    constraints["pattern"] = meta.pattern
        
        # Enum
        enum_values = None
        if hasattr(annotation, "__members__"):
            enum_values = list(annotation.__members__.keys())
        
        parameters.append(ToolParameter(
            name=field_name,
            type=json_type,
            description=description,
            required=required,
            default=default,
            enum=enum_values,
            **constraints
        ))
    
    return parameters


def _parse_docstring_params(docstring: str) -> Dict[str, str]:
    """Extrai descrições de parâmetros do docstring."""
    descriptions = {}
    
    if not docstring:
        return descriptions
    
    lines = docstring.split("\n")
    in_args = False
    current_param = None
    
    for line in lines:
        stripped = line.strip()
        
        if stripped.lower().startswith(("args:", "arguments:", "parameters:")):
            in_args = True
            continue
        elif stripped.lower().startswith(("returns:", "raises:", "examples:")):
            in_args = False
            continue
        
        if in_args and stripped:
            # Formato: param_name (type): description
            # ou: param_name: description
            if ":" in stripped:
                parts = stripped.split(":", 1)
                param_part = parts[0].strip()
                desc_part = parts[1].strip() if len(parts) > 1 else ""
                
                # Remove tipo se presente
                if "(" in param_part:
                    param_name = param_part.split("(")[0].strip()
                else:
                    param_name = param_part.strip().lstrip("-").strip()
                
                if param_name and not param_name.startswith("- "):
                    current_param = param_name
                    descriptions[param_name] = desc_part
            elif current_param and stripped:
                # Continuação da descrição
                descriptions[current_param] += " " + stripped
    
    return descriptions


# ============================================================================
# Tool Decorator
# ============================================================================


def tool(
    name: Optional[str] = None,
    description: Optional[str] = None,
    annotations: Optional[Dict[str, Any]] = None,
) -> Callable[[F], F]:
    """
    Decorator para registrar uma função como MCP tool.
    
    Pode ser usado de várias formas:
    
    1. Simples (usa nome e docstring da função):
        @tool()
        def minha_tool(param: str) -> str:
            '''Descrição da tool.'''
            return "resultado"
    
    2. Com nome customizado:
        @tool(name="nome_customizado")
        def minha_tool(param: str) -> str:
            return "resultado"
    
    3. Com Pydantic model:
        class InputModel(BaseModel):
            param: str = Field(..., description="Descrição")
        
        @tool()
        def minha_tool(params: InputModel) -> str:
            return "resultado"
    
    4. Com annotations:
        @tool(annotations={"readOnlyHint": True})
        def minha_tool(param: str) -> str:
            return "resultado"
    
    Args:
        name: Nome da tool (default: nome da função)
        description: Descrição da tool (default: docstring)
        annotations: Anotações de comportamento
    
    Returns:
        Função decorada com metadata MCP
    """
    def decorator(func: F) -> F:
        # Determina nome e descrição
        tool_name = name or func.__name__
        tool_description = description or (func.__doc__ or "").split("\n")[0].strip()
        
        if not tool_description:
            tool_description = f"Tool {tool_name}"
        
        # Extrai parâmetros
        sig = inspect.signature(func)
        params = list(sig.parameters.values())
        
        # Verifica se usa Pydantic model
        parameters: List[ToolParameter] = []
        if params and len(params) >= 1:
            first_param = params[0]
            first_hint = get_type_hints(func).get(first_param.name)
            
            if first_hint and isinstance(first_hint, type) and issubclass(first_hint, BaseModel):
                # Usa Pydantic model
                parameters = _extract_parameters_from_pydantic(first_hint)
            else:
                # Usa parâmetros da função
                parameters = _extract_parameters_from_function(func)
        
        # Processa annotations
        tool_annotations = ToolAnnotations()
        if annotations:
            tool_annotations = ToolAnnotations(**annotations)
        
        if not tool_annotations.title:
            tool_annotations.title = tool_name.replace("_", " ").title()
        
        # Cria definição
        definition = ToolDefinition(
            name=tool_name,
            description=tool_description,
            parameters=parameters,
            annotations=tool_annotations,
            handler=func
        )
        
        # Anexa metadata à função
        func._mcp_tool = definition  # type: ignore
        func._mcp_type = "tool"  # type: ignore
        
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return func(*args, **kwargs)
        
        wrapper._mcp_tool = definition  # type: ignore
        wrapper._mcp_type = "tool"  # type: ignore
        
        return wrapper  # type: ignore
    
    return decorator


# ============================================================================
# Resource Decorator
# ============================================================================


def resource(
    uri: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    mime_type: str = "text/plain",
) -> Callable[[F], F]:
    """
    Decorator para registrar uma função como MCP resource.
    
    Resources são dados estáticos ou semi-estáticos acessíveis por URI.
    
    Exemplo:
        @resource(uri="docs://{name}")
        def get_document(name: str) -> str:
            '''Retorna o conteúdo de um documento.'''
            return Path(f"docs/{name}").read_text()
    
    Args:
        uri: URI template do resource (ex: "config://{key}")
        name: Nome do resource (default: nome da função)
        description: Descrição (default: docstring)
        mime_type: MIME type do conteúdo
    
    Returns:
        Função decorada com metadata MCP
    """
    def decorator(func: F) -> F:
        resource_name = name or func.__name__
        resource_description = description or (func.__doc__ or "").split("\n")[0].strip()
        
        if not resource_description:
            resource_description = f"Resource {resource_name}"
        
        definition = ResourceDefinition(
            uri=uri,
            name=resource_name,
            description=resource_description,
            mime_type=mime_type,
            handler=func
        )
        
        func._mcp_resource = definition  # type: ignore
        func._mcp_type = "resource"  # type: ignore
        
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return func(*args, **kwargs)
        
        wrapper._mcp_resource = definition  # type: ignore
        wrapper._mcp_type = "resource"  # type: ignore
        
        return wrapper  # type: ignore
    
    return decorator


# ============================================================================
# Prompt Decorator
# ============================================================================


def prompt(
    name: Optional[str] = None,
    description: Optional[str] = None,
) -> Callable[[F], F]:
    """
    Decorator para registrar uma função como MCP prompt.
    
    Prompts são templates de instrução para o agente.
    
    Exemplo:
        @prompt(name="analise-cliente")
        def prompt_analise(cliente_id: str) -> str:
            '''Prompt para análise de cliente.'''
            return f"Analise o cliente {cliente_id}..."
    
    Args:
        name: Nome do prompt (default: nome da função)
        description: Descrição (default: docstring)
    
    Returns:
        Função decorada com metadata MCP
    """
    def decorator(func: F) -> F:
        prompt_name = name or func.__name__
        prompt_description = description or (func.__doc__ or "").split("\n")[0].strip()
        
        if not prompt_description:
            prompt_description = f"Prompt {prompt_name}"
        
        # Extrai argumentos
        arguments = []
        params = _extract_parameters_from_function(func)
        for param in params:
            arguments.append(PromptArgument(
                name=param.name,
                description=param.description,
                required=param.required
            ))
        
        definition = PromptDefinition(
            name=prompt_name,
            description=prompt_description,
            arguments=arguments,
            handler=func
        )
        
        func._mcp_prompt = definition  # type: ignore
        func._mcp_type = "prompt"  # type: ignore
        
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> str:
            return func(*args, **kwargs)
        
        wrapper._mcp_prompt = definition  # type: ignore
        wrapper._mcp_type = "prompt"  # type: ignore
        
        return wrapper  # type: ignore
    
    return decorator
