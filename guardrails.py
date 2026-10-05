"""Guardrails de borda: o que entra no prompt e nas f-strings de SQL.

Duas entradas cruzam a fronteira do agente e acabam interpoladas em texto:

- `group_id`: vai para `f"... = '{group_id}'"` na cláusula de tenant. Precisa ser
  um UUID; é o único caminho de SQL injection literal do fluxo.
- `pergunta`: vai para dentro de `<pergunta>…</pergunta>` no prompt de geração
  de SQL. Precisa ser tratada como dado, sem poder fechar a tag e virar
  instrução.

Este módulo não conhece LLM, langchain nem infra — é `uuid` e `re`. Fica no
pacote do agente de propósito, para viajar junto com ele.
"""

import re
import unicodedata
from uuid import UUID

# Limite da pergunta já reescrita pelo agente. Acima disso não é pergunta:
# é conteúdo colado tentando ocupar a janela de contexto.
MAX_QUESTION_LENGTH = 4000

# Tags que estruturam o prompt de geração de SQL (`sql_user.txt`). Uma pergunta
# que as contenha está tentando sair da região de dados.
_PROMPT_TAGS = (
    "pergunta",
    "dominio",
    "tabelas",
    "group_id",
    "system",
    "sistema",
    "instrucoes",
    "instruções",
)

_OPENING_PROMPT_TAG_RE = re.compile(
    r"<\s*(?:" + "|".join(_PROMPT_TAGS) + r")\s*>",
    re.IGNORECASE,
)

# Fechamento de qualquer tag. Nenhuma pergunta legítima traz `</algo>`, e é
# exatamente essa a sequência usada para escapar de `<pergunta>`.
_CLOSING_TAG_RE = re.compile(r"<\s*/\s*[A-Za-z_][\w\-]*\s*>")

# Caracteres de controle preservados: quebra de linha e tabulação.
_ALLOWED_CONTROL_CHARS = {"\n", "\t"}

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


class InvalidQuestionError(ValueError):
    """Pergunta vazia, longa demais ou de tipo inesperado."""


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


def sanitize_question(question: object) -> str:
    """Higieniza a pergunta antes de ela entrar no prompt.

    Remove caracteres de controle, neutraliza as tags que delimitam as seções
    do prompt e recusa entrada vazia ou grande demais.

    Args:
        question: pergunta reescrita pelo agente.

    Returns:
        Pergunta segura para interpolar dentro de `<pergunta>`.

    Raises:
        InvalidQuestionError: se não for texto, se ficar vazia depois da
            limpeza ou se ultrapassar `MAX_QUESTION_LENGTH`.
    """
    if not isinstance(question, str):
        raise InvalidQuestionError(
            f"pergunta deve ser uma string, veio {type(question).__name__}."
        )

    if len(question) > MAX_QUESTION_LENGTH:
        raise InvalidQuestionError(
            f"pergunta com {len(question)} caracteres excede o limite de "
            f"{MAX_QUESTION_LENGTH}. Reescreva de forma mais curta e objetiva."
        )

    cleaned = _strip_control_chars(question)
    cleaned = _CLOSING_TAG_RE.sub(" ", cleaned)
    cleaned = _OPENING_PROMPT_TAG_RE.sub(" ", cleaned)

    # Colapsa o espaço em branco deixado pelas remoções, preservando quebras.
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = cleaned.strip()

    if not cleaned:
        raise InvalidQuestionError("pergunta vazia depois da higienização.")

    return cleaned


def normalize_cnpj_cpf(question: str) -> str:
    """Remove a máscara de CNPJ/CPF antes de a pergunta virar SQL.

    O Databricks guarda esses documentos sem pontuação. Ao normalizar aqui, o
    modelo gera o filtro com o valor exato que existe na tabela:

    - ``12.345.678/0001-90`` -> ``12345678000190``
    - ``12.ABC.345/0001-90`` -> ``12ABC345000190``
    - ``123.456.789-00`` -> ``12345678900``
    """
    question = _CNPJ_FORMATTED_RE.sub(_normalize_cnpj_match, question)
    question = _CPF_FORMATTED_RE.sub(r"\1\2\3\4", question)
    return question


def _normalize_cnpj_match(match: re.Match) -> str:
    """Concatena os grupos do CNPJ e normaliza letras para maiúsculas."""
    return "".join(match.groups()).upper()


def _strip_control_chars(text: str) -> str:
    """Remove caracteres de controle e formatação invisível (Cc/Cf).

    Mantém `\\n` e `\\t`. A categoria `Cf` cobre os invisíveis usados para
    esconder instrução dentro do texto (zero-width, marcas de direção, BOM).
    """
    return "".join(
        char
        for char in text
        if char in _ALLOWED_CONTROL_CHARS
        or unicodedata.category(char) not in ("Cc", "Cf")
    )
