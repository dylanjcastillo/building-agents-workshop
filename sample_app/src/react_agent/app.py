# mypy: disable-error-code="no-untyped-def,misc"

"""FastHTML-based chat interface for the LangGraph agent.

This module implements a real-time chat interface using FastHTML components and Server-Sent Events (SSE)
for streaming responses. It maintains conversation history and supports multiple chat threads per user.

Mostly based on: https://github.com/AnswerDotAI/fasthtml-example/blob/main/04_sse/sse_chatbot.py

Note: the JS / CSS in this was largely vibe-coded. The main **point** of this repo is
to show that you can add custom routes to a langgraph deployment so you can do things like
stream responses or add a custom UI.
"""

import uuid
from typing import Dict

from fasthtml.common import (  # type: ignore
    H2,
    A,
    Button,
    Div,
    FastHTML,
    Form,
    Input,
    Link,
    Script,
    Title,
    picolink,
)
from fasthtml.core import Request  # type: ignore
from langgraph_sdk import get_client
from starlette.responses import RedirectResponse

# Initialize the LangGraph client
langgraph_client = get_client()

# Dictionary to track ongoing AI requests
ongoing_requests: Dict[str, Dict] = {}

# Define HTML headers for styling and client-side functionality
tlink = (Script(src="https://cdn.tailwindcss.com"),)
dlink = Link(
    rel="stylesheet",
    href="https://cdn.jsdelivr.net/npm/daisyui@4.11.1/dist/full.min.css",
)
# Add custom styles
custom_styles = Script(
    """
document.addEventListener('DOMContentLoaded', function() {
    const tailwind = window.tailwind || {};
    tailwind.config = {
        theme: {
            extend: {
                fontFamily: {
                    'sans': ['-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'Helvetica Neue', 'Arial', 'sans-serif'],
                },
                colors: {
                    'apple-blue': '#02AB55',  // LangChain green
                    'apple-gray': '#f5f5f7',
                    'apple-dark': '#1d1d1f',
                    'message-user': '#F6EDFE',  // Light purple for user messages
                    'message-assistant': '#EBFDF1',  // Light green for assistant messages
                    'langchain-green': '#02AB55',
                    'langchain-purple': '#9C3EE8'
                },
                boxShadow: {
                    'soft': '0 4px 14px 0 rgba(0, 0, 0, 0.05)'
                },
                keyframes: {
                    fadeIn: {
                      '0%': { opacity: '0', transform: 'translateY(10px)' },
                      '100%': { opacity: '1', transform: 'translateY(0)' }
                    }
                },
                animation: {
                    fadeIn: 'fadeIn 0.3s ease-out forwards'
                }
            }
        }
    };
    
    // Add animation to chat messages
    const observer = new MutationObserver((mutations) => {
        mutations.forEach(mutation => {
            if (mutation.type === 'childList') {
                mutation.addedNodes.forEach(node => {
                    if (node.nodeType === 1 && (node.id.startsWith('chat-message-') || node.classList.contains('chat'))) {
                        node.style.opacity = '0';
                        node.classList.add('animate-fadeIn');
                    }
                });
            }
        });
    });
    
    const chatlist = document.getElementById('chatlist');
    if (chatlist) {
        observer.observe(chatlist, { childList: true, subtree: true });
    }
    
    // Resizable sidebar
    let isResizing = false;
    let sidebar = null;
    
    function initResizer() {
        console.log('Initializing resizer');
        const resizer = document.getElementById('sidebar-resizer');
        sidebar = document.getElementById('sidebar');
        
        if (!resizer || !sidebar) {
            console.error('Resizer or sidebar elements not found');
            return;
        }
        
        console.log('Resizer and sidebar found', resizer, sidebar);
        
        // Load saved width from localStorage
        const savedWidth = localStorage.getItem('sidebar-width');
        if (savedWidth) {
            sidebar.style.width = savedWidth;
        }
        
        // Mouse events for desktop
        resizer.addEventListener('mousedown', function(e) {
            isResizing = true;
            document.body.classList.add('select-none', 'cursor-col-resize');
            document.addEventListener('mousemove', handleMouseMove);
            document.addEventListener('mouseup', stopResize);
            e.preventDefault();
            console.log('Mouse down on resizer');
        });
        
        // Touch events for mobile
        resizer.addEventListener('touchstart', function(e) {
            isResizing = true;
            document.body.classList.add('select-none');
            document.addEventListener('touchmove', handleTouchMove);
            document.addEventListener('touchend', stopResize);
            e.preventDefault();
            console.log('Touch start on resizer');
        });
    }
    
    function handleMouseMove(e) {
        if (!isResizing || !sidebar) return;
        console.log('Mouse move while resizing', e.clientX);
        const width = Math.max(200, Math.min(500, e.clientX));
        sidebar.style.width = width + 'px';
        localStorage.setItem('sidebar-width', width + 'px');
    }
    
    function handleTouchMove(e) {
        if (!isResizing || !sidebar || !e.touches[0]) return;
        console.log('Touch move while resizing', e.touches[0].clientX);
        const width = Math.max(200, Math.min(500, e.touches[0].clientX));
        sidebar.style.width = width + 'px';
        localStorage.setItem('sidebar-width', width + 'px');
    }
    
    function stopResize() {
        if (isResizing) {
            console.log('Stopping resize');
            isResizing = false;
            document.body.classList.remove('select-none', 'cursor-col-resize');
            document.removeEventListener('mousemove', handleMouseMove);
            document.removeEventListener('touchmove', handleTouchMove);
            document.removeEventListener('mouseup', stopResize);
            document.removeEventListener('touchend', stopResize);
        }
    }
    
    // Override default textarea Enter behavior globally
    document.addEventListener('keydown', function(e) {
        if (e.target.id === 'msg-input-div') {
            if (e.key === 'Enter') {
                if (e.shiftKey) {
                    // Allow Shift+Enter to insert a newline
                    // Let the event continue
                } else {
                    // Regular Enter should submit the form
                    e.preventDefault();
                    e.stopPropagation();
                    const submitButton = document.getElementById('send-button');
                    if (submitButton) {
                        submitButton.click();
                    }
                    return false;
                }
            }
        }
    }, true); // Using capturing phase to intercept before default behavior
    
    // Handle Shift+Enter for multi-line input
    function setupChatInput() {
        const chatInputDiv = document.getElementById('msg-input-div');
        const hiddenInput = document.getElementById('msg-input');
        
        if (!chatInputDiv || !hiddenInput) {
            console.error('Chat input elements not found');
            return;
        }
        
        // Transfer content to hidden input on any change
        chatInputDiv.addEventListener('input', function() {
            hiddenInput.value = this.innerText;
        });
        
        // Handle key events
        chatInputDiv.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') {
                if (e.shiftKey) {
                    // Allow default behavior for Shift+Enter (new line)
                    return true;
                } else {
                    // Prevent default behavior for regular Enter
                    e.preventDefault();
                    
                    // Only submit if there's content
                    if (this.innerText.trim()) {
                        // Transfer content to hidden input
                        hiddenInput.value = this.innerText.trim();
                        
                        // Click the submit button
                        const submitButton = document.getElementById('send-button');
                        if (submitButton) {
                            submitButton.click();
                        }
                        
                        // Clear the contenteditable div
                        this.innerText = '';
                    }
                    return false;
                }
            }
        });
    }
    
    // Initialize chat input handling with a retry mechanism
    function initChatInputWithRetry(attempts = 0) {
        if (attempts > 5) return; // Give up after 5 attempts
        
        if (document.getElementById('msg-input-div')) {
            setupChatInput();
        } else {
            // Retry after a delay
            setTimeout(() => initChatInputWithRetry(attempts + 1), 100);
        }
    }
    
    // Make sure the DOM is fully loaded before initializing
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            initResizer();
            initChatInputWithRetry();
        });
    } else {
        // If DOMContentLoaded has already fired, run immediately
        setTimeout(() => {
            initResizer();
            initChatInputWithRetry();
        }, 100);
    }
})
"""
)
fonts = Link(
    rel="stylesheet",
    href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap",
)
app = FastHTML(hdrs=(tlink, dlink, picolink, custom_styles, fonts), live=True)


