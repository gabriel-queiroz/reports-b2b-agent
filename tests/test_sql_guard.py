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

GRUPO = "550e8400-e29b-41d4-a716-446655440000"

EMPLOYEE = "main.ifoodoffice_management_silver.employee"
COMPANIES = "fintech_companies.companies"
RECARGAS = "main.fintech_finance.ifood_benefits_recharges"
CHARGEBACK = "main.ifoodoffice_recharge_chargeback.chargeback"
FIN_ACCOUNT = "main.ifood_benf_transaction_service.financial_account"
FIN_TRANSACTION = "main.ifood_benf_transaction_service.financial_transaction"


def guard(sql: str) -> str:
    return guard_query(sql, GRUPO)


def filtro_no_topo(sql: str, coluna: str) -> bool:
    """O predicado está na conjunção de topo do WHERE deste SELECT?"""
    from domain.agents.reports_b2b.sql_guard import _top_level_conjuncts
    from sqlglot import exp

    alvo = f"{coluna} = '{GRUPO}'".lower()
    for select in sqlglot.parse_one(sql, dialect=DIALECT).find_all(exp.Select):
        where = select.args.get("where")
        if where is None:
            continue
        if any(
            c.sql(dialect=DIALECT).lower() == alvo
            for c in _top_level_conjuncts(where.this)
        ):
            return True
    return False


def executavel(sql: str) -> bool:
    """O SQL devolvido volta a fazer parse — o bug do GROUP BY quebrava isto."""
    try:
        sqlglot.parse_one(sql, dialect=DIALECT)
    except sqlglot.ParseError:
        return False
    return True


# ------------------------------------------------- bugs do injetor antigo --


def test_filtro_entra_no_where_e_nao_depois_do_group_by():
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

    assert executavel(sql)
    assert filtro_no_topo(sql, "c.company_group_id")
    assert sql.index("WHERE") < sql.index("GROUP BY") < sql.index("LIMIT")


def test_filtro_nao_cai_dentro_de_um_ramo_de_or():
    """`WHERE a OR b` + AND cru vira `a OR (b AND filtro)` — não filtra nada."""
    sql = guard(
        f"SELECT c.company_group_id AS company_group_id, e.email AS email "
        f"FROM {EMPLOYEE} e "
        f"INNER JOIN {COMPANIES} c ON e.company_id = c.company_id "
        f"WHERE e.deleted = false OR e.person_id = '550e8400-e29b-41d4-a716-446655440001' "
        f"LIMIT 1000"
    )

    assert filtro_no_topo(sql, "c.company_group_id")
    assert (
        "(e.deleted = FALSE OR e.person_id = '550e8400-e29b-41d4-a716-446655440001')"
        in sql
    )


def test_filtro_dentro_de_or_nao_conta_como_filtro_valido():
    """O regex aceitava o UUID em qualquer lugar do texto, inclusive num OR."""
    sql = guard(
        f"SELECT c.company_group_id AS company_group_id, e.email AS email "
        f"FROM {EMPLOYEE} e "
        f"INNER JOIN {COMPANIES} c ON e.company_id = c.company_id "
        f"WHERE c.company_group_id = '{GRUPO}' OR e.person_id = '550e8400-e29b-41d4-a716-446655440001' "
        f"LIMIT 1000"
    )

    # o OR continua lá, mas agora dentro de um AND com o filtro real
    assert filtro_no_topo(sql, "c.company_group_id")
    assert sql.count(GRUPO) == 2


def test_where_apenas_na_subquery_nao_deixa_o_escopo_externo_sem_filtro():
    sql = guard(
        f"SELECT x.company_group_id AS company_group_id, x.email AS email FROM ("
        f"  SELECT c.company_group_id, e.email FROM {EMPLOYEE} e"
        f"  INNER JOIN {COMPANIES} c ON e.company_id = c.company_id"
        f"  WHERE e.deleted = false"
        f") x LIMIT 1000"
    )

    # o escopo que lê a tabela base é o de dentro — é lá que o filtro precisa estar
    assert filtro_no_topo(sql, "c.company_group_id")
    assert executavel(sql)


