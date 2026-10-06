"""Prompts do agente, mantidos como templates .txt nesta pasta.

Os placeholders ({domains}, {tables_documentation}, {examples}, ...) são
preenchidos aqui no carregamento; o conteúdo editável fica todo nos arquivos
.txt.
"""

from datetime import datetime
from pathlib import Path

_DIR = Path(__file__).parent


def _load(name: str) -> str:
    """Carrega um arquivo .txt de prompt."""
    return (_DIR / f"{name}.txt").read_text(encoding="utf-8")


def few_shot() -> str:
    """Retorna o conteúdo bruto dos exemplos few-shot (pergunta -> SQL).

    Carregado cru (sem `str.format`): o conteúdo usa UUID de exemplo e não tem
    placeholders, evitando conflito de chaves com o template do usuário.
    """
    return _load("few_shot")


def agent_system_prompt(domains: str, group_id: str = None) -> str:
    """Retorna o prompt do sistema com dominios, group_id e current_date.

    Args:
        dominios: Descrição dos domínios disponíveis
        group_id: UUID do grupo para multi-tenant (obrigatório para segurança)
    """
    group_id_str = group_id or "{{group_id_não_fornecido}}"
    current_date = datetime.now().strftime("%Y-%m-%d")
    return _load("agente").format(
        domains=domains, group_id=group_id_str, current_date=current_date
    )


def sql_system_prompt(
    group_id_restriction: str,
    tables_documentation: str,
    group_id: str,
) -> str:
    """Retorna o prompt de sistema para geração de SQL."""
    return _load("sql_system").format(
        tables_documentation=tables_documentation,
        group_id_restriction=group_id_restriction,
        group_id=group_id,
    )


def sql_user_prompt(
    domain: str,
    tables: str,
    question: str,
    group_id: str,
    requested_fields: str = "",
    examples: str = "",
) -> str:
    """Retorna o prompt do usuário para geração de SQL.

    Args:
        exemplos: conteúdo few-shot (pergunta -> SQL) injetado dentro de
            <exemplos> no template.
    """
    return _load("sql_user").format(
        domain=domain,
        tables=tables,
        question=question,
        group_id=group_id,
        requested_fields=requested_fields,
        examples=examples,
    )