def get_user_id(request: Request) -> str:
    """Get or create a user ID from cookies.

    Returns a UUID if no user ID cookie exists.
    """
    user_id = request.cookies.get("user_id")
    if not user_id:
        user_id = str(uuid.uuid4())
    return str(user_id)


def ChatMessage(msg: Dict[str, str], idx: str | int) -> Div:
    """Render a chat message bubble.

    Creates a styled message bubble with different colors for user/assistant messages.
    """
    is_human = msg["type"] == "human"

    # Apply different styles based on message type
    bubble_class = (
        "bg-message-user border-purple-200 border text-black shadow-sm"
        if is_human
        else "bg-message-assistant border-green-200 border text-black shadow-sm"
    )
    container_class = "justify-end" if is_human else "justify-start"
    avatar_class = (
        "flex items-center justify-center w-8 h-8 rounded-full bg-purple-100 border border-purple-200 shadow-sm"
        if is_human
        else "flex items-center justify-center w-8 h-8 rounded-full bg-green-100 border border-green-200 shadow-sm"
    )
    avatar_icon = "👤" if is_human else "🤖"

    # Process message content to preserve newlines
    content = msg["content"]

    return Div(
        Div(
            Div(
                avatar_icon,
                cls=avatar_class + (" order-last ml-2" if is_human else " mr-2"),
            ),
            Div(
                content,
                id=f"chat-content-{idx}",
                cls=f"px-4 py-3 rounded-2xl {bubble_class} whitespace-pre-line"
                + (" rounded-tr-sm" if is_human else " rounded-tl-sm"),
            ),
            cls="flex items-start max-w-[80%]",
        ),
        id=f"chat-message-{idx}",
        cls=f"py-2 flex {container_class}",
    )


