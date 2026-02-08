"""
Módulo de observabilidade para MCP Toolkit.

Fornece logging estruturado, métricas e tracing.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Callable, Dict, Generator, Optional

try:
    import structlog
    HAS_STRUCTLOG = True
except ImportError:
    HAS_STRUCTLOG = False

try:
    from prometheus_client import Counter, Histogram, start_http_server
    HAS_PROMETHEUS = True
except ImportError:
    HAS_PROMETHEUS = False


# ============================================================================
# Logging
# ============================================================================


class ToolkitLogger:
    """Logger estruturado para MCP Toolkit."""
    
    def __init__(
        self,
        name: str,
        level: str = "INFO",
        structured: bool = True,
    ):
        """
        Inicializa o logger.
        
        Args:
            name: Nome do logger
            level: Nível de log (DEBUG, INFO, WARNING, ERROR)
            structured: Se deve usar logging estruturado (JSON)
        """
        self.name = name
        self.level = level
        self.structured = structured
        
        if structured and HAS_STRUCTLOG:
            self._setup_structlog()
        else:
            self._setup_stdlib()
    
    def _setup_structlog(self) -> None:
        """Configura structlog."""
        structlog.configure(
            processors=[
                structlog.stdlib.filter_by_level,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.stdlib.PositionalArgumentsFormatter(),
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.UnicodeDecoder(),
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.stdlib.BoundLogger,
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )
        self._logger = structlog.get_logger(self.name)
    
    def _setup_stdlib(self) -> None:
        """Configura logging padrão."""
        self._logger = logging.getLogger(self.name)
        self._logger.setLevel(getattr(logging, self.level.upper()))
        
        if not self._logger.handlers:
            handler = logging.StreamHandler(sys.stderr)
            
            if self.structured:
                class JsonFormatter(logging.Formatter):
                    def format(self, record: logging.LogRecord) -> str:
                        log_data = {
                            "timestamp": datetime.utcnow().isoformat(),
                            "level": record.levelname,
                            "logger": record.name,
                            "message": record.getMessage(),
                        }
                        if hasattr(record, "extra"):
                            log_data.update(record.extra)
                        if record.exc_info:
                            log_data["exception"] = self.formatException(record.exc_info)
                        return json.dumps(log_data)
                
                handler.setFormatter(JsonFormatter())
            else:
                handler.setFormatter(
                    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
                )
            
            self._logger.addHandler(handler)
    
    def debug(self, message: str, **kwargs: Any) -> None:
        """Log debug."""
        if HAS_STRUCTLOG and self.structured:
            self._logger.debug(message, **kwargs)
        else:
            self._logger.debug(message, extra={"extra": kwargs})
    
    def info(self, message: str, **kwargs: Any) -> None:
        """Log info."""
        if HAS_STRUCTLOG and self.structured:
            self._logger.info(message, **kwargs)
        else:
            self._logger.info(message, extra={"extra": kwargs})
    
    def warning(self, message: str, **kwargs: Any) -> None:
        """Log warning."""
        if HAS_STRUCTLOG and self.structured:
            self._logger.warning(message, **kwargs)
        else:
            self._logger.warning(message, extra={"extra": kwargs})
    
    def error(self, message: str, **kwargs: Any) -> None:
        """Log error."""
        if HAS_STRUCTLOG and self.structured:
            self._logger.error(message, **kwargs)
        else:
            self._logger.error(message, extra={"extra": kwargs})
    
    def exception(self, message: str, **kwargs: Any) -> None:
        """Log exception com stack trace."""
        if HAS_STRUCTLOG and self.structured:
            self._logger.exception(message, **kwargs)
        else:
            self._logger.exception(message, extra={"extra": kwargs})


# ============================================================================
# Metrics
# ============================================================================


class MetricsCollector:
    """Coletor de métricas Prometheus."""
    
    def __init__(self, prefix: str = "mcp_toolkit"):
        """
        Inicializa o coletor.
        
        Args:
            prefix: Prefixo para nomes de métricas
        """
        self.prefix = prefix
        self._enabled = HAS_PROMETHEUS
        
        if self._enabled:
            self._tool_calls = Counter(
                f"{prefix}_tool_calls_total",
                "Total de chamadas de tools",
                ["tool_name", "status"],
            )
            
            self._tool_duration = Histogram(
                f"{prefix}_tool_duration_seconds",
                "Duração de execução de tools",
                ["tool_name"],
                buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
            )
            
            self._api_calls = Counter(
                f"{prefix}_api_calls_total",
                "Total de chamadas a APIs",
                ["base_url", "method", "status_code"],
            )
            
            self._api_duration = Histogram(
                f"{prefix}_api_duration_seconds",
                "Duração de chamadas a APIs",
                ["base_url", "method"],
                buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
            )
    
    def start_server(self, port: int = 9090) -> None:
        """Inicia servidor de métricas Prometheus."""
        if self._enabled:
            start_http_server(port)
    
    def record_tool_call(
        self,
        tool_name: str,
        status: str,
        duration: float,
    ) -> None:
        """Registra uma chamada de tool."""
        if self._enabled:
            self._tool_calls.labels(tool_name=tool_name, status=status).inc()
            self._tool_duration.labels(tool_name=tool_name).observe(duration)
    
    def record_api_call(
        self,
        base_url: str,
        method: str,
        status_code: int,
        duration: float,
    ) -> None:
        """Registra uma chamada de API."""
        if self._enabled:
            self._api_calls.labels(
                base_url=base_url,
                method=method,
                status_code=str(status_code),
            ).inc()
            self._api_duration.labels(base_url=base_url, method=method).observe(duration)
    
    @contextmanager
    def measure_tool(self, tool_name: str) -> Generator[None, None, None]:
        """Context manager para medir execução de tool."""
        start = time.time()
        status = "success"
        try:
            yield
        except Exception:
            status = "error"
            raise
        finally:
            duration = time.time() - start
            self.record_tool_call(tool_name, status, duration)
    
    @contextmanager
    def measure_api(
        self,
        base_url: str,
        method: str,
    ) -> Generator[Dict[str, Any], None, None]:
        """Context manager para medir chamada de API."""
        start = time.time()
        result: Dict[str, Any] = {"status_code": 0}
        try:
            yield result
        finally:
            duration = time.time() - start
            self.record_api_call(base_url, method, result.get("status_code", 0), duration)


# ============================================================================
# Tracing
# ============================================================================


class TraceContext:
    """Contexto de trace para correlação de logs."""
    
    def __init__(
        self,
        trace_id: Optional[str] = None,
        span_id: Optional[str] = None,
        parent_id: Optional[str] = None,
    ):
        """
        Inicializa contexto de trace.
        
        Args:
            trace_id: ID do trace (gerado se não fornecido)
            span_id: ID do span atual (gerado se não fornecido)
            parent_id: ID do span pai
        """
        import uuid
        
        self.trace_id = trace_id or str(uuid.uuid4())
        self.span_id = span_id or str(uuid.uuid4())[:16]
        self.parent_id = parent_id
        self.start_time = time.time()
        self.metadata: Dict[str, Any] = {}
    
    def child(self, name: str) -> "TraceContext":
        """Cria span filho."""
        import uuid
        
        child = TraceContext(
            trace_id=self.trace_id,
            span_id=str(uuid.uuid4())[:16],
            parent_id=self.span_id,
        )
        child.metadata["name"] = name
        return child
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_id": self.parent_id,
            "duration_ms": int((time.time() - self.start_time) * 1000),
            **self.metadata,
        }


@contextmanager
def trace_span(
    name: str,
    logger: Optional[ToolkitLogger] = None,
    parent: Optional[TraceContext] = None,
) -> Generator[TraceContext, None, None]:
    """
    Context manager para criar um span de trace.
    
    Args:
        name: Nome do span
        logger: Logger para registro
        parent: Contexto pai
    
    Yields:
        TraceContext do span
    """
    if parent:
        ctx = parent.child(name)
    else:
        ctx = TraceContext()
        ctx.metadata["name"] = name
    
    if logger:
        logger.debug(f"Starting span: {name}", **ctx.to_dict())
    
    try:
        yield ctx
    except Exception as e:
        ctx.metadata["error"] = str(e)
        ctx.metadata["status"] = "error"
        raise
    finally:
        ctx.metadata.setdefault("status", "success")
        if logger:
            logger.debug(f"Completed span: {name}", **ctx.to_dict())


__all__ = [
    "MetricsCollector",
    "ToolkitLogger",
    "TraceContext",
    "trace_span",
]
