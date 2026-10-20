import os

try:
    import spaces
except ImportError:
    class _DummySpaces:
        @staticmethod
        def GPU(fn=None, *args, **kwargs):
            if fn is not None and callable(fn):
                return fn
            return lambda f: f

    spaces = _DummySpaces()

try:
    import gradio as gr
except ImportError:
    gr = None

import uvicorn

from mobile.mobile_api import app as mobile_app


@spaces.GPU
def _zero_gpu_probe(x: str = "") -> str:
    return "AlphaSniper Ready"


if gr is not None:
    with gr.Blocks(
        title="AlphaSniper Terminal",
        css="""
            html, body, .gradio-container {
                margin: 0 !important;
                padding: 0 !important;
                width: 100% !important;
                height: 100% !important;
                max-width: 100% !important;
                overflow: hidden !important;
                background-color: #0b0f19 !important;
            }
            footer { display: none !important; }
            #app-iframe {
                position: fixed;
                top: 0;
                left: 0;
                width: 100vw;
                height: 100vh;
                border: none;
                margin: 0;
                padding: 0;
                z-index: 99999;
                display: block;
            }
        """,
    ) as demo:
        _inp = gr.Textbox(visible=False, value="ping")
        _out = gr.Textbox(visible=False)
        _btn = gr.Button("Probe", visible=False)
        _btn.click(fn=_zero_gpu_probe, inputs=_inp, outputs=_out)
        demo.load(fn=_zero_gpu_probe, inputs=_inp, outputs=_out)

        gr.HTML("""
            <iframe id="app-iframe" src="/sniper" allow="clipboard-read; clipboard-write"></iframe>
        """)

    mobile_app.router.routes = [
        r for r in mobile_app.router.routes if getattr(r, "path", "") != "/"
    ]
    app = gr.mount_gradio_app(mobile_app, demo, path="/")
else:
    app = mobile_app


if __name__ == "__main__":
    port = int(os.getenv("GRADIO_SERVER_PORT") or os.getenv("PORT") or "7860")
    uvicorn.run(app, host="0.0.0.0", port=port, access_log=False)
