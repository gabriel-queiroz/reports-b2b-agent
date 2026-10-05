"""Guard de AST: a última palavra sobre o SQL que o LLM escreveu.

Substitui a validação por string do `sql_validator`. A diferença que importa
não é de estilo: com AST o filtro de tenant é **injetado na estrutura** e
verificado **na estrutura**, então some a classe inteira de bugs em que o filtro
existia no texto mas não filtrava nada — dentro de um ramo de `OR`, depois do
`GROUP BY`, dentro de uma subquery ou no `ON` de um `LEFT JOIN`.

O que este módulo garante, nesta ordem:

1. o SQL faz parse no dialeto do Databricks;
2. é **um** statement, e é `SELECT` (ou `WITH`/`UNION` de selects);
3. nenhum nó de DML/DDL em lugar nenhum da árvore;
4. toda tabela referenciada está na allowlist do catálogo (`data/tabelas/`);
5. toda coluna existe na tabela em que foi citada, e cada `JOIN` usa uma chave
   declarada no catálogo;
6. **todo escopo** que lê uma tabela base tem o predicado de tenant no topo do
   `WHERE`, com o UUID da sessão — injetado via AST quando faltar;
7. o `SELECT` externo expõe `company_group_id` como coluna de saída;
8. o SQL devolvido é **regerado a partir da AST**, nunca a string do LLM.

A regra de tenant de cada tabela vem do `catalog`, que a lê de `data/tabelas/`.
Nada aqui é hardcoded por tabela.
"""

from difflib import get_close_matches

import sqlglot
from sqlglot import exp

from domain.agents.reports_b2b.catalog import (
    DIRECT,
    JOIN,
    STRUCT,
    Column,
    Table,
    allowed_tables,
    declared_joins_between,
    find_table,
    is_declared_join,
    is_detalhe_column,
)
from domain.agents.reports_b2b.guardrails import validate_group_id

__all__ = [
    "QueryNotAllowedError",
    "SqlGuardError",
    "SqlSyntaxError",
    "StatementNotAllowedError",
    "TableNotAllowedError",
    "ColumnNotFoundError",
    "AliasAsColumnError",
    "ColumnNotFilterableError",
    "JoinKeyError",
    "TenantFilterError",
    "OutputColumnError",
    "RechargesAggregationError",
    "guard_query",
]

DIALECT = "databricks"

# Não há teto de linhas: o relatório traz o recorte inteiro. O guard não injeta
# nem reduz `LIMIT` — o que o LLM escrever (porque o usuário pediu "top 10")
# passa intacto.

# Nós que não podem aparecer em consulta de relatório, em nenhuma profundidade.
# `Command` é o que o sqlglot devolve para o que ele não sabe analisar — deixar
# passar seria justamente o caso perigoso.
_FORBIDDEN_NODES = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Merge,
    exp.Create,
    exp.Drop,
    exp.Alter,
    exp.TruncateTable,
    exp.Command,
    exp.Use,
    exp.Set,
    exp.Grant,
)


class QueryNotAllowedError(Exception):
    """A query não atende aos requisitos de segurança multi-tenant.

    Vinha do `sql_validator`, que sumiu quando a validação por string acabou.
    Continua sendo a base dos erros do guard: quem capturava este tipo captura
    tudo que o guard levanta.
    """


class SqlGuardError(QueryNotAllowedError):
    """Base dos erros do guard."""


class SqlSyntaxError(SqlGuardError):
    """O SQL não faz parse no dialeto do Databricks."""


class StatementNotAllowedError(SqlGuardError):
    """Mais de um statement, ou statement que não é consulta."""


class TableNotAllowedError(SqlGuardError):
    """Tabela fora do catálogo (ou sem caminho multi-tenant confirmado)."""


class ColumnNotFoundError(SqlGuardError):
    """Coluna que não existe na tabela — alucinação de campo."""


