"""A simple chatbot."""

from typing import Literal

from dotenv import load_dotenv
from langchain_core.messages import SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, MessagesState, StateGraph

load_dotenv()

model = ChatOpenAI(model="gpt-4.1-mini", temperature=0)


# THIS IS DANGEROUS, DO NOT USE IN PRODUCTION
@tool
def run_python_code(code: str) -> str:
    """Run arbitrary Python code including imports, assignments, and statements. Do not use any external libraries. Save your results as a variable.

    Args:
        code: Python code to run
    """
    import sys
    from io import StringIO

    old_stdout = sys.stdout
    sys.stdout = captured_output = StringIO()

    namespace = {}

    try:
        exec(code, namespace)

        output = captured_output.getvalue()

        if not output.strip():
            user_vars = {
                k: v
                for k, v in namespace.items()
                if not k.startswith("__") and k not in ["StringIO", "sys"]
            }
            if user_vars:
                if len(user_vars) == 1:
                    output = str(list(user_vars.values())[0])
                else:
                    output = str(user_vars)

        return output.strip() if output.strip() else "Code executed successfully"

    except Exception as e:
        return f"Error: {str(e)}"
    finally:
        sys.stdout = old_stdout


# THIS IS DANGEROUS, DO NOT USE IN PRODUCTION

tools = [run_python_code]
tools_by_name = {tool.name: tool for tool in tools}
model_with_tools = model.bind_tools(tools)


def llm_call(state: MessagesState):
    """Call the LLM with the current messages."""
    messages = [
        SystemMessage(content="You are a helpful assistant that can run python code."),
    ] + state["messages"]
    return {"messages": [model_with_tools.invoke(messages)]}


def tool_node(state: dict):
    """Call the tools with the current messages."""
    result = []
    for tool_call in state["messages"][-1].tool_calls:
        tool = tools_by_name[tool_call["name"]]
        observation = tool.invoke(tool_call["args"])
        result.append(ToolMessage(content=observation, tool_call_id=tool_call["id"]))
    return {"messages": result}


def should_continue(state: MessagesState) -> Literal["environment", END]:
    """Determine if the agent should continue or end."""
    messages = state["messages"]
    last_message = messages[-1]
    if last_message.tool_calls:
        return "Action"
    return END


graph = StateGraph(MessagesState)

graph.add_node("llm_call", llm_call)
graph.add_node("environment", tool_node)

graph.add_edge(START, "llm_call")
graph.add_conditional_edges(
    "llm_call",
    should_continue,
    {
        "Action": "environment",
        END: END,
    },
)
graph.add_edge("environment", "llm_call")
