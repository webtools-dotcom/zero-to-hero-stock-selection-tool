import os

import uvicorn

from mobile.mobile_api import app as mobile_app

try:
    import spaces

    @spaces.GPU(duration=1)
    def _zero_gpu_probe():
        return "ok"

except Exception:
    pass


if __name__ == "__main__":
    port = int(os.getenv("GRADIO_SERVER_PORT") or os.getenv("PORT") or "7860")
    uvicorn.run(mobile_app, host="0.0.0.0", port=port, access_log=False)