def ToolCallMessage(tool_call: Dict, idx: str | int) -> Div:
    """Render a tool call message showing what tool is being executed."""
    tool_name = tool_call.get("name", "Unknown tool")
    tool_args = tool_call.get("args", {})

    # Format arguments nicely
    args_display = ""
    if tool_args:
        if len(str(tool_args)) > 100:
            args_display = f"Arguments: {str(tool_args)[:100]}..."
        else:
            args_display = f"Arguments: {tool_args}"

    return Div(
        Div(
            Div(
                "🔧",
                cls="flex items-center justify-center w-8 h-8 rounded-full bg-orange-100 border border-orange-200 shadow-sm mr-2",
            ),
            Div(
                Div(
                    f"🛠️ Calling tool: {tool_name}",
                    cls="font-semibold text-orange-800 mb-1",
                ),
                Div(
                    args_display,
                    cls="text-sm text-orange-600 font-mono bg-orange-50 p-2 rounded border",
                )
                if args_display
                else "",
                id=f"tool-call-content-{idx}",
                cls="px-4 py-3 rounded-2xl bg-orange-100 border-orange-200 border text-black shadow-sm rounded-tl-sm",
            ),
            cls="flex items-start max-w-[80%]",
        ),
        id=f"tool-call-{idx}",
        cls="py-2 flex justify-start",
    )


def ToolResultMessage(tool_result: str, tool_call_id: str, idx: str | int) -> Div:
    """Render a tool result message showing the output from tool execution."""
    # Truncate very long results for display
    display_result = tool_result
    if len(tool_result) > 500:
        display_result = tool_result[:500] + "... (truncated)"

    return Div(
        Div(
            Div(
                "📋",
                cls="flex items-center justify-center w-8 h-8 rounded-full bg-blue-100 border border-blue-200 shadow-sm mr-2",
            ),
            Div(
                Div("🔍 Tool Result:", cls="font-semibold text-blue-800 mb-2"),
                Div(
                    display_result,
                    cls="text-sm text-blue-900 font-mono bg-blue-50 p-3 rounded border whitespace-pre-wrap overflow-x-auto",
                ),
                id=f"tool-result-content-{idx}",
                cls="px-4 py-3 rounded-2xl bg-blue-100 border-blue-200 border text-black shadow-sm rounded-tl-sm",
            ),
            cls="flex items-start max-w-[85%]",
        ),
        id=f"tool-result-{idx}",
        cls="py-2 flex justify-start",
    )


def TypingIndicator(typing_id: str) -> Div:
    """Render a typing indicator for when AI is thinking."""
    return Div(
        Div(
            Div(
                "🤖",
                cls="flex items-center justify-center w-8 h-8 rounded-full bg-green-100 border border-green-200 shadow-sm mr-2",
            ),
            Div(
                Div(
                    Div(cls="w-2 h-2 bg-gray-400 rounded-full animate-bounce"),
                    Div(
                        cls="w-2 h-2 bg-gray-400 rounded-full animate-bounce",
                        style="animation-delay: 0.1s",
                    ),
                    Div(
                        cls="w-2 h-2 bg-gray-400 rounded-full animate-bounce",
                        style="animation-delay: 0.2s",
                    ),
                    cls="flex space-x-1 items-center",
                ),
                cls="px-4 py-3 rounded-2xl bg-message-assistant border-green-200 border text-black shadow-sm rounded-tl-sm",
            ),
            cls="flex items-start max-w-[80%]",
        ),
        id=f"typing-{typing_id}",
        cls="py-2 flex justify-start",
        hx_get=f"/conversations/get-ai-response/{typing_id}",
        hx_trigger="load delay:100ms",
        hx_swap="outerHTML",
    )


