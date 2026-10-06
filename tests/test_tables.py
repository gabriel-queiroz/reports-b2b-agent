"""Catálogo em `data/tabelas/`: um arquivo por tabela, schema sob demanda.

O prompt leva só o índice (nomes + relacionamentos); o resto de cada tabela
chega pela tool `get_table_schema`. Estes testes travam o contrato da pasta e o
que cada um desses textos pode — e não pode — conter.
"""

import re

from domain.agents.reports_b2b.catalog import (
    allowed_tables,
    is_declared_join,
    load_catalog,
    table_files,
)
from domain.agents.reports_b2b.schema_extractor import (
    build_tables_index,
    extract_tables_by_domain,
    table_doc,
)
from domain.agents.reports_b2b.tools.get_table_schema import get_table_schema

_SQL_TYPE = re.compile(r"[A-Z][A-Z0-9_]*(<.+>)?")


def test_one_file_per_table_with_physical_name():
    """Arquivo sem tabela, com duas tabelas ou com nome trocado quebra aqui."""
    assert sorted(file.stem for file in table_files()) == sorted(load_catalog())


def test_every_column_has_sql_type():
    """Tabela markdown fora da seção de colunas vira coluna fantasma.

    No `schema.md` único, o cabeçalho da tabela de cenários de faturamento
    virava a coluna `Cenário` (tipo "Pagamento (PIX/boleto)") de
    `financial_transaction`, e o `list_fields` oferecia "Efeito no cruzamento".
    """
    for table in load_catalog().values():
        for column in table.columns:
            assert _SQL_TYPE.fullmatch(column.type), (
                f"{table.name}.{column.name} tem tipo {column.type!r}"
            )


def test_financial_transaction_without_phantom_column():
    assert not load_catalog()["financial_transaction"].has_column("Cenário")


def test_domain_order_follows_section_number():
    """Ordem dos campos no `list_fields`/"all" não depende do nome do arquivo."""
    assert extract_tables_by_domain()["financeiro"] == [
        "main.fintech_finance.receivable_assets",
        "main.ifoodoffice_invoice_service.company_tax_invoice",
        "main.ifood_benf_transaction_service.financial_account",
        "main.ifood_benf_transaction_service.financial_transaction",
        "fintech_companies.companies",
    ]


def test_relationships_come_from_their_own_file():
    assert is_declared_join(("employee", "company_id"), ("companies", "company_id"))
    assert is_declared_join(
        ("chargeback_employee", "chargeback_id"), ("chargeback", "id")
    )


def test_prompt_index_has_names_and_relationships_not_columns():
    index = build_tables_index()

    for name in allowed_tables():
        assert f"`{name}`" in index
    assert re.search(r"employee\.company_id\s+──> companies\.company_id", index)
    assert "| Coluna |" not in index
    assert "id_colaborador" not in index  # alias só chega sob demanda
    assert "**Multi-tenant**" not in index


def test_table_schema_has_columns_rule_and_own_enums():
    schema = get_table_schema.func("ifood_benefits_recharges")

    assert schema.startswith("## 4. iFood Benefits Recharges")
    assert "**Multi-tenant**" in schema
    assert "| `order_status` |" in schema
    assert "STATUSES_POS" in schema  # enum da própria tabela
    assert "ChargebackStatusEnum" not in schema  # enum de outra tabela


def test_shared_enum_only_goes_to_tables_with_the_column():
    for name in (
        "ifood_benefits_recharges",
        "receivable_assets",
        "company_tax_invoice",
        "financial_account",
    ):
        assert "ProductsEnum" in table_doc(name), name

    for name in ("employee", "chargeback", "financial_transaction"):
        assert "ProductsEnum" not in table_doc(name), name


def test_accepts_full_path():
    assert get_table_schema.func(
        "main.ifoodoffice_management_silver.employee"
    ) == get_table_schema.func("employee")


def test_table_outside_catalog_responds_with_valid_ones():
    response = get_table_schema.func("anticipation")

    assert "não está no catálogo" in response
    assert "employee" in response


def test_name_does_not_become_file_path():
    response = get_table_schema.func("../../../etc/passwd")

    assert "não está no catálogo" in response
