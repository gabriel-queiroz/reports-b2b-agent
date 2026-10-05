"""Leitura estruturada do catálogo em `data/tabelas/` — a fonte da verdade única.

É o único parser do catálogo: o `schema_extractor` monta o índice do prompt e o
schema sob demanda a partir daqui, e o `sql_guard` tira daqui a allowlist e a
regra multi-tenant de cada tabela. A alternativa seria um dicionário paralelo no
Python, e toda vez que isso foi feito neste projeto apareceu divergência.

Um arquivo por tabela (`data/tabelas/<nome físico>.md`). Arquivos que começam
com `_` são de apoio, não tabela: `_relacionamentos.md` (chaves de JOIN),
`_regras_gerais.md` e `_enums_compartilhados.md`.

Cada arquivo de tabela é parseado sozinho. No `schema.md` único, tudo o que
vinha depois da última seção era lido como parte dela — foi assim que o
cabeçalho da tabela de cenários de faturamento virou a coluna `Cenário` de
`financial_transaction`.

O que é lido da seção `## N. Nome (Título)` de cada arquivo (N define a ordem
do catálogo):

- `**Local**: \\`caminho.completo\\`` → nome e caminho da tabela;
- `**Multi-tenant**: …` → como filtrar por grupo (é a linha que o
  `sql_guard` usa para montar o predicado);
- a tabela markdown de colunas (incluindo os campos de STRUCT).

Se a linha de multi-tenant de uma tabela deixar de ser reconhecida, a tabela
fica **fora** da allowlist — falha fechada, e os testes de catálogo apontam qual
seção mudou.
"""

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

# Estratégias de filtro multi-tenant reconhecidas na linha `**Multi-tenant**`.
DIRECT = "direct"  # a própria tabela tem a coluna de grupo
STRUCT = "struct"  # a coluna de grupo está dentro de um STRUCT
JOIN = "join"  # exige JOIN com outra tabela para chegar ao grupo
UNSUPPORTED = "unsupported"  # o catálogo não confirma caminho de grupo

_SECTION_RE = re.compile(r"^## (?P<numero>\d+)\.\s+(?P<titulo>.+)$", re.MULTILINE)
_LOCAL_RE = re.compile(r"\*\*Local(?:ização)?\*\*:\s*`([^`]+)`")
_TENANT_LINE_RE = re.compile(r"^\*\*Multi-tenant\*\*:\s*(?P<regra>.+)$", re.MULTILINE)

_UNSUPPORTED_RE = re.compile(
    r"não confirmado|não há coluna de grupo conhecida", re.IGNORECASE
)
_STRUCT_RE = re.compile(
    r"STRUCT embutido.*?filtrar direto em\s*`([\w.]+)`", re.IGNORECASE
)
_DIRECT_RE = re.compile(r"coluna direta\s*`([\w.]+)`", re.IGNORECASE)
_JOIN_RE = re.compile(
    r"Exige\s*`INNER JOIN\s+(?P<tabela>[\w.]+)\s+\w+\s+ON\s+[^`]+`"
    r".*?filtro em\s*`\w+\.(?P<coluna>\w+)`",
    re.IGNORECASE | re.DOTALL,
)

_ROW_RE = re.compile(r"^\|(?P<celulas>.+)\|\s*$", re.MULTILINE)

# No `Uso` (6ª célula), a marcação que torna uma coluna de saída não filtrável.
# Ex.: `Relatórios (não filtrar)` em `employee.name/email/cpf`.
_NON_FILTERABLE_RE = re.compile(r"não\s+filtr", re.IGNORECASE)

# Subtítulo `###` de uma seção define o agrupamento (nível) das colunas que
# aparecem abaixo dele. `####` é só rótulo de sub-tabela e não vira grupo.
_GROUP_RE = re.compile(r"^###\s+(?P<grupo>.+?)\s*$", re.MULTILINE)

# `_relacionamentos.md`: `tabela.coluna ──> tabela.coluna`, sempre com o
# nome físico das duas pontas. Linhas terminadas em `(grupo corporativo)` são
# nota de multi-tenant, não relacionamento entre tabelas.
_RELATIONSHIP_RE = re.compile(
    r"^(?P<esq_tabela>\w+)\.(?P<esq_coluna>[\w.]+)\s*──>\s*"
    r"(?P<dir_tabela>\w+)\.(?P<dir_coluna>[\w.]+)\s*$",
    re.MULTILINE,
)


@dataclass(frozen=True)
class TenantRule:
    """Como uma tabela é restringida ao grupo de empresas da sessão."""

    strategy: str
    column: str | None = None  # coluna (ou caminho de struct) na própria tabela
    join_table: str | None = None  # nome curto da tabela de apoio
    join_column: str | None = None  # coluna de grupo na tabela de apoio

    @property
    def is_usable(self) -> bool:
        return self.strategy != UNSUPPORTED


