import json
import uuid
import logging
import streamlit as st
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.messages.tool import ToolMessage

from graph import graph

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def set_page_config():
    st.set_page_config(
        page_title="Local Sales Agent",
        page_icon="🤖",
        layout="centered",
        initial_sidebar_state="collapsed"
    )

def initialize_session_state():
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "thread_id" not in st.session_state:
        st.session_state.thread_id = str(uuid.uuid4())
    if "pending_approval" not in st.session_state:
        st.session_state.pending_approval = None
    if "config" not in st.session_state:
        st.session_state.config = {
            "configurable": {
                "customer_id": "local_user_123",
                "thread_id": st.session_state.thread_id,
            }
        }

def display_chat():
    st.markdown("## 💬 Virtual Sales Assistant")

    for msg in st.session_state.messages:
        if isinstance(msg, HumanMessage):
            with st.chat_message("user"):
                st.write(msg.content)
        elif isinstance(msg, AIMessage):
            with st.chat_message("assistant"):
                st.write(msg.content)

# In main.py

def process_input():
    if prompt := st.chat_input("How can I help?"):
        st.session_state.messages.append(HumanMessage(content=prompt))
        logger.info(f"User Input: {prompt}")

        with st.spinner("Thinking..."):
            try:
                events = graph.stream(
                    {"messages": st.session_state.messages},
                    st.session_state.config
                )

                    for event in events:
                       if "messages" in event:
                          for msg in event["messages"]:
                             if isinstance(msg, AIMessage):
                               content = msg.content or parse_tool_results(msg.tool_calls)
                               st.session_state.messages.append(AIMessage(content=content))
                               display_message(content)
                             elif isinstance(msg, ToolMessage):
                    st.session_state.messages.append(msg)
                    display_message(f"🔧 System: {format_tool_result(msg.content)}")

            except Exception as e:
                logger.error(f"Error processing input: {str(e)}")
                st.error(f"Error: {str(e)}")
def main():
    set_page_config()
    initialize_session_state()

    st.markdown("""
    <style>
    .stChatInput textarea { min-height: 150px; }
    .stChatMessage { padding: 1rem; border-radius: 0.5rem; margin: 0.5rem 0; }
    </style>
    """, unsafe_allow_html=True)

    display_chat()
    process_input()

if __name__ == "__main__":
    main()
