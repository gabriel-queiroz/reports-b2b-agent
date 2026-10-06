"""Fase 2 — guard de AST.

Cada bug listado no `PLANO.md` vira um teste de regressão aqui: são todos casos
que a validação por string aceitava, produzindo SQL inválido ou sem filtro.
"""

import pytest
import sqlglot
from domain.agents.reports_b2b.guardrails import InvalidGroupIdError
from domain.agents.reports_b2b.sql_guard import (
    DIALECT,
    JoinKeyError,
    OutputColumnError,
    RechargesAggregationError,
    SqlSyntaxError,
    StatementNotAllowedError,
    TableNotAllowedError,
    TenantFilterError,
    guard_query,
)

GROUP = "550e8400-e29b-41d4-a716-446655440000"

EMPLOYEE = "main.ifoodoffice_management_silver.employee"
COMPANIES = "fintech_companies.companies"
RECHARGES = "main.fintech_finance.ifood_benefits_recharges"
CHARGEBACK = "main.ifoodoffice_recharge_chargeback.chargeback"
FIN_ACCOUNT = "main.ifood_benf_transaction_service.financial_account"
FIN_TRANSACTION = "main.ifood_benf_transaction_service.financial_transaction"


def guard(sql: str) -> str:
    return guard_query(sql, GROUP)


def top_level_filter(sql: str, column: str) -> bool:
    """O predicado está na conjunção de topo do WHERE deste SELECT?"""
    from domain.agents.reports_b2b.sql_guard import _top_level_conjuncts
    from sqlglot import exp

    target = f"{column} = '{GROUP}'".lower()
    for select in sqlglot.parse_one(sql, dialect=DIALECT).find_all(exp.Select):
        where = select.args.get("where")
        if where is None:
            continue
        if any(
            c.sql(dialect=DIALECT).lower() == target
            for c in _top_level_conjuncts(where.this)
        ):
            return True
    return False


def executable(sql: str) -> bool:
    """O SQL devolvido volta a fazer parse — o bug do GROUP BY quebrava isto."""
    try:
        sqlglot.parse_one(sql, dialect=DIALECT)
    except sqlglot.ParseError:
        return False
    return True


# ------------------------------------------------- bugs do injetor antigo --


def test_filter_goes_into_where_not_after_group_by():
    """O `_inject_filter_in_query_with_where` colava o AND depois do GROUP BY."""
    sql = guard(
        f"SELECT c.social_name AS razao_social_empresa, "
        f"c.company_group_id AS company_group_id, COUNT(*) AS total "
        f"FROM {EMPLOYEE} e "
        f"INNER JOIN {COMPANIES} c ON e.company_id = c.company_id "
        f"WHERE e.deleted = false "
        f"GROUP BY c.social_name, c.company_group_id "
        f"LIMIT 1000"
    )

    assert executable(sql)
    assert top_level_filter(sql, "c.company_group_id")
    assert sql.index("WHERE") < sql.index("GROUP BY") < sql.index("LIMIT")


def test_filter_does_not_land_inside_or_branch():
    """`WHERE a OR b` + AND cru vira `a OR (b AND filtro)` — não filtra nada."""
    sql = guard(
        f"SELECT c.company_group_id AS company_group_id, e.email AS email "
        f"FROM {EMPLOYEE} e "
        f"INNER JOIN {COMPANIES} c ON e.company_id = c.company_id "
        f"WHERE e.deleted = false OR e.person_id = '550e8400-e29b-41d4-a716-446655440001' "
        f"LIMIT 1000"
    )

    assert top_level_filter(sql, "c.company_group_id")
    assert (
        "(e.deleted = FALSE OR e.person_id = '550e8400-e29b-41d4-a716-446655440001')"
        in sql
    )


def test_filter_inside_or_does_not_count_as_valid_filter():
    """O regex aceitava o UUID em qualquer lugar do texto, inclusive num OR."""
    sql = guard(
        f"SELECT c.company_group_id AS company_group_id, e.email AS email "
        f"FROM {EMPLOYEE} e "
        f"INNER JOIN {COMPANIES} c ON e.company_id = c.company_id "
        f"WHERE c.company_group_id = '{GROUP}' OR e.person_id = '550e8400-e29b-41d4-a716-446655440001' "
        f"LIMIT 1000"
    )

    # o OR continua lá, mas agora dentro de um AND com o filtro real
    assert top_level_filter(sql, "c.company_group_id")
    assert sql.count(GROUP) == 2


