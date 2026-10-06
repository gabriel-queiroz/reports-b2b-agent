"""Geração do SQL a partir da pergunta, com o guard de AST na saída.

Não é uma tool: é o miolo chamado pela `execute_query`. O que sai daqui já
passou pelo `sql_guard` — statement de leitura, tabelas e colunas do catálogo,
filtro de tenant e coluna de grupo na saída.
"""

import logging

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from domain.agents.reports_b2b.guardrails import (
    InvalidGroupIdError,
    normalize_cnpj_cpf,
    sanitize_question,
    validate_group_id,
)
from domain.agents.reports_b2b.report_generator.prompts import (
    few_shot,
    sql_system_prompt,
    sql_user_prompt,
)
from domain.agents.reports_b2b.schema_extractor import (
    build_requested_fields_block,
    full_documentation,
    get_all_tables_for_sql_generation,
)
from domain.agents.reports_b2b.sql_guard import SqlGuardError, guard_query
from domain.core.ioc import get_logger
from domain.infra.genplat.genplat_provider import GenplatProvider

logger = logging.getLogger(__name__)

# Tentativas de geração de SQL. A partir da segunda, o LLM recebe o erro da
# tentativa anterior — antes disso, todas as validações tentavam duas vezes com
# exatamente o mesmo prompt.
MAX_SQL_ATTEMPTS = 2


class GeneratedQuery(BaseModel):
    """Query SQL gerada a partir da pergunta do usuário."""

    sql: str = Field(
        description=(
            "Query SELECT completa para Databricks (Spark SQL), "
            "sem markdown e sem explicações."
        )
    )


# Global LLM instance (will be initialized lazily)
_llm_instance: ChatOpenAI | None = None
_genplat_provider: GenplatProvider | None = None
_schema_content: str | None = None
_tables_doc: str | None = None


def _initialize_llm(genplat_provider: GenplatProvider) -> ChatOpenAI:
    """Initialize the LLM instance (lazy initialization).

    `temperature=0`: geração de SQL não se beneficia de variedade — a mesma
    pergunta deve dar a mesma query, e é isso que torna o golden set (fase 6)
    capaz de medir mudança de prompt.

    `max_tokens` alto: relatório com muitos campos trunca o structured output,
    e o SQL cortado chega ao usuário parecendo alucinação.
    """
    global _llm_instance, _genplat_provider
    if _llm_instance is None:
        _genplat_provider = genplat_provider
        _llm_instance = genplat_provider.create_llm(
            model="gpt-4.1",
            temperature=0,
            max_tokens=4096,
        )
    return _llm_instance


def _correction_message(rejected_sql: str, error: SqlGuardError) -> str:
    """A mensagem de correção que realimenta o LLM na próxima tentativa.

    Vai como turno de `user` (e não de `assistant`) de propósito: o structured
    output ocupa o turno do assistente, e nem todo provider aceita um turno de
    assistente avulso no meio.
    """
    return (
        "A query abaixo foi REJEITADA pela validação. Corrija o que o erro "
        "aponta e devolva a query completa e corrigida — não explique.\n\n"
        f"Query rejeitada:\n{rejected_sql}\n\n"
        f"Motivo da rejeição ({type(error).__name__}):\n{error}"
    )


def _load_schema() -> str:
    """O catálogo inteiro (`data/tabelas/`) num texto só, para o `sql_system.txt`.

    Transitório: some junto com este gerador quando o prompt único passar a
    consultar tabela a tabela. Sem o catálogo, falha — antes devolvia um texto
    de "schema não disponível" e o LLM gerava SQL às cegas.
    """
    global _schema_content
    if _schema_content is None:
        _schema_content = full_documentation()
    return _schema_content


def _load_tables_doc() -> str:
    """Documentação das tabelas para o prompt de SQL (o catálogo inteiro)."""
    global _tables_doc
    if _tables_doc is None:
        _tables_doc = _load_schema()
    return _tables_doc