def test_predicado_nao_cai_no_on_do_left_join():
    sql = guard(
        f"SELECT c.company_group_id AS company_group_id, e.email AS email "
        f"FROM {EMPLOYEE} e "
        f"LEFT JOIN {COMPANIES} c ON e.company_id = c.company_id "
        f"LIMIT 1000"
    )

    assert filtro_no_topo(sql, "c.company_group_id")
    assert "ON e.company_id = c.company_id AND" not in sql


def test_join_sem_alias_usa_o_nome_da_tabela_e_nao_a_palavra_on():
    """`_extract_companies_table_alias` devolvia `"ON"` neste caso."""
    sql = guard(
        f"SELECT companies.company_group_id AS company_group_id "
        f"FROM {EMPLOYEE} e "
        f"INNER JOIN {COMPANIES} ON e.company_id = companies.company_id "
        f"LIMIT 1000"
    )

    assert filtro_no_topo(sql, "companies.company_group_id")
    assert "ON.company_group_id" not in sql


def test_join_com_condicao_sem_colunas_e_recusado():
    """`ON 1 = 1` não liga tabela a tabela e não pode virar JOIN de catálogo."""
    with pytest.raises(JoinKeyError):
        guard(
            f"SELECT c.company_group_id AS company_group_id, e.email AS email "
            f"FROM {EMPLOYEE} e "
            f"INNER JOIN {COMPANIES} c ON 1 = 1 "
            f"LIMIT 1000"
        )


def test_cross_join_sem_chave_e_recusado():
    """CROSS JOIN não tem chave de catálogo e precisa ser rejeitado."""
    with pytest.raises(JoinKeyError):
        guard(
            f"SELECT c.company_group_id AS company_group_id, e.email AS email "
            f"FROM {EMPLOYEE} e "
            f"CROSS JOIN {COMPANIES} c "
            f"LIMIT 1000"
        )


def test_recargas_sem_filtro_de_grupo_recebe_o_filtro_do_struct():
    """Buraco conhecido: o domínio de recargas pulava a injeção por inteiro."""
    sql = guard(
        f"SELECT r.order_id AS id_recarga, r.company_group.id AS company_group_id "
        f"FROM {RECARGAS} r "
        f"WHERE r.update_month >= '2026-07' "
        f"LIMIT 1000"
    )

    assert filtro_no_topo(sql, "r.company_group.id")


# --------------------------------------------- agregação de medidas na recarga --


def test_recarga_amount_cru_sem_order_item_id_e_recusado():
    """No nível empresa, `amount` cru (sem SUM) é campo de item — precisa agregar."""
    with pytest.raises(RechargesAggregationError):
        guard(
            f"SELECT r.company_group.id AS company_group_id, r.order_id AS id_recarga, "
            f"r.amount AS valor_item_recarga "
            f"FROM {RECARGAS} r WHERE r.order_status = 'DISTRIBUTION_COMPLETE'"
        )


def test_recarga_cashback_cru_sem_order_item_id_e_recusado():
    with pytest.raises(RechargesAggregationError):
        guard(
            f"SELECT r.company_group.id AS company_group_id, r.order_id AS id_recarga, "
            f"r.cashback_amount AS valor_cashback_item "
            f"FROM {RECARGAS} r"
        )


def test_recarga_sum_mais_group_by_e_aceito():
    sql = guard(
        f"SELECT r.company_group.id AS company_group_id, r.order_id AS id_recarga, "
        f"SUM(r.amount) AS valor_recarga, SUM(r.cashback_amount) AS valor_cashback "
        f"FROM {RECARGAS} r "
        f"WHERE r.order_status = 'DISTRIBUTION_COMPLETE' "
        f"GROUP BY r.company_group.id, r.order_id"
    )

    assert "SUM(r.amount)" in sql
    assert "GROUP BY" in sql