@dataclass(frozen=True)
class Column:
    """Uma coluna do catálogo. `name` pode ser um caminho de struct (`a.b`)."""

    name: str
    type: str
    alias: str  # Alias PT-BR obrigatório na saída
    display: str  # Rótulo mostrado ao usuário
    group: str | None = None  # subtítulo `###` da seção (nível/agrupamento)
    usage: str = ""  # valor da coluna `Uso` no arquivo da tabela
    filterable: bool = True  # pode ser usada em WHERE/JOIN ON?


@dataclass(frozen=True)
class Table:
    """Uma tabela documentada no catálogo."""

    name: str  # employee
    path: str  # main.ifoodoffice_management_silver.employee
    title: str  # "Employee (Colaboradores)"
    tenant: TenantRule
    columns: tuple[Column, ...]

    @property
    def path_parts(self) -> tuple[str, ...]:
        return tuple(part.lower() for part in self.path.split("."))

    @property
    def column_names(self) -> frozenset[str]:
        return frozenset(column.name.lower() for column in self.columns)

    @property
    def aliases(self) -> frozenset[str]:
        return frozenset(
            column.alias.lower() for column in self.columns if column.alias
        )

    def has_column(self, name: str) -> bool:
        return name.lower() in self.column_names

    def column_for_alias(self, alias: str) -> Column | None:
        """A coluna física por trás de um Alias PT-BR (`id_estorno` → `id`)."""
        for column in self.columns:
            if column.alias.lower() == alias.lower():
                return column
        return None


# No catálogo, o subtítulo `###` de um nível de detalhe (colaborador) usa esta
# marca. É o que separa, num domínio multi-nível, o nível principal (empresa) do
# nível de item/detalhe — mesmo grupo que o `list_fields` expõe ao usuário. Vive
# aqui (fonte única) porque `schema_extractor` e `sql_guard` precisam concordar.
_DETALHE_GRUPO_RE = re.compile(r"granularidade de colaborador", re.IGNORECASE)


def is_detalhe_column(column: Column) -> bool:
    """A coluna pertence ao nível de detalhe (colaborador), não ao nível empresa."""
    return bool(column.group) and bool(_DETALHE_GRUPO_RE.search(column.group))


RELACIONAMENTOS = "_relacionamentos.md"


def tabelas_dir() -> Path:
    """Pasta do catálogo: um `<tabela>.md` por tabela + arquivos de apoio `_*.md`."""
    return Path(__file__).parent / "data" / "tabelas"


def table_files() -> list[Path]:
    """Arquivos de tabela da pasta — tudo que não começa com `_`."""
    return sorted(
        arquivo
        for arquivo in tabelas_dir().glob("*.md")
        if not arquivo.name.startswith("_")
    )


def table_file(name: str) -> Path:
    """Arquivo de uma tabela: `data/tabelas/<nome físico>.md`."""
    return tabelas_dir() / f"{name}.md"


@lru_cache(maxsize=1)
def load_catalog() -> dict[str, Table]:
    """Devolve o catálogo indexado pelo nome curto da tabela.

    Cada arquivo é parseado isolado, então o texto de um não vaza para a tabela
    de outro. A ordem é a do número da seção (`## N.`), não a do nome do
    arquivo: é ela que define a ordem dos campos no `list_fields` e no "all".
    Arquivo sem `## N. Título` não vira tabela (falha fechada; o teste acusa).

    O resultado é memoizado: o catálogo não muda em runtime.
    """
    secoes: list[tuple[int, dict[str, Table]]] = []
    for arquivo in table_files():
        conteudo = arquivo.read_text(encoding="utf-8")
        titulo = _SECTION_RE.search(conteudo)
        if titulo is None:
            continue
        secoes.append((int(titulo.group("numero")), _parse_catalog(conteudo)))

    catalogo: dict[str, Table] = {}
    for _, tabelas in sorted(secoes, key=lambda item: item[0]):
        catalogo.update(tabelas)
    return catalogo


@lru_cache(maxsize=1)
def allowed_tables() -> dict[str, Table]:
    """Tabelas que o agente pode consultar.

    É o catálogo menos as tabelas sem caminho multi-tenant reconhecido
    (estratégia `UNSUPPORTED`). Hoje todas as tabelas documentadas no
    catálogo têm regra multi-tenant válida, inclusive `chargeback_employee`
    via JOIN com `chargeback`.
    """
    return {
        name: table for name, table in load_catalog().items() if table.tenant.is_usable
    }


@lru_cache(maxsize=1)
def relationships() -> frozenset[frozenset[tuple[str, str]]]:
    """Chaves de JOIN declaradas no catálogo, como pares sem direção.

    Cada elemento é `{("employee", "company_id"), ("companies", "company_id")}`.
    É o que permite dizer que um `ON` liga as tabelas por onde o catálogo manda
    ligar — e não por uma coluna inventada.
    """
    content = (tabelas_dir() / RELACIONAMENTOS).read_text(encoding="utf-8")
    return frozenset(
        frozenset(
            {
                (match.group("esq_tabela"), match.group("esq_coluna")),
                (match.group("dir_tabela"), match.group("dir_coluna")),
            }
        )
        for match in _RELATIONSHIP_RE.finditer(content)
    )


