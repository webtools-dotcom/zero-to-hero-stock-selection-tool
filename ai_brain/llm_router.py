import os
from litellm import completion
from config import DEFAULT_LLM_PROVIDER, DEFAULT_LLM_MODEL

class LLMRouter:
    def __init__(self, provider: str = None, model: str = None, api_key: str = None):
        self.provider = (provider or DEFAULT_LLM_PROVIDER).lower()
        self.model = model or DEFAULT_LLM_MODEL
        if api_key:
            env_map = {
                "gemini": "GEMINI_API_KEY",
                "groq": "GROQ_API_KEY",
                "openrouter": "OPENROUTER_API_KEY",
                "openai": "OPENAI_API_KEY"
            }
            env_key = env_map.get(self.provider, "GEMINI_API_KEY")
            os.environ[env_key] = api_key

    def generate(self, system_prompt: str, user_prompt: str, temperature: float = 0.2) -> str:
        try:
            resp = completion(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=temperature
            )
            return resp.choices[0].message.content
        except Exception as e:
            return f"⚠️ LLM API Error ({self.model}): {str(e)}. Please check your API key in the sidebar."