class AliasAsColumnError(SqlGuardError):
    """Alias PT-BR usado onde o SQL exige a coluna física."""


class ColumnNotFilterableError(SqlGuardError):
    """Coluna de saída usada como filtro (WHERE/JOIN ON) sem ser filtrável."""


class JoinKeyError(SqlGuardError):
    """JOIN por uma chave que o catálogo não declara."""


class TenantFilterError(SqlGuardError):
    """Não há como amarrar o escopo ao grupo da sessão."""


class OutputColumnError(SqlGuardError):
    """Falta a coluna de saída `company_group_id`."""


class RechargesAggregationError(SqlGuardError):
    """`amount`/`cashback_amount` crus em recarga sem a granularidade de item.

    A tabela `ifood_benefits_recharges` denormaliza item e pedido na mesma linha.
    `amount`/`cashback_amount` são campos do item: no nível empresa (sem
    `order_item_id` projetado) precisam de `SUM(...)` + `GROUP BY`.
    """


# Nome curto da tabela de recargas e as medidas que não podem sair cruas no nível
# empresa (têm que virar `SUM`).
_RECARGAS = "ifood_benefits_recharges"
_RECARGA_MEDIDAS = frozenset({"amount", "cashback_amount"})


def guard_query(sql: str, group_id: str) -> str:
    """Valida, amarra ao tenant e devolve o SQL regerado a partir da AST.

    Args:
        sql: SQL como o LLM escreveu.
        group_id: UUID do grupo da sessão (revalidado aqui).

    Returns:
        SQL equivalente, gerado a partir da AST, com o filtro de tenant
        garantido em todo escopo que lê tabela base.

    Raises:
        SqlGuardError: qualquer violação — todas são `QueryNotAllowedError`.
    """
    group_id = validate_group_id(group_id)

    root = _parse_single_query(sql)
    _reject_forbidden_nodes(root)
    _check_tables_are_allowed(root)

    for select in root.find_all(exp.Select):
        _check_scope_columns(select)
        _check_join_keys(select)
        _check_filterable_columns(select)
        _check_recharges_aggregation(select)
        _enforce_tenant_scope(select, group_id)

    _check_group_column_in_output(root)

    return root.sql(dialect=DIALECT, comments=False)


# ------------------------------------------------------------ 1, 2 e 3: forma --


def _parse_single_query(sql: str):
    """Exige um único statement de leitura."""
    try:
        statements = [stmt for stmt in sqlglot.parse(sql, dialect=DIALECT) if stmt]
    except sqlglot.ParseError as e:
        raise SqlSyntaxError(f"SQL inválido para o Databricks: {e}") from e

    if not statements:
        raise SqlSyntaxError("SQL vazio.")

    if len(statements) > 1:
        raise StatementNotAllowedError(
            f"A query deve ter um único statement; vieram {len(statements)}. "
            "Não use ';' para encadear comandos."
        )

    root = statements[0]
    if not isinstance(root, (exp.Select, exp.SetOperation)):
        raise StatementNotAllowedError(
            f"Só é permitido SELECT (com WITH/UNION); veio "
            f"{type(root).__name__.upper()}."
        )

    return root


def _reject_forbidden_nodes(root) -> None:
    for node in root.walk():
        if isinstance(node, _FORBIDDEN_NODES):
            raise StatementNotAllowedError(
                f"Comando não permitido em consulta de relatório: "
                f"{type(node).__name__.upper()}."
            )


# ---------------------------------------------------------- 4: allowlist --


def _check_tables_are_allowed(root) -> None:
    """Toda tabela referenciada precisa estar no catálogo.

    Nomes de CTE também aparecem como `Table` na AST e são ignorados — eles
    apontam para um `SELECT` que já é validado por conta própria.
    """
    cte_names = {cte.alias_or_name.lower() for cte in root.find_all(exp.CTE)}

    for node in root.find_all(exp.Table):
        reference = _qualified_name(node)
        if reference.lower() in cte_names:
            continue

        if find_table(reference) is None:
            raise TableNotAllowedError(
                f"A tabela `{reference}` não está no catálogo de tabelas "
                f"permitidas. Use uma destas: "
                f"{', '.join(sorted(t.path for t in allowed_tables().values()))}."
            )


