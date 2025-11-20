# src/ui/contacts_panel.py
import gradio as gr
from typing import List, Tuple
import json

def mount_contacts(root_blocks: gr.Blocks, contacts, kairos):
    # Don't create a new context - we're already inside root_blocks
    with gr.Accordion("Contacts & Collaboration", open=False):
        contact_table = gr.Dataframe(headers=["Alias", "Peer ID"], row_count=5, col_count=(2, "fixed"), interactive=False)
        with gr.Row():
            peer_id_in = gr.Textbox(label="Peer ID")
            alias_in = gr.Textbox(label="Alias")
            vk_in = gr.Textbox(label="Verify Key (b64)")
        with gr.Row():
            add_btn = gr.Button("Add/Update Contact")
            trust_btn = gr.Button("Trust Contact (by Peer ID)")
        gr.Markdown("---")
        scope_in = gr.Textbox(label="Scope JSON", value='{"tools":["kb_query"],"args":{"max_k":3}}')
        ctx_in = gr.Textbox(label="Redacted Context", value="project alpha")
        invite_btn = gr.Button("Invite to Collaborate")
        status_out = gr.Textbox(label="Status", interactive=False)

        def refresh():
            return [(a, p) for a, p, _ in contacts.get_trusted_peers()]

        def add_contact(alias, pid, vk):
            contacts.add_pending(alias, pid, vk)
            return refresh()

        def trust_contact(pid):
            contacts.trust_contact(pid)
            return refresh()

        async def do_invite(pid, scope_json, ctx):
            try:
                scope = json.loads(scope_json)
            except Exception as e:
                return f"Invalid scope JSON: {e}"
            try:
                sid = await kairos.invite(pid, ctx, scope)
                return f"Invite sent. Session {sid}"
            except Exception as e:
                return f"Invite failed: {e}"

        add_btn.click(add_contact, [alias_in, peer_id_in, vk_in], [contact_table])
        trust_btn.click(trust_contact, [peer_id_in], [contact_table])
        invite_btn.click(do_invite, [peer_id_in, scope_in, ctx_in], [status_out])

        root_blocks.load(refresh, outputs=[contact_table])