def is_declared_join(left: tuple[str, str], right: tuple[str, str]) -> bool:
    """O par `(tabela, coluna)` × `(tabela, coluna)` está no catálogo?"""
    return frozenset({left, right}) in relationships()


def declared_joins_between(first: str, second: str) -> list[str]:
    """Chaves de JOIN declaradas entre duas tabelas, prontas para a mensagem.

    A ordem segue a dos argumentos, para o erro sair na mesma ordem em que as
    tabelas aparecem na query.
    """
    ligacoes = []
    for par in relationships():
        if {tabela for tabela, _ in par} != {first, second}:
            continue
        esquerda = next(ponta for ponta in par if ponta[0] == first)
        direita = next(ponta for ponta in par if ponta[0] == second)
        ligacoes.append(f"{esquerda[0]}.{esquerda[1]} = {direita[0]}.{direita[1]}")
    return sorted(ligacoes)


def find_table(reference: str) -> Table | None:
    """Resolve uma referência de tabela do SQL contra o catálogo.

    Aceita o caminho completo (`main.ifoodoffice_management_silver.employee`), o
    caminho parcial (`fintech_companies.companies`) ou o nome curto
    (`employee`) — desde que seja **sufixo** de um caminho documentado. Assim
    `outro_catalogo.employee` não passa por `employee`.
    """
    parts = tuple(part.lower() for part in reference.split(".") if part)
    if not parts:
        return None

    for table in allowed_tables().values():
        if table.path_parts[-len(parts) :] == parts:
            return table
    return None


# ------------------------------------------------------------------ parsing --


def _parse_catalog(content: str) -> dict[str, Table]:
    tables: dict[str, Table] = {}

    for section_title, section in _iter_sections(content):
        local = _LOCAL_RE.search(section)
        if not local:
            continue  # seções de texto (relacionamentos, filtros, tipos...)

        path = local.group(1).strip()
        name = path.split(".")[-1]
        tables[name] = Table(
            name=name,
            path=path,
            title=section_title,
            tenant=_parse_tenant_rule(section),
            columns=tuple(_parse_columns(section)),
        )

    return tables


def _iter_sections(content: str):
    """Fatia o documento nas seções `## N. Título`."""
    matches = list(_SECTION_RE.finditer(content))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        yield match.group("titulo").strip(), content[match.end() : end]


def _parse_tenant_rule(section: str) -> TenantRule:
    """Traduz a linha `**Multi-tenant**` em regra executável.

    O que não for reconhecido vira `UNSUPPORTED` — a tabela sai da allowlist em
    vez de entrar com um filtro adivinhado.
    """
    line = _TENANT_LINE_RE.search(section)
    if not line:
        return TenantRule(UNSUPPORTED)

    regra = line.group("regra")

    if _UNSUPPORTED_RE.search(regra):
        return TenantRule(UNSUPPORTED)

    struct = _STRUCT_RE.search(regra)
    if struct:
        return TenantRule(STRUCT, column=struct.group(1))

    direct = _DIRECT_RE.search(regra)
    if direct:
        return TenantRule(DIRECT, column=direct.group(1))

    join = _JOIN_RE.search(regra)
    if join:
        return TenantRule(
            JOIN,
            join_table=join.group("tabela").split(".")[-1],
            join_column=join.group("coluna"),
        )

    return TenantRule(UNSUPPORTED)


def _parse_columns(section: str):
    """Lê as linhas das tabelas markdown de colunas da seção.

    Cobre tanto "Colunas Principais" quanto os blocos de campos de STRUCT: as
    duas têm o mesmo formato `| Coluna | Tipo | Alias PT-BR | Exibição | …`.
    O subtítulo `###` mais recente vira o `group` da coluna (nível/agrupamento);
    `####` é ignorado.
    """
    seen: set[str] = set()
    group: str | None = None

    tokens = [
        (m.start(), m.group("grupo").strip()) for m in _GROUP_RE.finditer(section)
    ]
    tokens += [(m.start(), m) for m in _ROW_RE.finditer(section)]
    tokens.sort(key=lambda item: item[0])

    for _, payload in tokens:
        if isinstance(payload, str):
            group = payload
            continue

        row = payload
        cells = [cell.strip() for cell in row.group("celulas").split("|")]
        if len(cells) < 4:
            continue

        name = cells[0].strip("`").strip()
        # pula cabeçalho e separador da tabela markdown
        if not name or name.lower() == "coluna" or set(name) <= {"-", ":"}:
            continue
        if not re.fullmatch(r"[\w.]+", name) or name in seen:
            continue

        seen.add(name)
        usage = cells[5].strip() if len(cells) > 5 else ""
        yield Column(
            name=name,
            type=cells[1].strip("`").strip(),
            alias=cells[2].strip("`").strip(),
            display=cells[3].strip(),
            group=group,
            usage=usage,
            filterable=not _NON_FILTERABLE_RE.search(usage),
        )