def render_message_history(messages):
    """Render the complete message history from thread state.

    Processes different message types from LangGraph and returns appropriate UI components.
    """
    rendered_messages = []

    for i, msg in enumerate(messages):
        msg_id = f"history-{i}"

        # Handle different message types from LangGraph
        if hasattr(msg, "type"):
            msg_type = msg.type
            content = getattr(msg, "content", "")
        else:
            # Handle dict format
            msg_type = msg.get("type", "unknown")
            content = msg.get("content", "")

        # Handle human messages
        if msg_type == "human":
            rendered_messages.append(
                ChatMessage({"type": "human", "content": content}, msg_id)
            )

        # Handle AI messages
        elif msg_type == "ai":
            # Check if this AI message has tool calls
            tool_calls = getattr(msg, "tool_calls", None) or (
                msg.get("tool_calls") if isinstance(msg, dict) else None
            )

            if tool_calls:
                # Render tool calls
                for j, tool_call in enumerate(tool_calls):
                    tool_msg_id = f"{msg_id}-tool-{j}"
                    rendered_messages.append(ToolCallMessage(tool_call, tool_msg_id))

            # Render AI message content if it exists
            if content and content.strip():
                rendered_messages.append(
                    ChatMessage({"type": "ai", "content": content}, msg_id)
                )

        # Handle tool messages (results from tool calls)
        elif msg_type == "tool":
            tool_call_id = getattr(msg, "tool_call_id", None) or (
                msg.get("tool_call_id") if isinstance(msg, dict) else None
            )
            rendered_messages.append(
                ToolResultMessage(content, tool_call_id or "unknown", msg_id)
            )

    return rendered_messages


def ChatInputBubble(thread_id: str) -> Div:
    """Clean chatbot input."""
    return Div(
        Form(
            # Create a container with proper spacing
            Div(
                # Text input container with integrated button
                Div(
                    # Editable content area
                    Div(
                        "",  # Empty content to start
                        id="msg-input-div",
                        contenteditable="true",
                        cls="w-full px-4 pr-14 text-base bg-white border border-gray-300 rounded-lg focus:outline-none min-h-10 max-h-40 overflow-y-auto py-6",
                    ),
                    # Button positioned inside the input area
                    Div(
                        Button(
                            "➤",  # Right arrow
                            type="submit",
                            id="send-button",
                            cls="h-10 w-8 bg-apple-blue text-white text-lg rounded-full flex items-center justify-center hover:bg-apple-blue/90 shadow-sm",
                        ),
                        cls="absolute right-2 bottom-0 flex items-center justify-center",
                    ),
                    # Hidden input to store the actual value
                    Input(type="hidden", name="msg", id="msg-input"),
                    cls="flex-grow relative",
                ),
                # Container styling
                cls="flex w-full",
            ),
            hx_post=f"/conversations/{thread_id}/send-message",
            hx_target="#chatlist",
            hx_swap="beforeend",
            cls="w-full",
            # Add this to ensure the content from the contenteditable div is transferred to the hidden input on submit
            hx_on__submit="document.getElementById('msg-input').value = document.getElementById('msg-input-div').innerText;",
            # Clear the input after the request is completed
            hx_on__after_request="document.getElementById('msg-input-div').innerText = ''; document.getElementById('msg-input').value = '';",
            # Add auto-resize functionality for the input
            hx_on__load="""
                const msgInput = document.getElementById('msg-input-div');
                msgInput.style.height = 'auto';
                msgInput.style.height = (msgInput.scrollHeight > 40) ? Math.min(msgInput.scrollHeight, 160) + 'px' : '40px';
                
                msgInput.addEventListener('input', function() {
                    this.style.height = 'auto';
                    this.style.height = (this.scrollHeight > 40) ? Math.min(this.scrollHeight, 160) + 'px' : '40px';
                });
            """,
        ),
        cls="px-6 py-4 bg-white border-t border-gray-200",
        id="chat-input-bubble",
    )


