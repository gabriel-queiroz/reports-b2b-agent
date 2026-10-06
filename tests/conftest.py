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


ACCEPTED_SQL = (
    "SELECT c.social_name AS razao_social_empresa, "
    "c.company_group_id AS company_group_id, "
    "COUNT(*) AS total_colaboradores "
    "FROM main.ifoodoffice_management_silver.employee e "
    "INNER JOIN fintech_companies.companies c ON e.company_id = c.company_id "
    "WHERE e.deleted = false "
    "GROUP BY c.social_name, c.company_group_id "
    "LIMIT 1000"
)


class _StructuredLLM:
    """Imita `llm.with_structured_output(Schema)`, guardando o que recebeu."""

    def __init__(self, schema, responses, calls):
        self._schema = schema
        self._responses = responses
        self._calls = calls

    async def ainvoke(self, messages):
        """O agente chama o LLM por `ainvoke` — é assim que a tool não trava o loop."""
        self._calls.append(list(messages))
        index = min(len(self._calls) - 1, len(self._responses) - 1)
        return self._schema(sql=self._responses[index])


class _LLM:
    def __init__(self, responses, calls):
        self._responses = responses
        self._calls = calls

    def with_structured_output(self, schema):
        return _StructuredLLM(schema, self._responses, self._calls)


class SpyProvider:
    """Provider de LLM que registra os prompts em vez de chamar modelo algum.

    Recebe uma resposta por tentativa; a última se repete se o código insistir.
    """

    def __init__(self, *responses: str):
        self.calls: list[list] = []
        self.llm_params: dict = {}
        self._responses = list(responses) or [ACCEPTED_SQL]

    def create_llm(self, **kwargs):
        self.llm_params = kwargs
        return _LLM(self._responses, self.calls)

    def user_prompt(self, call: int = -1) -> str:
        """Texto da última mensagem `user` de uma das chamadas ao modelo."""
        role, content = self.calls[call][-1]
        assert role == "user"
        return content


@pytest.fixture
def provider():
    """Espião com o SQL padrão, e o LLM global do módulo zerado entre testes."""
    from domain.agents.reports_b2b.report_generator.tools import generate_query_tool

    generate_query_tool._llm_instance = None
    yield SpyProvider()
    generate_query_tool._llm_instance = None


@pytest.fixture
def provider_factory():
    """Como `provider`, mas com as respostas do LLM definidas pelo teste."""
    from domain.agents.reports_b2b.report_generator.tools import generate_query_tool

    generate_query_tool._llm_instance = None
    created = []

    def create(*responses: str) -> SpyProvider:
        spy = SpyProvider(*responses)
        created.append(spy)
        return spy

    yield create
    generate_query_tool._llm_instance = None
