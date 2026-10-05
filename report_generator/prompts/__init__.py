"""Prompts do agente, mantidos como templates .txt nesta pasta.

Os placeholders ({dominios}, {documentacao_tabelas}, {exemplos}, ...) são
preenchidos aqui no carregamento; o conteúdo editável fica todo nos arquivos
.txt.
"""

from datetime import datetime
from pathlib import Path

_DIR = Path(__file__).parent


def _carregar(nome: str) -> str:
    """Carrega um arquivo .txt de prompt."""
    return (_DIR / f"{nome}.txt").read_text(encoding="utf-8")


def few_shot() -> str:
    """Retorna o conteúdo bruto dos exemplos few-shot (pergunta -> SQL).

    Carregado cru (sem `str.format`): o conteúdo usa UUID de exemplo e não tem
    placeholders, evitando conflito de chaves com o template do usuário.
    """
    return _carregar("few_shot")


def agent_system_prompt(dominios: str, group_id: str = None) -> str:
    """Retorna o prompt do sistema com dominios, group_id e current_date.

    Args:
        dominios: Descrição dos domínios disponíveis
        group_id: UUID do grupo para multi-tenant (obrigatório para segurança)
    """
    group_id_str = group_id or "{{group_id_não_fornecido}}"
    current_date = datetime.now().strftime("%Y-%m-%d")
    return _carregar("agente").format(
        dominios=dominios, group_id=group_id_str, data_atual=current_date
    )


def sql_system_prompt(
    restricao_group_id: str,
    documentacao_tabelas: str,
    group_id: str,
) -> str:
    """Retorna o prompt de sistema para geração de SQL."""
    return _carregar("sql_system").format(
        documentacao_tabelas=documentacao_tabelas,
        restricao_group_id=restricao_group_id,
        group_id=group_id,
    )


def sql_user_prompt(
    dominio: str,
    tabelas: str,
    pergunta: str,
    group_id: str,
    campos_solicitados: str = "",
    exemplos: str = "",
) -> str:
    """Retorna o prompt do usuário para geração de SQL.

    Args:
        exemplos: conteúdo few-shot (pergunta -> SQL) injetado dentro de
            <exemplos> no template.
    """
    return _carregar("sql_user").format(
        dominio=dominio,
        tabelas=tabelas,
        pergunta=pergunta,
        group_id=group_id,
        campos_solicitados=campos_solicitados,
        exemplos=exemplos,
    )
