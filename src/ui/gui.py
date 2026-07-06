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
from ..core.config import update_web_access, update_search_provider, update_web_enabled, AppConfig
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
    """Panel to view/edit web access.

    THREE levels of control, top to bottom:

      1. 'Enable web access' (allow_web_search) -- the MASTER switch. When off,
         Aegis does no web activity at all (it does not even run the web-need
         classifier) and every control below is greyed out but keeps its value,
         so flipping it back on restores the exact prior state.

      2. 'Allow all sites' (allow_all_web) -- when on, any site may be opened and
         the domain list is ignored (but preserved); when off, only the listed
         domains (and subdomains) may be opened.

      3. The allowed-domains list and the search provider (+ optional Tavily
         key).

    All changes save immediately; a failed save is printed to the console
    instead of being silently swallowed.
    """
    current = list(cfg.assistant.allow_domains or [])
    start_enabled = bool(cfg.assistant.allow_web_search)
    start_allow_all = bool(cfg.assistant.allow_all_web)
    _prov_label = {"duckduckgo": "DuckDuckGo", "tavily": "Tavily"}
    start_provider = _prov_label.get(
        (cfg.assistant.search_provider or "tavily").lower(), "Tavily")

    with gr.Accordion("Web Access", open=False):
        gr.Markdown(
            "Turn **Enable web access** off to stop Aegis using the internet "
            "entirely (it will answer only from local knowledge and will not even "
            "try to look anything up). With it on, use **Allow all sites** to let "
            "it open any site, or turn that off to restrict it to the domains you "
            "list (one per line, e.g. `github.com`; subdomains included). Changes "
            "save automatically."
        )

        # 1. MASTER SWITCH.
        enable_web_cb = gr.Checkbox(
            label="Enable web access (master switch)",
            value=start_enabled,
        )

        # 2. Allow-all switch (greyed unless web is enabled).
        allow_all_cb = gr.Checkbox(
            label="Allow all sites (no domain restriction)",
            value=start_allow_all,
            interactive=start_enabled,
        )
        # 3a. Allowed-domains list (editable only when web is enabled AND
        # allow-all is off).
        domains_box = gr.Textbox(
            label="Allowed domains (one per line)",
            value="\n".join(current),
            lines=6,
            placeholder="github.com\nraw.githubusercontent.com\nwikipedia.org",
            interactive=start_enabled and not start_allow_all,
        )

        # Persist helper for the allow-all switch + domain list. Saves the
        # checkbox state (the mode) and the CURRENT textbox contents (always, so
        # the list is never lost). Any failure is printed, not swallowed.
        def _persist(is_all, text):
            try:
                saved_to = update_web_access(
                    cfg, policy, bool(is_all), (text or "").splitlines())
                print(f"[web_access] saved: allow_all={bool(is_all)} "
                      f"domains={cfg.assistant.allow_domains} -> {saved_to}")
            except Exception as e:  # noqa: BLE001
                print(f"[web_access] SAVE FAILED: {type(e).__name__}: {e}")

        # Toggling allow-all sets the mode: save, then grey/ungrey the domain box
        # (its text is left as-is so the list is preserved). The box is editable
        # only when web is enabled and allow-all is off.
        def _on_toggle(is_all, text, enabled):
            _persist(is_all, text)
            return gr.update(interactive=bool(enabled) and not bool(is_all))
        allow_all_cb.change(
            _on_toggle, inputs=[allow_all_cb, domains_box, enable_web_cb],
            outputs=[domains_box], queue=False,
        )

        # Editing the list saves on blur / submit (not each keystroke).
        def _on_domains(is_all, text):
            _persist(is_all, text)
        domains_box.blur(_on_domains, inputs=[allow_all_cb, domains_box], outputs=None, queue=False)
        domains_box.submit(_on_domains, inputs=[allow_all_cb, domains_box], outputs=None, queue=False)

        # 3b. Search provider. Exactly one at a time (radio). Tavily is listed
        # first (it is the default and works keyless). To add another provider
        # later: implement it in search.py, allow its value in
        # config.update_search_provider, and add a choice here.
        gr.Markdown("**Search provider** (used when Aegis searches; pick one)")
        provider_radio = gr.Radio(
            choices=["Tavily", "DuckDuckGo"],
            value=start_provider,
            show_label=False,
            interactive=start_enabled,
        )
        gr.Markdown(
            "Tavily: works with no key (rate-limited); add a free key from "
            "tavily.com for higher limits. DuckDuckGo: no key, often rate-limited."
        )
        tavily_key_box = gr.Textbox(
            label="Tavily API key (optional - blank uses keyless mode)",
            value=cfg.assistant.tavily_api_key or "",
            type="password",
            placeholder="tvly-...",
            interactive=start_enabled,
            visible=(start_provider == "Tavily"),
        )

        # Save provider + key together; a failure is printed, not swallowed.
        def _save_provider(prov_label, key):
            prov = "tavily" if prov_label == "Tavily" else "duckduckgo"
            try:
                saved_to = update_search_provider(cfg, prov, key or "")
                print(f"[web_access] saved: search_provider={prov} "
                      f"tavily_key={'set' if (key or '').strip() else 'empty'} "
                      f"-> {saved_to}")
            except Exception as e:  # noqa: BLE001
                print(f"[web_access] SAVE FAILED (provider): {type(e).__name__}: {e}")

        # Switching provider saves and shows the key box only for Tavily. The key
        # box stays editable only while web is enabled.
        def _on_provider(prov_label, key, enabled):
            _save_provider(prov_label, key)
            return gr.update(visible=(prov_label == "Tavily"),
                             interactive=bool(enabled))
        provider_radio.change(
            _on_provider, inputs=[provider_radio, tavily_key_box, enable_web_cb],
            outputs=[tavily_key_box], queue=False)

        # Save the key on blur / submit (not each keystroke).
        def _on_key(prov_label, key):
            _save_provider(prov_label, key)
        tavily_key_box.blur(_on_key, inputs=[provider_radio, tavily_key_box], outputs=None, queue=False)
        tavily_key_box.submit(_on_key, inputs=[provider_radio, tavily_key_box], outputs=None, queue=False)

        # MASTER SWITCH handler (wired last, once every sub-control exists).
        # Saves allow_web_search, then greys/ungreys ALL controls below without
        # changing their values, honoring the sub-rules (domain box only editable
        # when allow-all is off; key box only visible for Tavily).
        def _persist_enabled(enabled):
            try:
                saved_to = update_web_enabled(cfg, policy, bool(enabled))
                print(f"[web_access] saved: allow_web_search={bool(enabled)} "
                      f"-> {saved_to}")
            except Exception as e:  # noqa: BLE001
                print(f"[web_access] SAVE FAILED (enable): {type(e).__name__}: {e}")

        def _on_enable(enabled, is_all, prov_label):
            _persist_enabled(enabled)
            en = bool(enabled)
            return (
                gr.update(interactive=en),                                  # allow_all_cb
                gr.update(interactive=en and not bool(is_all)),             # domains_box
                gr.update(interactive=en),                                  # provider_radio
                gr.update(interactive=en, visible=(prov_label == "Tavily")),  # tavily_key_box
            )
        enable_web_cb.change(
            _on_enable,
            inputs=[enable_web_cb, allow_all_cb, provider_radio],
            outputs=[allow_all_cb, domains_box, provider_radio, tavily_key_box],
            queue=False,
        )