async def _generate_sql_internal(
    question: str,
    domain: str,
    group_id: str,
    genplat_provider: GenplatProvider,
    desired_fields: str = "all",
) -> str:
    """
    Generate SQL from question, validating fields against documentation.

    É `async` porque a chamada do LLM é a parte lenta e roda dentro de uma tool
    async: com `invoke` síncrono, o event loop ficava parado durante toda a
    geração, segurando as outras sessões.

    Args:
        question: User question
        domain: Data domain
        group_id: Company group UUID for data filtering
            (MANDATORY for multi-tenant safety)
        genplat_provider: GenPlat provider for LLM creation
        desired_fields: "all" ou rótulos de Exibição separados por vírgula.
            É propagado ao prompt como <campos_solicitados>, para o SQL projetar
            exatamente os campos confirmados com o usuário.

    Returns:
        Valid SQL to execute

    Raises:
        InvalidGroupIdError: If group_id is missing or is not a UUID
        InvalidQuestionError: If the question is empty or too long
        InvalidDesiredFieldsError: If a requested field does not resolve against
            the domain catalog
        SqlGuardError: If the AST guard rejects the query (a QueryNotAllowedError)
    """
    log = get_logger()

    log.log_information(
        "Starting SQL generation",
        domain=domain,
        question_length=len(question),
    )

    # GUARDRAIL: este é o ponto onde o group_id vira f-string (prompt e, depois,
    # WHERE do SQL). Daqui para baixo só circula o UUID canônico.
    try:
        group_id = validate_group_id(group_id)
    except InvalidGroupIdError as e:
        log.log_error("group_id invalid for SQL generation", e, domain=domain)
        raise

    # A pergunta é interpolada dentro de <pergunta> no prompt do usuário.
    question = sanitize_question(question)

    # CNPJ/CPF formatados não existem no Databricks: normaliza antes de o LLM
    # transformar a pergunta em filtro.
    question = normalize_cnpj_cpf(question)

    # `desired_fields` vira um bloco rígido no prompt: sem ele, o LLM decidia as
    # colunas sozinho e ignorava o que o usuário tinha confirmado na conversa.
    requested_fields = build_requested_fields_block(domain, desired_fields)

    # Load documentation
    tables_doc = _load_tables_doc()

    # Get all tables from the catalog for SQL generation
    # LLM needs to see all tables to understand relationships and create proper JOINs
    tables = get_all_tables_for_sql_generation()

    # Instrução de segurança multi-tenant. Não nomeia uma coluna fixa: cada
    # tabela tem a sua (linha **Multi-tenant** de cada tabela no catálogo), e
    # apontar `companies.company_group_id` para todas — como era feito aqui —
    # contradizia o próprio catálogo.
    group_id_restriction = (
        f"Toda query DEVE filtrar pelo grupo '{group_id}', usando a coluna de "
        f"grupo da própria tabela consultada (ou o JOIN indicado no catálogo "
        f"quando ela não tiver uma). Sem esse filtro a query é REJEITADA."
    )

    # Create prompts for SQL generation
    sql_system = sql_system_prompt(
        group_id_restriction=group_id_restriction,
        tables_documentation=tables_doc,
        group_id=group_id,
    )
    sql_user = sql_user_prompt(
        domain=domain,
        tables=tables,
        question=question,
        group_id=group_id,
        requested_fields=requested_fields,
        examples=few_shot(),
    )

    # Initialize LLM
    llm = _initialize_llm(genplat_provider)
    llm_with_struct = llm.with_structured_output(GeneratedQuery)

    # A conversa cresce a cada tentativa: o erro do guard entra como mensagem,
    # senão o retry reinvoca o prompt idêntico e só gasta uma chamada de LLM.
    messages = [("system", sql_system), ("user", sql_user)]

    for attempt in range(1, MAX_SQL_ATTEMPTS + 1):
        log.log_information(
            "Generating SQL with LLM",
            domain=domain,
            attempt=attempt,
            max_attempts=MAX_SQL_ATTEMPTS,
        )

        response: GeneratedQuery = await llm_with_struct.ainvoke(messages)
        sql = response.sql

        log.log_information(
            "LLM SQL generated",
            domain=domain,
            sql_length=len(sql),
            sql=sql,
        )

        # Guard de AST: statement único de leitura, tabelas do catálogo, filtro
        # de tenant injetado e conferido na árvore, coluna de grupo na saída.
        # O que volta é o SQL regerado a partir da AST — não a string do LLM.
        try:
            sql = guard_query(sql, group_id)
            log.log_information(
                "SQL generated successfully",
                domain=domain,
                sql_length=len(sql),
                sql=sql,
            )
            return sql
        except SqlGuardError as e:
            log.log_warning(
                "AST guard rejected the query",
                domain=domain,
                attempt=attempt,
                max_attempts=MAX_SQL_ATTEMPTS,
                reason=type(e).__name__,
                error=str(e),
            )
            if attempt < MAX_SQL_ATTEMPTS:
                messages.append(("user", _correction_message(sql, e)))
                continue

            log.log_error(
                "SQL generation failed after all attempts",
                e,
                domain=domain,
                max_attempts=MAX_SQL_ATTEMPTS,
            )
            raise