def _qualified_name(table: exp.Table) -> str:
    return ".".join(part for part in (table.catalog, table.db, table.name) if part)


# ------------------------------------------ 5: colunas e chaves de JOIN --


def _check_scope_columns(select: exp.Select) -> None:
    """Toda coluna citada existe — e existe na tabela em que foi citada.

    Escopo que enxerga CTE ou subquery é pulado: não dá para saber quais
    colunas elas expõem sem resolver o SELECT de dentro, que já é validado
    por conta própria.
    """
    if not _sources_are_transparent(select):
        return

    aliases = _visible_aliases(select)
    if not aliases:
        return

    # Alias de saída pode ser usado em GROUP BY/ORDER BY/HAVING — o Spark
    # resolve. O que não pode é o alias aparecer sem ter sido declarado.
    output_aliases = {
        item.alias.lower() for item in select.expressions if isinstance(item, exp.Alias)
    }
    scope_tables = list(dict.fromkeys(aliases.values()))

    # Coluna sem qualificador só pode ser cobrada quando todos os escopos
    # visíveis são tabelas do catálogo; com um CTE acima, ela pode vir de lá.
    strict = _chain_is_transparent(select)

    for column in _scope_columns(select):
        if isinstance(column.this, exp.Star):
            continue

        table, path = _resolve_column(column, aliases)
        if table is not None:
            _assert_column_exists(path, [table])
        elif strict and path.lower() not in output_aliases:
            _assert_column_exists(path, scope_tables)


def _assert_column_exists(path: str, tables: list[Table]) -> None:
    if any(table.has_column(path) for table in tables):
        return

    # o erro mais comum: Alias PT-BR usado como se fosse a coluna física
    for table in tables:
        real = table.column_for_alias(path)
        if real is not None:
            raise AliasAsColumnError(
                f"`{path}` é o Alias PT-BR de `{table.name}.{real.name}`, não uma "
                f"coluna. No SELECT use `{table.name}.{real.name} AS {path}`; em "
                f"WHERE, JOIN e GROUP BY use a coluna física `{real.name}`."
            )

    onde = ", ".join(f"`{table.name}`" for table in tables)
    raise ColumnNotFoundError(
        f"A coluna `{path}` não existe em {onde}.{_suggestion(path, tables)}"
    )


def _suggestion(path: str, tables: list[Table]) -> str:
    """ "Você quis dizer…" — com o alias PT-BR junto, que é o que confunde."""
    candidates: dict[str, Table] = {}
    for table in tables:
        for column in table.columns:
            candidates.setdefault(column.name, table)
            if column.alias:
                candidates.setdefault(column.alias, table)

    matches = get_close_matches(path, list(candidates), n=1, cutoff=0.6)
    if not matches:
        return ""

    match = matches[0]
    table = candidates[match]
    real = table.column_for_alias(match)
    if real is not None:
        return (
            f" Você quis dizer `{real.name}`, cujo alias é `{real.alias}`? "
            f"(em `{table.name}`)"
        )
    return f" Você quis dizer `{table.name}.{match}`?"


