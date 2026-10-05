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

GRUPO = "550e8400-e29b-41d4-a716-446655440000"

EMPLOYEE = "main.ifoodoffice_management_silver.employee"
COMPANIES = "fintech_companies.companies"
RECARGAS = "main.fintech_finance.ifood_benefits_recharges"
CHARGEBACK = "main.ifoodoffice_recharge_chargeback.chargeback"
FIN_ACCOUNT = "main.ifood_benf_transaction_service.financial_account"
FIN_TRANSACTION = "main.ifood_benf_transaction_service.financial_transaction"


def guard(sql: str) -> str:
    return guard_query(sql, GRUPO)


# ------------------------------------------------- alias PT-BR como coluna --


def test_alias_ptbr_no_where_e_recusado_nomeando_a_coluna_real():
    """O exemplo do PLANO: `id_estorno` não existe; a coluna é `id`."""
    with pytest.raises(AliasAsColumnError) as erro:
        guard(
            f"SELECT ch.id AS id_estorno, ch.group_id AS company_group_id "
            f"FROM {CHARGEBACK} ch WHERE ch.id_estorno = 'x' LIMIT 10"
        )

    mensagem = str(erro.value)
    assert "id_estorno" in mensagem
    assert "chargeback.id" in mensagem


def test_alias_ptbr_multilinha_tambem_e_pego():
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


def test_alias_ptbr_depois_de_as_e_uso_correto():
    sql = guard(
        f"SELECT ch.id AS id_estorno, ch.group_id AS company_group_id "
        f"FROM {CHARGEBACK} ch LIMIT 10"
    )
    assert "AS id_estorno" in sql


def test_alias_de_saida_pode_ser_usado_no_order_by():
    """Spark resolve alias de saída em ORDER BY — não é erro."""
    sql = guard(
        f"SELECT ch.id AS id_estorno, ch.group_id AS company_group_id "
        f"FROM {CHARGEBACK} ch ORDER BY id_estorno LIMIT 10"
    )
    assert "ORDER BY id_estorno" in sql


def test_alias_nao_declarado_no_order_by_e_recusado():
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
def test_query_correta_nao_e_mais_reprovada(sql):
    assert guard(sql)


# ------------------------------------------------------ coluna inexistente --


def test_coluna_inventada_e_recusada_com_sugestao():
    with pytest.raises(ColumnNotFoundError) as erro:
        guard(
            f"SELECT ch.chargeback_id AS id, ch.group_id AS company_group_id "
            f"FROM {CHARGEBACK} ch LIMIT 10"
        )

    mensagem = str(erro.value)
    assert "chargeback_id" in mensagem
    assert "chargeback" in mensagem


def test_coluna_da_tabela_errada_e_recusada():
    """`company_group_id` existe em companies, não em employee."""
    with pytest.raises(ColumnNotFoundError, match="employee"):
        guard(
            f"SELECT e.company_group_id AS company_group_id "
            f"FROM {EMPLOYEE} e "
            f"INNER JOIN {COMPANIES} c ON e.company_id = c.company_id LIMIT 10"
        )


def test_campo_de_struct_valido_passa():
    assert guard(
        f"SELECT r.company_group.id AS company_group_id, "
        f"r.order_info.payment_method AS metodo_pagamento_recarga_info "
        f"FROM {RECARGAS} r LIMIT 10"
    )


def test_campo_de_struct_inventado_e_recusado():
    with pytest.raises(ColumnNotFoundError):
        guard(
            f"SELECT r.company_group.id AS company_group_id, "
            f"r.company_group.uuid AS uuid FROM {RECARGAS} r LIMIT 10"
        )


def test_coluna_sem_qualificador_e_resolvida_contra_o_escopo():
    assert guard(
        f"SELECT group_id AS company_group_id, chargeback_status AS situacao "
        f"FROM {CHARGEBACK} WHERE chargeback_status = 'CONCLUDED' LIMIT 10"
    )


