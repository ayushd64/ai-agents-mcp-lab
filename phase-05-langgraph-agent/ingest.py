# ingest.py — one-time: turn ./knowledge files into a searchable vector store

import os, glob
from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

KNOWLEDGE_DIR = "knowledge"
CHROMA_DIR = "chroma_db"
EMBED_MODEL = "nomic-embed-text"

def main():
    # 1. Load every file in ./knowledge as a Document
    docs = []
    for path in glob.glob(os.path.join(KNOWLEDGE_DIR, "*")):
        with open(path, "r", encoding="utf-8") as f:
            docs.append(Document(page_content=f.read(),
                                 metadata={"source": os.path.basename(path)}))
    print(f"Loaded {len(docs)} file(s).")

    # 2. Split into overlapping chunks (small enough to retrieve precisely)
    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=100)
    chunks = splitter.split_documents(docs)
    print(f"Split into {len(chunks)} chunks.")

    # 3. Embed each chunk and persist to disk (slow first time; instant to load later)
    embeddings = OllamaEmbeddings(model=EMBED_MODEL)
    print("Embedding + storing... (first run takes a moment)")
    Chroma.from_documents(documents=chunks, embedding=embeddings, persist_directory=CHROMA_DIR)
    print(f"Done. Vector store saved to ./{CHROMA_DIR}")

if __name__ == "__main__":
    main()