def _check_join_keys(select: exp.Select) -> None:
    """O `ON` liga as tabelas por onde o catálogo manda ligar."""
    if not _sources_are_transparent(select):
        return

    aliases = _visible_aliases(select)

    for join in select.args.get("joins") or []:
        condition = join.args.get("on")
        if condition is None:
            # CROSS JOIN não tem chave alguma; USING continua fora da conferência
            # por ora, mas não pode servir de porta para JOIN sem igualdade.
            if join.args.get("using"):
                continue
            raise JoinKeyError(
                "O JOIN não usa uma chave de igualdade entre colunas do catálogo."
            )

        pairs = []
        for conjunct in _top_level_conjuncts(condition):
            if not isinstance(conjunct, exp.EQ):
                continue
            left, right = conjunct.this, conjunct.expression
            if not (isinstance(left, exp.Column) and isinstance(right, exp.Column)):
                continue

            left_table, left_path = _resolve_column(left, aliases)
            right_table, right_path = _resolve_column(right, aliases)
            if left_table is None or right_table is None:
                continue
            if left_table.name == right_table.name:
                continue

            pairs.append(((left_table.name, left_path), (right_table.name, right_path)))

        if not pairs:
            raise JoinKeyError(
                "O JOIN não usa uma igualdade entre colunas de tabelas do catálogo."
            )

        if not any(is_declared_join(left, right) for left, right in pairs):
            raise JoinKeyError(_join_key_message(pairs))


def _join_key_message(pairs: list[tuple[tuple[str, str], tuple[str, str]]]) -> str:
    (first_table, _), (second_table, _) = pairs[0]
    usadas = "; ".join(
        f"{left[0]}.{left[1]} = {right[0]}.{right[1]}" for left, right in pairs
    )
    declaradas = declared_joins_between(first_table, second_table)

    if declaradas:
        return (
            f"O JOIN entre `{first_table}` e `{second_table}` usa uma chave que o "
            f"catálogo não declara ({usadas}). O catálogo declara: "
            f"{'; '.join(declaradas)}."
        )
    return (
        f"O catálogo não declara ligação direta entre `{first_table}` e "
        f"`{second_table}` — o JOIN usado ({usadas}) não existe no schema."
    )


def _visible_aliases(select: exp.Select) -> dict[str, Table]:
    """Aliases de tabela visíveis neste escopo, incluindo os dos escopos acima.

    Subquery correlacionada enxerga o alias de fora; sem isso, uma referência
    legítima viraria "coluna inexistente".
    """
    visible: dict[str, Table] = {}

    scope = select
    while scope is not None:
        for table, alias in _base_sources(scope):
            visible.setdefault(alias, table)
        scope = _enclosing_select(scope)

    return visible


def _sources_are_transparent(select: exp.Select) -> bool:
    """As fontes **deste** escopo são todas tabelas do catálogo?

    Uma subquery ou um CTE no `FROM` são opacos: só o SELECT de dentro sabe
    quais colunas expõe — e ele é validado no seu próprio escopo.
    """
    return all(
        isinstance(node, exp.Table) and find_table(_qualified_name(node)) is not None
        for node in _source_nodes(select)
    )


def _chain_is_transparent(select: exp.Select) -> bool:
    """Idem, incluindo os escopos que envolvem este."""
    scope = select
    while scope is not None:
        if not _sources_are_transparent(scope):
            return False
        scope = _enclosing_select(scope)
    return True


def _scope_columns(select: exp.Select):
    """Colunas deste escopo — as de subquery pertencem ao escopo de dentro."""
    for column in select.find_all(exp.Column):
        if _enclosing_select(column) is select:
            yield column


def _enclosing_select(node) -> exp.Select | None:
    parent = node.parent
    while parent is not None:
        if isinstance(parent, exp.Select):
            return parent
        parent = parent.parent
    return None


def _resolve_column(
    column: exp.Column, aliases: dict[str, Table]
) -> tuple[Table | None, str]:
    """Separa a coluna em (tabela, caminho da coluna).

    Devolve `(None, caminho)` quando não há qualificador de tabela — inclui o
    caso de caminho de STRUCT (`company_group.id`), que é resolvido contra
    todas as tabelas do escopo.
    """
    parts = [part.name for part in column.parts]

    if len(parts) > 1 and parts[0] in aliases:
        return aliases[parts[0]], ".".join(parts[1:])

    if len(parts) > 1:
        table = find_table(".".join(parts[:-1]))
        if table is not None:
            return table, parts[-1]

    return None, ".".join(parts)


