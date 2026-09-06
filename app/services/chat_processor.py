"""Worker-side service for persisting and processing a chat command."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from time import perf_counter
from typing import Any

from elasticsearch import AsyncElasticsearch

from app.agents.food_search import FoodSearchDependencies
from app.agents.conversation_context import ConversationContextBuilder
from app.agents.orchestrator import FoodMindOrchestrator, OrchestratorDependencies
from app.aggregates import Message
from app.database import SessionFactory
from app.messaging.models import ChatCommand, ChatExecutionResult
from app.observability import metrics
from app.observability.tracing import tracing
from app.repositories.chat import ConversationRepository, MessageRepository


EventCallback = Callable[[str, dict[str, Any]], Awaitable[None]]


@dataclass
class ChatProcessor:
    """Run the orchestrator and persist its user and assistant messages."""

    elasticsearch: AsyncElasticsearch
    orchestrator: FoodMindOrchestrator
    retrieval_approach: str | None = None

    async def process(
        self, command: ChatCommand, event_callback: EventCallback
    ) -> ChatExecutionResult:
        """Process one command in a short-lived database session."""
        async with SessionFactory() as session:
            conversations = ConversationRepository(session)
            messages = MessageRepository(session)
            conversation = await conversations.get(command.chat_id)
            if conversation is None or conversation.user_id != command.user_id:
                raise ValueError("Chat does not belong to the command user")
            previous_messages = await messages.list_by_conversation(command.chat_id)
            context = ConversationContextBuilder().build(
                summary=conversation.summary,
                messages=previous_messages,
                current_message=command.content,
            )
            persistence_started = perf_counter()
            with tracing.span("foodmind.message.persist_user") as span:
                try:
                    await messages.create(
                        Message(
                            conversation_id=command.chat_id,
                            role="user",
                            content=command.content,
                        )
                    )
                    await session.commit()
                except Exception:
                    span.set_attribute("foodmind.outcome", "error")
                    metrics.record_message_step(
                        step="persist_user_message",
                        outcome="error",
                        duration_seconds=perf_counter() - persistence_started,
                    )
                    raise
                span.set_attribute("foodmind.outcome", "success")
            metrics.record_message_step(
                step="persist_user_message",
                outcome="success",
                duration_seconds=perf_counter() - persistence_started,
            )
            await event_callback("user_message_persisted", {"chat_id": command.chat_id})

            dependencies = OrchestratorDependencies.from_repositories(
                FoodSearchDependencies.from_client(
                    self.elasticsearch, self.retrieval_approach
                )
            )
            dependencies.event_callback = event_callback
            orchestrator_started = perf_counter()
            with tracing.span("foodmind.message.orchestrator") as span:
                try:
                    result = await self.orchestrator.run(
                        command.content, deps=dependencies, context=context
                    )
                    await event_callback("orchestrator_completed", {})
                except Exception:
                    span.set_attribute("foodmind.outcome", "error")
                    metrics.record_message_step(
                        step="orchestrator",
                        outcome="error",
                        duration_seconds=perf_counter() - orchestrator_started,
                    )
                    raise
                span.set_attribute("foodmind.outcome", "success")
            metrics.record_message_step(
                step="orchestrator",
                outcome="success",
                duration_seconds=perf_counter() - orchestrator_started,
            )

            persistence_started = perf_counter()
            with tracing.span("foodmind.message.persist_assistant") as span:
                try:
                    assistant_message = await messages.create(
                        Message(
                            conversation_id=command.chat_id,
                            role="assistant",
                            content=result.output.answer,
                            agent_name=",".join(result.output.used_agents) or None,
                        )
                    )
                    await session.commit()
                except Exception:
                    await session.rollback()
                    span.set_attribute("foodmind.outcome", "error")
                    metrics.record_message_step(
                        step="persist_assistant_message",
                        outcome="error",
                        duration_seconds=perf_counter() - persistence_started,
                    )
                    raise
                span.set_attribute("foodmind.outcome", "success")
            metrics.record_message_step(
                step="persist_assistant_message",
                outcome="success",
                duration_seconds=perf_counter() - persistence_started,
            )
            await event_callback(
                "assistant_message_persisted", {"chat_id": command.chat_id}
            )
            execution_state = dependencies.execution_state
            return ChatExecutionResult(
                chat_id=command.chat_id,
                message_id=assistant_message.id,
                answer=result.output.answer,
                used_agents=result.output.used_agents,
                selected_agents=(
                    execution_state.selected_agents if execution_state else []
                ),
                completed_steps=(
                    execution_state.completed_steps if execution_state else []
                ),
                errors=(execution_state.errors if execution_state else []),
                durations_ms=(execution_state.durations_ms if execution_state else {}),
            )
