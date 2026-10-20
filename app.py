"""Hugging Face Gradio entry point and local FastAPI launcher."""

import os

from mobile.mobile_api import app as mobile_app, start_backend, stop_backend

try:
    import spaces
except ImportError:
    class _LocalSpaces:
        @staticmethod
        def GPU(fn=None, *args, **kwargs):
            if fn is not None and callable(fn):
                return fn
            return lambda decorated: decorated

    spaces = _LocalSpaces()


@spaces.GPU(duration=1)
def _zero_gpu_probe(value: str = "") -> str:
    # Registered for ZeroGPU's startup check and never called automatically.
    return value or "AlphaSniper Ready"


def launch_huggingface_space() -> None:
    """Run Gradio as the sole server and graft the FastAPI routes onto it."""
    import atexit

    import gradio as gr
    css = """
    html, body, .gradio-container {
        margin: 0 !important;
        padding: 0 !important;
        width: 100% !important;
        height: 100% !important;
        max-width: 100% !important;
        overflow: hidden !important;
        background: #0b0f19 !important;
    }
    footer { display: none !important; }
    #app-iframe {
        position: fixed;
        inset: 0;
        width: 100vw;
        height: 100vh;
        border: 0;
        z-index: 99999;
    }
    """

    with gr.Blocks(title="AlphaSniper Terminal") as demo:
        probe_input = gr.Textbox(visible=False, value="ping")
        probe_output = gr.Textbox(visible=False)
        probe_button = gr.Button("Probe", visible=False)
        probe_button.click(fn=_zero_gpu_probe, inputs=probe_input, outputs=probe_output)
        gr.HTML(
            '<iframe id="app-iframe" src="/sniper" '
            'allow="clipboard-read; clipboard-write"></iframe>'
        )

    # Gradio owns the only listener on port 7860. Disable SSR's Node proxy so
    # custom FastAPI paths reach the Python ASGI app, then attach the backend
    # routes to Gradio's app before accepting normal user traffic.
    demo.launch(
        server_name="0.0.0.0",
        server_port=int(os.getenv("GRADIO_SERVER_PORT") or os.getenv("PORT") or "7860"),
        prevent_thread_lock=True,
        ssr_mode=False,
        css=css,
    )

    gradio_app = demo.app
    fastapi_routes = [
        route
        for route in mobile_app.router.routes
        if getattr(route, "path", None) != "/"
    ]
    gradio_app.router.routes[:0] = fastapi_routes

    start_backend()
    atexit.register(stop_backend)
    demo.block_thread()


if __name__ == "__main__":
    if os.getenv("SPACE_ID"):
        launch_huggingface_space()
    else:
        import uvicorn

        uvicorn.run(
            "mobile.mobile_api:app",
            host="0.0.0.0",
            port=int(os.getenv("PORT", "7860")),
            access_log=False,
        )
