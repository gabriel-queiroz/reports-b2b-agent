"""Fase 5 — o tenant é da sessão, não da instância do agente.

A instância do agente é **única** no grafo compilado: guardar `group_id` em
`self` significa que a segunda sessão sobrescreve a primeira, e o prompt de um
usuário pode sair com o UUID de outro. Este teste roda duas sessões
concorrentes de verdade e cobra o UUID certo em cada prompt.
"""

import asyncio

import pytest
from domain.agents.base.base_agent import BaseAgent
from domain.agents.reports_b2b.reports_react_agent.agent import ReportsB2bReactAgent
from langgraph.types import Command

GROUP_A = "550e8400-e29b-41d4-a716-446655440000"
GROUP_B = "6ba7b810-9dad-11d1-80b4-00c04fd430c8"


class SilentLogger:
    def log_information(self, *_args, **_kwargs):
        pass

    log_warning = log_information
    log_error = log_information


@pytest.fixture
def agent(provider):
    return ReportsB2bReactAgent(logger=SilentLogger(), genplat_provider=provider)


def session(group_id, user_id="u-1"):
    return {
        "message": "colaboradores ativos",
        "user_id": user_id,
        "session_id": f"s-{user_id}",
        "metadata": {"group_id": group_id},
    }


def test_prompt_uses_group_id_from_received_state(agent):
    prompt_a = agent._build_system_prompt(session(GROUP_A))
    prompt_b = agent._build_system_prompt(session(GROUP_B))

    assert GROUP_A in prompt_a and GROUP_B not in prompt_a
    assert GROUP_B in prompt_b and GROUP_A not in prompt_b


def test_agent_does_not_keep_tenant_on_instance(agent):
    """O atributo de instância era o mecanismo do vazamento."""
    assert not hasattr(agent, "group_id")
    assert not hasattr(agent, "user_id")


def test_two_concurrent_sessions_do_not_swap_groups(agent, monkeypatch):
    """Com `self.group_id`, a sessão que chega depois vencia as duas."""

    async def fake_loop(self, state):
        # devolve o controle ao event loop no meio do turno: é aqui que a
        # outra sessão entrava e sobrescrevia o tenant
        await asyncio.sleep(0.01)
        return Command(
            goto="__end__",
            update={"response": self._build_system_prompt(state)},
        )

    monkeypatch.setattr(BaseAgent, "__call__", fake_loop)

    async def run_agent():
        return await asyncio.gather(
            agent(session(GROUP_A, "u-a")),
            agent(session(GROUP_B, "u-b")),
        )

    command_a, command_b = asyncio.run(run_agent())

    assert GROUP_A in command_a.update["response"]
    assert GROUP_B not in command_a.update["response"]
    assert GROUP_B in command_b.update["response"]
    assert GROUP_A not in command_b.update["response"]


def test_group_id_reaches_prompt_canonical(agent, monkeypatch):
    """O `__call__` normaliza o UUID e é a forma normalizada que segue no state."""

    async def fake_loop(self, state):
        return Command(
            goto="__end__",
            update={"response": self._build_system_prompt(state)},
        )

    monkeypatch.setattr(BaseAgent, "__call__", fake_loop)

    command = asyncio.run(agent(session(GROUP_A.upper())))

    assert GROUP_A in command.update["response"]
    assert GROUP_A.upper() not in command.update["response"]


def test_agent_registers_catalog_tools_and_execute_query(agent):
    """Um agente só: sem gerador de SQL separado por trás da `execute_query`."""
    names = {tool.name for tool in agent.tools}

    assert names == {"list_fields", "resolve_fields", "get_table_schema", "execute_query"}


def test_session_without_valid_tenant_does_not_enter_loop(agent, monkeypatch):
    called = []

    async def fake_loop(self, state):  # pragma: no cover - não deve rodar
        called.append(state)
        return Command(goto="__end__", update={})

    monkeypatch.setattr(BaseAgent, "__call__", fake_loop)

    command = asyncio.run(agent(session("nao-e-uuid")))

    assert called == []
    assert command.update["fallback_used"] is True
