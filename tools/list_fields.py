"""Tool for listing available fields for a data domain.

Monta a lista a partir do catálogo (`data/tabelas/`), tabela a tabela, usando a
coluna **Exibição**. Antes esta tool devolvia o `schema.md` **inteiro** a cada
chamada e pedia para o LLM extrair os campos: ~44k caracteres por chamada, e a
lista saía diferente a cada vez.
"""

import logging
from typing import Literal

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from domain.agents.reports_b2b.catalog import find_table
from domain.agents.reports_b2b.schema_extractor import extract_tables_by_domain

logger = logging.getLogger(__name__)

# Domains reference for tool input validation
VALID_DOMAINS = Literal["colaboradores", "recargas", "financeiro", "estorno_recarga"]

# O STRUCT inteiro nunca é campo de relatório — só os caminhos de dentro dele,
# que já vêm listados como colunas próprias no catálogo.
_TIPOS_NAO_EXIBIVEIS = {"STRUCT"}


class ListFieldsInput(BaseModel):
    """Input for the list fields tool."""

    domain: VALID_DOMAINS = Field(description="The data domain to list fields for.")


@tool(args_schema=ListFieldsInput)
def list_fields(domain: VALID_DOMAINS) -> str:
    """Lists available fields for a specific data domain.

    Returns the user-facing field names (``Exibição`` column) grouped by table
    and, when a table has more than one level, by that level (``Recarga
    (granularidade de empresa)`` vs ``Detalhes da Recarga (granularidade de
    colaborador)``).
    """
    logger.info("list_fields called for domain: %s", domain)

    tabelas = extract_tables_by_domain().get(domain, [])
    if not tabelas:
        return f"Não há domínio '{domain}' no catálogo."

    blocos = []
    for caminho in tabelas:
        tabela = find_table(caminho)
        if tabela is None:
            continue

        grupos: dict[str, list[str]] = {}
        for coluna in tabela.columns:
            if not (coluna.display and coluna.type.upper() not in _TIPOS_NAO_EXIBIVEIS):
                continue
            grupos.setdefault(coluna.group or "Campos", []).append(
                f"- {coluna.display}"
            )

        if not grupos:
            continue

        if len(grupos) == 1:
            linhas = next(iter(grupos.values()))
        else:
            linhas = []
            for grupo, campos in grupos.items():
                linhas.append(f"**{grupo}**")
                linhas.extend(campos)

        blocos.append(f"**{tabela.title}**\n" + "\n".join(linhas))

    if not blocos:
        return f"Não há campos catalogados para o domínio '{domain}'."

    return (
        f"Campos disponíveis no domínio **{domain}**:\n\n"
        + "\n\n".join(blocos)
        + "\n\nApresente estes nomes ao usuário exatamente como estão aqui. "
        "Os grupos em negrito indicam o nível de cada campo (ex.: Recarga "
        "(granularidade de empresa), Detalhes da Recarga (granularidade de "
        "colaborador)) — ofereça apenas os campos do nível que a pergunta "
        "exige. Não invente campos e não mostre nomes técnicos de colunas."
    )
