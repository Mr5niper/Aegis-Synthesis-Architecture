import gradio as gr, uuid, asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Callable
from ..memory.inbox import MemoryInbox
from ..memory.graph_crdt import LWWGraph
from ..services.sync import SyncService
from .contacts_panel import mount_contacts
from .identity_panel import mount_identity
from gradio import update
from .consent import ConsentBroker
from ..learning.lora_trainer import LoRATrainer
from ..learning.style_adapter import StyleAdapter
from ..__version__ import get_version_info # Added for versioning
from ..core.config import update_web_access, AppConfig
AUDIT_FILE = Path("data/user_data/inbox_approved.jsonl")
def _inbox_choices(inbox: MemoryInbox):
    return [(f"{s} {r} {d}", i) for i, s, r, d in inbox.list_pending()]
def refresh_inbox(inbox: MemoryInbox):
    return update(choices=_inbox_choices(inbox), value=[])
async def approve_facts_handler(selected_ids, inbox, graph, sync_service):
    ids = [int(i) for i in (selected_ids or [])]
    approved = inbox.pop(ids)
    rels_to_sync = []
    if approved:
        AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
    for src, rel, dst, conf in approved:
        rel_obj = graph.upsert(src, rel, dst)
        rels_to_sync.append((rel_obj.src, rel_obj.rel, rel_obj.dst, rel_obj.ts))
        with AUDIT_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": datetime.utcnow().isoformat(),
                "src": src, "rel": rel, "dst": dst, "confidence": conf,
            }) + "\n")
    if rels_to_sync:
        await sync_service.broadcast_relations(rels_to_sync)
    return None
def approve_req(req_id: str, broker: ConsentBroker):
    if broker and req_id.strip():
        broker.resolve(req_id.strip(), True)
    return ""
def deny_req(req_id: str, broker: ConsentBroker):
    if broker and req_id.strip():
        broker.resolve(req_id.strip(), False)
    return ""
def mount_training_viewer(root_blocks: gr.Blocks, trainer: LoRATrainer):
    """Optional training data viewer"""
    # Don't nest contexts
    with gr.Accordion("Training Data", open=False):
        gr.Markdown("### LoRA Fine-tuning Progress")
        
        def get_training_status():
            if not trainer.corrections_file.exists():
                return "No corrections logged yet.", ""
            
            try:
                with open(trainer.corrections_file) as f:
                    corrections = [json.loads(line) for line in f]
                
                count = len(corrections)
                needed = trainer.min_corrections_for_training
                progress = f"{count}/{needed} corrections logged"
                
                if count >= needed:
                    ready = trainer.prepare_training_dataset(needed)
                    if ready:
                        return f"✅ {progress} - Dataset ready!", trainer.get_training_script()
                
                return f"📊 {progress}", ""
            except Exception as e:
                return f"Error: {e}", ""
        
        status_text = gr.Textbox(label="Status", interactive=False)
        script_text = gr.Code(label="Training Script (copy when ready)", language="python", interactive=False)
        refresh_btn = gr.Button("Refresh Status")
        
        def update_status():
            status, script = get_training_status()
            return status, script
        
        refresh_btn.click(update_status, outputs=[status_text, script_text])
        root_blocks.load(update_status, outputs=[status_text, script_text])      
