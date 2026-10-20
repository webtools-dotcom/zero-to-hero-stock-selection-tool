import os

try:
    import spaces
except Exception:
    spaces = None

try:
    import gradio as gr
except Exception:
    gr = None

import uvicorn

from mobile.mobile_api import app as mobile_app


if spaces is not None and gr is not None:

    @spaces.GPU(duration=1)
    def _zero_gpu_probe(x: str = "") -> str:
        return "ok"

    with gr.Blocks(title="AlphaSniper Terminal") as _zero_gpu_demo:
        _inp = gr.Textbox(visible=False)
        _out = gr.Textbox(visible=False)
        _btn = gr.Button(visible=False)
        _btn.click(fn=_zero_gpu_probe, inputs=_inp, outputs=_out)

    mobile_app = gr.mount_gradio_app(mobile_app, _zero_gpu_demo, path="/_gradio")

app = mobile_app


if __name__ == "__main__":
    port = int(os.getenv("GRADIO_SERVER_PORT") or os.getenv("PORT") or "7860")
    uvicorn.run(mobile_app, host="0.0.0.0", port=port, access_log=False)
