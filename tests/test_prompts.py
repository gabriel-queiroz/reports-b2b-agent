"""Testes dos templates de prompt e da injeção de few-shot.

Cobrem o que mudou na refatoração: arquivos .txt, CoT no `sql_system` e o
parâmetro `exemplos` do `sql_user`.
"""

from domain.agents.reports_b2b.report_generator.prompts import (
    few_shot,
    sql_system_prompt,
    sql_user_prompt,
)

GRUPO = "550e8400-e29b-41d4-a716-446655440000"


def test_few_shot_retorna_exemplos_pergunta_sql():
    conteudo = few_shot()

    assert "<exemplo>" in conteudo
    assert "<pergunta_exemplo>" in conteudo
    assert "<sql>" in conteudo
    assert "company_group_id" in conteudo


def test_sql_user_prompt_injeta_exemplos():
    prompt = sql_user_prompt(
        dominio="colaboradores",
        tabelas="employee, companies",
        pergunta="colaboradores ativos",
        group_id=GRUPO,
        campos_solicitados="Nome",
        exemplos="<exemplo><sql>SELECT 1</sql></exemplo>",
    )

    assert "<exemplo><sql>SELECT 1</sql></exemplo>" in prompt
    assert "colaboradores ativos" in prompt
    assert GRUPO in prompt


def test_sql_user_prompt_injeta_few_shot_real():
    prompt = sql_user_prompt(
        dominio="recargas",
        tabelas="ifood_benefits_recharges",
        pergunta="recargas de julho",
        group_id=GRUPO,
        campos_solicitados="",
        exemplos=few_shot(),
    )

    assert "<exemplo>" in prompt
    assert "<pergunta_exemplo>" in prompt


def test_sql_system_prompt_contem_pensamento_cot():
    prompt = sql_system_prompt(
        restricao_group_id="filtre pelo grupo",
        documentacao_tabelas="# doc",
        group_id=GRUPO,
    )

    assert "<pensamento>" in prompt
    assert "# doc" in prompt
    assert "filtre pelo grupo" in prompt
