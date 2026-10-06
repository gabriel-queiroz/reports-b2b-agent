"""Tool que traduz os campos confirmados com o usuário para colunas do catálogo.

O usuário escolhe campos pelo nome de Exibição (`list_fields`). Para escrever o
SQL, o agente precisa da coluna física, do alias PT-BR e de como cada medida
entra (`SUM` no nível empresa, crua no nível item). Isso é determinístico e já
existia em `build_requested_fields_block` — antes ia para o prompt do gerador
de SQL separado; agora o próprio agente pede, depois da confirmação.
"""

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from domain.agents.reports_b2b.guardrails import InvalidDesiredFieldsError
from domain.agents.reports_b2b.schema_extractor import build_requested_fields_block
from domain.agents.reports_b2b.tools.list_fields import VALID_DOMAINS


class ResolveFieldsInput(BaseModel):
    """Input for the resolve fields tool."""

    domain: VALID_DOMAINS = Field(description="Domínio do relatório.")
    desired_fields: str = Field(
        default="all",
        description=(
            "Campos confirmados com o usuário, exatamente como retornados por "
            "list_fields, separados por vírgula. Use 'all' para todos os campos "
            "do domínio no nível principal."
        ),
    )


@tool(args_schema=ResolveFieldsInput)
def resolve_fields(domain: VALID_DOMAINS, desired_fields: str = "all") -> str:
    """Traduz os campos confirmados para coluna física + alias PT-BR do SQL.

    Indica também quando uma medida entra como SUM(...) com GROUP BY. Chame
    depois da confirmação do usuário e antes de escrever o SQL.
    """
    try:
        return build_requested_fields_block(domain, desired_fields)
    except InvalidDesiredFieldsError as e:
        return f"Não foi possível resolver os campos: {e}"