# ------------------------------------------ 5b: colunas de saída não filtráveis --


def _check_filterable_columns(select: exp.Select) -> None:
    """Rejeita colunas marcadas como "não filtrar" usadas em WHERE/JOIN ON.

    A marcação vem do `Uso` no catálogo (`Relatórios (não filtrar)`). O
    catálogo permite a coluna como saída, mas não como filtro de identificação
    — caso do `employee.name/email/cpf`, que só podem ser filtradas por
    `employee.person_id`.
    """
    if not _sources_are_transparent(select):
        return

    aliases = _visible_aliases(select)
    scope_tables = list(dict.fromkeys(aliases.values()))

    predicates: list[exp.Expression] = []
    where = select.args.get("where")
    if where is not None:
        predicates.append(where.this)
    for join in select.args.get("joins") or []:
        on = join.args.get("on")
        if on is not None:
            predicates.append(on)

    for predicate in predicates:
        for column in predicate.find_all(exp.Column):
            table, path = _resolve_column(column, aliases)
            if table is not None:
                _assert_column_filterable(table, path)
                continue

            # Sem qualificador, vale a regra do escopo: a coluna precisa existir
            # em ao menos uma das tabelas visíveis. Se uma delas marcar a coluna
            # como não filtrável, bloqueia.
            for candidate in scope_tables:
                catalogada = _find_column(candidate, path)
                if catalogada is not None and not catalogada.filterable:
                    raise ColumnNotFilterableError(
                        f"A coluna `{candidate.name}.{catalogada.name}` é de saída "
                        "e não pode ser usada como filtro no WHERE/JOIN ON."
                    )


def _find_column(table: Table, path: str) -> Column | None:
    for column in table.columns:
        if column.name.lower() == path.lower():
            return column
    return None


def _assert_column_filterable(table: Table, path: str) -> None:
    column = _find_column(table, path)
    if column is None or column.filterable:
        return

    raise ColumnNotFilterableError(
        f"A coluna `{table.name}.{column.name}` é de saída e não pode ser usada "
        "como filtro no WHERE/JOIN ON. Use a coluna de filtro documentada no "
        "catálogo para esta tabela."
    )


# ----------------------------------------- 5c: agregação de medidas na recarga --


def _check_recharges_aggregation(select: exp.Select) -> None:
    """Regra explícita: `amount`/`cashback_amount` da recarga não saem crus no nível empresa.

    A tabela `ifood_benefits_recharges` denormaliza item e pedido na mesma linha.
    `amount`/`cashback_amount` são do item: só podem ser projetados crus quando a
    query declara a granularidade de item (alguma coluna de identidade do item na
    saída, ex. `order_item_id`/`product_key`/`employee_id`). Sem isso, é relatório
    de nível empresa e os campos precisam de `SUM(...)` + `GROUP BY`.
    """
    if not _sources_are_transparent(select):
        return

    aliases = _visible_aliases(select)
    if _RECARGAS not in {table.name for table in aliases.values()}:
        return

    # granularidade de item presente em qualquer expressão da saída → medida crua ok
    if _output_mentions_recharge_identity(select, aliases):
        return

    for item in select.expressions:
        column = _extract_column(item)
        if column is None:
            continue
        table, path = _resolve_column(column, aliases)
        if _is_recharge_measure(table, path, aliases):
            raise RechargesAggregationError(
                "`amount` e `cashback_amount` são campos do item da recarga. No "
                "nível empresa (sem coluna de item na saída), agregue-os com "
                "SUM(...) e agrupe por `order_id` e demais campos da recarga: "
                "`SUM(r.amount) AS valor_recarga`, "
                "`SUM(r.cashback_amount) AS valor_cashback`. Para granularidade "
                "de item, projete `r.order_item_id`."
            )


