import os
from datetime import datetime
from typing import Annotated
import logging

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable, RunnableConfig
from langchain_ollama import ChatOllama

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import AnyMessage, add_messages
from langgraph.prebuilt import tools_condition
from typing_extensions import TypedDict
# main.py
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from tools import (
    check_order_status,
    create_order,
    get_available_categories,
    search_products,
    search_products_recommendations,
)
from utils import create_tool_node_with_fallback

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class State(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    user_info: str

# In graph.py

class Assistant:
    def __init__(self, runnable: Runnable):
        self.runnable = runnable

    def __call__(self, state: State, config: RunnableConfig):
        state = {**state, "user_info": config.get("configurable", {}).get("customer_id")}
        result = self.runnable.invoke(state)
        
        # If empty response but tool results exist
        if not result.content and state.get("messages"):
            last_tool = next((msg for msg in reversed(state["messages"]) 
                            if isinstance(msg, ToolMessage)), None)
            if last_tool:
                result.content = f"Here are the results:\n{last_tool.content}"
        
        return {"messages": [result]}
llm = ChatOllama(
    model="llama3.2:latest",
    temperature=0.3,
    base_url="http://localhost:11434",
    num_gpu=1,
    format="json",
    num_ctx=4096
)

assistant_prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        """You are a helpful sales assistant. Follow these rules:
1. Always format tool results for readability
2. Include prices and stock quantities
3. Use bullet points for product lists
4. Add emojis for engagement

Tools: {tool_names}
Current user: {user_info}
Time: {time}"""
    ),
    ("placeholder", "{messages}")
]).partial(
    time=datetime.now,
    tool_names=", ".join([
        "get_available_categories",
        "search_products",
        "search_products_recommendations",
        "check_order_status",
        "create_order"
    ])
)

safe_tools = [
    get_available_categories,
    search_products,
    search_products_recommendations,
    check_order_status,
]

sensitive_tools = [create_order]
sensitive_tool_names = {tool.name for tool in sensitive_tools}

assistant_runnable = assistant_prompt | llm.bind_tools(safe_tools + sensitive_tools)

builder = StateGraph(State)
builder.add_node("assistant", Assistant(assistant_runnable))
builder.add_node("safe_tools", create_tool_node_with_fallback(safe_tools))
builder.add_node("sensitive_tools", create_tool_node_with_fallback(sensitive_tools))

def route_tools(state: State):
    next_node = tools_condition(state)
    if next_node == END:
        return END
    ai_message = state["messages"][-1]
    if ai_message.tool_calls:
        first_tool_call = ai_message.tool_calls[0]
        if first_tool_call["name"] in sensitive_tool_names:
            return "sensitive_tools"
    return "safe_tools"

builder.add_edge(START, "assistant")
builder.add_conditional_edges(
    "assistant", route_tools, ["safe_tools", "sensitive_tools", END]
)
builder.add_edge("safe_tools", "assistant")
builder.add_edge("sensitive_tools", "assistant")

memory = MemorySaver()
graph = builder.compile(checkpointer=memory, interrupt_before=["sensitive_tools"])
