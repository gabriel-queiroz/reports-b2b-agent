"""LangGraph subgraph for the reports-b2b flow.

Topology:
    reports_b2b_react → END
"""

from langgraph.graph import StateGraph
from langgraph.graph.state import CompiledStateGraph

from domain.agents.graph.agent_state import AgentState
from domain.agents.reports_b2b.reports_react_agent.agent import (
    ReportsB2bReactAgent,
)
from domain.core.logger import Logger
from domain.infra.genplat.genplat_provider import GenplatProvider


class ReportsB2bSubgraph:
    """Reports B2B subgraph with ReAct agent."""

    def __init__(
        self,
        logger: Logger,
        genplat_provider: GenplatProvider,
    ):
        self.logger = logger
        self.reports_b2b_react = ReportsB2bReactAgent(
            logger=logger,
            genplat_provider=genplat_provider,
        )

    def build(self) -> CompiledStateGraph:
        """Build the reports B2B subgraph."""
        workflow = StateGraph(AgentState)

        workflow.add_node("reports_b2b_react", self.reports_b2b_react)
        workflow.set_entry_point("reports_b2b_react")

        return workflow.compile()