def _extract_column(item: exp.Expression) -> exp.Column | None:
    """Coluna simples por trás de um item do SELECT; `None` para SUM/função/`*`."""
    if isinstance(item, exp.Alias):
        item = item.this
    return item if isinstance(item, exp.Column) else None


def _recharge_item_identity_columns() -> frozenset[str]:
    """Colunas de identidade do item (nível detalhe, exceto medidas) da recarga.

    São o sinal de que a query é de item (uma linha por item), e não de empresa —
    neste caso `amount`/`cashback_amount` podem sair crus. Derivado do catálogo
    (mesma fonte de `is_detalhe_column`), não hardcoded.
    """
    table = find_table(_RECARGAS)
    if table is None:
        return frozenset()
    return frozenset(
        column.name.lower()
        for column in table.columns
        if is_detalhe_column(column) and column.name.lower() not in _RECARGA_MEDIDAS
    )


def _output_mentions_recharge_identity(
    select: exp.Select, aliases: dict[str, Table]
) -> bool:
    """A saída menciona alguma coluna de identidade do item da recarga?"""
    identidade = _recharge_item_identity_columns()
    for item in select.expressions:
        for column in item.find_all(exp.Column):
            table, path = _resolve_column(column, aliases)
            if (
                table is not None
                and table.name == _RECARGAS
                and path.lower() in identidade
            ):
                return True
    return False


def _is_recharge_measure(
    table: Table | None, path: str, aliases: dict[str, Table]
) -> bool:
    """A coluna é uma medida (`amount`/`cashback_amount`) da tabela de recargas?"""
    if path.lower() not in _RECARGA_MEDIDAS:
        return False
    if table is not None:
        return table.name == _RECARGAS
    # coluna sem qualificador: conta se a recarga está em escopo e tem a coluna
    return any(
        t.name == _RECARGAS and path.lower() in t.column_names for t in aliases.values()
    )


# --------------------------------------------------- 6: predicado de tenant --


def _enforce_tenant_scope(select: exp.Select, group_id: str) -> None:
    """Garante o filtro de grupo no `WHERE` deste escopo (mutação in-place).

    Só age em escopos que leem tabela base: um `SELECT` que lê apenas CTE ou
    subquery já está coberto pelo escopo de dentro.
    """
    sources = _base_sources(select)
    if not sources:
        return

    predicate = _tenant_predicate(sources, group_id)
    if predicate is None:
        raise TenantFilterError(_missing_join_message(sources))

    if _has_predicate(select, predicate):
        return

    select.where(predicate, dialect=DIALECT, copy=False)

    # O `where()` do sqlglot conecta com AND no topo (parentizando o que já
    # estava lá). Conferir depois de injetar é barato e fecha a porta para
    # qualquer surpresa do builder.
    if not _has_predicate(select, predicate):  # pragma: no cover - defensivo
        raise TenantFilterError(
            "Não foi possível garantir o filtro de grupo na consulta."
        )


def _source_nodes(select: exp.Select) -> list[exp.Expression]:
    """O que este escopo lê: o `FROM` e cada `JOIN`, sem descer em subquery."""
    nodes = []

    # sqlglot 30 guarda o FROM em `from_`; versões anteriores, em `from`.
    from_clause = select.args.get("from_") or select.args.get("from")
    if from_clause is not None:
        nodes.append(from_clause.this)
    for join in select.args.get("joins") or []:
        nodes.append(join.this)

    return nodes


def _base_sources(select: exp.Select) -> list[tuple[Table, str]]:
    """Tabelas do catálogo lidas diretamente por este escopo, com seus aliases."""
    sources = []
    for node in _source_nodes(select):
        if not isinstance(node, exp.Table):
            continue
        table = find_table(_qualified_name(node))
        if table is not None:
            sources.append((table, node.alias_or_name))
    return sources