async def ConversationList(user_id: str, current_thread_id: str) -> Div:
    """Render the sidebar list of conversations.

    Shows all threads for the user with the current thread highlighted.
    """
    threads = await langgraph_client.threads.search(
        metadata={"user_id": user_id}, limit=50, offset=0
    )

    return Div(
        Div(
            H2("Threads", cls="text-xl font-medium text-langchain-green mb-4"),
            cls="flex items-center h-[69px] px-6 border-b border-gray-200 bg-white/90 sticky top-0 z-10",
        ),
        Div(
            *[
                A(
                    Div(
                        Div(f"Thread {i + 1}", cls="font-medium text-sm"),
                        Div(f"{thread['created_at']}", cls="text-xs text-gray-500"),
                        cls="flex flex-col",
                    ),
                    href=f"/conversations/{thread['thread_id']}",
                    cls="block px-4 py-3 my-1.5 rounded-xl transition-all duration-200 hover:bg-gray-100"
                    + (
                        " bg-purple-100 border-l-4 border-purple-500"
                        if thread["thread_id"] == current_thread_id
                        else ""
                    ),
                )
                for i, thread in enumerate(threads)
            ],
            cls="overflow-y-auto h-[calc(100vh-5rem)] px-2",
        ),
        id="sidebar",
        cls="w-80 bg-white border-r border-gray-200 shadow-sm transition-all duration-100 ease-in-out",
    )


@app.get("/")  # type: ignore
async def root(request: Request):
    """Root index for redirecting to a new conversation."""
    thread_id = str(uuid.uuid4())
    user_id = get_user_id(request)
    response = RedirectResponse(f"/conversations/{thread_id}", status_code=302)
    response.set_cookie(key="user_id", value=user_id, httponly=True)
    return response


@app.get("/conversations/{thread_id}")  # type: ignore[misc]
async def conversation(thread_id: str, request: Request):
    """Display the chat interface for a specific conversation.

    Shows message history and handles new message streaming.
    """
    user_id = get_user_id(request)

    # Create thread with user_id in metadata
    await langgraph_client.threads.create(
        thread_id=thread_id, if_exists="do_nothing", metadata={"user_id": user_id}
    )

    # Fetch thread state
    try:
        state = await langgraph_client.threads.get_state(thread_id)
        values = state["values"]
        if isinstance(values, list):
            messages = values[-1]["messages"]
        else:
            messages = values["messages"]
    except Exception:
        messages = []

    # Define the "New Thread" button as a regular link
    new_thread_button = A(
        "New Thread",
        href="/new-thread",
        cls="rounded-full px-4 py-2 bg-apple-blue text-white text-sm font-medium hover:bg-green-600 transition-colors duration-200 shadow-sm",
    )

    # Main chat content
    chat_content = Div(
        Div(
            Div(
                "LangChain Chat Demo. Do not share private data - this is an unauthenticated demo!",
                cls="text-sm text-gray-600 font-medium",
            ),
            new_thread_button,
            cls="flex justify-between items-center py-4 px-6 bg-white border-b border-gray-200 shadow-sm sticky top-0 z-10",
        ),
        Div(
            *render_message_history(messages),
            id="chatlist",
            cls="chat-box h-[calc(100vh-10rem)] overflow-y-auto px-6 py-6 bg-gradient-to-br from-purple-50 to-green-50",
        ),
        ChatInputBubble(thread_id),
        cls="flex-1 flex flex-col",
    )

    page = Div(
        await ConversationList(user_id, thread_id),
        Div(
            "",
            id="sidebar-resizer",
            cls="w-1 hover:w-2 bg-gray-200 hover:bg-apple-blue cursor-col-resize transition-all duration-200",
        ),
        chat_content,
        cls="flex w-full h-screen bg-gray-50 text-apple-dark font-sans overflow-hidden",
    )
    return (
        Title(
            "LangChain Chat Demo",
        ),
        page,
    )


@app.get("/new-thread")  # type: ignore[misc]
async def new_thread(request: Request):
    """Create a new conversation thread.

    Redirects to the new thread's conversation page.
    """
    thread_id = str(uuid.uuid4())
    user_id = get_user_id(request)
    response = RedirectResponse(f"/conversations/{thread_id}", status_code=302)
    response.set_cookie(key="user_id", value=user_id, httponly=True)
    return response


