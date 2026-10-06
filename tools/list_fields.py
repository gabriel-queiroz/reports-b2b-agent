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
_NON_DISPLAYABLE_TYPES = {"STRUCT"}


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

    tables = extract_tables_by_domain().get(domain, [])
    if not tables:
        return f"Não há domínio '{domain}' no catálogo."

    blocks = []
    for table_path in tables:
        table = find_table(table_path)
        if table is None:
            continue

        groups: dict[str, list[str]] = {}
        for column in table.columns:
            if not (column.display and column.type.upper() not in _NON_DISPLAYABLE_TYPES):
                continue
            groups.setdefault(column.group or "Campos", []).append(
                f"- {column.display}"
            )

        if not groups:
            continue

        if len(groups) == 1:
            lines = next(iter(groups.values()))
        else:
            lines = []
            for group, fields in groups.items():
                lines.append(f"**{group}**")
                lines.extend(fields)

        blocks.append(f"**{table.title}**\n" + "\n".join(lines))

    if not blocks:
        return f"Não há campos catalogados para o domínio '{domain}'."

    return (
        f"Campos disponíveis no domínio **{domain}**:\n\n"
        + "\n\n".join(blocks)
        + "\n\nApresente estes nomes ao usuário exatamente como estão aqui. "
        "Os grupos em negrito indicam o nível de cada campo (ex.: Recarga "
        "(granularidade de empresa), Detalhes da Recarga (granularidade de "
        "colaborador)) — ofereça apenas os campos do nível que a pergunta "
        "exige. Não invente campos e não mostre nomes técnicos de colunas."
    )
