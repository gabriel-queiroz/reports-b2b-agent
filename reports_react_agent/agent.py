"""ReAct agent for reports B2B data consultation."""

from typing import Any

from langchain_core.messages import AIMessage
from langgraph.types import Command

from domain.agents.base.base_agent import BaseAgent
from domain.agents.graph.agent_state import AgentState
from domain.agents.i18n.pt_br import INTERACTION_ERROR_RESPONSE
from domain.agents.reports_b2b.guardrails import (
    InvalidGroupIdError,
    validate_group_id,
)
from domain.agents.reports_b2b.reports_react_agent.prompts import agent_system_prompt
from domain.agents.reports_b2b.tools.execute_query import execute_query
from domain.agents.reports_b2b.tools.get_table_schema import get_table_schema
from domain.agents.reports_b2b.tools.list_fields import list_fields
from domain.agents.reports_b2b.tools.resolve_fields import resolve_fields
from domain.core.logger import Logger
from domain.infra.genplat.genplat_provider import GenplatProvider


class ReportsB2bReactAgent(BaseAgent):
    """ReAct agent for reports B2B data queries.

    Um agente só: conversa com o usuário, consulta o catálogo sob demanda
    (`list_fields`, `resolve_fields`, `get_table_schema`), escreve o SQL e o
    entrega à `execute_query`, que valida no `sql_guard` e pede o relatório.
    Se o guard recusar, o motivo volta como resultado da tool e o agente
    corrige no próprio loop.
    """

    TOOLS = [list_fields, resolve_fields, get_table_schema, execute_query]

    def __init__(
        self,
        logger: Logger,
        genplat_provider: GenplatProvider,
    ):
        self.logger = logger
        self.genplat_provider = genplat_provider

        # O group_id entra por sessão em `_build_system_prompt`.
        super().__init__(
            name="reports_b2b_react",
            system_prompt=agent_system_prompt(group_id=None),
            tools=self.TOOLS,
            state_schema=AgentState,
        )

    def _create_llm(self):
        return self.genplat_provider.create_llm(
            model="gemini-3.1-pro-preview",
            temperature=0,
        )

    def _build_system_prompt(self, state: dict) -> str:
        """Build system prompt with the group_id of THIS state.

        O group_id sai do `state`, não de atributo de instância: a instância é
        única no grafo compilado, e com duas sessões concorrentes o prompt de
        um usuário receberia o UUID do outro.
        """
        return agent_system_prompt(group_id=state.get("metadata", {}).get("group_id"))

    @staticmethod
    def _reject_group_id(error_message: str) -> Command:
        """Encerra o turno sem chamar o LLM quando o tenant não é confiável."""
        response = "Missing groupId. Cannot process queries."
        return Command(
            goto="__end__",
            update={
                "response": response,
                "messages": [
                    AIMessage(
                        content=response,
                        id="reports_b2b_react_groupid_validation",
                    )
                ],
                "agent_used": "reports_b2b",
                "current_step": "completed",
                "error_message": error_message,
                "fallback_used": True,
            },
        )

    async def __call__(self, state: dict) -> Command:
        user_id = str(state.get("user_id", "unknown"))
        session_id = str(state.get("session_id", "unknown"))

        self.logger.log_information(
            "🚀 [ReportsB2bReactAgent] Started",
            user_id=user_id,
            session_id=session_id,
        )

        # GUARDRAIL: groupId validation - extract from session metadata
        # (stored at session creation). The metadata dict is passed through
        # from session creation and contains the locked-in group_id
        session_metadata = state.get("metadata", {})
        group_id = session_metadata.get("group_id")

        self.logger.log_information(
            "🔐 [ReportsB2bReactAgent] Validating groupId from session metadata",
            user_id=user_id,
            has_group_id=bool(group_id),
            session_id=session_id,
        )

        if not group_id:
            self.logger.log_warning(
                (
                    "❌ [ReportsB2bReactAgent] groupId validation FAILED - "
                    "missing in session metadata"
                ),
                user_id=user_id,
                session_id=session_id,
            )
            return self._reject_group_id(
                "groupId validation failed: missing group_id in session metadata"
            )

        # GUARDRAIL: o group_id é interpolado em f-string no prompt e no SQL.
        # Só segue adiante como UUID canônico, nunca como o valor cru.
        try:
            group_id = validate_group_id(group_id)
        except InvalidGroupIdError as e:
            self.logger.log_warning(
                "❌ [ReportsB2bReactAgent] groupId validation FAILED - not a UUID",
                user_id=user_id,
                session_id=session_id,
                error=str(e),
            )
            return self._reject_group_id(f"groupId validation failed: {e}")

        # O UUID canônico segue no próprio state: é o que `_build_system_prompt`
        # lê, e é por sessão — nada de atributo de instância, que é
        # compartilhado por todas as sessões do grafo compilado.
        state = {**state, "metadata": {**session_metadata, "group_id": group_id}}

        self.logger.log_information(
            "✅ [ReportsB2bReactAgent] Security passed - starting ReAct loop",
            user_id=user_id,
            session_id=session_id,
            group_id=group_id,
        )

        try:
            return await super().__call__(state)
        except Exception as e:
            self.logger.log_error(
                "reports_b2b_react error",
                e,
                user_id=user_id,
                group_id=group_id,
            )
            return Command(
                goto="__end__",
                update={
                    "response": INTERACTION_ERROR_RESPONSE,
                    "messages": [
                        AIMessage(
                            content=INTERACTION_ERROR_RESPONSE,
                            id="reports_b2b_react_error",
                        )
                    ],
                    "agent_used": "reports_b2b",
                    "current_step": "completed",
                    "error_message": str(e),
                    "fallback_used": True,
                },
            )

    def _build_command(self, structured: Any, state: dict) -> Command:
        user_id = str(state.get("user_id", "unknown"))
        self.logger.log_information(
            "reports_b2b_react response generated",
            user_id=user_id,
        )
        return Command(
            goto="__end__",
            update={
                "response": structured,
                "messages": [
                    AIMessage(
                        content=structured,
                        id="reports_b2b_react_response",
                    )
                ],
                "agent_used": "reports_b2b",
                "current_step": "completed",
                "error_message": None,
                "fallback_used": False,
            },
        )
