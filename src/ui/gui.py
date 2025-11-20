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
def launch_gui(agent_factory: Callable, subscribe_suggestions: Callable, contacts, kairos, inbox: MemoryInbox, graph: LWWGraph, sync_service: SyncService, broker: ConsentBroker = None, identity=None, trainer: LoRATrainer = None, style_adapter: StyleAdapter = None, model_names: list[str] = None, on_switch_model=None):
    
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
            
            for i, (user_msg, assistant_msg) in enumerate(history, 1):
                md += f"## Turn {i}\n\n"
                md += f"**You:** {user_msg}\n\n"
                md += f"**Aegis:** {assistant_msg}\n\n"
                md += "---\n\n"
            
            # Save to file
            filename = f"conversation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
            filepath = Path("data/user_data") / filename
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_text(md, encoding='utf-8')
            
            return f"✅ Exported to: {filename}"
        # FIX #2 HANDLER: Updated Rating Handler
        def handle_rating(rating, history, correction_text):
            if not history or not trainer:
                return "⚠️ No conversation history available.", gr.update(visible=False), gr.update(value=None)
            
            if not rating:  # No rating selected
                return "", gr.update(visible=False), gr.update(value=None)
            
            last_user, last_assistant = history[-1]
            
            if rating == "✏️ Needs Correction":
                if correction_text and correction_text.strip():
                    trainer.log_correction(
                        last_user,
                        last_assistant,
                        correction_text.strip(),
                        "user_correction"
                    )
                    return "✅ Correction logged! I'll learn from this.", gr.update(visible=False), gr.update(value=None)
                else:
                    return "⚠️ Please enter your correction above.", gr.update(visible=True), gr.update(value=rating)
            
            elif rating == "👍 Good":
                # Could log positive feedback here
                return "✅ Thanks! Glad I could help.", gr.update(visible=False), gr.update(value=None)
            
            elif rating == "👎 Bad":
                # Could log negative feedback here
                return "📝 Noted. I'll try to improve!", gr.update(visible=False), gr.update(value=None)
            
            return "", gr.update(visible=False), gr.update(value=None)
            
        # FIX #2: Updated Chat Flow to handle message disappearance
        async def user_turn(message, history, s, c):
            c.clear()
            # FIX: Use placeholder message so the user message remains visible while processing
            return history + [(message, "⏳ Thinking...")], "", s, c 
            
        async def bot_turn(history, s, c):
            agent = agent_factory()
            
            current_response = ""
            
            try:
                # FIX: Accumulate response and overwrite history[-1][1] completely, 
                # ensuring the "Thinking..." placeholder is cleared immediately by the stream.
                async for chunk in agent.run(s, history[-1][0], c):
                    current_response += chunk
                    history[-1] = (history[-1][0], current_response)
                    yield history
            except Exception as e:
                error_msg = f"\n\n❌ **Error:** {str(e)}\n\n"
                if "exceed context window" in str(e):
                    error_msg += "💡 **Tip:** Your message was too long. Try:\n"
                    error_msg += "- Breaking it into smaller chunks\n"
                    error_msg += "- Using `kb_add` tool to store large text\n"
                    error_msg += "- Switching to the 'large' model (8K context)\n"
                
                # Append error message to whatever partial response was streamed (current_response)
                history[-1] = (history[-1][0], current_response + error_msg)
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
        # Wire up Rating flow 
        rating_btn.change(
            lambda r: gr.update(visible=(r == "✏️ Needs Correction")),
            inputs=[rating_btn],
            outputs=[correction_box],
            queue=False
        )
        rating_btn.change(
            handle_rating,
            inputs=[rating_btn, chatbot, correction_box],
            outputs=[rating_output, correction_box, rating_btn],
            queue=False
        )
        correction_box.submit(
            handle_rating,
            inputs=[rating_btn, chatbot, correction_box],
            outputs=[rating_output, correction_box, rating_btn],
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
        
    demo.queue().launch()