def test_where_only_in_subquery_does_not_leave_outer_scope_unfiltered():
    sql = guard(
        f"SELECT x.company_group_id AS company_group_id, x.email AS email FROM ("
        f"  SELECT c.company_group_id, e.email FROM {EMPLOYEE} e"
        f"  INNER JOIN {COMPANIES} c ON e.company_id = c.company_id"
        f"  WHERE e.deleted = false"
        f") x LIMIT 1000"
    )

    # o escopo que lê a tabela base é o de dentro — é lá que o filtro precisa estar
    assert top_level_filter(sql, "c.company_group_id")
    assert executable(sql)


def test_predicate_does_not_land_in_left_join_on():
    sql = guard(
        f"SELECT c.company_group_id AS company_group_id, e.email AS email "
        f"FROM {EMPLOYEE} e "
        f"LEFT JOIN {COMPANIES} c ON e.company_id = c.company_id "
        f"LIMIT 1000"
    )

    assert top_level_filter(sql, "c.company_group_id")
    assert "ON e.company_id = c.company_id AND" not in sql


def test_join_without_alias_uses_table_name_not_on_keyword():
    """`_extract_companies_table_alias` devolvia `"ON"` neste caso."""
    sql = guard(
        f"SELECT companies.company_group_id AS company_group_id "
        f"FROM {EMPLOYEE} e "
        f"INNER JOIN {COMPANIES} ON e.company_id = companies.company_id "
        f"LIMIT 1000"
    )

    assert top_level_filter(sql, "companies.company_group_id")
    assert "ON.company_group_id" not in sql


def test_join_with_condition_without_columns_is_rejected():
    """`ON 1 = 1` não liga tabela a tabela e não pode virar JOIN de catálogo."""
    with pytest.raises(JoinKeyError):
        guard(
            f"SELECT c.company_group_id AS company_group_id, e.email AS email "
            f"FROM {EMPLOYEE} e "
            f"INNER JOIN {COMPANIES} c ON 1 = 1 "
            f"LIMIT 1000"
        )


def test_cross_join_without_key_is_rejected():
    """CROSS JOIN não tem chave de catálogo e precisa ser rejeitado."""
    with pytest.raises(JoinKeyError):
        guard(
            f"SELECT c.company_group_id AS company_group_id, e.email AS email "
            f"FROM {EMPLOYEE} e "
            f"CROSS JOIN {COMPANIES} c "
            f"LIMIT 1000"
        )


def test_recharges_without_group_filter_get_struct_filter():
    """Buraco conhecido: o domínio de recargas pulava a injeção por inteiro."""
    sql = guard(
        f"SELECT r.order_id AS id_recarga, r.company_group.id AS company_group_id "
        f"FROM {RECHARGES} r "
        f"WHERE r.update_month >= '2026-07' "
        f"LIMIT 1000"
    )

    assert top_level_filter(sql, "r.company_group.id")


# --------------------------------------------- agregação de medidas na recarga --


def test_raw_recharge_amount_without_order_item_id_is_rejected():
    """No nível empresa, `amount` cru (sem SUM) é campo de item — precisa agregar."""
    with pytest.raises(RechargesAggregationError):
        guard(
            f"SELECT r.company_group.id AS company_group_id, r.order_id AS id_recarga, "
            f"r.amount AS valor_item_recarga "
            f"FROM {RECHARGES} r WHERE r.order_status = 'DISTRIBUTION_COMPLETE'"
        )


def test_raw_recharge_cashback_without_order_item_id_is_rejected():
    with pytest.raises(RechargesAggregationError):
        guard(
            f"SELECT r.company_group.id AS company_group_id, r.order_id AS id_recarga, "
            f"r.cashback_amount AS valor_cashback_item "
            f"FROM {RECHARGES} r"
        )


def test_recharge_sum_with_group_by_is_accepted():
    sql = guard(
        f"SELECT r.company_group.id AS company_group_id, r.order_id AS id_recarga, "
        f"SUM(r.amount) AS valor_recarga, SUM(r.cashback_amount) AS valor_cashback "
        f"FROM {RECHARGES} r "
        f"WHERE r.order_status = 'DISTRIBUTION_COMPLETE' "
        f"GROUP BY r.company_group.id, r.order_id"
    )

    assert "SUM(r.amount)" in sql
    assert "GROUP BY" in sql


