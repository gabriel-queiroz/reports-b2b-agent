"""Resolução de `desired_fields` contra o catálogo.

`desired_fields="all"` resolve o nível empresa nos domínios multi-nível: exclui a
identidade de item/detalhe e a tabela transversal `companies`, mantendo as medidas
(`amount`/`cashback_amount`) que entram como `SUM` no nível empresa.
"""

from domain.agents.reports_b2b.schema_extractor import (
    build_campos_solicitados_block,
    resolve_desired_fields,
)


def nomes(pares) -> set[str]:
    """Nomes físicos das colunas resolvidas, para asserções curtas."""
    return {f"{tabela.name}.{coluna.name}" for tabela, coluna in pares}


# ------------------------------------------------- "all" = nível empresa + medidas --


def test_all_em_recargas_resolve_nivel_empresa_e_medidas():
    """`amount`/`cashback_amount` entram como medidas; a identidade do item
    (order_item_id/product_key/employee_id/person_id/company.*) fica fora."""
    pares = resolve_desired_fields("recargas", "all")

    assert {
        "ifood_benefits_recharges.order_id",
        "ifood_benefits_recharges.order_status",
        "ifood_benefits_recharges.order_info.payment_method",
        "ifood_benefits_recharges.amount",
        "ifood_benefits_recharges.cashback_amount",
    }.issubset(nomes(pares))

    assert {
        "ifood_benefits_recharges.order_item_id",
        "ifood_benefits_recharges.order_item_status",
        "ifood_benefits_recharges.product_key",
        "ifood_benefits_recharges.employee_id",
        "ifood_benefits_recharges.person_id",
        "ifood_benefits_recharges.company.id",
        "ifood_benefits_recharges.company.name",
    }.isdisjoint(nomes(pares))


def test_all_em_estorno_resolve_so_empresa():
    pares = resolve_desired_fields("estorno_recarga", "all")

    assert {
        "chargeback.id",
        "chargeback.total_amount_requested",
    }.issubset(nomes(pares))
    assert {
        "chargeback_employee.tax_id",
        "chargeback_employee.reason",
    }.isdisjoint(nomes(pares))


def test_all_nao_inclui_tabela_transversal_companies():
    """`companies` não é campo de relatório default em domínio nenhum."""
    for domain in ("colaboradores", "recargas", "financeiro", "estorno_recarga"):
        pares = resolve_desired_fields(domain, "all")
        assert all(tabela.name != "companies" for tabela, _ in pares), domain


# --------------------------------------- campos explícitos --


def test_campo_de_companies_explicito_ainda_resolve():
    """Pedir 'Razão Social' continua trazendo a coluna da transversal."""
    pares = resolve_desired_fields("colaboradores", "Razão Social")
    assert nomes(pares) == {"companies.social_name"}


def test_campo_de_detalhe_explicito_ainda_resolve():
    pares = resolve_desired_fields("recargas", "Valor da Recarga")
    assert nomes(pares) == {"ifood_benefits_recharges.amount"}


def test_bloco_de_item_nao_agrega_amount():
    """Pedir 'ID Item Recarga, Valor da Recarga' (nível item) deixa amount cru."""
    bloco = build_campos_solicitados_block(
        "recargas", "ID Item Recarga, Valor da Recarga"
    )

    assert "`ifood_benefits_recharges.order_item_id`" in bloco
    assert "`ifood_benefits_recharges.amount` AS `valor_item_recarga`" in bloco
    assert "SUM(" not in bloco
    assert "GROUP BY" not in bloco


def test_campo_de_detalhe_de_estorno_explicito_ainda_resolve():
    pares = resolve_desired_fields("estorno_recarga", "Motivo Estorno")
    assert nomes(pares) == {"chargeback_employee.reason"}


# ------------------------------------------------- bloco do prompt --


def test_bloco_all_de_recargas_lista_campos_e_agrega_medidas():
    bloco = build_campos_solicitados_block("recargas", "all")

    # campos do nível recarga aparecem; medidas viram SUM
    assert "order_id" in bloco
    assert "id_recarga" in bloco
    assert "SUM(" in bloco
    assert "valor_recarga" in bloco
    assert "valor_cashback" in bloco
    assert "GROUP BY" in bloco

    # identidade de item não entra no nível empresa
    assert "order_item_id" not in bloco
    assert "product_key" not in bloco

    assert "company_group_id" in bloco
