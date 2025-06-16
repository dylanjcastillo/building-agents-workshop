"""React agent with human-in-the-loop functionality for tool execution review."""

from typing import Any, Callable

from dotenv import load_dotenv
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, tool
from langchain_core.tools import tool as create_tool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langgraph.prebuilt.interrupt import HumanInterrupt, HumanInterruptConfig
from langgraph.types import interrupt

load_dotenv()

model = ChatOpenAI(model="gpt-4.1-mini", temperature=0)


def add_human_in_the_loop(
    tool: Callable | BaseTool,
    *,
    interrupt_config: HumanInterruptConfig | None = None,
) -> BaseTool:
    """Wrap a tool to support human-in-the-loop review."""
    if not isinstance(tool, BaseTool):
        tool = create_tool(tool)

    if not interrupt_config:
        interrupt_config = HumanInterruptConfig(
            allow_ignore=False,
            allow_accept=True,
            allow_edit=False,
            allow_respond=False,
        )

    @create_tool(tool.name, description=tool.description, args_schema=tool.args_schema)
    def call_tool_with_interrupt(config: RunnableConfig, **tool_input):
        request = HumanInterrupt(
            action_request={"action": tool.name, "args": tool_input},
            config=interrupt_config,
            description="Please review the tool call",
        )
        response = interrupt([request])[0]
        if response["type"] == "accept":
            tool_response = tool.invoke(tool_input, config)
        elif response["type"] == "edit":
            tool_input = response["args"]["args"]
            tool_response = tool.invoke(tool_input, config)
        elif response["type"] == "response":
            user_feedback = response["args"]
            tool_response = user_feedback
        else:
            raise ValueError(f"Unsupported interrupt response type: {response['type']}")

        return tool_response

    return call_tool_with_interrupt


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

    namespace: dict[str, Any] = {}

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


graph = create_react_agent(
    model="openai:gpt-4.1-mini",
    tools=[
        add_human_in_the_loop(run_python_code),
    ],
)
