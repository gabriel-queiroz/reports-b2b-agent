"""Tool que devolve o schema de UMA tabela, sob demanda.

O prompt carrega só o índice do catálogo (nomes, domínios e relacionamentos —
`build_tables_index`). Colunas, aliases PT-BR, regra multi-tenant, partição,
filtros padrão e valores possíveis de cada tabela vêm daqui, quando o agente
precisar daquela tabela.
"""

import logging

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from domain.agents.reports_b2b.catalog import allowed_tables
from domain.agents.reports_b2b.schema_extractor import table_doc

logger = logging.getLogger(__name__)


class GetTableSchemaInput(BaseModel):
    """Input for the table schema tool."""

    table: str = Field(
        description=(
            "Nome físico da tabela, exatamente como aparece no índice do prompt "
            "(ex.: employee, ifood_benefits_recharges)."
        )
    )


@tool(args_schema=GetTableSchemaInput)
def get_table_schema(table: str) -> str:
    """Retorna o schema de uma tabela do catálogo.

    Traz as colunas (nome físico, tipo, Alias PT-BR e Exibição), a regra
    multi-tenant, partição obrigatória, filtros padrão e os valores possíveis
    (enums) das colunas. Consulte antes de escrever SQL sobre a tabela.
    """
    documento = table_doc(table)
    if documento is None:
        logger.info("get_table_schema: tabela fora do catálogo: %r", table)
        return (
            f"A tabela '{table}' não está no catálogo. "
            f"Tabelas disponíveis: {', '.join(allowed_tables())}."
        )
    return documento
