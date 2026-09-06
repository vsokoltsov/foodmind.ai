"""NiceGUI interface for the FoodMind chat API."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

import httpx
from nicegui import app, ui


API_URL = os.getenv("FOODMIND_API_URL", "http://localhost:8000").rstrip("/")
STORAGE_SECRET = os.getenv("NICEGUI_STORAGE_SECRET")
REQUEST_TIMEOUT = httpx.Timeout(connect=10, read=30, write=30, pool=30)
STREAM_TIMEOUT = httpx.Timeout(connect=10, read=1800, write=30, pool=30)


@dataclass
class FoodMindApiClient:
    """Client for the public FoodMind chat API."""

    base_url: str

    async def request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Call an API endpoint and return its JSON response."""
        async with httpx.AsyncClient(
            base_url=self.base_url, timeout=REQUEST_TIMEOUT
        ) as client:
            response = await client.request(method, path, **kwargs)
            response.raise_for_status()
            return response.json()

    async def list_chats(self, user_id: UUID) -> list[dict[str, Any]]:
        """Return chats that belong to one browser user."""
        response = await self.request("GET", "/chats", params={"user_id": str(user_id)})
        return list(response)

    async def list_messages(self, chat_id: UUID, user_id: UUID) -> list[dict[str, Any]]:
        """Return a chat's persisted messages in chronological order."""
        response = await self.request(
            "GET",
            f"/chats/{chat_id}/messages",
            params={"user_id": str(user_id)},
        )
        return list(response["messages"])

    async def upsert_feedback(
        self, *, chat_id: UUID, message_id: str, user_id: UUID, is_useful: bool
    ) -> dict[str, Any]:
        """Create or replace usefulness feedback for an assistant message."""
        response = await self.request(
            "PUT",
            f"/chats/{chat_id}/messages/{message_id}/feedback",
            json={"user_id": str(user_id), "is_useful": is_useful},
        )
        return dict(response)

    async def stream_chat(
        self,
        *,
        user_id: UUID,
        message: str,
        chat_id: UUID | None,
        on_event: Any,
    ) -> dict[str, Any]:
        """Send a message and forward server-sent execution events to the UI."""
        payload = {
            "user_id": str(user_id),
            "message": message,
            "chat_id": str(chat_id) if chat_id is not None else None,
        }
        answer: dict[str, Any] | None = None
        async with httpx.AsyncClient(
            base_url=self.base_url, timeout=STREAM_TIMEOUT
        ) as client:
            async with client.stream("POST", "/chats/stream", json=payload) as response:
                response.raise_for_status()
                event = "message"
                async for line in response.aiter_lines():
                    if line.startswith("event: "):
                        event = line[7:]
                    elif line.startswith("data: "):
                        data = json.loads(line[6:])
                        await on_event(event, data)
                        if event == "completed":
                            answer = dict(data)
                        if event == "error":
                            raise RuntimeError(
                                str(data.get("message", "Request failed"))
                            )
        if answer is None:
            raise RuntimeError("The API stream completed without an answer")
        return answer


@dataclass
class ChatState:
    """Per-page UI state backed by the FoodMind API."""

    user_id: UUID
    chat_id: UUID | None = None
    messages: list[dict[str, Any]] = field(default_factory=list)


