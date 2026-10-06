"""O catálogo é a fonte da verdade — estes testes travam a leitura dele.

A regra multi-tenant de cada tabela é lida da prosa do catálogo. Isso é bom
(não existe cópia da regra no código) e tem um custo: se alguém reescrever a
linha `**Multi-tenant**` de um jeito não reconhecido, a tabela sai da allowlist
e some das consultas. Estes testes fazem esse acidente falhar aqui, em CI, e não
em produção.
"""

import pytest
from domain.agents.reports_b2b.catalog import (
    DIRECT,
    JOIN,
    STRUCT,
    UNSUPPORTED,
    allowed_tables,
    find_table,
    load_catalog,
)
from domain.agents.reports_b2b.schema_extractor import extract_tables_by_domain

# (tabela, estratégia, coluna de grupo, tabela de apoio)
EXPECTED_RULES = [
    ("employee", JOIN, "company_group_id", "companies"),
    ("ifood_benefits_recharges", STRUCT, "company_group.id", None),
    ("receivable_assets", DIRECT, "company_group_id", None),
    ("companies", DIRECT, "company_group_id", None),
    ("chargeback", DIRECT, "group_id", None),
    ("company_tax_invoice", DIRECT, "group_id", None),
    ("financial_account", DIRECT, "group_id", None),
    ("financial_transaction", JOIN, "group_id", "financial_account"),
    ("chargeback_employee", JOIN, "group_id", "chargeback"),
]


@pytest.mark.parametrize("name,strategy,column,support", EXPECTED_RULES)
def test_multi_tenant_rule_of_each_table(name, strategy, column, support):
    rule = load_catalog()[name].tenant

    assert rule.strategy == strategy
    if strategy == JOIN:
        assert rule.join_table == support
        assert rule.join_column == column
    else:
        assert rule.column == column


def test_allowlist_excludes_only_what_catalog_does_not_confirm():
    assert set(allowed_tables()) == {
        name for name, strategy, _, _ in EXPECTED_RULES if strategy != UNSUPPORTED
    }


def test_full_path_of_each_table():
    table_paths = {name: table.path for name, table in load_catalog().items()}

    assert table_paths["employee"] == "main.ifoodoffice_management_silver.employee"
    assert table_paths["companies"] == "fintech_companies.companies"
    assert table_paths["chargeback"] == ("main.ifoodoffice_recharge_chargeback.chargeback")


def test_columns_and_aliases_are_read():
    chargeback = load_catalog()["chargeback"]

    assert "group_id" in chargeback.column_names
    assert "id_estorno" in chargeback.aliases

    recharges = load_catalog()["ifood_benefits_recharges"]
    # os campos de STRUCT entram com o caminho completo
    assert "company_group.id" in recharges.column_names
    assert "order_info.payment_method" in recharges.column_names


def test_employee_person_id_is_unique_filter():
    employee = load_catalog()["employee"]

    columns = {column.name: column for column in employee.columns}
    assert "person_id" in columns
    assert columns["person_id"].filterable is True
    assert columns["person_id"].display == ""

    for name in ("name", "email", "cpf"):
        assert columns[name].filterable is False
        assert columns[name].display


def test_recharges_columns_carry_level():
    recharges = load_catalog()["ifood_benefits_recharges"]

    by_group: dict[str, set[str]] = {}
    for column in recharges.columns:
        by_group.setdefault(column.group, set()).add(column.name)

    assert "Recarga (granularidade de empresa)" in by_group
    assert "Detalhes da Recarga (granularidade de colaborador)" in by_group
    assert "Técnico / Partição" in by_group

    assert "order_id" in by_group["Recarga (granularidade de empresa)"]
    assert (
        "order_info.payment_method" in by_group["Recarga (granularidade de empresa)"]
    )
    assert "amount" in by_group["Detalhes da Recarga (granularidade de colaborador)"]
    assert (
        "company.id" in by_group["Detalhes da Recarga (granularidade de colaborador)"]
    )
    assert "update_month" in by_group["Técnico / Partição"]


def test_chargeback_columns_carry_level():
    chargeback = load_catalog()["chargeback"]
    chargeback_employee = load_catalog()["chargeback_employee"]

    by_group_chargeback: dict[str, set[str]] = {}
    for column in chargeback.columns:
        by_group_chargeback.setdefault(column.group, set()).add(column.name)

    by_group_employee: dict[str, set[str]] = {}
    for column in chargeback_employee.columns:
        by_group_employee.setdefault(column.group, set()).add(column.name)

    assert "Estorno (granularidade de empresa)" in by_group_chargeback
    assert (
        "Estorno por Colaborador (granularidade de colaborador)" in by_group_employee
    )

    assert "id" in by_group_chargeback["Estorno (granularidade de empresa)"]
    assert (
        "total_amount_requested"
        in by_group_chargeback["Estorno (granularidade de empresa)"]
    )
    assert (
        "employee_id"
        in by_group_employee["Estorno por Colaborador (granularidade de colaborador)"]
    )
    assert (
        "reason"
        in by_group_employee["Estorno por Colaborador (granularidade de colaborador)"]
    )


def test_reference_resolution_by_suffix():
    assert find_table("main.ifoodoffice_management_silver.employee").name == "employee"
    assert find_table("employee").name == "employee"
    assert find_table("fintech_companies.companies").name == "companies"
    assert find_table("outro.employee") is None
    assert find_table("chargeback_employee").name == "chargeback_employee"
    assert find_table("") is None


def test_prompt_domains_still_come_from_same_catalog():
    """`schema_extractor` e `catalog` leem o mesmo arquivo — e concordam."""
    by_domain = extract_tables_by_domain()

    assert by_domain["colaboradores"] == [
        "main.ifoodoffice_management_silver.employee",
        "fintech_companies.companies",
    ]
    assert by_domain["recargas"] == [
        "main.fintech_finance.ifood_benefits_recharges",
        "fintech_companies.companies",
    ]
    assert by_domain["estorno_recarga"] == [
        "main.ifoodoffice_recharge_chargeback.chargeback",
        "main.ifoodoffice_recharge_chargeback.chargeback_employee",
        "fintech_companies.companies",
    ]
    assert set(by_domain["financeiro"]) == {
        "main.fintech_finance.receivable_assets",
        "main.ifoodoffice_invoice_service.company_tax_invoice",
        "main.ifood_benf_transaction_service.financial_account",
        "main.ifood_benf_transaction_service.financial_transaction",
        "fintech_companies.companies",
    }
