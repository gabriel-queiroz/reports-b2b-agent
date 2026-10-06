"""Domínios, índice do prompt e schema sob demanda, a partir do catálogo.

O catálogo (`data/tabelas/`) é a fonte de verdade única; o parse fica no
`catalog`. Daqui sai o texto que o agente vê: o índice de tabelas com os
relacionamentos (prompt) e o schema de uma tabela (tool `get_table_schema`).
"""

import re
from typing import Dict, List

from domain.agents.reports_b2b.catalog import (
    RELATIONSHIPS,
    Column,
    Table,
    find_table,
    is_detail_column,
    load_catalog,
    tables_dir,
    table_file,
)
from domain.agents.reports_b2b.guardrails import InvalidDesiredFieldsError

# Mapeamento de nomes de tabelas no schema para domínios
TABLE_TO_DOMAIN = {
    "employee": "colaboradores",
    "mv_employee_config": "colaboradores",
    "ifood_benefits_recharges": "recargas",
    "chargeback": "estorno_recarga",
    "chargeback_employee": "estorno_recarga",
    "company_tax_invoice": "financeiro",
    "receivable_assets": "financeiro",
    "financial_account": "financeiro",
    "financial_transaction": "financeiro",
    "anticipation": "financeiro",
}


def extract_tables_by_domain() -> Dict[str, List[str]]:
    """
    Tabelas do catálogo organizadas por domínio, na ordem do catálogo.

    O domínio de cada tabela vem de `TABLE_TO_DOMAIN`. Retorna um dict com
    domínios mapeados para os caminhos completos das tabelas.
    """
    result: Dict[str, List[str]] = {
        "colaboradores": [],
        "recargas": [],
        "financeiro": [],
        "estorno_recarga": [],
    }

    for table in load_catalog().values():
        domain = TABLE_TO_DOMAIN.get(table.name)
        if domain and table.path not in result[domain]:
            result[domain].append(table.path)

    # Garantir que fintech_companies.companies está em todos os domínios
    # (necessário para JOIN com company_group_id)
    for domain in result:
        if "fintech_companies.companies" not in result[domain]:
            result[domain].append("fintech_companies.companies")

    return result


def get_all_tables_for_sql_generation() -> str:
    """
    Retorna TODAS as tabelas de todos os domínios como string separada por vírgula.

    Isso permite que o LLM veja todos os relacionamentos entre tabelas
    e gere SQL com JOINs corretos mesmo quando precisar consultar tabelas
    de outros domínios para responder a pergunta completamente.

    Returns:
        String com todas as tabelas separadas por vírgula e espaço
    """
    tables_by_domain = extract_tables_by_domain()

    all_tables = []
    for domain, tables in tables_by_domain.items():
        all_tables.extend(tables)

    # Remove duplicatas mantendo ordem
    unique_tables = []
    for table in all_tables:
        if table not in unique_tables:
            unique_tables.append(table)

    return ", ".join(unique_tables)


