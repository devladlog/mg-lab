"""The Foundry side. One prompt agent per model, same instructions, the same question sent through each agent.

API shape (Learn, "Quickstart: Create a prompt agent", Azure AI Projects 2.x, Foundry projects (new) API):
  project = AIProjectClient(endpoint=..., credential=DefaultAzureCredential())
  project.agents.create_version(agent_name=..., definition=PromptAgentDefinition(model=<deployment name>, instructions=...))
  openai = project.get_openai_client(agent_name=...)         # OpenAI client bound to the agent
  conversation = openai.conversations.create()
  openai.responses.create(conversation=conversation.id, input=...)
The `model` of a prompt agent is the name of a model DEPLOYMENT in the project's Foundry resource.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class AgentHandle:
    name: str
    version: str
    model: str


@dataclass
class Answer:
    text: str
    input_tokens: int | None
    output_tokens: int | None
    seconds: float
    served_model: str | None = None


class Backend(Protocol):
    def create_agent(self, name: str, model: str, instructions: str) -> AgentHandle: ...
    def ask(self, agent: AgentHandle, question: str) -> Answer: ...
    def delete_agent(self, agent: AgentHandle) -> None: ...


def agent_name_for(prefix: str, model: str) -> str:
    """Lowercase letters, digits and hyphens only, so it is a safe agent name. (Learn's samples use names like
    'MyAgent' and 'your-agent-name'; a length or character rule is not stated on the quickstart page.)"""
    slug = re.sub(r"[^a-z0-9]+", "-", model.lower()).strip("-")
    return f"{prefix}-{slug}"[:63].rstrip("-")


class FoundryBackend:
    def __init__(self, project: Any, sleep=time.sleep, max_retries: int = 2):
        self.project = project
        self.sleep = sleep
        self.max_retries = max_retries
        self._clients: dict[str, Any] = {}

    @classmethod
    def from_endpoint(cls, endpoint: str) -> "FoundryBackend":
        from azure.ai.projects import AIProjectClient  # imported late: not needed for scoring or tests
        from azure.identity import DefaultAzureCredential
        return cls(AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential()))

    def create_agent(self, name: str, model: str, instructions: str) -> AgentHandle:
        from azure.ai.projects.models import PromptAgentDefinition
        created = self.project.agents.create_version(
            agent_name=name, definition=PromptAgentDefinition(model=model, instructions=instructions))
        return AgentHandle(name=created.name, version=str(created.version), model=model)

    def ask(self, agent: AgentHandle, question: str) -> Answer:
        client = self._clients.get(agent.name)
        if client is None:
            client = self._clients[agent.name] = self.project.get_openai_client(agent_name=agent.name)
        conversation = client.conversations.create()
        started = time.perf_counter()
        try:
            for attempt in range(self.max_retries + 1):
                try:
                    resp = client.responses.create(conversation=conversation.id, input=question)
                    break
                except Exception as exc:  # noqa: BLE001 - retry only throttling
                    if attempt < self.max_retries and getattr(exc, "status_code", None) == 429:
                        self.sleep(2 ** attempt)
                        continue
                    raise
            seconds = time.perf_counter() - started
            usage = getattr(resp, "usage", None)
            return Answer(text=resp.output_text or "",
                          input_tokens=getattr(usage, "input_tokens", None),
                          output_tokens=getattr(usage, "output_tokens", None),
                          seconds=seconds, served_model=getattr(resp, "model", None))
        finally:
            try:
                client.conversations.delete(conversation.id)
            except Exception:  # noqa: BLE001 - cleanup must not hide the real result
                pass

    def delete_agent(self, agent: AgentHandle) -> None:
        self.project.agents.delete_version(agent.name, agent.version)
