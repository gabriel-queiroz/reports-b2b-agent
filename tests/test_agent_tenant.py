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

GRUPO_A = "550e8400-e29b-41d4-a716-446655440000"
GRUPO_B = "6ba7b810-9dad-11d1-80b4-00c04fd430c8"


class LoggerMudo:
    def log_information(self, *_args, **_kwargs):
        pass

    log_warning = log_information
    log_error = log_information


@pytest.fixture
def agente(provider):
    return ReportsB2bReactAgent(logger=LoggerMudo(), genplat_provider=provider)


def sessao(group_id, user_id="u-1"):
    return {
        "message": "colaboradores ativos",
        "user_id": user_id,
        "session_id": f"s-{user_id}",
        "metadata": {"group_id": group_id},
    }


def test_prompt_usa_o_group_id_do_state_recebido(agente):
    prompt_a = agente._build_system_prompt(sessao(GRUPO_A))
    prompt_b = agente._build_system_prompt(sessao(GRUPO_B))

    assert GRUPO_A in prompt_a and GRUPO_B not in prompt_a
    assert GRUPO_B in prompt_b and GRUPO_A not in prompt_b


def test_agente_nao_guarda_tenant_na_instancia(agente):
    """O atributo de instância era o mecanismo do vazamento."""
    assert not hasattr(agente, "group_id")
    assert not hasattr(agente, "user_id")


def test_duas_sessoes_concorrentes_nao_trocam_de_grupo(agente, monkeypatch):
    """Com `self.group_id`, a sessão que chega depois vencia as duas."""

    async def loop_falso(self, state):
        # devolve o controle ao event loop no meio do turno: é aqui que a
        # outra sessão entrava e sobrescrevia o tenant
        await asyncio.sleep(0.01)
        return Command(
            goto="__end__",
            update={"response": self._build_system_prompt(state)},
        )

    monkeypatch.setattr(BaseAgent, "__call__", loop_falso)

    async def rodar():
        return await asyncio.gather(
            agente(sessao(GRUPO_A, "u-a")),
            agente(sessao(GRUPO_B, "u-b")),
        )

    comando_a, comando_b = asyncio.run(rodar())

    assert GRUPO_A in comando_a.update["response"]
    assert GRUPO_B not in comando_a.update["response"]
    assert GRUPO_B in comando_b.update["response"]
    assert GRUPO_A not in comando_b.update["response"]


def test_group_id_chega_canonico_ao_prompt(agente, monkeypatch):
    """O `__call__` normaliza o UUID e é a forma normalizada que segue no state."""

    async def loop_falso(self, state):
        return Command(
            goto="__end__",
            update={"response": self._build_system_prompt(state)},
        )

    monkeypatch.setattr(BaseAgent, "__call__", loop_falso)

    comando = asyncio.run(agente(sessao(GRUPO_A.upper())))

    assert GRUPO_A in comando.update["response"]
    assert GRUPO_A.upper() not in comando.update["response"]


def test_prompt_descreve_a_tool_como_ela_e():
    """O prompt mandava chamar `execute_query(pergunta=, dominio=, group_id=…)`.

    Nenhum desses parâmetros existe no schema — o modelo era instruído a chamar
    uma ferramenta que não é a que está registrada.
    """
    from domain.agents.reports_b2b.report_generator.prompts import agent_system_prompt
    from domain.agents.reports_b2b.tools.execute_query import ExecuteQueryInput

    prompt = agent_system_prompt(dominios="qualquer", group_id=GRUPO_A)
    parametros = set(ExecuteQueryInput.model_fields)

    assert parametros == {"question", "domain", "desired_fields"}
    for parametro in parametros:
        assert f"{parametro}=" in prompt

    for inexistente in ("pergunta=", "dominio=", "campos_desejados=", "group_id="):
        assert inexistente not in prompt


def test_sessao_sem_tenant_valido_nao_entra_no_loop(agente, monkeypatch):
    chamou = []

    async def loop_falso(self, state):  # pragma: no cover - não deve rodar
        chamou.append(state)
        return Command(goto="__end__", update={})

    monkeypatch.setattr(BaseAgent, "__call__", loop_falso)

    comando = asyncio.run(agente(sessao("nao-e-uuid")))

    assert chamou == []
    assert comando.update["fallback_used"] is True