def build_domains_text() -> str:
    """Monta a descrição dos domínios a partir do catálogo, não de texto hardcoded.

    É a fonte do bloco `<dominios>` do agente conversacional. A lista de tabelas
    vem de `extract_tables_by_domain` e os títulos, de `find_table` — ou seja, a
    mesma origem do `list_fields` e do `sql_guard`.
    """
    tables_by_domain = extract_tables_by_domain()
    lines = []

    for domain, paths in tables_by_domain.items():
        titles = []
        for path in paths:
            if path == "fintech_companies.companies":
                continue
            table = find_table(path)
            if table is not None:
                titles.append(table.title)

        if not titles:
            titles.append("sem tabelas catalogadas")
        lines.append(f"- **{domain}**: " + ", ".join(titles) + ".")

    lines.append(
        "- **empresas** (transversal): use `companies` para nome/CNPJ da empresa "
        "e para o JOIN de grupo quando a tabela consultada não tiver coluna própria."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Resolução de `desired_fields`
# ---------------------------------------------------------------------------


# Colunas físicas que são filtro/controle, não saída de relatório.
_FILTER_COLUMNS = {"deleted", "test", "test_mode"}

# A tabela `companies` é transversal (ponte do filtro multi-tenant e fonte de
# CNPJ/razão social quando a tabela consultada não tem campos próprios). Ela não
# entra no default "all" — seus campos são pedidos explicitamente.
_COMPANIES = "companies"

# Campos do nível item/detalhe que, quando o relatório é de nível empresa, viram
# **medida**: entram no SELECT como `SUM(coluna)` e o alias é o agregado (não o
# alias PT-BR do item). Só são devolvidos no "all" por causa desta agregação — os
# demais campos de item (identidade: order_item_id, product_key, ...) ficam fora.
_MEASURES_BY_TABLE: dict[str, dict[str, str]] = {
    "ifood_benefits_recharges": {
        "amount": "valor_recarga",
        "cashback_amount": "valor_cashback",
    },
}

# Valores que o agente pode usar para pedir todos os campos do domínio.
_ALL_LABELS = {
    "all",
    "todos",
    "todas",
    "todos os campos",
    "campos padrão",
    "campos padrao",
}


def _domain_tables(domain: str) -> list[Table]:
    """Tabelas permitidas do domínio, na ordem do catálogo."""
    tables: list[Table] = []
    for path in extract_tables_by_domain().get(domain, []):
        table = find_table(path)
        if table is not None:
            tables.append(table)
    return tables


def _is_reportable_column(column: Column) -> bool:
    """Uma coluna é campo de relatório quando tem Exibição e não é filtro/struct."""
    if not column.display:
        return False
    if column.type.upper() == "STRUCT":
        return False
    if column.name.split(".")[-1].lower() in _FILTER_COLUMNS:
        return False
    return True


def _is_measure(table: Table, column: Column) -> bool:
    """A coluna é uma medida de item que, no nível empresa, entra como `SUM`."""
    return column.name in _MEASURES_BY_TABLE.get(table.name, {})


def _measure_alias(table: Table, column: Column) -> str:
    """Alias PT-BR agregado da medida (`valor_recarga`), não o do item cru."""
    return _MEASURES_BY_TABLE[table.name][column.name]


def resolve_desired_fields(
    domain: str, desired_fields: str
) -> list[tuple[Table, Column]]:
    """Resolve `desired_fields` contra a coluna `Exibição` do catálogo.

    Retorna pares `(tabela, coluna)` na ordem do catálogo. `desired_fields`
    pode ser "all" (ou variações) ou uma lista separada por vírgula/ponto-e-
    vírgula de rótulos de `Exibição` (também aceita alias PT-BR e nome físico
    como fallback). Rótulo ambíguo ou inexistente gera erro acionável.

    "all" resolve o nível principal (empresa) nos domínios multi-nível, exclui a
    tabela transversal `companies` e mantém as medidas do nível item apenas como
    `SUM` (nunca crus). Os demais campos de item/detalhe (identidade) e os de
    `companies` só entram quando pedidos explicitamente.
    """
    available = [
        (table, column)
        for table in _domain_tables(domain)
        for column in table.columns
        if _is_reportable_column(column)
    ]

    if not available:
        raise InvalidDesiredFieldsError(
            f"Não há campos catalogados para o domínio '{domain}'."
        )

    text = (desired_fields or "").strip()
    if not text or text.lower() in _ALL_LABELS:
        return [
            pair
            for pair in available
            if pair[0].name != _COMPANIES
            and (not is_detail_column(pair[1]) or _is_measure(pair[0], pair[1]))
        ]

    text = re.sub(r"\s+e\s+", ",", text, flags=re.IGNORECASE)
    tokens = [token.strip(" .") for token in re.split(r"[,;]", text) if token.strip()]

    if not tokens:
        return available

    selected: list[tuple[Table, Column]] = []
    for token in tokens:
        matches = [
            pair for pair in available if pair[1].display.lower() == token.lower()
        ]
        if not matches:
            matches = [
                pair for pair in available if pair[1].alias.lower() == token.lower()
            ]
        if not matches:
            matches = [
                pair for pair in available if pair[1].name.lower() == token.lower()
            ]

        if len(matches) == 1:
            if matches[0] not in selected:
                selected.append(matches[0])
            continue

        if len(matches) > 1:
            options = "; ".join(
                f"{table.name}.{column.name} ({column.display})"
                for table, column in matches
            )
            raise InvalidDesiredFieldsError(
                f"O campo '{token}' é ambíguo no domínio '{domain}'. "
                f"Escolha entre: {options}."
            )

        raise InvalidDesiredFieldsError(
            f"O campo '{token}' não existe no domínio '{domain}'. "
            "Os disponíveis são: "
            + ", ".join(column.display for _, column in available)
        )

    return selected


def build_requested_fields_block(domain: str, desired_fields: str) -> str:
    """Monta o bloco `<campos_solicitados>` que restringe o SQL aos campos pedidos.

    Fixa **quais** campos entram e, para medidas (campos de item no nível empresa),
    **como** entram. A agregação é **condicional ao nível**: quando a seleção é
    nível item (contém uma coluna de identidade do item, ex. `order_item_id`), as
    medidas saem **cruas** (uma linha por item); quando é nível empresa, saem como
    `SUM(...)` + `GROUP BY`.
    """
    selected = resolve_desired_fields(domain, desired_fields)

    detail = any(
        is_detail_column(column) and not _is_measure(table, column)
        for table, column in selected
    )

    lines = []
    measures: list[str] = []
    for table, column in selected:
        alias = column.alias or column.name.split(".")[-1]
        if _is_measure(table, column) and not detail:
            alias = _measure_alias(table, column)
            lines.append(
                f"- `SUM({table.name}.{column.name})` AS `{alias}` ({column.display})"
            )
            measures.append(alias)
        else:
            lines.append(
                f"- `{table.name}.{column.name}` AS `{alias}` ({column.display})"
            )

    group_by = ""
    if measures:
        group_by = (
            "\nAplique GROUP BY por TODAS as colunas de dimensão listadas acima "
            "(todas exceto as medidas SUM). As medidas nunca saem cruas: use "
            "sempre SUM(...). Não inclua colunas de item além das medidas."
        )

    return (
        "Gere o SELECT projetando os campos abaixo (coluna física + alias PT-BR "
        "indicados). Não invente colunas além das listadas. Inclua sempre a coluna "
        "de grupo da regra multi-tenant, com alias exato `company_group_id`."
        + group_by
        + "\n"
        + "\n".join(lines)
    )


# ---------------------------------------------------------------------------
# Catálogo sob demanda: índice no prompt, schema de cada tabela pela tool
# ---------------------------------------------------------------------------

GENERAL_RULES = "_regras_gerais.md"
SHARED_ENUMS = "_enums_compartilhados.md"

_H3_RE = re.compile(r"^### .+$", re.MULTILINE)
_TITLE_COLUMNS_RE = re.compile(r"\bcolunas?\b(?P<rest>.*)$", re.IGNORECASE)


def _read(name: str) -> str:
    return (tables_dir() / name).read_text(encoding="utf-8").strip()


def build_tables_index() -> str:
    """Índice do catálogo para o prompt: nomes, domínios e relacionamentos.

    É todo o schema que o prompt carrega. Colunas, aliases, partição, filtros
    padrão e enums de cada tabela vêm sob demanda, por `table_doc`.
    """
    lines = ["Tabelas consultáveis (o schema de cada uma vem de `get_table_schema`):"]
    for domain, paths in extract_tables_by_domain().items():
        names = []
        for path in paths:
            if path == "fintech_companies.companies":
                continue
            table = find_table(path)
            if table is not None:
                names.append(f"`{table.name}` ({table.title})")
        if names:
            lines.append(f"- **{domain}**: " + ", ".join(names))

    companies = find_table("fintech_companies.companies")
    if companies is not None:
        lines.append(
            f"- **transversal**: `{companies.name}` ({companies.title}) — nome/CNPJ "
            "da empresa e JOIN de grupo quando a tabela consultada não tiver coluna "
            "de grupo própria."
        )

    return "\n".join(lines) + "\n\n" + _read(RELATIONSHIPS)


def _shared_enums_for(table: Table) -> list[str]:
    """Blocos de `_enums_compartilhados.md` que valem para as colunas da tabela.

    O título de cada bloco cita as colunas (`— colunas `product_key`,
    `product_type``); o bloco vale para toda tabela que tenha alguma delas.
    """
    content = _read(SHARED_ENUMS)
    marks = list(_H3_RE.finditer(content))
    blocks = []
    for index, mark in enumerate(marks):
        end = marks[index + 1].start() if index + 1 < len(marks) else len(content)
        cited = _TITLE_COLUMNS_RE.search(mark.group(0))
        columns = re.findall(r"`([\w.]+)`", cited.group("rest")) if cited else []
        if any(table.has_column(column) for column in columns):
            # `###` -> `####`: no schema da tabela, fica sob "Valores possíveis".
            blocks.append("#" + content[mark.start() : end].strip())
    return blocks


def table_doc(reference: str) -> str | None:
    """Schema de uma tabela: o arquivo dela + os enums compartilhados que valem
    para as colunas dela. `None` quando a tabela não está na allowlist.

    Aceita o nome curto ou o caminho completo (mesma resolução do `sql_guard`).
    """
    table = find_table(reference.strip())
    if table is None:
        return None

    parts = [table_file(table.name).read_text(encoding="utf-8").strip()]
    shared = _shared_enums_for(table)
    if shared:
        parts.append(
            "### Valores possíveis compartilhados (enums)\n\n"
            + "\n\n".join(shared)
        )
    return "\n\n".join(parts)


def full_documentation() -> str:
    """Todo o catálogo num texto só, para o gerador de SQL atual (`sql_system.txt`).

    Transitório: com o prompt único o agente lê tabela a tabela (`table_doc`), e
    esta função sai junto com o gerador de SQL separado.
    """
    parts = [_read(GENERAL_RULES)]
    parts += [
        table_file(table.name).read_text(encoding="utf-8").strip()
        for table in load_catalog().values()
    ]
    parts += [_read(RELATIONSHIPS), _read(SHARED_ENUMS)]
    return "\n\n---\n\n".join(parts)
