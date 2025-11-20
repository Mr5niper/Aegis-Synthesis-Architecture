# src/ui/identity_panel.py
import gradio as gr

def mount_identity(root: gr.Blocks, peer_id: str, vk_b64: str, fingerprint: str):
    # Don't nest contexts
    with gr.Accordion("Local Identity", open=False):
        gr.Markdown("Share your Verify Key (base64) with trusted contacts. Confirm the fingerprint out-of-band (TOFU).")
        gr.Textbox(label="Peer ID", value=peer_id, interactive=False)
        gr.Textbox(label="Verify Key (base64)", value=vk_b64, lines=3, interactive=False)
        gr.Textbox(label="Fingerprint (SHA256 short)", value=fingerprint, interactive=False)