def launch_gui(agent_factory: Callable, subscribe_suggestions: Callable, contacts, kairos, inbox: MemoryInbox, graph: LWWGraph, sync_service: SyncService, broker: ConsentBroker = None, identity=None, trainer: LoRATrainer = None, style_adapter: StyleAdapter = None, model_names: list[str] = None, on_switch_model=None, cfg=None, policy=None):
    
    # Theme + palette. We build on gr.themes.Base (which, unlike Soft, carries
    # no purple defaults) with a blue primary hue, then pin exact colors for
    # dark and light via CSS variables so both modes match the intended look
    # (deep navy dark; a clean light inversion). The light/dark toggle is kept.
    # Theme built with gr.themes.Base and configured through .set(), which is
    # how Gradio applies colors across every component consistently (setting raw
    # CSS variables alone only reaches some surfaces). The dark values are
    # sampled directly from the target design: near-black navy page, slightly
    # lighter navy panels, a muted steel-blue primary button, and subtle blue
    # borders. Light values are a clean inversion using the same blue accent.
    # No purple anywhere; the light/dark/system toggle is preserved.
    aegis_theme = gr.themes.Base(
        primary_hue=gr.themes.colors.blue,
        secondary_hue=gr.themes.colors.blue,
        neutral_hue=gr.themes.colors.slate,
        font=[gr.themes.GoogleFont("Inter"), "system-ui", "sans-serif"],
    ).set(
        # Page and block surfaces. *_dark are the values used in dark mode.
        body_background_fill="#f4f7fb",
        body_background_fill_dark="#0e1014",
        background_fill_primary="#ffffff",
        background_fill_primary_dark="#141c2b",
        background_fill_secondary="#eef3fa",
        background_fill_secondary_dark="#1a2334",
        block_background_fill="#ffffff",
        block_background_fill_dark="#141c2b",
        block_border_color="#d7e0ee",
        block_border_color_dark="#1e2b45",
        border_color_primary="#d7e0ee",
        border_color_primary_dark="#1e2b45",
        # Panels/accordions.
        panel_background_fill="#ffffff",
        panel_background_fill_dark="#1a2334",
        # Inputs.
        input_background_fill="#ffffff",
        input_background_fill_dark="#0e1014",
        input_border_color="#d7e0ee",
        input_border_color_dark="#1e2b45",
        # Text.
        body_text_color="#0f1729",
        body_text_color_dark="#e8eefc",
        body_text_color_subdued="#52607a",
        body_text_color_subdued_dark="#8a97ad",
        # Links / accent.
        link_text_color="#1d4ed8",
        link_text_color_dark="#60a5fa",
        # Primary button: muted steel-blue in dark (matches the design),
        # standard blue in light; both brighten on hover.
        button_primary_background_fill="#2563eb",
        button_primary_background_fill_dark="#274270",
        button_primary_background_fill_hover="#1d4ed8",
        button_primary_background_fill_hover_dark="#2f5490",
        button_primary_text_color="#ffffff",
        button_primary_text_color_dark="#ffffff",
        # Secondary button.
        button_secondary_background_fill="#eef3fa",
        button_secondary_background_fill_dark="#182130",
        button_secondary_background_fill_hover="#e2ebf7",
        button_secondary_background_fill_hover_dark="#20293a",
        button_secondary_text_color="#0f1729",
        button_secondary_text_color_dark="#e8eefc",
    )

    # CSS is now only the scroll fix plus a safety net that forces focus rings,
    # sliders, and toggles to blue in case any component ignores the theme.
    custom_css = """
    .chatbot-container {
        max-height: 600px !important;
        overflow-y: auto !important;
    }
    .gradio-column { overflow: visible !important; }
    *:focus-visible { outline-color: #2563eb !important; }
    input[type=range] { accent-color: #2563eb !important; }
    input[type=checkbox], input[type=radio] { accent-color: #2563eb !important; }
    """
    
    with gr.Blocks(theme=aegis_theme, title="Aegis Synthesis", css=custom_css) as demo:
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
                        # Just the selector; it always shows the working model.
                        # The status textbox was removed as redundant: the
                        # dropdown value is the source of truth for which model
                        # is active. _switch performs the swap and returns the
                        # name straight back into the dropdown so the selection
                        # reflects the model in use.
                        model_dd = gr.Dropdown(choices=model_names, value=model_names[0], label="Active model")
                        async def _switch(name):
                            await on_switch_model(name)
                            return gr.update(value=name)
                        model_dd.change(_switch, inputs=[model_dd], outputs=[model_dd])
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
            agent = await agent_factory()
            
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
        # show_progress="hidden": suppress Gradio's elapsed-seconds timer on the
        # streaming response event. That timer is only a stopwatch of how long the
        # event has run (it cannot predict time remaining), which was misleading.
        req = msg.submit(user_turn, [msg, chatbot, sid, cancel], [chatbot, msg, sid, cancel], queue=False).then(
            bot_turn, [chatbot, sid, cancel], chatbot, show_progress="hidden"
        )
        req2 = send_btn.click(user_turn, [msg, chatbot, sid, cancel], [chatbot, msg, sid, cancel], queue=False).then(
            bot_turn, [chatbot, sid, cancel], chatbot, show_progress="hidden"
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