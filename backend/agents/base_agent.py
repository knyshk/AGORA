from langchain_openai import ChatOpenAI
from config import get_provider_config

def run_agent(role: str, prompt: str) -> str:
    cfg = get_provider_config()
    llm = ChatOpenAI(base_url=cfg["base_url"], api_key=cfg["api_key"], model=cfg["model"])
    return llm.invoke(f"You are a {role} agent. {prompt}").content