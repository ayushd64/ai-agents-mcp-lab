# evaluate_rag.py — grade the RAG pipeline with Ragas (local generator, GLM judge)

import sys, types
import os
from dotenv import load_dotenv

# 1. Handle legacy LangChain community imports securely to prevent execution crashes 
try: 
    import langchain_community.chat_models.vertexai # noqa 
except ModuleNotFoundError: 
    stub = types.ModuleType("langchain_community.chat_models.vertexai") 
    stub.ChatVertexAI = object # satisfy the initialization checks internally 
    sys.modules["langchain_community.chat_models.vertexai"] = stub 


from langchain_openai import ChatOpenAI
from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma

from ragas import evaluate
from ragas.dataset_schema import SingleTurnSample, EvaluationDataset
from ragas.metrics import Faithfulness, ResponseRelevancy, LLMContextPrecisionWithoutReference
from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper

load_dotenv(override=True)
CHROMA_DIR, EMBED_MODEL = "chroma_db", "nomic-embed-text"

# --- The RAG pipeline UNDER TEST: retriever + your local model as generator ---
embeddings = OllamaEmbeddings(model=EMBED_MODEL)
vectorstore = Chroma(persist_directory=CHROMA_DIR, embedding_function=embeddings)
generator = ChatOpenAI(model=os.environ["MODEL"],
                       base_url=os.environ["OPENAI_BASE_URL"],
                       api_key=os.environ["OPENAI_API_KEY"])

# --- The JUDGE Ragas uses to score (strong cloud model = trustworthy grades) ---
judge = ChatOpenAI(model=os.environ.get("JUDGE_MODEL", "z-ai/glm-5.2"),
                   base_url=os.environ.get("JUDGE_BASE_URL", "https://integrate.api.nvidia.com/v1"),
                   api_key=os.environ["JUDGE_API_KEY"], temperature=0)

def run_rag(question: str):
    """Retrieve chunks, then answer from them — this is the pipeline we're grading."""
    docs = vectorstore.similarity_search(question, k=3)
    contexts = [d.page_content for d in docs]
    prompt = ("Answer the question using ONLY the context below. "
              "If it's not there, say you don't know.\n\n"
              f"Context:\n{chr(10).join(contexts)}\n\nQuestion: {question}")
    answer = generator.invoke(prompt).content
    return contexts, answer

questions = [
    "What is the refund policy?",
    "How much can the Acme Rover X9 carry?",
    "How many weeks of parental leave do full-time employees get?",
    "What are the support hours?",
]

def main():
    samples = []
    for q in questions:
        contexts, answer = run_rag(q)
        print(f"Q: {q}\nA: {answer[:100]}\n")
        samples.append(SingleTurnSample(
            user_input=q,
            response=answer,
            retrieved_contexts=contexts,
        ))

    result = evaluate(
        dataset=EvaluationDataset(samples=samples),
        metrics=[Faithfulness(), ResponseRelevancy(), LLMContextPrecisionWithoutReference()],
        llm=LangchainLLMWrapper(judge),
        embeddings=LangchainEmbeddingsWrapper(embeddings),
    )
    print("\n=== Ragas scores (0–1, higher is better) ===")
    print(result)
    print(result.to_pandas()[["user_input", "faithfulness", "answer_relevancy",
                              "llm_context_precision_without_reference"]])

if __name__ == "__main__":
    main()

