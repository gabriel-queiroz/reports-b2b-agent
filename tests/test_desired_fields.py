"""Resolução de `desired_fields` contra o catálogo.

`desired_fields="all"` resolve o nível empresa nos domínios multi-nível: exclui a
identidade de item/detalhe e a tabela transversal `companies`, mantendo as medidas
(`amount`/`cashback_amount`) que entram como `SUM` no nível empresa.
"""

from domain.agents.reports_b2b.schema_extractor import (
    build_requested_fields_block,
    resolve_desired_fields,
)


def names(pairs) -> set[str]:
    """Nomes físicos das colunas resolvidas, para asserções curtas."""
    return {f"{table.name}.{column.name}" for table, column in pairs}


# ------------------------------------------------- "all" = nível empresa + medidas --


def test_all_in_recharges_resolves_company_level_and_measures():
    """`amount`/`cashback_amount` entram como medidas; a identidade do item
    (order_item_id/product_key/employee_id/person_id/company.*) fica fora."""
    pairs = resolve_desired_fields("recargas", "all")

    assert {
        "ifood_benefits_recharges.order_id",
        "ifood_benefits_recharges.order_status",
        "ifood_benefits_recharges.order_info.payment_method",
        "ifood_benefits_recharges.amount",
        "ifood_benefits_recharges.cashback_amount",
    }.issubset(names(pairs))

    assert {
        "ifood_benefits_recharges.order_item_id",
        "ifood_benefits_recharges.order_item_status",
        "ifood_benefits_recharges.product_key",
        "ifood_benefits_recharges.employee_id",
        "ifood_benefits_recharges.person_id",
        "ifood_benefits_recharges.company.id",
        "ifood_benefits_recharges.company.name",
    }.isdisjoint(names(pairs))


def test_all_in_chargeback_resolves_company_level_only():
    pairs = resolve_desired_fields("estorno_recarga", "all")

    assert {
        "chargeback.id",
        "chargeback.total_amount_requested",
    }.issubset(names(pairs))
    assert {
        "chargeback_employee.tax_id",
        "chargeback_employee.reason",
    }.isdisjoint(names(pairs))


def test_all_excludes_cross_cutting_companies_table():
    """`companies` não é campo de relatório default em domínio nenhum."""
    for domain in ("colaboradores", "recargas", "financeiro", "estorno_recarga"):
        pairs = resolve_desired_fields(domain, "all")
        assert all(table.name != "companies" for table, _ in pairs), domain


# --------------------------------------- campos explícitos --


def test_explicit_companies_field_still_resolves():
    """Pedir 'Razão Social' continua trazendo a coluna da transversal."""
    pairs = resolve_desired_fields("colaboradores", "Razão Social")
    assert names(pairs) == {"companies.social_name"}


def test_explicit_detail_field_still_resolves():
    pairs = resolve_desired_fields("recargas", "Valor da Recarga")
    assert names(pairs) == {"ifood_benefits_recharges.amount"}


def test_item_block_does_not_aggregate_amount():
    """Pedir 'ID Item Recarga, Valor da Recarga' (nível item) deixa amount cru."""
    block = build_requested_fields_block(
        "recargas", "ID Item Recarga, Valor da Recarga"
    )

    assert "`ifood_benefits_recharges.order_item_id`" in block
    assert "`ifood_benefits_recharges.amount` AS `valor_item_recarga`" in block
    assert "SUM(" not in block
    assert "GROUP BY" not in block


def test_explicit_chargeback_detail_field_still_resolves():
    pairs = resolve_desired_fields("estorno_recarga", "Motivo Estorno")
    assert names(pairs) == {"chargeback_employee.reason"}


# ------------------------------------------------- bloco do prompt --


def test_recharges_all_block_lists_fields_and_aggregates_measures():
    block = build_requested_fields_block("recargas", "all")

    # campos do nível recarga aparecem; medidas viram SUM
    assert "order_id" in block
    assert "id_recarga" in block
    assert "SUM(" in block
    assert "valor_recarga" in block
    assert "valor_cashback" in block
    assert "GROUP BY" in block

    # identidade de item não entra no nível empresa
    assert "order_item_id" not in block
    assert "product_key" not in block

    assert "company_group_id" in block
