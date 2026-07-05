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

User: you have web access can you check espn.com
{ "tool": "fetch_url", "args": { "url": "https://espn.com" }, "rationale": "User asked me to read a specific site; add https:// to the bare domain." }

User: can you look at what's on wikipedia.org about otters
{ "tool": "search_web", "args": { "query": "otters site:wikipedia.org", "k": 5 }, "rationale": "Named site plus a topic; search it live." }

User: check the news on cnn.com
{ "tool": "fetch_url", "args": { "url": "https://cnn.com" }, "rationale": "User named a site to read; fetch it." }

User: who did the Portland Trail Blazers just trade for?
{ "tool": "search_web", "args": { "query": "Portland Trail Blazers latest trade", "k": 5 }, "rationale": "Recent event, needs live info." }

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
        f"Guidance: Most messages need NO tool. For greetings, small talk, "
        f"questions about yourself (your name, your purpose, what you can do), "
        f"opinions, explanations, writing, or anything you can answer from what you "
        f"already know, you MUST choose \"none\" and answer directly. Never use "
        f"kb_add or kb_query for simple conversational questions; the knowledge base "
        f"is only for information the user explicitly asked you to store or look up.\n"
        f"Only use a tool when the question genuinely requires one: search_web for "
        f"current events, recent facts, prices, versions, or people you are not "
        f"certain about; calc for arithmetic; now for the current time; fetch_url "
        f"for a specific page. When the user names a website or asks you to check, "
        f"open, read, or look at a site (even a bare domain like \"espn.com\"), you "
        f"DO have web access through these tools: use fetch_url for that page (add "
        f"\"https://\" to a bare domain), or search_web if they name a site plus a "
        f"topic. Never reply that you cannot access the internet or a website; the "
        f"tools above are your web access. If in doubt for a conversational message, "
        f"choose \"none\".\n\n"
        f"{ROUTER_EXAMPLES}\n\n"
        f"Conversation and observations so far:\n{scratchpad}\n\n"
        f"User: {user}\n"
        f"Respond with the JSON object only:"
    )


def final_answer_prompt(system: str, chat: str, rag: str, observations: str, user: str) -> str:
    # The style instruction goes in the SYSTEM block, not just before the answer.
    # Small models parrot whatever instruction sits right before the generation
    # point, so putting "answer in plain English" at the end made it echo that
    # sentence verbatim. Kept high up, it steers without being copied.
    style = (
        "You are answering a person in a chat. Reply with a single, direct answer "
        "in plain, natural English prose. Do NOT output JSON, key/value pairs, code "
        "blocks, curly braces, or field names. Do NOT write \"Observation\", "
        "\"Action\", \"Note\", stage directions in parentheses, or any further "
        "turns of dialogue. Write the answer and then stop."
    )
    parts = [f"System:\n{system}\n\n{style}"]
    if chat:
        parts.append("Recent conversation:\n" + chat)
    if rag:
        parts.append("Knowledge context:\n" + rag)
    if observations:
        parts.append("Tool observations (use these for your answer; cite URLs when present):\n" + observations)
    parts.append("User:\n" + user + "\nAssistant:")
    return "\n\n".join(parts)


def build_answer_messages(system: str, history: list, rag: str, observations: str, user: str) -> list:
    """Build a messages list for the model's native chat template
    (create_chat_completion). This replaces the flat User:/Assistant: string
    format the models were never trained on. history is a list of prior turns
    as {'role': 'user'|'assistant', 'content': str}; rag/observations are folded
    into the system message as context so they do not pollute the turn roles.
    """
    style = (
        "You are answering a person in a chat. Reply with a single, direct answer "
        "in plain, natural English prose. Do NOT output JSON, key/value pairs, code "
        "blocks, curly braces, or field names. Do NOT write \"Observation\", "
        "\"Action\", \"Note\", stage directions in parentheses, or any further "
        "turns of dialogue. Write the answer and then stop."
    )
    sys_content = f"{system}\n\n{style}"
    if rag:
        sys_content += "\n\nKnowledge context:\n" + rag
    if observations:
        sys_content += ("\n\nTool observations (use these for your answer; cite "
                        "URLs when present):\n" + observations)
    messages = [{"role": "system", "content": sys_content}]
    # Prior conversation turns, if any, so the template frames real multi-turn.
    for turn in (history or []):
        role = turn.get("role")
        content = turn.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user})
    return messages