def mount_web_access(root_blocks: gr.Blocks, cfg: "AppConfig", policy):
    """Panel to view/edit which web domains the assistant may fetch.

    Two modes:
      - Allow all sites: represented internally as an EMPTY allow list, which
        the policy and fetch layer treat as "no restriction".
      - Restrict to a list: only the listed domains (and their subdomains) may
        be fetched.
    Changes apply immediately to the running app and are saved to config.yaml.
    """
    current = list(cfg.assistant.allow_domains or [])
    start_allow_all = len(current) == 0

    with gr.Accordion("Web Access", open=False):
        gr.Markdown(
            "Control which websites Aegis may open when it searches or fetches a "
            "page. Turn on **Allow all sites** for unrestricted access, or leave "
            "it off and list the allowed domains (one per line, e.g. `github.com`). "
            "Subdomains are included automatically."
        )
        allow_all_cb = gr.Checkbox(
            label="Allow all sites (no domain restriction)",
            value=start_allow_all,
        )
        domains_box = gr.Textbox(
            label="Allowed domains (one per line)",
            value="\n".join(current),
            lines=6,
            placeholder="github.com\nraw.githubusercontent.com\nwikipedia.org",
            interactive=not start_allow_all,
        )
        with gr.Row():
            save_btn = gr.Button("Save Web Access", variant="primary")
        web_status = gr.Textbox(label="Status", interactive=False, lines=1)
        gr.Markdown(
            "_Note: saving rewrites `config.yaml`. Your settings are preserved; "
            "hand-written comments in the file are not._"
        )

        # Grey out the list when Allow-all is on.
        def _toggle_all(is_all):
            return gr.update(interactive=not is_all)
        allow_all_cb.change(_toggle_all, inputs=[allow_all_cb], outputs=[domains_box], queue=False)

        def _save(is_all, text):
            domains = [line for line in (text or "").splitlines()]
            try:
                saved_path = update_web_access(cfg, policy, bool(is_all), domains)
            except Exception as e:
                return gr.update(), f"Error saving: {e}"
            # Reflect the normalized result back into the box.
            normalized = list(cfg.assistant.allow_domains)
            if is_all:
                msg = "Saved. All sites are now allowed (no restriction)."
            else:
                if normalized:
                    msg = "Saved. Allowing %d domain(s)." % len(normalized)
                else:
                    msg = ("Saved, but the list is empty, so ALL sites are allowed. "
                           "Add domains or this is effectively allow-all.")
            return gr.update(value="\n".join(normalized)), msg

        save_btn.click(_save, inputs=[allow_all_cb, domains_box], outputs=[domains_box, web_status], queue=False)

