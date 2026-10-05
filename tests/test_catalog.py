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
REGRAS_ESPERADAS = [
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


@pytest.mark.parametrize("nome,estrategia,coluna,apoio", REGRAS_ESPERADAS)
def test_regra_multi_tenant_de_cada_tabela(nome, estrategia, coluna, apoio):
    regra = load_catalog()[nome].tenant

    assert regra.strategy == estrategia
    if estrategia == JOIN:
        assert regra.join_table == apoio
        assert regra.join_column == coluna
    else:
        assert regra.column == coluna


def test_allowlist_exclui_apenas_o_que_o_catalogo_nao_confirma():
    assert set(allowed_tables()) == {
        nome for nome, estrategia, _, _ in REGRAS_ESPERADAS if estrategia != UNSUPPORTED
    }


def test_caminho_completo_de_cada_tabela():
    caminhos = {nome: tabela.path for nome, tabela in load_catalog().items()}

    assert caminhos["employee"] == "main.ifoodoffice_management_silver.employee"
    assert caminhos["companies"] == "fintech_companies.companies"
    assert caminhos["chargeback"] == ("main.ifoodoffice_recharge_chargeback.chargeback")


def test_colunas_e_aliases_sao_lidos():
    chargeback = load_catalog()["chargeback"]

    assert "group_id" in chargeback.column_names
    assert "id_estorno" in chargeback.aliases

    recargas = load_catalog()["ifood_benefits_recharges"]
    # os campos de STRUCT entram com o caminho completo
    assert "company_group.id" in recargas.column_names
    assert "order_info.payment_method" in recargas.column_names


def test_employee_person_id_e_filtro_unico():
    employee = load_catalog()["employee"]

    colunas = {coluna.name: coluna for coluna in employee.columns}
    assert "person_id" in colunas
    assert colunas["person_id"].filterable is True
    assert colunas["person_id"].display == ""

    for nome in ("name", "email", "cpf"):
        assert colunas[nome].filterable is False
        assert colunas[nome].display


def test_recargas_colunas_carregam_nivel():
    recargas = load_catalog()["ifood_benefits_recharges"]

    por_grupo: dict[str, set[str]] = {}
    for coluna in recargas.columns:
        por_grupo.setdefault(coluna.group, set()).add(coluna.name)

    assert "Recarga (granularidade de empresa)" in por_grupo
    assert "Detalhes da Recarga (granularidade de colaborador)" in por_grupo
    assert "Técnico / Partição" in por_grupo

    assert "order_id" in por_grupo["Recarga (granularidade de empresa)"]
    assert (
        "order_info.payment_method" in por_grupo["Recarga (granularidade de empresa)"]
    )
    assert "amount" in por_grupo["Detalhes da Recarga (granularidade de colaborador)"]
    assert (
        "company.id" in por_grupo["Detalhes da Recarga (granularidade de colaborador)"]
    )
    assert "update_month" in por_grupo["Técnico / Partição"]


def test_estorno_colunas_carregam_nivel():
    chargeback = load_catalog()["chargeback"]
    chargeback_employee = load_catalog()["chargeback_employee"]

    por_grupo_chargeback: dict[str, set[str]] = {}
    for coluna in chargeback.columns:
        por_grupo_chargeback.setdefault(coluna.group, set()).add(coluna.name)

    por_grupo_employee: dict[str, set[str]] = {}
    for coluna in chargeback_employee.columns:
        por_grupo_employee.setdefault(coluna.group, set()).add(coluna.name)

    assert "Estorno (granularidade de empresa)" in por_grupo_chargeback
    assert (
        "Estorno por Colaborador (granularidade de colaborador)" in por_grupo_employee
    )

    assert "id" in por_grupo_chargeback["Estorno (granularidade de empresa)"]
    assert (
        "total_amount_requested"
        in por_grupo_chargeback["Estorno (granularidade de empresa)"]
    )
    assert (
        "employee_id"
        in por_grupo_employee["Estorno por Colaborador (granularidade de colaborador)"]
    )
    assert (
        "reason"
        in por_grupo_employee["Estorno por Colaborador (granularidade de colaborador)"]
    )


def test_resolucao_de_referencia_por_sufixo():
    assert find_table("main.ifoodoffice_management_silver.employee").name == "employee"
    assert find_table("employee").name == "employee"
    assert find_table("fintech_companies.companies").name == "companies"
    assert find_table("outro.employee") is None
    assert find_table("chargeback_employee").name == "chargeback_employee"
    assert find_table("") is None


def test_dominios_do_prompt_continuam_saindo_do_mesmo_catalogo():
    """`schema_extractor` e `catalog` leem o mesmo arquivo — e concordam."""
    por_dominio = extract_tables_by_domain()

    assert por_dominio["colaboradores"] == [
        "main.ifoodoffice_management_silver.employee",
        "fintech_companies.companies",
    ]
    assert por_dominio["recargas"] == [
        "main.fintech_finance.ifood_benefits_recharges",
        "fintech_companies.companies",
    ]
    assert por_dominio["estorno_recarga"] == [
        "main.ifoodoffice_recharge_chargeback.chargeback",
        "main.ifoodoffice_recharge_chargeback.chargeback_employee",
        "fintech_companies.companies",
    ]
    assert set(por_dominio["financeiro"]) == {
        "main.fintech_finance.receivable_assets",
        "main.ifoodoffice_invoice_service.company_tax_invoice",
        "main.ifood_benf_transaction_service.financial_account",
        "main.ifood_benf_transaction_service.financial_transaction",
        "fintech_companies.companies",
    }
