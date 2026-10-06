"""Fase 5 — `list_fields` monta a lista do catálogo, em vez de despejar o arquivo."""

import pytest
from domain.agents.reports_b2b.catalog import find_table, load_catalog, tables_dir
from domain.agents.reports_b2b.schema_extractor import extract_tables_by_domain
from domain.agents.reports_b2b.tools.list_fields import list_fields

DOMAINS = ["colaboradores", "recargas", "financeiro", "estorno_recarga"]


def list_tables(domain: str) -> str:
    return list_fields.func(domain)


@pytest.mark.parametrize("domain", DOMAINS)
def test_response_is_field_list_not_whole_schema(domain):
    output = list_tables(domain)
    schema = "".join(
        file.read_text(encoding="utf-8") for file in tables_dir().glob("*.md")
    )

    assert len(output) < len(schema) / 10
    assert "<schema_documentation>" not in output
    assert "**Local**" not in output


@pytest.mark.parametrize("domain", DOMAINS)
def test_uses_display_column_not_technical_alias(domain):
    output = list_tables(domain)

    assert "- Razão Social" in output
    assert "data_criacao" not in output
    assert "company_group_id" not in output


def test_financial_includes_account_and_transaction():
    """`DOMAIN_MARKERS["financeiro"]` não citava nenhuma das duas."""
    output = list_tables("financeiro")

    assert "Financial Account" in output
    assert "Financial Transaction" in output
    assert "Company Tax Invoice" in output
    assert "Receivable Assets" in output


def test_recharge_chargeback_includes_chargebacks():
    """Estorno de recarga é domínio independente — não entra em recargas."""
    output = list_tables("estorno_recarga")

    assert "Chargeback (Estornos)" in output
    assert "Chargeback Employee (Estorno por Colaborador)" in output
    assert "Chargeback (Estornos)" not in list_tables("recargas")


def test_employees_offers_output_but_not_person_id_as_field():
    output = list_tables("colaboradores")

    assert "Nome" in output
    assert "Email" in output
    assert "CPF" in output
    assert "ID Usuário iFB" not in output


def test_whole_struct_is_not_offered_as_field():
    """O catálogo é explícito: nunca selecionar o struct inteiro."""
    recharges = load_catalog()["ifood_benefits_recharges"]
    structs = [c for c in recharges.columns if c.type.upper() == "STRUCT"]
    assert structs, "o catálogo deveria documentar structs nesta tabela"

    offered = list_tables("recargas").count("\n- ")
    cataloged = sum(
        1
        for table_path in extract_tables_by_domain()["recargas"]
        for column in find_table(table_path).columns
        if column.display and column.type.upper() != "STRUCT"
    )

    assert offered == cataloged


def test_recharges_listed_grouped_by_recharge_and_item():
    output = list_tables("recargas")

    assert "**Recarga (granularidade de empresa)**" in output
    assert "**Detalhes da Recarga (granularidade de colaborador)**" in output
    assert output.index("**Recarga (granularidade de empresa)**") < output.index(
        "**Detalhes da Recarga (granularidade de colaborador)**"
    )


def test_domain_without_catalog_responds_without_crashing():
    assert "não há domínio" in list_tables("inexistente").lower()
