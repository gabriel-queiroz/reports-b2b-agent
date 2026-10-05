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

_TIPO_SQL = re.compile(r"[A-Z][A-Z0-9_]*(<.+>)?")


def test_um_arquivo_por_tabela_com_o_nome_fisico():
    """Arquivo sem tabela, com duas tabelas ou com nome trocado quebra aqui."""
    assert sorted(arquivo.stem for arquivo in table_files()) == sorted(load_catalog())


def test_toda_coluna_tem_tipo_sql():
    """Tabela markdown fora da seção de colunas vira coluna fantasma.

    No `schema.md` único, o cabeçalho da tabela de cenários de faturamento
    virava a coluna `Cenário` (tipo "Pagamento (PIX/boleto)") de
    `financial_transaction`, e o `list_fields` oferecia "Efeito no cruzamento".
    """
    for tabela in load_catalog().values():
        for coluna in tabela.columns:
            assert _TIPO_SQL.fullmatch(coluna.type), (
                f"{tabela.name}.{coluna.name} tem tipo {coluna.type!r}"
            )


def test_financial_transaction_sem_a_coluna_fantasma():
    assert not load_catalog()["financial_transaction"].has_column("Cenário")


def test_ordem_dos_dominios_e_a_do_numero_da_secao():
    """Ordem dos campos no `list_fields`/"all" não depende do nome do arquivo."""
    assert extract_tables_by_domain()["financeiro"] == [
        "main.fintech_finance.receivable_assets",
        "main.ifoodoffice_invoice_service.company_tax_invoice",
        "main.ifood_benf_transaction_service.financial_account",
        "main.ifood_benf_transaction_service.financial_transaction",
        "fintech_companies.companies",
    ]


def test_relacionamentos_vem_do_arquivo_proprio():
    assert is_declared_join(("employee", "company_id"), ("companies", "company_id"))
    assert is_declared_join(
        ("chargeback_employee", "chargeback_id"), ("chargeback", "id")
    )


def test_indice_do_prompt_tem_nomes_e_relacionamentos_e_nao_colunas():
    indice = build_tables_index()

    for nome in allowed_tables():
        assert f"`{nome}`" in indice
    assert re.search(r"employee\.company_id\s+──> companies\.company_id", indice)
    assert "| Coluna |" not in indice
    assert "id_colaborador" not in indice  # alias só chega sob demanda
    assert "**Multi-tenant**" not in indice


def test_schema_da_tabela_traz_colunas_regra_e_os_proprios_enums():
    schema = get_table_schema.func("ifood_benefits_recharges")

    assert schema.startswith("## 4. iFood Benefits Recharges")
    assert "**Multi-tenant**" in schema
    assert "| `order_status` |" in schema
    assert "STATUSES_POS" in schema  # enum da própria tabela
    assert "ChargebackStatusEnum" not in schema  # enum de outra tabela


def test_enum_compartilhado_so_vai_para_quem_tem_a_coluna():
    for nome in (
        "ifood_benefits_recharges",
        "receivable_assets",
        "company_tax_invoice",
        "financial_account",
    ):
        assert "ProductsEnum" in table_doc(nome), nome

    for nome in ("employee", "chargeback", "financial_transaction"):
        assert "ProductsEnum" not in table_doc(nome), nome


def test_aceita_caminho_completo():
    assert get_table_schema.func(
        "main.ifoodoffice_management_silver.employee"
    ) == get_table_schema.func("employee")


def test_tabela_fora_do_catalogo_responde_com_as_validas():
    resposta = get_table_schema.func("anticipation")

    assert "não está no catálogo" in resposta
    assert "employee" in resposta


def test_nome_nao_vira_caminho_de_arquivo():
    resposta = get_table_schema.func("../../../etc/passwd")

    assert "não está no catálogo" in resposta
