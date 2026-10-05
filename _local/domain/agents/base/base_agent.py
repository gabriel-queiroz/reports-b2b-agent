class BaseAgent:
    """Só o contrato que o `ReportsB2bReactAgent` usa; o loop ReAct real fica no projeto principal."""

    def __init__(self, name, system_prompt, tools, state_schema=None):
        self.name = name
        self.system_prompt = system_prompt
        self.tools = tools
        self.state_schema = state_schema

    def _build_system_prompt(self, state):
        return self.system_prompt

    async def __call__(self, state):
        raise NotImplementedError("stub: o loop ReAct real fica no projeto principal")
