"""Testes dos templates de prompt e da injeção de few-shot.

Cobrem o que mudou na refatoração: arquivos .txt, CoT no `sql_system` e o
parâmetro `examples` do `sql_user`.
"""

from domain.agents.reports_b2b.report_generator.prompts import (
    few_shot,
    sql_system_prompt,
    sql_user_prompt,
)

GROUP = "550e8400-e29b-41d4-a716-446655440000"


def test_few_shot_returns_question_sql_examples():
    content = few_shot()

    assert "<exemplo>" in content
    assert "<pergunta_exemplo>" in content
    assert "<sql>" in content
    assert "company_group_id" in content


def test_sql_user_prompt_injects_examples():
    prompt = sql_user_prompt(
        domain="colaboradores",
        tables="employee, companies",
        question="colaboradores ativos",
        group_id=GROUP,
        requested_fields="Nome",
        examples="<exemplo><sql>SELECT 1</sql></exemplo>",
    )

    assert "<exemplo><sql>SELECT 1</sql></exemplo>" in prompt
    assert "colaboradores ativos" in prompt
    assert GROUP in prompt


def test_sql_user_prompt_injects_real_few_shot():
    prompt = sql_user_prompt(
        domain="recargas",
        tables="ifood_benefits_recharges",
        question="recargas de julho",
        group_id=GROUP,
        requested_fields="",
        examples=few_shot(),
    )

    assert "<exemplo>" in prompt
    assert "<pergunta_exemplo>" in prompt


def test_sql_system_prompt_contains_cot_reasoning():
    prompt = sql_system_prompt(
        group_id_restriction="filtre pelo grupo",
        tables_documentation="# doc",
        group_id=GROUP,
    )

    assert "<pensamento>" in prompt
    assert "# doc" in prompt
    assert "filtre pelo grupo" in prompt