def _tenant_predicate(sources: list[tuple[Table, str]], group_id: str) -> exp.EQ | None:
    """Monta `<coluna de grupo> = '<uuid>'` a partir das regras do catálogo.

    Percorre as fontes na ordem em que aparecem (FROM primeiro) e usa a
    primeira que resolve: coluna direta, caminho de STRUCT ou a tabela de apoio
    quando ela também está neste escopo.
    """
    by_name = {table.name: alias for table, alias in sources}

    for table, alias in sources:
        rule = table.tenant

        if rule.strategy in (DIRECT, STRUCT):
            return _equals(f"{alias}.{rule.column}", group_id)

        if rule.strategy == JOIN and rule.join_table in by_name:
            return _equals(f"{by_name[rule.join_table]}.{rule.join_column}", group_id)

    return None


def _equals(column_path: str, group_id: str) -> exp.EQ:
    parts = column_path.split(".")
    keys = ("col", "table", "db", "catalog")
    column = exp.column(**dict(zip(keys, reversed(parts))))
    return exp.EQ(this=column, expression=exp.Literal.string(group_id))


def _has_predicate(select: exp.Select, predicate: exp.EQ) -> bool:
    """Procura o predicado na conjunção de topo do `WHERE`.

    Só conta o que está no topo: um filtro dentro de um ramo de `OR` não
    restringe nada, e é exatamente isso que a validação por regex aceitava.
    """
    where = select.args.get("where")
    if where is None:
        return False

    alvo = predicate.sql(dialect=DIALECT).lower()
    return any(
        conjunct.sql(dialect=DIALECT).lower() == alvo
        for conjunct in _top_level_conjuncts(where.this)
    )


def _top_level_conjuncts(condition: exp.Expression):
    """Decompõe `a AND b AND c`, atravessando parênteses."""
    if isinstance(condition, exp.And):
        yield from _top_level_conjuncts(condition.left)
        yield from _top_level_conjuncts(condition.right)
    elif isinstance(condition, exp.Paren):
        yield from _top_level_conjuncts(condition.this)
    else:
        yield condition


def _missing_join_message(sources: list[tuple[Table, str]]) -> str:
    """Erro acionável: diz qual JOIN falta, com o texto do catálogo."""
    pendentes = [table for table, _ in sources if table.tenant.strategy == JOIN]
    if pendentes:
        table = pendentes[0]
        rule = table.tenant
        return (
            f"A tabela `{table.name}` não tem coluna de grupo: o mesmo SELECT "
            f"precisa de INNER JOIN com `{rule.join_table}` para filtrar por "
            f"`{rule.join_column}`."
        )

    return (
        "Não foi possível determinar por qual coluna filtrar o grupo de "
        "empresas neste SELECT."
    )


# ------------------------------------------- 7: coluna de saída do grupo --


def _check_group_column_in_output(root) -> None:
    """O CSV precisa carregar o grupo: `… AS company_group_id` no SELECT externo."""
    for select in _outermost_selects(root):
        if not any(_is_group_output(item) for item in select.expressions):
            raise OutputColumnError(
                "O SELECT deve expor a coluna de grupo com o alias exato "
                "`company_group_id`, a partir de um campo real da tabela "
                "(ex.: `c.company_group_id AS company_group_id`, "
                "`r.company_group.id AS company_group_id`, "
                "`fa.group_id AS company_group_id`)."
            )


def _outermost_selects(root):
    """Os SELECTs que definem as colunas de saída (os ramos de um UNION)."""
    if isinstance(root, exp.SetOperation):
        yield from _outermost_selects(root.left)
        yield from _outermost_selects(root.right)
    elif isinstance(root, exp.Select):
        yield root


def _is_group_output(item: exp.Expression) -> bool:
    if isinstance(item, exp.Alias):
        return item.alias.lower() == "company_group_id" and isinstance(
            item.this, exp.Column
        )
    # coluna sem alias já sai com o nome certo
    return isinstance(item, exp.Column) and item.name.lower() == "company_group_id"
