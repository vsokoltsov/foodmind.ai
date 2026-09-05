"""Streamlit interface for the FoodMind chat API.

The filename is retained for compatibility with the existing UI container.
"""

from __future__ import annotations

import json
import os
from uuid import UUID, uuid4

import httpx
import streamlit as st
from st_cookie import CookieManager

API_URL = os.getenv("FOODMIND_API_URL", "http://localhost:8000").rstrip("/")


def _user_id(cookies: CookieManager) -> UUID:
    """Return a persistent browser user ID, creating it on first visit."""
    with cookies.sync("foodmind_user_id"):
        value = st.session_state.get("foodmind_user_id")
        try:
            return UUID(str(value))
        except (ValueError, TypeError, AttributeError):
            value = uuid4()
            st.session_state["foodmind_user_id"] = str(value)
            return value


def _request(method: str, path: str, **kwargs):
    """Call an existing FoodMind API endpoint."""
    with httpx.Client(base_url=API_URL, timeout=30) as client:
        response = client.request(method, path, **kwargs)
        response.raise_for_status()
        return response.json()


def _stream_message(
    user_id: UUID, message: str, chat_id: str | None, status
) -> tuple[str | None, dict]:
    """Stream execution events and return the final answer and chat ID."""
    payload = {"user_id": str(user_id), "message": message, "chat_id": chat_id}
    answer: dict = {}
    resolved_chat_id = chat_id
    with httpx.Client(base_url=API_URL, timeout=1800) as client:
        with client.stream("POST", "/chats/stream", json=payload) as response:
            response.raise_for_status()
            event = "message"
            for line in response.iter_lines():
                if line.startswith("event: "):
                    event = line[7:]
                elif line.startswith("data: "):
                    data = json.loads(line[6:])
                    if event == "chat_created":
                        resolved_chat_id = data["chat_id"]
                    elif event == "agent_started":
                        agent = (
                            str(data.get("agent", "unknown")).replace("_", " ").title()
                        )
                        status.write(f"Agent: {agent}")
                    elif event == "agent_completed":
                        agent = (
                            str(data.get("agent", "unknown")).replace("_", " ").title()
                        )
                        status.write(f"Agent completed: {agent}")
                    elif event == "tool_started":
                        tool = str(data.get("tool", "unknown")).replace("_", " ")
                        status.write(f"Tool: {tool}")
                    elif event == "tool_completed":
                        tool = str(data.get("tool", "unknown")).replace("_", " ")
                        status.write(f"Tool completed: {tool}")
                    elif event == "completed":
                        answer = data
                    elif event == "error":
                        raise RuntimeError(data.get("message", "Request failed"))
    return resolved_chat_id, answer


def _record_feedback(
    user_id: UUID, chat_id: str, message: dict, is_useful: bool
) -> None:
    """Persist feedback and update the displayed message state."""
    feedback = _request(
        "PUT",
        f"/chats/{chat_id}/messages/{message['id']}/feedback",
        json={"user_id": str(user_id), "is_useful": is_useful},
    )
    message["feedback"] = feedback


def _render_feedback_controls(
    user_id: UUID, chat_id: str | None, message: dict
) -> None:
    """Render usefulness controls for a persisted assistant message."""
    if chat_id is None or not message.get("id"):
        return

    feedback = message.get("feedback")
    selected = feedback.get("is_useful") if feedback else None
    helpful, not_helpful = st.columns(2)
    with helpful:
        if st.button(
            "👍 Useful",
            key=f"feedback-useful-{message['id']}",
            type="primary" if selected is True else "secondary",
        ):
            _record_feedback(user_id, chat_id, message, True)
            st.rerun()
    with not_helpful:
        if st.button(
            "👎 Not useful",
            key=f"feedback-not-useful-{message['id']}",
            type="primary" if selected is False else "secondary",
        ):
            _record_feedback(user_id, chat_id, message, False)
            st.rerun()


def _chat_label(chat: dict) -> str:
    """Return a readable and unique label for a chat in the sidebar."""
    title = chat.get("title") or chat.get("summary")
    if title:
        return str(title)
    return f"Untitled chat · {str(chat['id'])[:8]}"


def main() -> None:
    """Render the FoodMind chat interface."""
    st.set_page_config(page_title="FoodMind", page_icon="🍎", layout="wide")
    cookies = CookieManager()
    user_id = _user_id(cookies)

    if "chat_id" not in st.session_state:
        st.session_state.chat_id = None
    if "messages" not in st.session_state:
        st.session_state.messages = []

    with st.sidebar:
        st.title("Your chats")
        if st.button("＋ New chat", use_container_width=True):
            st.session_state.chat_id = None
            st.session_state.messages = []
            st.rerun()
        try:
            chats = _request("GET", "/chats", params={"user_id": str(user_id)})
        except httpx.HTTPError as error:
            st.error(f"Could not load chats: {error}")
            chats = []
        for chat in chats:
            chat_id = str(chat["id"])
            if st.button(
                _chat_label(chat),
                key=f"chat-{chat_id}",
                type="primary" if chat_id == st.session_state.chat_id else "secondary",
                use_container_width=True,
            ):
                data = _request(
                    "GET",
                    f"/chats/{chat_id}/messages",
                    params={"user_id": str(user_id)},
                )
                st.session_state.chat_id = chat_id
                st.session_state.messages = data["messages"]
                st.rerun()

    st.title("FoodMind")
    for item in st.session_state.messages:
        with st.chat_message(item["role"]):
            st.markdown(item["content"])
            if item["role"] == "assistant":
                _render_feedback_controls(user_id, st.session_state.chat_id, item)

    if prompt := st.chat_input("Ask about food, nutrition, or recommendations…"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            result: dict = {}
            with st.status("Thinking…") as status:
                try:
                    chat_id, result = _stream_message(
                        user_id, prompt, st.session_state.chat_id, status
                    )
                    st.session_state.chat_id = chat_id
                    answer = result.get("answer", "")
                    status.update(label="Completed", state="complete", expanded=False)
                except (httpx.HTTPError, RuntimeError) as error:
                    answer = f"The FoodMind API is unavailable: {error}"
                    status.update(label="Failed", state="error", expanded=True)
            st.markdown(answer)
            assistant_message = {
                "id": result.get("message_id"),
                "role": "assistant",
                "content": answer,
                "feedback": None,
            }
            _render_feedback_controls(
                user_id, st.session_state.chat_id, assistant_message
            )
        st.session_state.messages.append(assistant_message)


if __name__ == "__main__":
    main()
