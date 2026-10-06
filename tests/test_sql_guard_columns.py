"""Fase 3 — coluna e chave de JOIN conferidas contra o catálogo.

O validador antigo (`validate_alias_misuse`) fazia isto por regex de linha:
reprovava query correta e deixava passar o erro real quando o SQL vinha
multi-linha. Aqui a conferência é por tabela, resolvendo o alias no AST.
"""

import pytest
from domain.agents.reports_b2b.sql_guard import (
    AliasAsColumnError,
    ColumnNotFilterableError,
    ColumnNotFoundError,
    JoinKeyError,
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


# ------------------------------------------------- alias PT-BR como coluna --


def test_ptbr_alias_in_where_is_rejected_naming_real_column():
    """O exemplo do PLANO: `id_estorno` não existe; a coluna é `id`."""
    with pytest.raises(AliasAsColumnError) as error:
        guard(
            f"SELECT ch.id AS id_estorno, ch.group_id AS company_group_id "
            f"FROM {CHARGEBACK} ch WHERE ch.id_estorno = 'x' LIMIT 10"
        )

    message = str(error.value)
    assert "id_estorno" in message
    assert "chargeback.id" in message


def test_multiline_ptbr_alias_is_also_caught():
    """O regex de linha do validador antigo perdia o erro quando quebrava linha."""
    with pytest.raises(AliasAsColumnError):
        guard(
            f"SELECT ch.id AS id_estorno,\n"
            f"       ch.group_id AS company_group_id\n"
            f"FROM {CHARGEBACK} ch\n"
            f"WHERE\n"
            f"  ch.id_estorno = 'x'\n"
            f"LIMIT 10"
        )


def test_ptbr_alias_after_as_is_valid_usage():
    sql = guard(
        f"SELECT ch.id AS id_estorno, ch.group_id AS company_group_id "
        f"FROM {CHARGEBACK} ch LIMIT 10"
    )
    assert "AS id_estorno" in sql


def test_output_alias_can_be_used_in_order_by():
    """Spark resolve alias de saída em ORDER BY — não é erro."""
    sql = guard(
        f"SELECT ch.id AS id_estorno, ch.group_id AS company_group_id "
        f"FROM {CHARGEBACK} ch ORDER BY id_estorno LIMIT 10"
    )
    assert "ORDER BY id_estorno" in sql


def test_undeclared_alias_in_order_by_is_rejected():
    with pytest.raises((AliasAsColumnError, ColumnNotFoundError)):
        guard(
            f"SELECT ch.id AS id, ch.group_id AS company_group_id "
            f"FROM {CHARGEBACK} ch ORDER BY id_estorno LIMIT 10"
        )


@pytest.mark.parametrize(
    "sql",
    [
        # os falsos positivos que o validador antigo produzia
        f"SELECT c.company_group_id AS company_group_id, c.cnpj AS cnpj, "
        f"COUNT(*) AS total FROM {COMPANIES} c "
        f"GROUP BY c.cnpj, c.company_group_id LIMIT 10",
        f"SELECT c.company_group_id AS company_group_id, c.social_name AS razao_social "
        f"FROM {COMPANIES} c WHERE c.deleted = false "
        f"GROUP BY c.social_name, c.company_group_id LIMIT 10",
    ],
)
def test_correct_query_is_no_longer_rejected(sql):
    assert guard(sql)


# ------------------------------------------------------ coluna inexistente --


def test_invented_column_is_rejected_with_suggestion():
    with pytest.raises(ColumnNotFoundError) as error:
        guard(
            f"SELECT ch.chargeback_id AS id, ch.group_id AS company_group_id "
            f"FROM {CHARGEBACK} ch LIMIT 10"
        )

    message = str(error.value)
    assert "chargeback_id" in message
    assert "chargeback" in message


def test_column_from_wrong_table_is_rejected():
    """`company_group_id` existe em companies, não em employee."""
    with pytest.raises(ColumnNotFoundError, match="employee"):
        guard(
            f"SELECT e.company_group_id AS company_group_id "
            f"FROM {EMPLOYEE} e "
            f"INNER JOIN {COMPANIES} c ON e.company_id = c.company_id LIMIT 10"
        )


def test_valid_struct_field_passes():
    assert guard(
        f"SELECT r.company_group.id AS company_group_id, "
        f"r.order_info.payment_method AS metodo_pagamento_recarga_info "
        f"FROM {RECHARGES} r LIMIT 10"
    )


def test_invented_struct_field_is_rejected():
    with pytest.raises(ColumnNotFoundError):
        guard(
            f"SELECT r.company_group.id AS company_group_id, "
            f"r.company_group.uuid AS uuid FROM {RECHARGES} r LIMIT 10"
        )


def test_unqualified_column_is_resolved_against_scope():
    assert guard(
        f"SELECT group_id AS company_group_id, chargeback_status AS situacao "
        f"FROM {CHARGEBACK} WHERE chargeback_status = 'CONCLUDED' LIMIT 10"
    )


def test_missing_unqualified_column_is_rejected():
    with pytest.raises(ColumnNotFoundError):
        guard(
            f"SELECT group_id AS company_group_id FROM {CHARGEBACK} "
            f"WHERE situacao_do_estorno = 'CONCLUDED' LIMIT 10"
        )


# ------------------------------------------- colunas de saída não filtráveis --


@pytest.mark.parametrize("column", ["name", "email", "cpf"])
def test_employee_rejects_filter_by_personal_field(column):
    with pytest.raises(ColumnNotFilterableError):
        guard(
            f"SELECT c.company_group_id AS company_group_id, "
            f"e.{column} AS campo "
            f"FROM {EMPLOYEE} e "
            f"INNER JOIN {COMPANIES} c ON e.company_id = c.company_id "
            f"WHERE e.{column} = 'x' LIMIT 10"
        )


def test_employee_rejects_unqualified_personal_filter():
    with pytest.raises(ColumnNotFilterableError):
        guard(
            f"SELECT c.company_group_id AS company_group_id, "
            f"e.name AS nome_colaborador "
            f"FROM {EMPLOYEE} e "
            f"INNER JOIN {COMPANIES} c ON e.company_id = c.company_id "
            f"WHERE name = 'João' LIMIT 10"
        )


def test_employee_accepts_filter_by_person_id():
    sql = guard(
        f"SELECT c.company_group_id AS company_group_id, "
        f"e.name AS nome_colaborador "
        f"FROM {EMPLOYEE} e "
        f"INNER JOIN {COMPANIES} c ON e.company_id = c.company_id "
        f"WHERE e.person_id = '550e8400-e29b-41d4-a716-446655440000' LIMIT 10"
    )

    assert "person_id" in sql
    assert "c.company_group_id = '" + GROUP + "'" in sql


def test_cte_with_valid_columns_has_no_false_positive():
    assert guard(
        f"WITH estornos AS ("
        f"  SELECT ch.id AS id_estorno, ch.group_id AS company_group_id "
        f"  FROM {CHARGEBACK} ch"
        f") SELECT id_estorno, company_group_id FROM estornos LIMIT 10"
    )


# --------------------------------------------------------- chave de JOIN --


def test_join_by_declared_key_passes():
    assert guard(
        f"SELECT c.company_group_id AS company_group_id, e.email AS email "
        f"FROM {EMPLOYEE} e "
        f"INNER JOIN {COMPANIES} c ON e.company_id = c.company_id LIMIT 10"
    )


def test_join_by_undeclared_key_is_rejected():
    with pytest.raises(JoinKeyError) as error:
        guard(
            f"SELECT c.company_group_id AS company_group_id, e.email AS email "
            f"FROM {EMPLOYEE} e "
            f"INNER JOIN {COMPANIES} c ON e.id = c.company_id LIMIT 10"
        )

    message = str(error.value)
    assert "employee.company_id = companies.company_id" in message


def test_financial_transaction_join_by_account_passes():
    assert guard(
        f"SELECT ft.id AS id_transacao, fa.group_id AS company_group_id "
        f"FROM {FIN_TRANSACTION} ft "
        f"INNER JOIN {FIN_ACCOUNT} fa ON ft.account_id = fa.id LIMIT 10"
    )


def test_join_with_extra_condition_stays_valid():
    assert guard(
        f"SELECT c.company_group_id AS company_group_id, e.email AS email "
        f"FROM {EMPLOYEE} e "
        f"INNER JOIN {COMPANIES} c "
        f"  ON e.company_id = c.company_id AND c.deleted = false LIMIT 10"
    )


def test_join_between_tables_without_declared_link_is_rejected():
    with pytest.raises(JoinKeyError, match="não declara ligação direta"):
        guard(
            f"SELECT ch.group_id AS company_group_id, e.email AS email "
            f"FROM {CHARGEBACK} ch "
            f"INNER JOIN {EMPLOYEE} e ON ch.company_id = e.company_id LIMIT 10"
        )
