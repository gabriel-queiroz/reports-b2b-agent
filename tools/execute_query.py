"""Tool que recebe o SQL escrito pelo agente, valida e pede o relatório.

O SQL vem pronto do próprio agente ReAct — não existe mais um segundo LLM
gerando a query. Quem garante a segurança continua sendo o `sql_guard`: statement
único de leitura, tabelas e colunas do catálogo, JOIN por chave declarada,
filtro de tenant conferido (e injetado se faltar) na AST, coluna de grupo na
saída. O que vai para o Reports Service é o SQL regerado a partir da AST, nunca
a string do modelo.

Quando o guard recusa, o motivo volta como resultado da tool
(`"status": "invalid_sql"`) e o agente corrige na mesma conversa — o retry que
antes ficava escondido dentro do gerador agora é o próprio loop ReAct.
"""

import json
import re
from typing import Annotated

from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState
from pydantic import BaseModel, Field

from domain.agents.reports_b2b.guardrails import (
    InvalidGroupIdError,
    normalize_cnpj_cpf,
    validate_group_id,
)
from domain.agents.reports_b2b.sql_guard import SqlGuardError, guard_query
from domain.core.ioc import get_logger

# Acima disso não é uma consulta de relatório: é conteúdo tentando ocupar a
# janela de contexto ou o parser. O maior exemplo do few-shot tem ~2k.
MAX_SQL_LENGTH = 20_000

# Literal SQL entre aspas simples ('' é aspa escapada dentro dele).
_STRING_LITERAL_RE = re.compile(r"'((?:[^']|'')*)'")

SUCCESS_MESSAGE = (
    "Seu relatório será gerado em .csv e irá chegar na central de notificação"
)


class ExecuteQueryInput(BaseModel):
    """Input for the query execution tool."""

    sql: str = Field(
        description=(
            "Query SELECT completa para Databricks (Spark SQL), sem markdown e "
            "sem explicações, escrita com os schemas de get_table_schema e os "
            "campos de resolve_fields."
        )
    )


def _response(status: str, message: str, **extra) -> str:
    return json.dumps({"status": status, "message": message, **extra}, ensure_ascii=False)


@tool(args_schema=ExecuteQueryInput)
async def execute_query(
    sql: str,
    state: Annotated[dict, InjectedState],
) -> str:
    """Valida o SQL e pede a geração do relatório em .csv.

    Retorna JSON com "status":
    - "success": relatório pedido.
    - "invalid_sql": o SQL foi recusado; "message" diz o motivo. Corrija e
      chame de novo.
    - "error": problema na sessão ou no serviço; não adianta reescrever o SQL.

    O group_id e o user_id vêm do state da sessão, nunca do modelo.
    """
    logger = get_logger()

    metadata = state.get("metadata", {})
    user_id = state.get("user_id", "unknown")

    # GUARDRAIL: sem tenant válido não há consulta.
    try:
        group_id = validate_group_id(metadata.get("group_id"))
    except InvalidGroupIdError as e:
        logger.log_warning(
            "execute_query blocked: invalid group_id", user_id=user_id, error=str(e)
        )
        return _response(
            "error",
            "Não foi possível identificar o grupo de empresas desta sessão. "
            "A consulta não foi executada.",
        )

    if not isinstance(sql, str) or not sql.strip():
        return _response("invalid_sql", "O SQL está vazio.")
    if len(sql) > MAX_SQL_LENGTH:
        return _response(
            "invalid_sql",
            f"O SQL tem {len(sql)} caracteres e excede o limite de {MAX_SQL_LENGTH}.",
        )

    # CNPJ/CPF formatados não existem no Databricks. Só os literais são
    # normalizados: a máscara aceita espaço como separador e, aplicada ao SQL
    # inteiro, poderia casar com uma sequência de identificadores.
    sql = _STRING_LITERAL_RE.sub(lambda m: f"'{normalize_cnpj_cpf(m.group(1))}'", sql)

    try:
        sql = guard_query(sql, group_id)
    except SqlGuardError as e:
        logger.log_warning(
            "execute_query: SQL rejected by guard",
            user_id=user_id,
            reason=type(e).__name__,
            error=str(e),
        )
        return _response("invalid_sql", f"{type(e).__name__}: {e}")

    logger.log_information(
        "execute_query: SQL accepted, calling Reports Service",
        user_id=user_id,
        group_id=group_id,
        sql_length=len(sql),
        sql=sql,
    )

    try:
        from domain.agents.reports_b2b.reports_service import generate_reports

        result = await generate_reports(sql, group_id=group_id, user_id=user_id)
    except Exception as e:
        logger.log_error("execute_query: Reports Service failed", e, user_id=user_id)
        return _response(
            "error",
            "Ocorreu um problema temporário ao pedir o relatório. Tente novamente em instantes.",
        )

    report_id = result.get("id")
    logger.log_information(
        "Report generation requested successfully",
        report_id=report_id,
        user_id=user_id,
    )
    return _response("success", SUCCESS_MESSAGE, report_id=report_id)
