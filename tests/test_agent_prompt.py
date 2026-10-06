"""O prompt único do agente: índice do catálogo, regras, exemplos e sessão.

Antes havia três templates (`agente.txt`, `sql_system.txt`, `sql_user.txt`) e um
segundo LLM recebia o catálogo inteiro. Agora o mesmo agente escreve o SQL e
consulta o schema de cada tabela sob demanda.
"""

import re

from domain.agents.reports_b2b.reports_react_agent.agent import ReportsB2bReactAgent
from domain.agents.reports_b2b.reports_react_agent.prompts import (
    agent_system_prompt,
    few_shot,
)
from domain.agents.reports_b2b.schema_extractor import build_tables_index, table_doc


GROUP = "6ba7b810-9dad-11d1-80b4-00c04fd430c8"


def prompt():
    return agent_system_prompt(group_id=GROUP)


def test_all_placeholders_are_filled():
    assert not re.search(r"\{[a-z_]+\}", prompt())


def test_session_data_is_in_prompt():
    text = prompt()

    assert f"`{GROUP}`" in text
    assert re.search(r"Data atual: `\d{4}-\d{2}-\d{2}`", text)


def test_prompt_has_index_rules_and_examples():
    text = prompt()

    assert build_tables_index() in text
    assert "## Aliases em PT-BR" in text  # _regras_gerais.md
    assert "<pergunta_exemplo>" in text
    assert few_shot().count("<exemplo>") == text.count("<exemplo>")


def test_prompt_does_not_carry_the_catalog_columns():
    """O schema de cada tabela vem da tool, não do prompt."""
    text = prompt()

    assert "| Coluna | Tipo |" not in text
    assert table_doc("chargeback") not in text
    assert "ChargebackStatusEnum" not in text


def test_prompt_mentions_every_registered_tool():
    text = prompt()

    for tool in ReportsB2bReactAgent.TOOLS:
        assert f"{tool.name}(" in text, tool.name


def test_prompt_describes_execute_query_as_it_is():
    """Só `sql`: tenant e usuário vêm do state, nunca do modelo."""
    text = prompt()

    assert "execute_query(sql)" in text
    for missing in ("question=", "desired_fields=\"", "group_id=", "domain=\""):
        assert f"execute_query({missing}" not in text


def test_prompt_explains_how_to_handle_each_status():
    text = prompt()

    for status in ("success", "invalid_sql", "error"):
        assert f'"status": "{status}"' in text


def test_prompt_is_much_smaller_than_the_old_generator_context():
    """O gerador antigo recebia ~43k caracteres só de catálogo."""
    assert len(prompt()) < 30_000


def test_examples_filter_by_the_session_group():
    """O modelo copia o filtro dos exemplos; com UUID fictício copiaria o errado."""
    text = prompt()
    examples = text.split("<exemplos>")[1]

    assert "<GROUP_ID>" in few_shot()
    assert "<GROUP_ID>" not in text
    assert examples.count(f"'{GROUP}'") == few_shot().count("'<GROUP_ID>'")


def test_every_example_sql_passes_the_guard():
    """Exemplo que o guard recusa ensina o agente a errar."""
    from domain.agents.reports_b2b.sql_guard import guard_query

    examples = re.findall(r"<sql>(.*?)</sql>", few_shot(), re.DOTALL)
    assert examples

    for sql in examples:
        guard_query(sql.replace("<GROUP_ID>", GROUP), GROUP)
