#!/usr/bin/env python3
"""Migração única: divide `data/schema.md` em `data/tabelas/` (um arquivo por tabela).

Uso:
    python split_schema.py <reports_b2b>/data/schema.md <reports_b2b>/data/tabelas

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
ENUM_OWNER = {
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
GLOBAL_SECTIONS = {
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
_TABLE_RE = re.compile(r"^## \d+\.\s")
_LOCAL_RE = re.compile(r"\*\*Local(?:ização)?\*\*:\s*`([^`]+)`")
_RELATIONSHIP_LINE_RE = re.compile(r"^\*\*Relacionamentos\*\*:.*\n\n?", re.MULTILINE)
_H3_RE = re.compile(r"^### (?P<title>.+)$", re.MULTILINE)


def clean(text: str) -> str:
    """Tira o separador `---`, o rodapé e as linhas em branco do fim."""
    lines = text.rstrip().splitlines()
    while lines and (
        not lines[-1].strip()
        or lines[-1].strip() == "---"
        or lines[-1].startswith("*Documentação atualizada")
    ):
        lines.pop()
    return "\n".join(lines)


def untitled(section: str) -> str:
    """Corpo da seção, sem a linha `## Título`."""
    return clean(section.split("\n", 1)[1]).strip("\n")


def split_h2(text: str) -> list[str]:
    marks = list(_H2_RE.finditer(text))
    return [
        text[m.start() : marks[i + 1].start() if i + 1 < len(marks) else len(text)]
        for i, m in enumerate(marks)
    ]


def split_h3(body: str) -> tuple[str, list[tuple[str, str]]]:
    """(texto antes do primeiro `###`, [(título, bloco sem a linha do título)])."""
    marks = list(_H3_RE.finditer(body))
    intro = body[: marks[0].start()].strip() if marks else body.strip()
    blocks = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(body)
        blocks.append((m.group("title").strip(), clean(body[m.end() : end]).strip("\n")))
    return intro, blocks


def enum_owner(title: str) -> str | None:
    owners = [owner for prefix, owner in ENUM_OWNER.items() if title.startswith(prefix)]
    if len(owners) != 1:
        raise SystemExit(f"Bloco de enum sem dono único: {title!r}")
    return owners[0]


def main(source: Path, destination: Path) -> None:
    text = source.read_text(encoding="utf-8")
    destination.mkdir(parents=True, exist_ok=True)

    tables: dict[str, str] = {}
    global_sections: dict[str, str] = {}
    for section in split_h2(text):
        title = section.splitlines()[0]
        if _TABLE_RE.match(title):
            name = _LOCAL_RE.search(section).group(1).split(".")[-1]
            tables[name] = _RELATIONSHIP_LINE_RE.sub("", clean(section))
            continue
        key = next((v for k, v in GLOBAL_SECTIONS.items() if k in title), None)
        if key is None:
            raise SystemExit(f"Seção sem destino definido: {title!r}")
        global_sections[key] = untitled(section)

    # --- enums: cada bloco para a tabela dona; produtos para o compartilhado
    intro_enums, blocks = split_h3(global_sections["enums"])
    table_enums: dict[str, list[str]] = {}
    shared: list[str] = []
    for title, block in blocks:
        owner = enum_owner(title)
        if owner is None:
            shared.append(f"### {title}\n\n{block}")
        else:
            if owner not in tables:
                raise SystemExit(f"Enum {title!r} aponta para tabela inexistente {owner!r}")
            table_enums.setdefault(owner, []).append(f"#### {title}\n\n{block}")

    for name, content in tables.items():
        parts = [content]
        if name in table_enums:
            parts.append("### Valores possíveis (enums)\n\n" + "\n\n".join(table_enums[name]))
        (destination / f"{name}.md").write_text("\n\n".join(parts) + "\n", encoding="utf-8")

    # --- relacionamentos (+ cenários de faturamento, que explicam um desses JOINs)
    (destination / "_relacionamentos.md").write_text(
        "# Relacionamentos entre tabelas\n\n"
        "Só estas ligações são aceitas em `JOIN ... ON`; JOIN por qualquer outra "
        "coluna é rejeitado.\n\n"
        f"{global_sections['relacionamentos']}\n\n"
        "## Cruzamento recebível × nota fiscal (configurações de pagamento e faturamento)\n\n"
        f"{global_sections['faturamento']}\n",
        encoding="utf-8",
    )

    # --- regras transversais
    multi_tenant = global_sections["multi_tenant"]
    output_start = multi_tenant.find("Além do filtro")
    if output_start < 0:
        raise SystemExit("Não achei o parágrafo da coluna de grupo na saída.")
    (destination / "_regras_gerais.md").write_text(
        "# Regras gerais do catálogo\n\n"
        "Valem para qualquer tabela. Colunas, aliases, partição, filtros padrão e "
        "enums de cada tabela estão no schema dela (`get_table_schema`).\n\n"
        "## Aliases em PT-BR\n\n"
        f"{global_sections['aliases']}\n\n"
        "## Filtro por grupo\n\n"
        "O filtro por grupo é obrigatório em toda query. A regra de cada tabela está na "
        "linha **Multi-tenant** do schema dela; query sem esse filtro é rejeitada.\n\n"
        f"{multi_tenant[output_start:].strip()}\n\n"
        "## Licenças (separada × unificada)\n\n"
        f"{global_sections['licencas']}\n\n"
        "## Enums\n\n"
        "Cada arquivo de tabela termina com os valores possíveis das suas colunas "
        "(`### Valores possíveis (enums)`); os de produto, usados por várias tabelas, "
        f"ficam em `_enums_compartilhados.md`. {intro_enums}\n\n"
        "## Tipos de dados\n\n"
        f"{global_sections['tipos']}\n",
        encoding="utf-8",
    )

    (destination / "_enums_compartilhados.md").write_text(
        "# Enums compartilhados\n\n"
        "Valores de colunas que existem em mais de uma tabela. A tool `get_table_schema` "
        "anexa cada bloco ao schema das tabelas que têm alguma das colunas citadas no "
        "título (depois de `coluna`/`colunas`, entre crases).\n\n"
        + "\n\n".join(shared)
        + "\n",
        encoding="utf-8",
    )

    print(f"{len(tables)} tabelas: {', '.join(sorted(tables))}")
    print(f"{sum(len(v) for v in table_enums.values())} enums distribuídos, "
          f"{len(shared)} compartilhado(s)")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
