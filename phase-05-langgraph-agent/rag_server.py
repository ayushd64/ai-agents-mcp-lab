# rag_server.py — an MCP server that exposes your knowledge base as a search tool

from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma
from mcp.server.fastmcp import FastMCP

CHROMA_DIR = "chroma_db"
EMBED_MODEL = "nomic-embed-text"

mcp = FastMCP("Knowledge Base")

# Load the persisted vector store once when the server starts (no re-embedding)
embeddings = OllamaEmbeddings(model=EMBED_MODEL)
vectorstore = Chroma(persist_directory=CHROMA_DIR, embedding_function=embeddings)

@mcp.tool()
def search_docs(query: str) -> str:
    """Search the company knowledge base for information relevant to the query.
    Use this whenever the user asks about company policies, products, or internal facts."""
    results = vectorstore.similarity_search(query, k=3)   # top 3 closest chunks
    if not results:
        return "No relevant information found in the knowledge base."
    return "\n\n---\n\n".join(
        f"[from {d.metadata.get('source', '?')}]\n{d.page_content}" for d in results
    )

if __name__ == "__main__":
    mcp.run()

