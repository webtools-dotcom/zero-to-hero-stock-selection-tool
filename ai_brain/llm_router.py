from config import DEFAULT_LLM_PROVIDER, DEFAULT_LLM_MODEL

class LLMRouter:
    def __init__(self, provider: str = None, model: str = None, api_key: str = None):
        self.provider = (provider or DEFAULT_LLM_PROVIDER).lower()
        self.model = model or DEFAULT_LLM_MODEL
        self.api_key = (api_key or "").strip()

    def generate(self, system_prompt: str, user_prompt: str, temperature: float = 0.2) -> str:
        try:
            from litellm import completion

            kwargs = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": temperature,
                "timeout": 20,
                "num_retries": 1,
            }
            if self.api_key:
                kwargs["api_key"] = self.api_key
            resp = completion(**kwargs)
            return resp.choices[0].message.content
        except Exception as e:
            return f"⚠️ LLM API Error ({self.model}): {str(e)}. Please check your API key in the sidebar."