import os

import uvicorn

from mobile.mobile_api import app as mobile_app

try:
    import gradio as gr
    import spaces
except Exception:
    gr = None
    spaces = None

if gr is not None and spaces is not None:

    @spaces.GPU(duration=1)
    def _zero_gpu_probe():
        return "ok"

    with gr.Blocks(title="AlphaSniper runtime") as _zero_gpu_demo:
        _probe_output = gr.Textbox(visible=False)
        gr.Button(visible=False).click(_zero_gpu_probe, outputs=_probe_output)

    mobile_app = gr.mount_gradio_app(mobile_app, _zero_gpu_demo, path="/_gradio")


if __name__ == "__main__":
    port = int(os.getenv("GRADIO_SERVER_PORT") or os.getenv("PORT") or "7860")
    uvicorn.run(mobile_app, host="0.0.0.0", port=port, access_log=False)
