# knowledge_server.py — an MCP server that lets the agent look up business definitions

from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma
from mcp.server.fastmcp import FastMCP

CHROMA_DIR, EMBED_MODEL = "dict_db", "nomic-embed-text"

mcp = FastMCP("Data Dictionary")

# Load the persisted index once at startup (fast — no re-embedding)
embeddings = OllamaEmbeddings(model=EMBED_MODEL)
vectorstore = Chroma(persist_directory=CHROMA_DIR, embedding_function=embeddings)

@mcp.tool()
def search_glossary(query: str) -> str:
    """Look up the meaning of a business term, metric, or column (e.g. 'Q1', 'growth',
    'what does revenue include'). Call this when a question uses terms not obvious from column names."""
    results = vectorstore.similarity_search(query, k=3)
    if not results:
        return "No matching definition found."
    return "\n\n".join(d.page_content for d in results)

if __name__ == "__main__":
    mcp.run()

