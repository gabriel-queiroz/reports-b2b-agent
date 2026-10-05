"""Fase 5 — `list_fields` monta a lista do catálogo, em vez de despejar o arquivo."""

import pytest
from domain.agents.reports_b2b.catalog import find_table, load_catalog, tabelas_dir
from domain.agents.reports_b2b.schema_extractor import extract_tables_by_domain
from domain.agents.reports_b2b.tools.list_fields import list_fields

DOMINIOS = ["colaboradores", "recargas", "financeiro", "estorno_recarga"]


def listar(dominio: str) -> str:
    return list_fields.func(dominio)


@pytest.mark.parametrize("dominio", DOMINIOS)
def test_resposta_e_a_lista_de_campos_e_nao_o_schema_inteiro(dominio):
    saida = listar(dominio)
    schema = "".join(
        arquivo.read_text(encoding="utf-8") for arquivo in tabelas_dir().glob("*.md")
    )

    assert len(saida) < len(schema) / 10
    assert "<schema_documentation>" not in saida
    assert "**Local**" not in saida


@pytest.mark.parametrize("dominio", DOMINIOS)
def test_usa_a_coluna_exibicao_e_nao_o_alias_tecnico(dominio):
    saida = listar(dominio)

    assert "- Razão Social" in saida
    assert "data_criacao" not in saida
    assert "company_group_id" not in saida


def test_financeiro_inclui_conta_e_transacao_financeira():
    """`DOMAIN_MARKERS["financeiro"]` não citava nenhuma das duas."""
    saida = listar("financeiro")

    assert "Financial Account" in saida
    assert "Financial Transaction" in saida
    assert "Company Tax Invoice" in saida
    assert "Receivable Assets" in saida


def test_estorno_recarga_inclui_chargebacks():
    """Estorno de recarga é domínio independente — não entra em recargas."""
    saida = listar("estorno_recarga")

    assert "Chargeback (Estornos)" in saida
    assert "Chargeback Employee (Estorno por Colaborador)" in saida
    assert "Chargeback (Estornos)" not in listar("recargas")


def test_colaboradores_oferece_saida_mas_nao_oferece_person_id_como_campo():
    saida = listar("colaboradores")

    assert "Nome" in saida
    assert "Email" in saida
    assert "CPF" in saida
    assert "ID Usuário iFB" not in saida


def test_struct_inteiro_nao_e_oferecido_como_campo():
    """O catálogo é explícito: nunca selecionar o struct inteiro."""
    recargas = load_catalog()["ifood_benefits_recharges"]
    structs = [c for c in recargas.columns if c.type.upper() == "STRUCT"]
    assert structs, "o catálogo deveria documentar structs nesta tabela"

    oferecidos = listar("recargas").count("\n- ")
    catalogados = sum(
        1
        for caminho in extract_tables_by_domain()["recargas"]
        for coluna in find_table(caminho).columns
        if coluna.display and coluna.type.upper() != "STRUCT"
    )

    assert oferecidos == catalogados


def test_recargas_lista_agrupado_por_recarga_e_item():
    saida = listar("recargas")

    assert "**Recarga (granularidade de empresa)**" in saida
    assert "**Detalhes da Recarga (granularidade de colaborador)**" in saida
    assert saida.index("**Recarga (granularidade de empresa)**") < saida.index(
        "**Detalhes da Recarga (granularidade de colaborador)**"
    )


def test_dominio_sem_catalogo_responde_sem_estourar():
    assert "não há domínio" in listar("inexistente").lower()
