#!/usr/bin/env python3
"""Migração única: divide `data/schema.md` em `data/tabelas/` (um arquivo por tabela).

Uso:
    python dividir_schema.py <reports_b2b>/data/schema.md <reports_b2b>/data/tabelas

O conteúdo de cada tabela sai como estava no schema.md. O que muda de lugar:

- enums: cada bloco vai para o arquivo da tabela dona da coluna; o de produtos,
  usado por várias tabelas, vai para `_enums_compartilhados.md`;
- RELACIONAMENTOS + cenários de pagamento/faturamento: `_relacionamentos.md`;
- aliases PT-BR, coluna de grupo na saída, licenças e tipos: `_regras_gerais.md`.

O que sai:

- o índice "TABELAS DISPONÍVEIS" (agora é gerado do catálogo);
- os exemplos SQL de "FILTROS DE SEGURANÇA MULTI-TENANT" (repetiam a linha
  `**Multi-tenant**` de cada tabela, que é o que o `sql_guard` lê);
- a linha `**Relacionamentos**` de cada tabela (repetia a seção RELACIONAMENTOS
  e, em três tabelas, a contradizia).

Toda seção `##` do schema.md precisa ter destino aqui: se aparecer uma nova, o
script para em vez de descartá-la em silêncio.
"""

import re
import sys
from pathlib import Path

# Prefixo do título `###` de cada bloco de enum -> tabela dona da coluna.
# `None` = enum compartilhado entre tabelas.
ENUM_DONO = {
    "Produtos (": None,
    "Recarga — Status do pedido": "ifood_benefits_recharges",
    "Recarga — Status pós-pago": "ifood_benefits_recharges",
    "Recarga — Status do participante": "ifood_benefits_recharges",
    "Recarga — Método de pagamento": "ifood_benefits_recharges",
    "Recarga — Uso de saldo": "ifood_benefits_recharges",
    "Recarga — Agendamento da distribuição": "ifood_benefits_recharges",
    "Financeiro — Status de pagamento": "receivable_assets",
    "Financeiro — Método de pagamento": "receivable_assets",
    "Financeiro — Status de nota fiscal": "company_tax_invoice",
    "Financeiro — Motivo de transação": "financial_transaction",
    "Financeiro — Tipo de transação": "financial_transaction",
    "Financeiro — Tipo de conta da empresa": "financial_account",
    "Financeiro — Origem da conta financeira": "financial_account",
    "Estorno de recarga — Status (": "chargeback",
    "Estorno de recarga — Motivo": "chargeback_employee",
    "Estorno de recarga — Status por item": "chargeback_employee",
}

# Seções `##` sem número -> chave usada abaixo.
SECOES_GLOBAIS = {
    "INSTRUÇÃO IMPORTANTE": "aliases",
    "TABELAS DISPONÍVEIS": "indice",
    "RELACIONAMENTOS": "relacionamentos",
    "ESTRUTURA DE LICENÇAS": "licencas",
    "CONFIGURAÇÕES DE PAGAMENTO": "faturamento",
    "FILTROS DE SEGURANÇA MULTI-TENANT": "multi_tenant",
    "REFERÊNCIA DE ENUMS": "enums",
    "TIPOS DE DADOS": "tipos",
}

_H2_RE = re.compile(r"^## .+$", re.MULTILINE)
_TABELA_RE = re.compile(r"^## \d+\.\s")
_LOCAL_RE = re.compile(r"\*\*Local(?:ização)?\*\*:\s*`([^`]+)`")
_RELACIONAMENTOS_LINHA_RE = re.compile(r"^\*\*Relacionamentos\*\*:.*\n\n?", re.MULTILINE)
_H3_RE = re.compile(r"^### (?P<titulo>.+)$", re.MULTILINE)


def limpar(texto: str) -> str:
    """Tira o separador `---`, o rodapé e as linhas em branco do fim."""
    linhas = texto.rstrip().splitlines()
    while linhas and (
        not linhas[-1].strip()
        or linhas[-1].strip() == "---"
        or linhas[-1].startswith("*Documentação atualizada")
    ):
        linhas.pop()
    return "\n".join(linhas)


def sem_titulo(secao: str) -> str:
    """Corpo da seção, sem a linha `## Título`."""
    return limpar(secao.split("\n", 1)[1]).strip("\n")


def fatiar_h2(texto: str) -> list[str]:
    marcas = list(_H2_RE.finditer(texto))
    return [
        texto[m.start() : marcas[i + 1].start() if i + 1 < len(marcas) else len(texto)]
        for i, m in enumerate(marcas)
    ]


def fatiar_h3(corpo: str) -> tuple[str, list[tuple[str, str]]]:
    """(texto antes do primeiro `###`, [(título, bloco sem a linha do título)])."""
    marcas = list(_H3_RE.finditer(corpo))
    intro = corpo[: marcas[0].start()].strip() if marcas else corpo.strip()
    blocos = []
    for i, m in enumerate(marcas):
        fim = marcas[i + 1].start() if i + 1 < len(marcas) else len(corpo)
        blocos.append((m.group("titulo").strip(), limpar(corpo[m.end() : fim]).strip("\n")))
    return intro, blocos


