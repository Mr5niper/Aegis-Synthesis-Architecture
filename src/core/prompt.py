# Tool descriptions shown to the router so the model knows WHAT each tool does
# and WHEN to use it. Keep this in sync with AsyncToolRegistry.
TOOL_DESCRIPTIONS = {
    "search_web": "Search the live internet for current, factual, or recent information (news, prices, releases, people, events, anything that may have changed or that you are unsure about). args: {\"query\": \"...\", \"k\": 5}",
    "fetch_url": "Download and read the text of a specific web page. args: {\"url\": \"https://...\"}",
    "ingest_url": "Download a web page and store it in the knowledge base for later. args: {\"url\": \"https://...\"}",
    "calc": "Evaluate a arithmetic expression exactly. args: {\"expr\": \"23 * 456\"}",
    "now": "Get the current local date and time. args: {}",
    "kb_query": "Search the user's private local knowledge base. args: {\"query\": \"...\", \"k\": 3}",
    "kb_add": "Store a piece of text in the local knowledge base. args: {\"text\": \"...\", \"source\": \"...\"}",
    "code_exec": "Run a short Python snippet in a sandbox. args: {\"code\": \"...\"}",
    "none": "Use this when you already know the answer and no tool is needed.",
}

TOOLS_SCHEMA = """To use a tool, output ONLY a single JSON object on one line, with this exact schema and NOTHING else:
{ "tool": "<tool_name>", "args": { ... }, "rationale": "<one short sentence>" }
If no tool is needed because you can answer directly, output exactly:
{ "tool": "none", "args": {}, "rationale": "I can answer directly." }

Output the single JSON object and then STOP. Do not write an Observation,
do not write the answer, do not continue the conversation, do not invent
further turns. Exactly one JSON object, nothing before or after it."""

# Few-shot examples steer small models hard. The web-search examples are the
# ones that were previously missing, which is why the model rarely searched.
ROUTER_EXAMPLES = """Examples:
User: What is 19% of 240?
{ "tool": "calc", "args": { "expr": "240 * 0.19" }, "rationale": "Exact arithmetic." }

User: Who won the F1 race last weekend?
{ "tool": "search_web", "args": { "query": "F1 race winner last weekend", "k": 5 }, "rationale": "Recent event, needs live info." }

User: What's the latest stable version of Python?
{ "tool": "search_web", "args": { "query": "latest stable Python version", "k": 5 }, "rationale": "Version info changes over time." }

User: Summarize what's on this page https://example.com/post
{ "tool": "fetch_url", "args": { "url": "https://example.com/post" }, "rationale": "Need the page contents." }

User: What time is it?
{ "tool": "now", "args": {}, "rationale": "Needs the current clock." }

User: Write me a haiku about the sea.
{ "tool": "none", "args": {}, "rationale": "Creative task, no tool needed." }

User: Hello, what is your name?
{ "tool": "none", "args": {}, "rationale": "I can answer about myself directly." }

User: What can you do?
{ "tool": "none", "args": {}, "rationale": "Question about myself, answer directly." }"""


def _tool_menu(tools_list: list[str]) -> str:
    lines = []
    for name in tools_list:
        desc = TOOL_DESCRIPTIONS.get(name, "(no description)")
        lines.append(f"- {name}: {desc}")
    return "\n".join(lines)


def react_step_prompt(system: str, tools_list: list[str], scratchpad: str, user: str) -> str:
    return (
        f"System:\n{system}\n\n"
        f"You can call ONE tool to help answer the user. Available tools:\n"
        f"{_tool_menu(tools_list)}\n\n"
        f"{TOOLS_SCHEMA}\n\n"
        f"Guidance: If the question is about current events, recent facts, prices, "
        f"versions, people, or anything you are not certain is still accurate, you MUST "
        f"use search_web rather than guessing.\n"
        f"For greetings, small talk, questions about yourself (your name, your "
        f"purpose, what you can do), opinions, or anything you can answer from what "
        f"you already know, choose \"none\" and answer directly. Do NOT use kb_add or "
        f"kb_query for simple conversational questions; the knowledge base is for "
        f"information the user explicitly asked you to store or look up.\n\n"
        f"{ROUTER_EXAMPLES}\n\n"
        f"Conversation and observations so far:\n{scratchpad}\n\n"
        f"User: {user}\n"
        f"Respond with the JSON object only:"
    )


def final_answer_prompt(system: str, chat: str, rag: str, observations: str, user: str) -> str:
    parts = [f"System:\n{system}"]
    if chat:
        parts.append("Recent conversation:\n" + chat)
    if rag:
        parts.append("Knowledge context:\n" + rag)
    if observations:
        parts.append("Tool observations (use these for your answer; cite URLs when present):\n" + observations)
    parts.append("User:\n" + user + "\nAssistant:")
    return "\n\n".join(parts)