def test_coluna_sem_qualificador_inexistente_e_recusada():
    with pytest.raises(ColumnNotFoundError):
        guard(
            f"SELECT group_id AS company_group_id FROM {CHARGEBACK} "
            f"WHERE situacao_do_estorno = 'CONCLUDED' LIMIT 10"
        )


# ------------------------------------------- colunas de saída não filtráveis --


@pytest.mark.parametrize("coluna", ["name", "email", "cpf"])
def test_employee_nao_aceita_filtro_por_campo_pessoal(coluna):
    with pytest.raises(ColumnNotFilterableError):
        guard(
            f"SELECT c.company_group_id AS company_group_id, "
            f"e.{coluna} AS campo "
            f"FROM {EMPLOYEE} e "
            f"INNER JOIN {COMPANIES} c ON e.company_id = c.company_id "
            f"WHERE e.{coluna} = 'x' LIMIT 10"
        )


def test_employee_nao_aceita_filtro_pessoal_sem_qualificador():
    with pytest.raises(ColumnNotFilterableError):
        guard(
            f"SELECT c.company_group_id AS company_group_id, "
            f"e.name AS nome_colaborador "
            f"FROM {EMPLOYEE} e "
            f"INNER JOIN {COMPANIES} c ON e.company_id = c.company_id "
            f"WHERE name = 'João' LIMIT 10"
        )


def test_employee_aceita_filtro_por_person_id():
    sql = guard(
        f"SELECT c.company_group_id AS company_group_id, "
        f"e.name AS nome_colaborador "
        f"FROM {EMPLOYEE} e "
        f"INNER JOIN {COMPANIES} c ON e.company_id = c.company_id "
        f"WHERE e.person_id = '550e8400-e29b-41d4-a716-446655440000' LIMIT 10"
    )

    assert "person_id" in sql
    assert "c.company_group_id = '" + GRUPO + "'" in sql


def test_cte_com_colunas_validas_nao_gera_falso_positivo():
    assert guard(
        f"WITH estornos AS ("
        f"  SELECT ch.id AS id_estorno, ch.group_id AS company_group_id "
        f"  FROM {CHARGEBACK} ch"
        f") SELECT id_estorno, company_group_id FROM estornos LIMIT 10"
    )


# --------------------------------------------------------- chave de JOIN --


def test_join_por_chave_declarada_passa():
    assert guard(
        f"SELECT c.company_group_id AS company_group_id, e.email AS email "
        f"FROM {EMPLOYEE} e "
        f"INNER JOIN {COMPANIES} c ON e.company_id = c.company_id LIMIT 10"
    )


def test_join_por_chave_nao_declarada_e_recusado():
    with pytest.raises(JoinKeyError) as erro:
        guard(
            f"SELECT c.company_group_id AS company_group_id, e.email AS email "
            f"FROM {EMPLOYEE} e "
            f"INNER JOIN {COMPANIES} c ON e.id = c.company_id LIMIT 10"
        )

    mensagem = str(erro.value)
    assert "employee.company_id = companies.company_id" in mensagem


def test_join_de_financial_transaction_pela_conta_passa():
    assert guard(
        f"SELECT ft.id AS id_transacao, fa.group_id AS company_group_id "
        f"FROM {FIN_TRANSACTION} ft "
        f"INNER JOIN {FIN_ACCOUNT} fa ON ft.account_id = fa.id LIMIT 10"
    )


def test_join_com_condicao_extra_continua_valido():
    assert guard(
        f"SELECT c.company_group_id AS company_group_id, e.email AS email "
        f"FROM {EMPLOYEE} e "
        f"INNER JOIN {COMPANIES} c "
        f"  ON e.company_id = c.company_id AND c.deleted = false LIMIT 10"
    )


def test_join_entre_tabelas_sem_ligacao_declarada_e_recusado():
    with pytest.raises(JoinKeyError, match="não declara ligação direta"):
        guard(
            f"SELECT ch.group_id AS company_group_id, e.email AS email "
            f"FROM {CHARGEBACK} ch "
            f"INNER JOIN {EMPLOYEE} e ON ch.company_id = e.company_id LIMIT 10"
        )
