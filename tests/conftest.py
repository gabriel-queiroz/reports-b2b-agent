"""Resolução de imports e dublê de LLM para os testes.

Os testes importam o agente pelo caminho de produção
(`domain.agents.reports_b2b.…`). No projeto principal o pacote `domain` já
existe e o bloco abaixo não faz nada — este arquivo pode ir junto sem ajuste.

Fora dele, cai na camada de `_local/`, que é o andaime descartável.
"""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent

try:  # projeto principal: o `domain` real está instalado
    import domain  # noqa: F401
except ModuleNotFoundError:  # repositório isolado: usa o andaime de `_local/`
    sys.path.insert(0, str(_ROOT / "_local"))
    sys.path.insert(0, str(_ROOT))


GROUP = "550e8400-e29b-41d4-a716-446655440000"


class FakeProvider:
    """Provider de LLM que só registra os parâmetros de criação.

    O agente cria o LLM no loop ReAct do `BaseAgent` real; aqui nenhum teste
    conversa com modelo.
    """

    def __init__(self):
        self.llm_params: dict = {}

    def create_llm(self, **kwargs):
        self.llm_params = kwargs
        return object()


@pytest.fixture
def provider():
    return FakeProvider()


@pytest.fixture
def reports_calls(monkeypatch):
    """Troca o Reports Service por um dublê que registra o SQL recebido."""
    from domain.agents.reports_b2b import reports_service

    calls: list[dict] = []

    async def fake_generate_reports(sql, group_id=None, user_id=None):
        calls.append({"sql": sql, "group_id": group_id, "user_id": user_id})
        return {"id": "report-123"}

    monkeypatch.setattr(reports_service, "generate_reports", fake_generate_reports)
    return calls