@app.post("/conversations/{thread_id}/send-message")  # type: ignore[misc]
async def send_message(request: Request, thread_id: str):
    """Handle sending a new message in a conversation.

    Returns the user message and typing indicator immediately.
    """
    form_data = await request.form()
    msg = form_data.get("msg", "")

    if not msg or msg.isspace():
        return None

    # Generate unique IDs for this conversation turn
    user_msg_id = f"user-{uuid.uuid4()}"
    typing_id = str(uuid.uuid4())

    # Create user message immediately
    user_msg_div = ChatMessage({"type": "human", "content": msg}, user_msg_id)

    # Create typing indicator
    typing_indicator = TypingIndicator(typing_id)

    # Start AI request in background and store details
    run = await langgraph_client.runs.create(
        thread_id=thread_id,
        assistant_id="agent",
        input={"messages": [{"type": "human", "content": msg}]},
        stream_mode="updates",
    )

    # Store the ongoing request details
    ongoing_requests[typing_id] = {
        "thread_id": thread_id,
        "run_id": run["run_id"],
        "started": True,
    }

    return user_msg_div, typing_indicator


@app.get("/conversations/get-ai-response/{typing_id}")  # type: ignore[misc]
async def get_ai_response(typing_id: str):
    """Get the AI response for a specific typing indicator."""
    if typing_id not in ongoing_requests:
        return Div("Error: Request not found", cls="text-red-500")

    request_info = ongoing_requests[typing_id]
    thread_id = request_info["thread_id"]
    run_id = request_info["run_id"]

    try:
        # Collect all updates from the stream
        stream_updates = []
        async for chunk in langgraph_client.runs.join_stream(
            thread_id, run_id, stream_mode="updates"
        ):
            if chunk.event == "updates":
                stream_updates.append(chunk.data)

        # Clean up the ongoing request
        del ongoing_requests[typing_id]

        # Extract new messages from the stream updates
        # Updates stream mode gives us the state updates after each node
        new_messages = []
        for update in stream_updates:
            # Each update contains the node name and the state changes
            for node_name, node_output in update.items():
                if "messages" in node_output:
                    # Get the new messages from this node's output
                    messages = node_output["messages"]
                    if isinstance(messages, list):
                        new_messages.extend(messages)
                    else:
                        new_messages.append(messages)

        # Use the same rendering logic as render_message_history
        rendered_components = []

        for i, msg in enumerate(new_messages):
            msg_id = f"stream-{typing_id}-{i}"

            # Handle different message types from LangGraph
            if hasattr(msg, "type"):
                msg_type = msg.type
                content = getattr(msg, "content", "")
            else:
                # Handle dict format
                msg_type = msg.get("type", "unknown")
                content = msg.get("content", "")

            # Handle AI messages
            if msg_type == "ai":
                # Check if this AI message has tool calls
                tool_calls = getattr(msg, "tool_calls", None) or (
                    msg.get("tool_calls") if isinstance(msg, dict) else None
                )

                if tool_calls:
                    # Render tool calls
                    for j, tool_call in enumerate(tool_calls):
                        tool_msg_id = f"{msg_id}-tool-{j}"
                        rendered_components.append(
                            ToolCallMessage(tool_call, tool_msg_id)
                        )

                # Render AI message content if it exists
                if content and content.strip():
                    rendered_components.append(
                        ChatMessage({"type": "ai", "content": content}, msg_id)
                    )

            # Handle tool messages (results from tool calls)
            elif msg_type == "tool":
                tool_call_id = getattr(msg, "tool_call_id", None) or (
                    msg.get("tool_call_id") if isinstance(msg, dict) else None
                )
                rendered_components.append(
                    ToolResultMessage(content, tool_call_id or "unknown", msg_id)
                )

        # Return all rendered components
        # If we have multiple components, wrap them in a container
        if len(rendered_components) == 1:
            return rendered_components[0]
        elif len(rendered_components) > 1:
            return Div(*rendered_components)
        else:
            # Fallback to empty response if no valid messages
            return Div("No response received", cls="text-gray-500")

    except Exception as e:
        # Clean up on error
        if typing_id in ongoing_requests:
            del ongoing_requests[typing_id]
        return Div(f"Error getting response: {str(e)}", cls="text-red-500")
