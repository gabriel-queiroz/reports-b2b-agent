"""Prompt do agente ReAct, montado a partir dos templates desta pasta.

Um prompt só: o mesmo agente conversa com o usuário e escreve o SQL. Ele leva o
índice do catálogo (nomes de tabelas, domínios e relacionamentos), as regras
gerais e os exemplos pergunta → SQL. Colunas, aliases e regra multi-tenant de
cada tabela não entram aqui: vêm da tool `get_table_schema`, sob demanda.
"""

from datetime import datetime
from functools import lru_cache
from pathlib import Path

from domain.agents.reports_b2b.catalog import tables_dir
from domain.agents.reports_b2b.schema_extractor import GENERAL_RULES, build_tables_index

_DIR = Path(__file__).parent

# Placeholder usado quando o prompt é montado sem sessão (no `__init__` do
# agente). Nunca chega ao modelo: `_build_system_prompt` remonta com o UUID.
GROUP_ID_NOT_SET = "{group_id_not_set}"

# Marca do group_id nos exemplos (`few_shot.txt`). É trocada pelo UUID da
# sessão: o modelo copia o filtro dos exemplos, e com um UUID fictício ali
# copiaria o valor errado.
EXAMPLE_GROUP_ID = "<GROUP_ID>"


def _read(name: str) -> str:
    return (_DIR / name).read_text(encoding="utf-8")


def few_shot() -> str:
    """Exemplos pergunta → SQL, crus (sem `str.format`)."""
    return _read("few_shot.txt").strip()


@lru_cache(maxsize=1)
def _static_parts() -> dict[str, str]:
    """O que não depende da sessão: lido uma vez por processo."""
    return {
        "tables_index": build_tables_index(),
        "catalog_rules": (tables_dir() / GENERAL_RULES).read_text(encoding="utf-8").strip(),
        "examples": few_shot(),
    }


def agent_system_prompt(group_id: str | None = None) -> str:
    """Prompt de sistema do agente para a sessão de `group_id`.

    `group_id` já deve vir validado (`validate_group_id`): ele é interpolado no
    prompt e nos exemplos de SQL.
    """
    group_id = group_id or GROUP_ID_NOT_SET
    parts = _static_parts()
    return _read("agent_prompt.txt").format(
        tables_index=parts["tables_index"],
        catalog_rules=parts["catalog_rules"],
        examples=parts["examples"].replace(EXAMPLE_GROUP_ID, group_id),
        group_id=group_id,
        current_date=datetime.now().strftime("%Y-%m-%d"),
    )