def test_recharge_item_level_with_order_item_id_is_accepted():
    """Com `order_item_id` na saída, é granularidade de item — amount cru é legítimo."""
    sql = guard(
        f"SELECT r.company_group.id AS company_group_id, r.order_item_id AS id_item_recarga, "
        f"r.order_id AS id_recarga, r.amount AS valor_item_recarga "
        f"FROM {RECHARGES} r"
    )

    assert "r.amount" in sql


def test_raw_recharge_amount_in_split_with_order_item_id_is_accepted():
    """`order_item_id` dentro de função (split) também marca granularidade de item."""
    sql = guard(
        f"SELECT r.company_group.id AS company_group_id, "
        f"CAST(CONCAT('ID_', split(r.order_item_id, '-')[3]) AS STRING) AS id_item, "
        f"r.amount AS valor_item_recarga "
        f"FROM {RECHARGES} r"
    )

    assert "r.amount" in sql


def test_raw_amount_from_other_table_is_not_flagged():
    """A regra é só da recarga: `receivable_assets.amount` cru segue passando."""
    sql = guard(
        "SELECT ra.company_group_id AS company_group_id, ra.amount AS valor_pagamento "
        "FROM main.fintech_finance.receivable_assets ra"
    )

    assert "ra.amount" in sql


# ------------------------------------------------------ forma do statement --


@pytest.mark.parametrize(
    "sql",
    [
        f"SELECT c.company_group_id AS company_group_id FROM {COMPANIES} c; "
        f"DROP TABLE {EMPLOYEE}",
        f"SELECT c.company_group_id AS company_group_id FROM {COMPANIES} c;"
        f"DELETE FROM {EMPLOYEE}",
    ],
)
def test_two_statements_are_rejected(sql):
    with pytest.raises(StatementNotAllowedError):
        guard(sql)


@pytest.mark.parametrize(
    "sql",
    [
        f"DELETE FROM {EMPLOYEE}",
        f"UPDATE {EMPLOYEE} SET deleted = true",
        f"DROP TABLE {EMPLOYEE}",
        f"INSERT INTO {EMPLOYEE} SELECT * FROM {EMPLOYEE}",
        f"CREATE TABLE x AS SELECT * FROM {EMPLOYEE}",
    ],
)
def test_dml_and_ddl_are_rejected(sql):
    with pytest.raises(StatementNotAllowedError):
        guard(sql)


def test_invalid_sql_is_rejected_with_syntax_error():
    with pytest.raises(SqlSyntaxError):
        guard("SELEC company_group_id FROM WHERE")


def test_comment_does_not_survive_guard():
    """O SQL entregue é regerado da AST; comentário do LLM não viaja junto."""
    sql = guard(
        f"SELECT c.company_group_id AS company_group_id -- comentário\n"
        f"FROM {COMPANIES} c WHERE c.deleted = false LIMIT 10"
    )

    assert "--" not in sql and "/*" not in sql


def test_returned_sql_comes_from_ast_not_llm_string():
    sql = guard(
        f"select   c.company_group_id   as company_group_id\n\n"
        f"from {COMPANIES} c   where c.deleted = false   limit 10"
    )

    assert sql.startswith("SELECT c.company_group_id AS company_group_id FROM")
    assert "\n" not in sql


# ----------------------------------------------------------------- LIMIT --


def test_query_without_limit_stays_without_limit():
    """Não há teto: o relatório traz o recorte inteiro e o guard não injeta nada."""
    sql = guard(f"SELECT c.company_group_id AS company_group_id FROM {COMPANIES} c")

    assert "LIMIT" not in sql.upper()


def test_user_requested_limit_is_kept():
    """ "as 10 maiores" continua sendo uma pergunta legítima."""
    sql = guard(
        f"SELECT c.company_group_id AS company_group_id FROM {COMPANIES} c LIMIT 10"
    )

    assert sql.endswith("LIMIT 10")


def test_large_limit_is_not_reduced():
    sql = guard(
        f"SELECT c.company_group_id AS company_group_id FROM {COMPANIES} c LIMIT 50000"
    )

    assert sql.endswith("LIMIT 50000")


# ------------------------------------------------------------- allowlist --


def test_table_outside_catalog_is_rejected():
    with pytest.raises(TableNotAllowedError, match="information_schema.tables"):
        guard(
            "SELECT t.company_group_id AS company_group_id "
            "FROM information_schema.tables t LIMIT 10"
        )


