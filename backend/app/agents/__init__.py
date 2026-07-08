"""Deterministic scientific agents for ResearchOS."""

from app.agents.base import BaseAgent, ScientificAgent
from app.agents.manager import AgentManager, create_default_agent_manager

__all__ = ["AgentManager", "BaseAgent", "ScientificAgent", "create_default_agent_manager"]
