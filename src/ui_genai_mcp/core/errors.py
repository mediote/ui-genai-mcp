"""Erros de aplicação com mensagem amigável (pt-BR) separada do detalhe técnico.

`user_message` é o único texto que pode chegar ao modelo/usuário. O `str(exc)` é
detalhe técnico destinado exclusivamente aos logs.
"""


class AppError(Exception):
    """Base de todos os erros esperados da aplicação."""

    user_message: str = "Não foi possível concluir a operação agora. Tente novamente em breve."

    def __init__(self, detail: str = "", *, user_message: str | None = None) -> None:
        super().__init__(detail or self.__class__.__name__)
        if user_message is not None:
            self.user_message = user_message


class AuthenticationRequired(AppError):
    user_message = (
        "Não foi possível validar sua autorização. Faça login novamente e repita a pergunta."
    )


class PermissionDenied(AppError):
    user_message = "Você não tem permissão para acessar esta informação."


class ResourceNotFound(AppError):
    user_message = "O recurso solicitado não foi encontrado."


class UpstreamUnavailable(AppError):
    user_message = "O serviço de dados está temporariamente indisponível. Tente novamente em breve."


class ConfigurationError(AppError):
    user_message = (
        "Serviço indisponível por um problema de configuração do servidor. Acione o time de GenAI."
    )