def test_recarga_item_level_com_order_item_id_e_aceito():
    """Com `order_item_id` na saída, é granularidade de item — amount cru é legítimo."""
    sql = guard(
        f"SELECT r.company_group.id AS company_group_id, r.order_item_id AS id_item_recarga, "
        f"r.order_id AS id_recarga, r.amount AS valor_item_recarga "
        f"FROM {RECARGAS} r"
    )

    assert "r.amount" in sql


def test_recarga_amount_cru_dentro_de_split_com_order_item_id_e_aceito():
    """`order_item_id` dentro de função (split) também marca granularidade de item."""
    sql = guard(
        f"SELECT r.company_group.id AS company_group_id, "
        f"CAST(CONCAT('ID_', split(r.order_item_id, '-')[3]) AS STRING) AS id_item, "
        f"r.amount AS valor_item_recarga "
        f"FROM {RECARGAS} r"
    )

    assert "r.amount" in sql


def test_amount_de_outra_tabela_cru_nao_e_sinalizado():
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
def test_dois_statements_sao_recusados(sql):
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
def test_dml_e_ddl_sao_recusados(sql):
    with pytest.raises(StatementNotAllowedError):
        guard(sql)


def test_sql_invalido_e_recusado_com_erro_de_sintaxe():
    with pytest.raises(SqlSyntaxError):
        guard("SELEC company_group_id FROM WHERE")


def test_comentario_nao_sobrevive_ao_guard():
    """O SQL entregue é regerado da AST; comentário do LLM não viaja junto."""
    sql = guard(
        f"SELECT c.company_group_id AS company_group_id -- comentário\n"
        f"FROM {COMPANIES} c WHERE c.deleted = false LIMIT 10"
    )

    assert "--" not in sql and "/*" not in sql


def test_sql_devolvido_vem_da_ast_nao_da_string_do_llm():
    sql = guard(
        f"select   c.company_group_id   as company_group_id\n\n"
        f"from {COMPANIES} c   where c.deleted = false   limit 10"
    )

    assert sql.startswith("SELECT c.company_group_id AS company_group_id FROM")
    assert "\n" not in sql


# ----------------------------------------------------------------- LIMIT --


def test_query_sem_limit_continua_sem_limit():
    """Não há teto: o relatório traz o recorte inteiro e o guard não injeta nada."""
    sql = guard(f"SELECT c.company_group_id AS company_group_id FROM {COMPANIES} c")

    assert "LIMIT" not in sql.upper()


def test_limit_pedido_pelo_usuario_e_preservado():
    """ "as 10 maiores" continua sendo uma pergunta legítima."""
    sql = guard(
        f"SELECT c.company_group_id AS company_group_id FROM {COMPANIES} c LIMIT 10"
    )

    assert sql.endswith("LIMIT 10")


def test_limit_grande_nao_e_reduzido():
    sql = guard(
        f"SELECT c.company_group_id AS company_group_id FROM {COMPANIES} c LIMIT 50000"
    )

    assert sql.endswith("LIMIT 50000")


# ------------------------------------------------------------- allowlist --


def test_tabela_fora_do_catalogo_e_recusada():
    with pytest.raises(TableNotAllowedError, match="information_schema.tables"):
        guard(
            "SELECT t.company_group_id AS company_group_id "
            "FROM information_schema.tables t LIMIT 10"
        )


def test_chargeback_employee_sem_join_com_chargeback_e_recusada():
    """`chargeback_employee` só filtra por grupo via JOIN com `chargeback`."""
    with pytest.raises(TenantFilterError):
        guard(
            "SELECT ce.employee_id AS id_colaborador, ce.chargeback_id "
            "FROM main.ifoodoffice_recharge_chargeback.chargeback_employee ce "
            "LIMIT 10"
        )


def test_nome_curto_de_tabela_permitida_passa():
    sql = guard(
        "SELECT c.company_group_id AS company_group_id FROM companies c LIMIT 10"
    )
    assert filtro_no_topo(sql, "c.company_group_id")


