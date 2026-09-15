"""Logging estruturado em JSON com contexto de requisição e redação de segredos (LGPD).

Regras: nunca logar tokens, argumentos de tools, nomes pesquisados ou e-mails.
O usuário é identificado apenas por `user_ref` (hash do tenant+oid).
"""

import logging
import re
import sys
from contextvars import ContextVar

from pythonjsonlogger.json import JsonFormatter

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
user_ref_var: ContextVar[str | None] = ContextVar("user_ref", default=None)
tool_var: ContextVar[str | None] = ContextVar("tool", default=None)

_JWT_RE = re.compile(r"eyJ[\w-]+\.[\w-]+\.[\w-]+")
_BEARER_RE = re.compile(r"(?i)bearer\s+\S+")
_SENSITIVE_KEYS = ("token", "authorization", "secret", "assertion", "password")


class ContextFilter(logging.Filter):
    """Injeta request_id, user_ref e tool em cada registro."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        record.user_ref = user_ref_var.get()
        record.tool = tool_var.get()
        return True


class RedactionFilter(logging.Filter):
    """Rede de segurança: remove JWTs/Bearer da mensagem e atributos com nomes sensíveis."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _redact(record.msg)
        if record.args:
            args = record.args if isinstance(record.args, tuple) else (record.args,)
            record.args = tuple(_redact(a) if isinstance(a, str) else a for a in args)
        for key in list(vars(record)):
            if any(s in key.lower() for s in _SENSITIVE_KEYS):
                setattr(record, key, "[REDACTED]")
        return True


def _redact(text: str) -> str:
    return _BEARER_RE.sub("Bearer [REDACTED]", _JWT_RE.sub("[REDACTED_JWT]", text))


def setup_logging(level: str = "INFO") -> None:
    formatter = JsonFormatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s %(request_id)s %(user_ref)s %(tool)s",
        rename_fields={"asctime": "timestamp", "levelname": "level", "name": "logger"},
        json_ensure_ascii=False,
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    handler.addFilter(ContextFilter())
    handler.addFilter(RedactionFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())

    # O uvicorn instala handlers de texto próprios antes de chamar a factory: redireciona
    # para o root para que todo o stdout do container seja JSON.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True

    for noisy in ("uvicorn.access", "httpx", "httpcore", "httpx2", "msal", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
