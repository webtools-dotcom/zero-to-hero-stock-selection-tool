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
def _zero_gpu_probe(prompt: str = "") -> str:
    return "AlphaSniper Ready"


if gr is not None:
    _zero_gpu_demo = gr.Interface(
        fn=_zero_gpu_probe,
        inputs=gr.Textbox(label="Status", value="Ready"),
        outputs=gr.Textbox(label="Response"),
        title="AlphaSniper ZeroGPU Probe",
    )
    app = gr.mount_gradio_app(mobile_app, _zero_gpu_demo, path="/gradio")
else:
    app = mobile_app


if __name__ == "__main__":
    port = int(os.getenv("GRADIO_SERVER_PORT") or os.getenv("PORT") or "7860")
    uvicorn.run(app, host="0.0.0.0", port=port, access_log=False)