def test_tabela_homonima_em_outro_catalogo_e_recusada():
    with pytest.raises(TableNotAllowedError):
        guard(
            "SELECT e.company_group_id AS company_group_id "
            "FROM outro_catalogo.employee e LIMIT 10"
        )


def test_tabela_dentro_de_cte_tambem_passa_pela_allowlist():
    with pytest.raises(TableNotAllowedError):
        guard(
            "WITH x AS (SELECT * FROM information_schema.tables) "
            "SELECT x.company_group_id AS company_group_id FROM x LIMIT 10"
        )


# ------------------------------------------------- JOIN obrigatório / tenant --


def test_employee_sozinho_exige_join_com_companies():
    with pytest.raises(TenantFilterError, match="employee"):
        guard(
            f"SELECT e.email AS email, e.company_id AS company_group_id "
            f"FROM {EMPLOYEE} e WHERE e.deleted = false LIMIT 10"
        )


def test_financial_transaction_sozinha_exige_join_com_financial_account():
    with pytest.raises(TenantFilterError, match="financial_account"):
        guard(
            f"SELECT ft.id AS id, ft.account_id AS company_group_id "
            f"FROM {FIN_TRANSACTION} ft LIMIT 10"
        )


def test_financial_transaction_com_join_filtra_pela_conta():
    sql = guard(
        f"SELECT ft.id AS id_transacao, fa.group_id AS company_group_id "
        f"FROM {FIN_TRANSACTION} ft "
        f"INNER JOIN {FIN_ACCOUNT} fa ON ft.account_id = fa.id "
        f"LIMIT 1000"
    )

    assert filtro_no_topo(sql, "fa.group_id")


def test_chargeback_filtra_por_group_id_direto_sem_join():
    sql = guard(
        f"SELECT ch.id AS id_estorno, ch.group_id AS company_group_id "
        f"FROM {CHARGEBACK} ch LIMIT 1000"
    )

    assert filtro_no_topo(sql, "ch.group_id")


def test_filtro_correto_do_llm_e_preservado_sem_duplicar():
    sql = guard(
        f"SELECT ch.id AS id_estorno, ch.group_id AS company_group_id "
        f"FROM {CHARGEBACK} ch WHERE ch.group_id = '{GRUPO}' LIMIT 1000"
    )

    assert sql.count(GRUPO) == 1


def test_guard_e_idempotente():
    sql = (
        f"SELECT c.company_group_id AS company_group_id FROM {COMPANIES} c "
        f"WHERE c.deleted = false LIMIT 10"
    )
    uma_vez = guard(sql)
    assert guard(uma_vez) == uma_vez


def test_union_filtra_os_dois_ramos():
    sql = guard(
        f"SELECT ch.group_id AS company_group_id FROM {CHARGEBACK} ch "
        f"UNION ALL "
        f"SELECT c.company_group_id AS company_group_id FROM {COMPANIES} c"
    )

    assert filtro_no_topo(sql, "ch.group_id")
    assert filtro_no_topo(sql, "c.company_group_id")


def test_group_id_invalido_nao_gera_sql():
    with pytest.raises(InvalidGroupIdError):
        guard_query(
            f"SELECT c.company_group_id AS company_group_id FROM {COMPANIES} c",
            "unknown",
        )


# ------------------------------------------------ coluna de saída do grupo --


def test_select_sem_company_group_id_e_recusado():
    with pytest.raises(OutputColumnError):
        guard(
            f"SELECT c.social_name AS razao_social_empresa FROM {COMPANIES} c LIMIT 10"
        )


def test_literal_nao_serve_como_coluna_de_grupo():
    with pytest.raises(OutputColumnError):
        guard(
            f"SELECT '{GRUPO}' AS company_group_id, c.social_name AS razao_social "
            f"FROM {COMPANIES} c LIMIT 10"
        )


def test_coluna_sem_alias_ja_sai_com_o_nome_certo():
    sql = guard(f"SELECT c.company_group_id FROM {COMPANIES} c LIMIT 10")
    assert filtro_no_topo(sql, "c.company_group_id")
