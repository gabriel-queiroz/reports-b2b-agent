"""Resolução de imports e dublê de LLM para os testes.

Os testes importam o agente pelo caminho de produção
(`domain.agents.reports_b2b.…`). No projeto principal o pacote `domain` já
existe e o bloco abaixo não faz nada — este arquivo pode ir junto sem ajuste.

Fora dele, cai na camada de `_local/`, que é o andaime descartável.
"""

import sys
from pathlib import Path

import pytest

_RAIZ = Path(__file__).resolve().parent.parent

try:  # projeto principal: o `domain` real está instalado
    import domain  # noqa: F401
except ModuleNotFoundError:  # repositório isolado: usa o andaime de `_local/`
    sys.path.insert(0, str(_RAIZ / "_local"))
    sys.path.insert(0, str(_RAIZ))


SQL_ACEITO = (
    "SELECT c.social_name AS razao_social_empresa, "
    "c.company_group_id AS company_group_id, "
    "COUNT(*) AS total_colaboradores "
    "FROM main.ifoodoffice_management_silver.employee e "
    "INNER JOIN fintech_companies.companies c ON e.company_id = c.company_id "
    "WHERE e.deleted = false "
    "GROUP BY c.social_name, c.company_group_id "
    "LIMIT 1000"
)


class _LLMEstruturado:
    """Imita `llm.with_structured_output(Schema)`, guardando o que recebeu."""

    def __init__(self, schema, respostas, chamadas):
        self._schema = schema
        self._respostas = respostas
        self._chamadas = chamadas

    async def ainvoke(self, mensagens):
        """O agente chama o LLM por `ainvoke` — é assim que a tool não trava o loop."""
        self._chamadas.append(list(mensagens))
        indice = min(len(self._chamadas) - 1, len(self._respostas) - 1)
        return self._schema(sql=self._respostas[indice])


class _LLM:
    def __init__(self, respostas, chamadas):
        self._respostas = respostas
        self._chamadas = chamadas

    def with_structured_output(self, schema):
        return _LLMEstruturado(schema, self._respostas, self._chamadas)


class ProviderEspiao:
    """Provider de LLM que registra os prompts em vez de chamar modelo algum.

    Recebe uma resposta por tentativa; a última se repete se o código insistir.
    """

    def __init__(self, *respostas: str):
        self.chamadas: list[list] = []
        self.parametros_llm: dict = {}
        self._respostas = list(respostas) or [SQL_ACEITO]

    def create_llm(self, **kwargs):
        self.parametros_llm = kwargs
        return _LLM(self._respostas, self.chamadas)

    def prompt_do_usuario(self, chamada: int = -1) -> str:
        """Texto da última mensagem `user` de uma das chamadas ao modelo."""
        papel, conteudo = self.chamadas[chamada][-1]
        assert papel == "user"
        return conteudo


@pytest.fixture
def provider():
    """Espião com o SQL padrão, e o LLM global do módulo zerado entre testes."""
    from domain.agents.reports_b2b.report_generator.tools import generate_query_tool

    generate_query_tool._llm_instance = None
    yield ProviderEspiao()
    generate_query_tool._llm_instance = None


@pytest.fixture
def provider_factory():
    """Como `provider`, mas com as respostas do LLM definidas pelo teste."""
    from domain.agents.reports_b2b.report_generator.tools import generate_query_tool

    generate_query_tool._llm_instance = None
    criados = []

    def criar(*respostas: str) -> ProviderEspiao:
        espiao = ProviderEspiao(*respostas)
        criados.append(espiao)
        return espiao

    yield criar
    generate_query_tool._llm_instance = None
