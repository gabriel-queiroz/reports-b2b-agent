"""A `execute_query` recebe o SQL do agente: valida, amarra ao tenant e pede o relatório.

Substitui os testes do gerador de SQL separado. O retry não é mais um loop
interno: quando o guard recusa, o motivo volta como resultado da tool e o agente
corrige no próprio loop ReAct. Aqui se cobra que esse resultado é acionável e
que nada recusado chega ao Reports Service.
"""

import asyncio
import json

import pytest
from conftest import GROUP
from domain.agents.reports_b2b.tools.execute_query import (
    MAX_SQL_LENGTH,
    SUCCESS_MESSAGE,
    execute_query,
)

GOOD_SQL = (
    "SELECT ch.id AS id_estorno, ch.group_id AS company_group_id "
    "FROM main.ifoodoffice_recharge_chargeback.chargeback ch "
    f"WHERE ch.group_id = '{GROUP}'"
)

# usa o Alias PT-BR como se fosse coluna física — erro clássico do LLM
SQL_WITH_WRONG_ALIAS = (
    "SELECT ch.id AS id_estorno, ch.group_id AS company_group_id "
    "FROM main.ifoodoffice_recharge_chargeback.chargeback ch "
    "WHERE ch.id_estorno = 'x'"
)


def call(sql, metadata=None, user_id="u-1"):
    state = {"metadata": {"group_id": GROUP} if metadata is None else metadata, "user_id": user_id}
    return json.loads(asyncio.run(execute_query.coroutine(sql=sql, state=state)))


# ------------------------------------------------------------------ schema --


def test_tool_receives_only_the_sql():
    """O modelo não passa tenant nem usuário: os dois vêm do state da sessão."""
    assert set(execute_query.args) == {"sql"}


# ------------------------------------------------------------------ sucesso --


def test_valid_sql_reaches_reports_service(reports_calls):
    response = call(GOOD_SQL)

    assert response == {"status": "success", "message": SUCCESS_MESSAGE, "report_id": "report-123"}
    assert len(reports_calls) == 1
    assert reports_calls[0]["group_id"] == GROUP
    assert reports_calls[0]["user_id"] == "u-1"


def test_sql_sent_comes_from_ast_not_from_model_string(reports_calls):
    call(GOOD_SQL + "  -- comentário do modelo")

    sent = reports_calls[0]["sql"]
    assert "comentário" not in sent
    assert GROUP in sent


def test_missing_tenant_filter_is_injected(reports_calls):
    sql = (
        "SELECT ch.id AS id_estorno, ch.group_id AS company_group_id "
        "FROM main.ifoodoffice_recharge_chargeback.chargeback ch"
    )
    response = call(sql)

    assert response["status"] == "success"
    assert f"ch.group_id = '{GROUP}'" in reports_calls[0]["sql"]


def test_other_group_in_sql_does_not_leak(reports_calls):
    """O modelo escreve o group_id; o guard garante o da sessão mesmo assim."""
    other = "6ba7b810-9dad-11d1-80b4-00c04fd430c8"
    response = call(GOOD_SQL.replace(GROUP, other))

    if response["status"] == "success":
        assert f"'{GROUP}'" in reports_calls[0]["sql"]
    else:
        assert reports_calls == []


# ------------------------------------------------------- recusa e correção --


def test_guard_rejection_returns_actionable_reason(reports_calls):
    response = call(SQL_WITH_WRONG_ALIAS)

    assert response["status"] == "invalid_sql"
    assert "AliasAsColumnError" in response["message"]
    assert "id_estorno" in response["message"]  # nomeia a coluna errada
    assert reports_calls == []


def test_missing_mandatory_join_is_rejected(reports_calls):
    without_join = (
        "SELECT e.email AS email, e.company_id AS company_group_id "
        "FROM main.ifoodoffice_management_silver.employee e"
    )
    response = call(without_join)

    assert response["status"] == "invalid_sql"
    assert reports_calls == []


@pytest.mark.parametrize(
    "sql",
    [
        f"DELETE FROM main.ifoodoffice_recharge_chargeback.chargeback WHERE group_id = '{GROUP}'",
        GOOD_SQL + "; " + GOOD_SQL,
        "SELECT * FROM main.outro_catalogo.segredos",
    ],
)
def test_dangerous_sql_never_reaches_reports_service(reports_calls, sql):
    response = call(sql)

    assert response["status"] == "invalid_sql"
    assert reports_calls == []


def test_corrected_sql_after_rejection_goes_through(reports_calls):
    """O loop de correção: recusa, o agente reescreve, a segunda chamada passa."""
    assert call(SQL_WITH_WRONG_ALIAS)["status"] == "invalid_sql"
    assert call(GOOD_SQL)["status"] == "success"
    assert len(reports_calls) == 1


@pytest.mark.parametrize("sql", ["", "   ", None])
def test_empty_sql_is_rejected(reports_calls, sql):
    assert call(sql)["status"] == "invalid_sql"
    assert reports_calls == []


def test_too_long_sql_is_rejected(reports_calls):
    response = call(GOOD_SQL + " " * MAX_SQL_LENGTH)

    assert response["status"] == "invalid_sql"
    assert "excede o limite" in response["message"]
    assert reports_calls == []


# ------------------------------------------------------------------- tenant --


@pytest.mark.parametrize(
    "metadata",
    [{}, {"group_id": None}, {"group_id": ""}, {"group_id": "unknown"}, {"group_id": "' OR '1'='1"}],
)
def test_session_without_valid_tenant_is_rejected(reports_calls, metadata):
    response = call(GOOD_SQL, metadata=metadata)

    assert response["status"] == "error"
    assert "grupo de empresas" in response["message"]
    assert reports_calls == []


def test_group_id_is_canonicalized(reports_calls):
    call(GOOD_SQL, metadata={"group_id": GROUP.upper()})

    assert reports_calls[0]["group_id"] == GROUP


# ----------------------------------------------------------------- cnpj/cpf --


def test_masked_cnpj_in_literal_is_normalized(reports_calls):
    sql = (
        "SELECT c.social_name AS razao_social_empresa, c.company_group_id AS company_group_id "
        "FROM fintech_companies.companies c "
        f"WHERE c.company_group_id = '{GROUP}' AND c.cnpj = '12.345.678/0001-90'"
    )
    response = call(sql)

    assert response["status"] == "success", response
    assert "'12345678000190'" in reports_calls[0]["sql"]
    assert "12.345.678/0001-90" not in reports_calls[0]["sql"]


def test_date_literal_is_not_touched(reports_calls):
    sql = GOOD_SQL + " AND ch.updated_at >= '2026-01-01'"
    call(sql)

    assert "'2026-01-01'" in reports_calls[0]["sql"]


# ------------------------------------------------------------ Reports Service --


def test_reports_service_failure_is_error_not_invalid_sql(monkeypatch):
    """Falha do serviço não é culpa do SQL: o agente não deve reescrever a query."""
    from domain.agents.reports_b2b import reports_service

    async def broken(*_args, **_kwargs):
        raise RuntimeError("timeout")

    monkeypatch.setattr(reports_service, "generate_reports", broken)

    response = call(GOOD_SQL)

    assert response["status"] == "error"
    assert "timeout" not in response["message"]
