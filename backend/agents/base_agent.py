import os
from langchain_openai import ChatOpenAI
from config import PROVIDER_ENDPOINTS

async def run_agent(role: str, prompt: str, provider: str = None, model: str = None) -> str:
    provider = provider or os.getenv("LLM_PROVIDER", "groq")
    model = model or os.getenv("LLM_MODEL")
    api_key = os.getenv(f"{provider.upper()}_API_KEY")
    llm = ChatOpenAI(
        base_url=PROVIDER_ENDPOINTS[provider],
        api_key=api_key,
        model=model,
        timeout=20,
        max_retries=1,
    )
    return (await llm.ainvoke(f"You are a {role} agent. {prompt}")).content
