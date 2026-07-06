import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()

judge = ChatOpenAI(
    model=os.environ.get("JUDGE_MODEL"),
    base_url=os.environ.get("JUDGE_BASE_URL"),
    api_key=os.environ.get("JUDGE_API_KEY"),
    temperature=0,
)

response = judge.invoke("Say hello in one sentence.")

print(response.content)
