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


def _stream_message(user_id: UUID, message: str, chat_id: str | None, status) -> tuple[str | None, str]:
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
                        status.write("Chat created")
                    elif event == "orchestrator_started":
                        status.write("Orchestrator started")
                    elif event == "progress":
                        status.write(data.get("message", "Agents are still working"))
                    elif event.endswith("_started"):
                        status.write(event.removesuffix("_started").replace("_", " ").title())
                    elif event.endswith("_completed"):
                        status.write(event.removesuffix("_completed").replace("_", " ").title())
                    elif event == "completed":
                        answer = data
                    elif event == "error":
                        raise RuntimeError(data.get("message", "Request failed"))
    return resolved_chat_id, answer.get("answer", "")


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
        options = {chat["id"]: chat.get("title") or chat.get("summary") or "Untitled chat" for chat in chats}
        selected = st.selectbox("Previous chats", [None, *options], format_func=lambda item: "New chat" if item is None else options[item], label_visibility="collapsed")
        if selected and selected != st.session_state.chat_id:
            data = _request("GET", f"/chats/{selected}/messages", params={"user_id": str(user_id)})
            st.session_state.chat_id = selected
            st.session_state.messages = [{"role": item["role"], "content": item["content"]} for item in data["messages"]]

    st.title("FoodMind")
    for item in st.session_state.messages:
        with st.chat_message(item["role"]):
            st.markdown(item["content"])

    if prompt := st.chat_input("Ask about food, nutrition, or recommendations…"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.status("Thinking…") as status:
                try:
                    chat_id, answer = _stream_message(user_id, prompt, st.session_state.chat_id, status)
                    st.session_state.chat_id = chat_id
                    status.update(label="Completed", state="complete", expanded=False)
                except (httpx.HTTPError, RuntimeError) as error:
                    answer = f"The FoodMind API is unavailable: {error}"
                    status.update(label="Failed", state="error", expanded=True)
            st.markdown(answer)
        st.session_state.messages.append({"role": "assistant", "content": answer})


if __name__ == "__main__":
    main()
