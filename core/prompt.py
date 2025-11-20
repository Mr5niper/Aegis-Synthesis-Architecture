TOOLS_SCHEMA = """When invoking a tool, output ONLY a JSON object with this schema:
{ "tool": "<tool_name>", "args": { ... }, "rationale": "<why>" }
If no tool is needed, output your final answer as plain text (no JSON)."""

def react_step_prompt(system: str, tools_list: list[str], scratchpad: str, user: str) -> str:
    return (f"System:\n{system}\n\nAvailable tools: {', '.join(tools_list)}\n{TOOLS_SCHEMA}\n\nHistory and observations so far:\n{scratchpad}\n\nUser: {user}\nAssistant:")

def final_answer_prompt(system: str, chat: str, rag: str, observations: str, user: str) -> str:
    parts = [f"System:\n{system}"]
    if chat: parts.append("Recent conversation:\n" + chat)
    if rag: parts.append("Knowledge context:\n" + rag)
    if observations: parts.append("Tool observations:\n" + observations)
    parts.append("User:\n" + user + "\nAssistant:")
    return "\n\n".join(parts)