def launch_gui(agent_factory: Callable, subscribe_suggestions: Callable, contacts, kairos, inbox: MemoryInbox, graph: LWWGraph, sync_service: SyncService, broker: ConsentBroker = None, identity=None, trainer: LoRATrainer = None, style_adapter: StyleAdapter = None, model_names: list[str] = None, on_switch_model=None, cfg=None, policy=None):
    
    # FIX #1: Custom CSS to resolve the double scrollbar issue.
    custom_css = """
    /* Ensure the Chatbot container has clear scroll boundaries */
    .chatbot-container {
        /* Gradio sets height=600, which enforces internal scroll. */
        /* We enforce the scroll here and ensure the outer column doesn't also scroll */
        max-height: 600px !important; 
        overflow-y: auto !important;
    }
    /* Prevent the parent Gradio column from scrolling */
    .gradio-column {
        overflow: visible !important;
    }
    """
    
    with gr.Blocks(theme=gr.themes.Soft(), title="Aegis Synthesis", css=custom_css) as demo:
        gr.Markdown(f"# {get_version_info()}")
        
        with gr.Row():
            with gr.Column(scale=3):
                # FIX #1: Double Scrollbar Fix (using CSS)
                chatbot = gr.Chatbot(
                    label="Conversation",
                    type="messages",
                    height=600, 
                    container=True,
                    show_copy_button=True,
                    elem_classes="chatbot-container" 
                )
                msg = gr.Textbox(label="Your Message", placeholder="Ask me anything...", autofocus=True)
                
                # COMPLETE VERSION: Clear/Export Buttons
                with gr.Row():
                    send_btn = gr.Button("Send", variant="primary", scale=2)
                    stop_btn = gr.Button("⏹️ Stop", variant="stop", scale=1)
                    clear_btn = gr.Button("🗑️ Clear", variant="secondary", scale=1)
                    export_btn = gr.Button("💾 Export", variant="secondary", scale=1)
                
                # FIX #2 & BONUS: Polished Rating/Correction UI
                with gr.Row():
                    rating_btn = gr.Radio(
                        choices=["👍 Good", "👎 Bad", "✏️ Needs Correction"],
                        label="Rate this response",
                        value=None,
                        interactive=True,
                        info="Help me learn from your feedback!"
                    )
                with gr.Row():
                    correction_box = gr.Textbox(
                        label="Your Correction (if needed)",
                        placeholder="Enter the correct response here...",
                        visible=False,
                        lines=3,
                        interactive=True
                    )
                rating_output = gr.Textbox(
                    label="Feedback Status", 
                    interactive=False,
                    show_label=True,
                    lines=2,
                    visible=True 
                )

            with gr.Column(scale=1):
                gr.Markdown("### Suggestions")
                suggestions = gr.Textbox(label="Proactive Feed", lines=10, interactive=False)
                use_sug_btn = gr.Button("Use Last Suggestion")
                if model_names and on_switch_model:
                    with gr.Accordion("Models", open=False):
                        model_dd = gr.Dropdown(choices=model_names, value=model_names[0], label="Active model")
                        model_status = gr.Textbox(label="Model status", interactive=False)
                        def _switch(name):
                            return on_switch_model(name)
                        model_dd.change(_switch, inputs=[model_dd], outputs=[model_status])
                if cfg is not None:
                    mount_web_access(demo, cfg, policy)
                gr.Markdown("### Memory Inbox")
                pending_facts = gr.CheckboxGroup(label="Approve Pending Facts", choices=[])
                approve_btn = gr.Button("Approve Selected")
                with gr.Accordion("Collaboration Requests", open=False):
                    req_id_box = gr.Textbox(label="Request ID (from Suggestion Feed)", interactive=True)
                    collab_approve_btn = gr.Button("Approve Collaboration")
                    collab_deny_btn = gr.Button("Deny Collaboration")
                mount_contacts(demo, contacts, kairos)
                if identity:
                    pid, vk_b64, fpr = identity
                    mount_identity(demo, pid, vk_b64, fpr)
                
                if trainer:
                    mount_training_viewer(demo, trainer)

        sid = gr.State(lambda: str(uuid.uuid4()))
        cancel = gr.State(lambda: asyncio.Event())
        
        # Clear conversation handler
        def clear_conversation():
            """Clear chat and start fresh session"""
            new_session_id = str(uuid.uuid4())
            return [], new_session_id 
        # Export handler
        def export_conversation(history):
            """Export chat as markdown"""
            if not history:
                return "No conversation to export."
            
            md = "# Aegis Conversation Export\n\n"
            md += f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            md += "---\n\n"
            
            turn = 0
            for m in history:
                role = m.get("role")
                content = m.get("content", "")
                if role == "user":
                    turn += 1
                    md += f"## Turn {turn}\n\n"
                    md += f"**You:** {content}\n\n"
                elif role == "assistant":
                    md += f"**Aegis:** {content}\n\n"
                    md += "---\n\n"
            
            # Save to file
            filename = f"conversation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
            filepath = Path("data/user_data") / filename
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_text(md, encoding='utf-8')
            
            return f"✅ Exported to: {filename}"
        # Rating handler. Returns exactly two outputs: the feedback-status text
        # and the correction box visibility. It does NOT write back to rating_btn
        # (doing so retriggers .change with rating=None, which blanked the status
        # message and made it look like nothing happened).
        def handle_rating(rating, history, correction_text):
            if not rating:  # nothing selected (e.g. radio was cleared)
                return "", gr.update(visible=False)

            if not history:
                return "⚠️ No conversation yet to rate.", gr.update(visible=False)

            last_user = next(
                (m.get("content", "") for m in reversed(history) if m.get("role") == "user"), ""
            )
            last_assistant = next(
                (m.get("content", "") for m in reversed(history) if m.get("role") == "assistant"), ""
            )

            if rating == "✏️ Needs Correction":
                if correction_text and correction_text.strip():
                    if trainer:
                        trainer.log_correction(
                            last_user,
                            last_assistant,
                            correction_text.strip(),
                            "user_correction",
                        )
                        return "✅ Correction logged! I'll learn from this.", gr.update(visible=False)
                    return "⚠️ Correction training is not enabled.", gr.update(visible=False)
                else:
                    # Reveal the correction box and wait for the user to type + submit.
                    return "✏️ Enter your correction below, then press Enter.", gr.update(visible=True)

            elif rating == "👍 Good":
                return "✅ Thanks! Glad I could help.", gr.update(visible=False)

            elif rating == "👎 Bad":
                return "📝 Noted. I'll try to improve!", gr.update(visible=False)

            return "", gr.update(visible=False)
            
        # FIX #2: Updated Chat Flow to handle message disappearance
        async def user_turn(message, history, s, c):
            c.clear()
            # Messages format: append the user turn, then an assistant placeholder
            # that gets overwritten as the response streams in.
            return history + [
                {"role": "user", "content": message},
                {"role": "assistant", "content": "⏳ Thinking..."},
            ], "", s, c 
            
        async def bot_turn(history, s, c):
            agent = agent_factory()
            
            current_response = ""
            
            # The latest user message is the entry before the assistant
            # placeholder appended in user_turn.
            user_message = next(
                (m.get("content", "") for m in reversed(history) if m.get("role") == "user"), ""
            )
            
            try:
                # Accumulate response and overwrite the last assistant message's
                # content, clearing the "Thinking..." placeholder on first chunk.
                async for chunk in agent.run(s, user_message, c):
                    current_response += chunk
                    history[-1] = {"role": "assistant", "content": current_response}
                    yield history
            except Exception as e:
                error_msg = f"\n\n❌ **Error:** {str(e)}\n\n"
                if "exceed context window" in str(e):
                    error_msg += "💡 **Tip:** Your message was too long. Try:\n"
                    error_msg += "- Breaking it into smaller chunks\n"
                    error_msg += "- Using `kb_add` tool to store large text\n"
                    error_msg += "- Switching to the 'large' model (8K context)\n"
                
                # Append error message to whatever partial response was streamed (current_response)
                history[-1] = {"role": "assistant", "content": current_response + error_msg}
                yield history
        
        # Wire up chat flow
        req = msg.submit(user_turn, [msg, chatbot, sid, cancel], [chatbot, msg, sid, cancel], queue=False).then(
            bot_turn, [chatbot, sid, cancel], chatbot
        )
        req2 = send_btn.click(user_turn, [msg, chatbot, sid, cancel], [chatbot, msg, sid, cancel], queue=False).then(
            bot_turn, [chatbot, sid, cancel], chatbot
        )
        stop_btn.click(lambda c: c.set(), inputs=cancel, outputs=None, queue=False, cancels=[req, req2])
        
        # Clear button
        clear_btn.click(
            clear_conversation,
            inputs=None,
            outputs=[chatbot, sid],
            queue=False
        ).then(
            lambda: gr.update(value=None),  # Reset rating
            outputs=[rating_btn],
            queue=False
        ).then(
            lambda: "",  # Clear rating output
            outputs=[rating_output],
            queue=False
        ).then(
            lambda: gr.update(visible=False),  # Hide correction box
            outputs=[correction_box],
            queue=False
        )
        # Export button wiring
        export_btn.click(
            export_conversation,
            inputs=[chatbot],
            outputs=[rating_output],
            queue=False
        )
        # Wire up Rating flow. A single change-handler writes the feedback status
        # and toggles the correction box. It deliberately does NOT output back to
        # rating_btn (that retriggered change and wiped the status message).
        rating_btn.change(
            handle_rating,
            inputs=[rating_btn, chatbot, correction_box],
            outputs=[rating_output, correction_box],
            queue=False
        )
        correction_box.submit(
            handle_rating,
            inputs=[rating_btn, chatbot, correction_box],
            outputs=[rating_output, correction_box],
            queue=False
        )
        async def suggestions_stream():
            buf = []
            async for item in subscribe_suggestions():
                buf.append(f"• {item}")
                buf = buf[-15:]
                yield "\n".join(buf)
        use_sug_btn.click(lambda t: (t.strip().splitlines()[-1].lstrip("• ").strip() if t.strip() else ""),
                          inputs=suggestions, outputs=msg, queue=False)
        def do_refresh():
            return refresh_inbox(inbox)
        # Using closure instead of gr.State for approve handler
        async def approve_handler(selected_ids):
            return await approve_facts_handler(selected_ids, inbox, graph, sync_service)
        approve_btn.click(
            approve_handler,
            inputs=[pending_facts],
            outputs=[],
            queue=True
        ).then(do_refresh, outputs=[pending_facts])
        # Using closure for consent handlers
        def approve_req_handler(req_id):
            return approve_req(req_id, broker)
        
        def deny_req_handler(req_id):
            return deny_req(req_id, broker)
        collab_approve_btn.click(approve_req_handler, inputs=[req_id_box], outputs=[req_id_box], queue=False)
        collab_deny_btn.click(deny_req_handler, inputs=[req_id_box], outputs=[req_id_box], queue=False)
        
    demo.queue().launch(
        server_name="127.0.0.1",
        server_port=7860,
        show_api=False,        # avoid gradio_client get_api_info() schema bug ('bool' is not iterable)
        show_error=True,
        inbrowser=True,
    )