class FoodMindPage:
    """Render and coordinate one user's interactive FoodMind chat page."""

    def __init__(self, user_id: UUID) -> None:
        """Create page state and its API client."""
        self.api = FoodMindApiClient(API_URL)
        self.state = ChatState(user_id=user_id)
        self.chat_list: Any = None
        self.messages_container: Any = None
        self.composer: Any = None
        self.send_button: Any = None

    async def render(self) -> None:
        """Build the persistent page layout and restore the selected chat."""
        ui.add_css(
            """
            .nicegui-content { max-width: 100%; padding: 0; }
            .foodmind-message { width: 100%; }
            """
        )
        with ui.header(elevated=True).classes("items-center justify-between"):
            ui.label("FoodMind").classes("text-h6 font-bold")
            ui.label("Food intelligence assistant").classes("text-caption")

        with (
            ui.left_drawer(value=True, bordered=True)
            .props("width=320 behavior=desktop")
            .classes("p-3")
        ):
            ui.label("Your chats").classes("text-h6")
            ui.button("New chat", icon="add", on_click=self.start_new_chat).classes(
                "w-full q-mt-sm"
            )
            ui.separator().classes("q-my-md")
            self.chat_list = ui.column().classes("w-full gap-1")

        with ui.column().classes("w-full max-w-4xl mx-auto q-pa-md gap-4"):
            self.messages_container = ui.column().classes("w-full gap-4")
            with ui.row().classes("w-full items-end no-wrap"):
                self.composer = (
                    ui.textarea(
                        placeholder="Ask about food, nutrition, or recommendations…"
                    )
                    .props("outlined autogrow")
                    .classes("flex-grow")
                )
                self.composer.on("keydown.enter", self._submit_on_enter)
                self.send_button = ui.button(
                    "Send", icon="send", on_click=self.send_message
                ).classes("q-mb-sm")

        await self.refresh_chats()
        selected_chat = self._stored_chat_id()
        if selected_chat is not None:
            await self.open_chat(selected_chat, refresh_chats=False)
        else:
            self.render_messages()

    async def _submit_on_enter(self, event: Any) -> None:
        """Submit on Enter while preserving Shift+Enter for a new line."""
        if not event.args.get("shiftKey", False):
            await self.send_message()

    async def start_new_chat(self) -> None:
        """Reset the page without creating an empty server-side chat."""
        self.state.chat_id = None
        self.state.messages = []
        app.storage.user.pop("foodmind_selected_chat_id", None)
        self.render_messages()

    async def refresh_chats(self) -> None:
        """Load and render the user's chat navigation list."""
        self.chat_list.clear()
        try:
            chats = await self.api.list_chats(self.state.user_id)
        except httpx.HTTPError as error:
            with self.chat_list:
                ui.label(f"Could not load chats: {error}").classes("text-negative")
            return

        with self.chat_list:
            if not chats:
                ui.label("No chats yet").classes("text-caption text-grey")
            for chat in chats:
                chat_id = UUID(str(chat["id"]))
                label = self._chat_label(chat)
                button = ui.button(
                    label,
                    on_click=lambda chat_id=chat_id: self.open_chat(chat_id),
                ).props("flat no-caps align=left")
                button.classes("w-full justify-start text-left")
                if chat_id == self.state.chat_id:
                    button.props("color=primary")
                else:
                    button.props("color=grey-8")

    async def open_chat(self, chat_id: UUID, *, refresh_chats: bool = True) -> None:
        """Select a chat, persist the selection, and render its messages."""
        try:
            self.state.messages = await self.api.list_messages(
                chat_id, self.state.user_id
            )
        except httpx.HTTPError as error:
            app.storage.user.pop("foodmind_selected_chat_id", None)
            ui.notify(f"Could not load chat: {error}", type="negative")
            return
        self.state.chat_id = chat_id
        app.storage.user["foodmind_selected_chat_id"] = str(chat_id)
        self.render_messages()
        if refresh_chats:
            await self.refresh_chats()

    def render_messages(self) -> None:
        """Replace the main conversation area with the selected chat history."""
        self.messages_container.clear()
        with self.messages_container:
            if not self.state.messages:
                ui.label("Start a new conversation").classes(
                    "text-h6 text-grey q-mt-xl self-center"
                )
                ui.label(
                    "Ask for foods, nutrition facts, comparisons, or recommendations."
                ).classes("text-grey self-center")
                return
            for message in self.state.messages:
                self._render_message(message)

    def _render_message(self, message: dict[str, Any]) -> None:
        """Render one persisted user or assistant message and its feedback controls."""
        is_assistant = message["role"] == "assistant"
        ui.chat_message(
            str(message["content"]),
            name="FoodMind" if is_assistant else "You",
            sent=not is_assistant,
        ).classes("foodmind-message")
        if is_assistant and self.state.chat_id is not None and message.get("id"):
            feedback = message.get("feedback")
            selected = feedback.get("is_useful") if feedback else None
            with ui.row().classes("w-full justify-end -q-mt-3"):
                useful = ui.button(
                    icon="thumb_up",
                    on_click=lambda: self.save_feedback(message, True),
                    color="positive" if selected is True else "grey-7",
                ).props("flat round dense")
                useful.tooltip("Useful")
                not_useful = ui.button(
                    icon="thumb_down",
                    on_click=lambda: self.save_feedback(message, False),
                    color="negative" if selected is False else "grey-7",
                ).props("flat round dense")
                not_useful.tooltip("Not useful")

    async def save_feedback(self, message: dict[str, Any], is_useful: bool) -> None:
        """Save usefulness feedback and redraw the selected chat."""
        if self.state.chat_id is None or not message.get("id"):
            return
        try:
            message["feedback"] = await self.api.upsert_feedback(
                chat_id=self.state.chat_id,
                message_id=str(message["id"]),
                user_id=self.state.user_id,
                is_useful=is_useful,
            )
        except httpx.HTTPError as error:
            ui.notify(f"Could not save feedback: {error}", type="negative")
            return
        self.render_messages()

    async def send_message(self) -> None:
        """Append a user message, stream execution details, and render the answer."""
        content = str(self.composer.value or "").strip()
        if not content:
            return

        self.composer.value = ""
        self.composer.update()
        self.composer.disable()
        self.send_button.disable()
        self.state.messages.append({"role": "user", "content": content})
        self.render_messages()

        tool_and_agent_events: list[str] = []
        with self.messages_container:
            details = ui.expansion("Working…", icon="psychology", value=True).classes(
                "w-full"
            )
            with details:
                event_list = ui.column().classes("gap-1")

        async def on_event(event: str, data: dict[str, Any]) -> None:
            """Render only meaningful agent and tool events from the SSE stream."""
            if event == "chat_created":
                self.state.chat_id = UUID(str(data["chat_id"]))
                app.storage.user["foodmind_selected_chat_id"] = str(self.state.chat_id)
                return
            label = self._event_label(event, data)
            if label is None or label in tool_and_agent_events:
                return
            tool_and_agent_events.append(label)
            with event_list:
                ui.label(label).classes("text-caption")

        try:
            answer = await self.api.stream_chat(
                user_id=self.state.user_id,
                message=content,
                chat_id=self.state.chat_id,
                on_event=on_event,
            )
        except (httpx.HTTPError, RuntimeError) as error:
            details.set_text("Unable to process the request")
            details.set_value(False)
            with self.messages_container:
                ui.chat_message(
                    f"The FoodMind API is unavailable: {error}", name="FoodMind"
                ).classes("foodmind-message")
            return
        finally:
            self.composer.enable()
            self.send_button.enable()

        self.state.chat_id = UUID(str(answer["chat_id"]))
        app.storage.user["foodmind_selected_chat_id"] = str(self.state.chat_id)
        details.set_text("Tools and agents used")
        details.set_value(False)
        assistant_message = {
            "id": answer["message_id"],
            "role": "assistant",
            "content": answer["answer"],
            "feedback": None,
        }
        self.state.messages.append(assistant_message)
        with self.messages_container:
            self._render_message(assistant_message)
        await self.refresh_chats()

    @staticmethod
    def _event_label(event: str, data: dict[str, Any]) -> str | None:
        """Format relevant streamed agent and tool events for a compact UI."""
        match event:
            case "agent_started":
                agent = str(data.get("agent", "unknown")).replace("_", " ").title()
                return f"Agent: {agent}"
            case "tool_started":
                tool = str(data.get("tool", "unknown")).replace("_", " ")
                return f"Tool: {tool}"
            case _:
                return None

    @staticmethod
    def _chat_label(chat: dict[str, Any]) -> str:
        """Return a concise label for a chat in the left drawer."""
        title = chat.get("title") or chat.get("summary")
        return str(title) if title else f"Untitled chat · {str(chat['id'])[:8]}"

    @staticmethod
    def _stored_chat_id() -> UUID | None:
        """Return the last selected chat ID from per-user NiceGUI storage."""
        value = app.storage.user.get("foodmind_selected_chat_id")
        try:
            return UUID(str(value))
        except (TypeError, ValueError):
            return None


def _user_id() -> UUID:
    """Return the persistent per-browser user ID, creating it on first visit."""
    value = app.storage.user.get("foodmind_user_id")
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        user_id = uuid4()
        app.storage.user["foodmind_user_id"] = str(user_id)
        return user_id


@ui.page("/")
async def index() -> None:
    """Build the FoodMind page for the current NiceGUI browser session."""
    page = FoodMindPage(_user_id())
    await page.render()


def main() -> None:
    """Start the NiceGUI development server."""
    if not STORAGE_SECRET:
        raise RuntimeError(
            "NICEGUI_STORAGE_SECRET must be configured for the FoodMind UI"
        )
    ui.run(
        host="0.0.0.0",
        port=7860,
        title="FoodMind",
        reload=True,
        uvicorn_reload_dirs="/app/app",
        storage_secret=STORAGE_SECRET,
    )


if __name__ in {"__main__", "__mp_main__"}:
    main()
