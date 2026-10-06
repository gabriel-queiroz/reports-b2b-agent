"""Guardrails de borda: o que entra no prompt e nas f-strings de SQL.

- `group_id`: vai para o prompt e para `f"... = '{group_id}'"` na cláusula de
  tenant. Precisa ser um UUID; é o único caminho de SQL injection literal do
  fluxo.
- CNPJ/CPF: o agente pode escrever o documento com máscara no filtro; a
  `execute_query` normaliza os literais antes do guard.
- `desired_fields`: rótulos que não resolvem contra o catálogo viram erro
  acionável (`InvalidDesiredFieldsError`).

O SQL em si é validado no `sql_guard`, não aqui.

Este módulo não conhece LLM, langchain nem infra — é `uuid` e `re`. Fica no
pacote do agente de propósito, para viajar junto com ele.
"""

import re
from uuid import UUID

# Máscaras comuns de CNPJ/CPF. O Databricks guarda esses documentos sem
# pontuação, então normalizamos a entrada antes de ela virar SQL.
#
# O CNPJ alfanumérico (nova lei) aceita letras de A-Z na base; os dois dígitos
# verificadores continuam numéricos. Normalizamos para maiúsculas porque é a
# forma canônica do documento.
_CNPJ_FORMATTED_RE = re.compile(
    r"(?<![A-Za-z0-9])([A-Za-z0-9]{2})[.\s/-]([A-Za-z0-9]{3})[.\s/-]"
    r"([A-Za-z0-9]{3})[/\s]([A-Za-z0-9]{4})[-\s](\d{2})(?![A-Za-z0-9])"
)
_CPF_FORMATTED_RE = re.compile(
    r"(?<!\d)(\d{3})[.\s/-](\d{3})[.\s/-](\d{3})[-\s](\d{2})(?!\d)"
)


class InvalidGroupIdError(ValueError):
    """`group_id` ausente ou fora do formato UUID."""


class InvalidDesiredFieldsError(ValueError):
    """`desired_fields` não resolve contra os campos exibidos do domínio."""


def validate_group_id(group_id: object) -> str:
    """Valida o `group_id` como UUID e devolve a forma canônica.

    O valor devolvido é o que deve ser usado daqui para frente: ele vem de
    `str(UUID(...))`, então é sempre `[0-9a-f-]{36}` e não tem como carregar
    aspas, comentário de SQL ou `OR '1'='1`.

    Args:
        group_id: valor cru vindo da sessão / do estado do grafo.

    Returns:
        UUID canônico em minúsculas, com hífens.

    Raises:
        InvalidGroupIdError: se estiver ausente, vazio ou não for um UUID.
    """
    if group_id is None:
        raise InvalidGroupIdError(
            "group_id ausente: sem ele não há isolamento multi-tenant."
        )

    if isinstance(group_id, UUID):
        return str(group_id)

    if not isinstance(group_id, str):
        raise InvalidGroupIdError(
            f"group_id deve ser uma string UUID, veio {type(group_id).__name__}."
        )

    candidate = group_id.strip()
    if not candidate:
        raise InvalidGroupIdError(
            "group_id vazio: sem ele não há isolamento multi-tenant."
        )

    try:
        return str(UUID(candidate))
    except (ValueError, AttributeError, TypeError) as exc:
        raise InvalidGroupIdError(
            "group_id não é um UUID válido; a consulta foi recusada antes de "
            "chegar ao SQL."
        ) from exc


def is_valid_group_id(group_id: object) -> bool:
    """Versão booleana de `validate_group_id`, para logs e ramificações."""
    try:
        validate_group_id(group_id)
    except InvalidGroupIdError:
        return False
    return True


def normalize_cnpj_cpf(text: str) -> str:
    """Remove a máscara de CNPJ/CPF de um texto.

    O Databricks guarda esses documentos sem pontuação; um filtro com a máscara
    não encontra nada:

    - ``12.345.678/0001-90`` -> ``12345678000190``
    - ``12.ABC.345/0001-90`` -> ``12ABC345000190``
    - ``123.456.789-00`` -> ``12345678900``
    """
    text = _CNPJ_FORMATTED_RE.sub(_normalize_cnpj_match, text)
    text = _CPF_FORMATTED_RE.sub(r"\1\2\3\4", text)
    return text


def _normalize_cnpj_match(match: re.Match) -> str:
    """Concatena os grupos do CNPJ e normaliza letras para maiúsculas."""
    return "".join(match.groups()).upper()
