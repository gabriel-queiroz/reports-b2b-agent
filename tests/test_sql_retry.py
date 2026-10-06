"""Fase 4 — o retry precisa levar informação nova.

Antes, o `continue` reinvocava o **prompt idêntico**: a segunda tentativa era
uma segunda chance de sortear a mesma resposta. Agora o erro do guard volta
como mensagem, e a query rejeitada vai junto.
"""

import asyncio

import pytest
from domain.agents.reports_b2b.report_generator.tools.generate_query_tool import (
    MAX_SQL_ATTEMPTS,
    _generate_sql_internal,
)
from domain.agents.reports_b2b.sql_guard import AliasAsColumnError, SqlGuardError

GROUP = "550e8400-e29b-41d4-a716-446655440000"

GOOD_SQL = (
    "SELECT ch.id AS id_estorno, ch.group_id AS company_group_id "
    "FROM main.ifoodoffice_recharge_chargeback.chargeback ch LIMIT 1000"
)

# usa o Alias PT-BR como se fosse coluna física — erro clássico do LLM
SQL_WITH_WRONG_ALIAS = (
    "SELECT ch.id AS id_estorno, ch.group_id AS company_group_id "
    "FROM main.ifoodoffice_recharge_chargeback.chargeback ch "
    "WHERE ch.id_estorno = 'x' LIMIT 1000"
)


def generate(provider):
    return asyncio.run(
        _generate_sql_internal("estornos de julho", "estorno_recarga", GROUP, provider)
    )


def test_guard_error_returns_as_message_to_llm(provider_factory):
    provider = provider_factory(SQL_WITH_WRONG_ALIAS, GOOD_SQL)

    sql = generate(provider)

    assert len(provider.calls) == 2, "não houve segunda tentativa"

    correction = provider.user_prompt(call=1)
    assert "REJEITADA" in correction
    assert "id_estorno" in correction  # o erro nomeia a coluna
    assert "ch.id_estorno = 'x'" in correction  # e a query rejeitada vai junto
    assert "AliasAsColumnError" in correction

    assert "id_estorno = 'x'" not in sql


def test_second_attempt_keeps_original_prompt(provider_factory):
    """A correção é acrescentada à conversa, não substitui o prompt."""
    provider = provider_factory(SQL_WITH_WRONG_ALIAS, GOOD_SQL)

    generate(provider)

    first, second = provider.calls
    assert second[: len(first)] == first
    assert len(second) == len(first) + 1


def test_identical_prompt_is_not_resent(provider_factory):
    """O bug: as duas chamadas saíam exatamente iguais."""
    provider = provider_factory(SQL_WITH_WRONG_ALIAS, GOOD_SQL)

    generate(provider)

    assert provider.calls[0] != provider.calls[1]


def test_persistent_error_raises_after_attempts(provider_factory):
    provider = provider_factory(SQL_WITH_WRONG_ALIAS)

    with pytest.raises(AliasAsColumnError):
        generate(provider)

    assert len(provider.calls) == MAX_SQL_ATTEMPTS


def test_all_rejections_go_through_same_retry_path(provider_factory):
    """Antes, o JOIN obrigatório levantava sem retry e as outras tentavam duas vezes."""
    without_join = (
        "SELECT e.email AS email, e.company_id AS company_group_id "
        "FROM main.ifoodoffice_management_silver.employee e LIMIT 1000"
    )
    provider = provider_factory(without_join)

    with pytest.raises(SqlGuardError):
        generate(provider)

    assert len(provider.calls) == MAX_SQL_ATTEMPTS


def test_sql_llm_is_deterministic_with_token_headroom(provider_factory):
    """`temperature=0.2` sorteava a query; `max_tokens=1024` truncava o SQL."""
    provider = provider_factory(GOOD_SQL)

    generate(provider)

    assert provider.llm_params["temperature"] == 0
    assert provider.llm_params["max_tokens"] >= 4096


def test_valid_sql_on_first_try_uses_no_retry(provider_factory):
    provider = provider_factory(GOOD_SQL)

    sql = generate(provider)

    assert len(provider.calls) == 1
    assert GROUP in sql


def test_few_shot_is_injected_in_user_prompt(provider_factory):
    provider = provider_factory(GOOD_SQL)

    generate(provider)

    user_prompt = provider.user_prompt(call=0)

    assert "<exemplos>" in user_prompt
    assert "<exemplo>" in user_prompt
    assert "company_group_id" in user_prompt
