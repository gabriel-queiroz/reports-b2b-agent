class GenplatProvider:
    """Sem LLM de verdade: os testes usam o `ProviderEspiao` do conftest."""

    def __init__(self, logger=None):
        self.logger = logger

    def create_llm(self, **kwargs):
        raise RuntimeError("stub: nenhum LLM disponível fora do projeto principal")