def test_chargeback_employee_without_chargeback_join_is_rejected():
    """`chargeback_employee` só filtra por grupo via JOIN com `chargeback`."""
    with pytest.raises(TenantFilterError):
        guard(
            "SELECT ce.employee_id AS id_colaborador, ce.chargeback_id "
            "FROM main.ifoodoffice_recharge_chargeback.chargeback_employee ce "
            "LIMIT 10"
        )


def test_short_name_of_allowed_table_passes():
    sql = guard(
        "SELECT c.company_group_id AS company_group_id FROM companies c LIMIT 10"
    )
    assert top_level_filter(sql, "c.company_group_id")


def test_same_name_table_in_other_catalog_is_rejected():
    with pytest.raises(TableNotAllowedError):
        guard(
            "SELECT e.company_group_id AS company_group_id "
            "FROM outro_catalogo.employee e LIMIT 10"
        )


def test_table_inside_cte_also_goes_through_allowlist():
    with pytest.raises(TableNotAllowedError):
        guard(
            "WITH x AS (SELECT * FROM information_schema.tables) "
            "SELECT x.company_group_id AS company_group_id FROM x LIMIT 10"
        )


# ------------------------------------------------- JOIN obrigatório / tenant --


def test_employee_alone_requires_companies_join():
    with pytest.raises(TenantFilterError, match="employee"):
        guard(
            f"SELECT e.email AS email, e.company_id AS company_group_id "
            f"FROM {EMPLOYEE} e WHERE e.deleted = false LIMIT 10"
        )


def test_financial_transaction_alone_requires_financial_account_join():
    with pytest.raises(TenantFilterError, match="financial_account"):
        guard(
            f"SELECT ft.id AS id, ft.account_id AS company_group_id "
            f"FROM {FIN_TRANSACTION} ft LIMIT 10"
        )


def test_financial_transaction_with_join_filters_by_account():
    sql = guard(
        f"SELECT ft.id AS id_transacao, fa.group_id AS company_group_id "
        f"FROM {FIN_TRANSACTION} ft "
        f"INNER JOIN {FIN_ACCOUNT} fa ON ft.account_id = fa.id "
        f"LIMIT 1000"
    )

    assert top_level_filter(sql, "fa.group_id")


def test_chargeback_filters_by_group_id_directly_without_join():
    sql = guard(
        f"SELECT ch.id AS id_estorno, ch.group_id AS company_group_id "
        f"FROM {CHARGEBACK} ch LIMIT 1000"
    )

    assert top_level_filter(sql, "ch.group_id")


def test_correct_llm_filter_is_kept_without_duplication():
    sql = guard(
        f"SELECT ch.id AS id_estorno, ch.group_id AS company_group_id "
        f"FROM {CHARGEBACK} ch WHERE ch.group_id = '{GROUP}' LIMIT 1000"
    )

    assert sql.count(GROUP) == 1


def test_guard_is_idempotent():
    sql = (
        f"SELECT c.company_group_id AS company_group_id FROM {COMPANIES} c "
        f"WHERE c.deleted = false LIMIT 10"
    )
    once = guard(sql)
    assert guard(once) == once


def test_union_filters_both_branches():
    sql = guard(
        f"SELECT ch.group_id AS company_group_id FROM {CHARGEBACK} ch "
        f"UNION ALL "
        f"SELECT c.company_group_id AS company_group_id FROM {COMPANIES} c"
    )

    assert top_level_filter(sql, "ch.group_id")
    assert top_level_filter(sql, "c.company_group_id")


def test_invalid_group_id_generates_no_sql():
    with pytest.raises(InvalidGroupIdError):
        guard_query(
            f"SELECT c.company_group_id AS company_group_id FROM {COMPANIES} c",
            "unknown",
        )


# ------------------------------------------------ coluna de saída do grupo --


def test_select_without_company_group_id_is_rejected():
    with pytest.raises(OutputColumnError):
        guard(
            f"SELECT c.social_name AS razao_social_empresa FROM {COMPANIES} c LIMIT 10"
        )


def test_literal_does_not_count_as_group_column():
    with pytest.raises(OutputColumnError):
        guard(
            f"SELECT '{GROUP}' AS company_group_id, c.social_name AS razao_social "
            f"FROM {COMPANIES} c LIMIT 10"
        )


def test_column_without_alias_already_has_right_name():
    sql = guard(f"SELECT c.company_group_id FROM {COMPANIES} c LIMIT 10")
    assert top_level_filter(sql, "c.company_group_id")
