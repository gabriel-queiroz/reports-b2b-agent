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

GRUPO = "550e8400-e29b-41d4-a716-446655440000"

SQL_BOM = (
    "SELECT ch.id AS id_estorno, ch.group_id AS company_group_id "
    "FROM main.ifoodoffice_recharge_chargeback.chargeback ch LIMIT 1000"
)

# usa o Alias PT-BR como se fosse coluna física — erro clássico do LLM
SQL_COM_ALIAS_ERRADO = (
    "SELECT ch.id AS id_estorno, ch.group_id AS company_group_id "
    "FROM main.ifoodoffice_recharge_chargeback.chargeback ch "
    "WHERE ch.id_estorno = 'x' LIMIT 1000"
)


def gerar(provider):
    return asyncio.run(
        _generate_sql_internal("estornos de julho", "estorno_recarga", GRUPO, provider)
    )


def test_erro_do_guard_volta_como_mensagem_para_o_llm(provider_factory):
    provider = provider_factory(SQL_COM_ALIAS_ERRADO, SQL_BOM)

    sql = gerar(provider)

    assert len(provider.chamadas) == 2, "não houve segunda tentativa"

    correcao = provider.prompt_do_usuario(chamada=1)
    assert "REJEITADA" in correcao
    assert "id_estorno" in correcao  # o erro nomeia a coluna
    assert "ch.id_estorno = 'x'" in correcao  # e a query rejeitada vai junto
    assert "AliasAsColumnError" in correcao

    assert "id_estorno = 'x'" not in sql


def test_segunda_tentativa_mantem_o_prompt_original(provider_factory):
    """A correção é acrescentada à conversa, não substitui o prompt."""
    provider = provider_factory(SQL_COM_ALIAS_ERRADO, SQL_BOM)

    gerar(provider)

    primeira, segunda = provider.chamadas
    assert segunda[: len(primeira)] == primeira
    assert len(segunda) == len(primeira) + 1


def test_prompt_identico_nao_e_mais_reenviado(provider_factory):
    """O bug: as duas chamadas saíam exatamente iguais."""
    provider = provider_factory(SQL_COM_ALIAS_ERRADO, SQL_BOM)

    gerar(provider)

    assert provider.chamadas[0] != provider.chamadas[1]


def test_erro_persistente_levanta_depois_das_tentativas(provider_factory):
    provider = provider_factory(SQL_COM_ALIAS_ERRADO)

    with pytest.raises(AliasAsColumnError):
        gerar(provider)

    assert len(provider.chamadas) == MAX_SQL_ATTEMPTS


def test_todas_as_rejeicoes_passam_pelo_mesmo_caminho_de_retry(provider_factory):
    """Antes, o JOIN obrigatório levantava sem retry e as outras tentavam duas vezes."""
    sem_join = (
        "SELECT e.email AS email, e.company_id AS company_group_id "
        "FROM main.ifoodoffice_management_silver.employee e LIMIT 1000"
    )
    provider = provider_factory(sem_join)

    with pytest.raises(SqlGuardError):
        gerar(provider)

    assert len(provider.chamadas) == MAX_SQL_ATTEMPTS


def test_llm_de_sql_e_deterministico_e_com_folga_de_tokens(provider_factory):
    """`temperature=0.2` sorteava a query; `max_tokens=1024` truncava o SQL."""
    provider = provider_factory(SQL_BOM)

    gerar(provider)

    assert provider.parametros_llm["temperature"] == 0
    assert provider.parametros_llm["max_tokens"] >= 4096


def test_sql_valido_na_primeira_nao_gasta_tentativa(provider_factory):
    provider = provider_factory(SQL_BOM)

    sql = gerar(provider)

    assert len(provider.chamadas) == 1
    assert GRUPO in sql


def test_few_shot_e_injetado_no_prompt_do_usuario(provider_factory):
    provider = provider_factory(SQL_BOM)

    gerar(provider)

    prompt_usuario = provider.prompt_do_usuario(chamada=0)

    assert "<exemplos>" in prompt_usuario
    assert "<exemplo>" in prompt_usuario
    assert "company_group_id" in prompt_usuario