def dono_do_enum(titulo: str) -> str | None:
    donos = [dono for prefixo, dono in ENUM_DONO.items() if titulo.startswith(prefixo)]
    if len(donos) != 1:
        raise SystemExit(f"Bloco de enum sem dono único: {titulo!r}")
    return donos[0]


def main(origem: Path, destino: Path) -> None:
    texto = origem.read_text(encoding="utf-8")
    destino.mkdir(parents=True, exist_ok=True)

    tabelas: dict[str, str] = {}
    globais: dict[str, str] = {}
    for secao in fatiar_h2(texto):
        titulo = secao.splitlines()[0]
        if _TABELA_RE.match(titulo):
            nome = _LOCAL_RE.search(secao).group(1).split(".")[-1]
            tabelas[nome] = _RELACIONAMENTOS_LINHA_RE.sub("", limpar(secao))
            continue
        chave = next((v for k, v in SECOES_GLOBAIS.items() if k in titulo), None)
        if chave is None:
            raise SystemExit(f"Seção sem destino definido: {titulo!r}")
        globais[chave] = sem_titulo(secao)

    # --- enums: cada bloco para a tabela dona; produtos para o compartilhado
    intro_enums, blocos = fatiar_h3(globais["enums"])
    enums_da_tabela: dict[str, list[str]] = {}
    compartilhados: list[str] = []
    for titulo, bloco in blocos:
        dono = dono_do_enum(titulo)
        if dono is None:
            compartilhados.append(f"### {titulo}\n\n{bloco}")
        else:
            if dono not in tabelas:
                raise SystemExit(f"Enum {titulo!r} aponta para tabela inexistente {dono!r}")
            enums_da_tabela.setdefault(dono, []).append(f"#### {titulo}\n\n{bloco}")

    for nome, conteudo in tabelas.items():
        partes = [conteudo]
        if nome in enums_da_tabela:
            partes.append("### Valores possíveis (enums)\n\n" + "\n\n".join(enums_da_tabela[nome]))
        (destino / f"{nome}.md").write_text("\n\n".join(partes) + "\n", encoding="utf-8")

    # --- relacionamentos (+ cenários de faturamento, que explicam um desses JOINs)
    (destino / "_relacionamentos.md").write_text(
        "# Relacionamentos entre tabelas\n\n"
        "Só estas ligações são aceitas em `JOIN ... ON`; JOIN por qualquer outra "
        "coluna é rejeitado.\n\n"
        f"{globais['relacionamentos']}\n\n"
        "## Cruzamento recebível × nota fiscal (configurações de pagamento e faturamento)\n\n"
        f"{globais['faturamento']}\n",
        encoding="utf-8",
    )

    # --- regras transversais
    multi_tenant = globais["multi_tenant"]
    inicio_saida = multi_tenant.find("Além do filtro")
    if inicio_saida < 0:
        raise SystemExit("Não achei o parágrafo da coluna de grupo na saída.")
    (destino / "_regras_gerais.md").write_text(
        "# Regras gerais do catálogo\n\n"
        "Valem para qualquer tabela. Colunas, aliases, partição, filtros padrão e "
        "enums de cada tabela estão no schema dela (`get_table_schema`).\n\n"
        "## Aliases em PT-BR\n\n"
        f"{globais['aliases']}\n\n"
        "## Filtro por grupo\n\n"
        "O filtro por grupo é obrigatório em toda query. A regra de cada tabela está na "
        "linha **Multi-tenant** do schema dela; query sem esse filtro é rejeitada.\n\n"
        f"{multi_tenant[inicio_saida:].strip()}\n\n"
        "## Licenças (separada × unificada)\n\n"
        f"{globais['licencas']}\n\n"
        "## Enums\n\n"
        "Cada arquivo de tabela termina com os valores possíveis das suas colunas "
        "(`### Valores possíveis (enums)`); os de produto, usados por várias tabelas, "
        f"ficam em `_enums_compartilhados.md`. {intro_enums}\n\n"
        "## Tipos de dados\n\n"
        f"{globais['tipos']}\n",
        encoding="utf-8",
    )

    (destino / "_enums_compartilhados.md").write_text(
        "# Enums compartilhados\n\n"
        "Valores de colunas que existem em mais de uma tabela. A tool `get_table_schema` "
        "anexa cada bloco ao schema das tabelas que têm alguma das colunas citadas no "
        "título (depois de `coluna`/`colunas`, entre crases).\n\n"
        + "\n\n".join(compartilhados)
        + "\n",
        encoding="utf-8",
    )

    print(f"{len(tabelas)} tabelas: {', '.join(sorted(tabelas))}")
    print(f"{sum(len(v) for v in enums_da_tabela.values())} enums distribuídos, "
          f"{len(compartilhados)} compartilhado(s)")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
