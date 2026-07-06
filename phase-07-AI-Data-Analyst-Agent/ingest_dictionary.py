# ingest_dictionary.py — build a searchable index of the data dictionary (run once)

from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

DICT_FILE, CHROMA_DIR, EMBED_MODEL = "data_dictionary.md", "dict_db", "nomic-embed-text"

def main():
    with open(DICT_FILE, "r", encoding="utf-8") as f:
        doc = Document(page_content=f.read(), metadata={"source": DICT_FILE})

    # Small chunks so each definition retrieves precisely
    chunks = RecursiveCharacterTextSplitter(chunk_size=300, chunk_overlap=50).split_documents([doc])
    print(f"Split dictionary into {len(chunks)} chunks.")

    embeddings = OllamaEmbeddings(model=EMBED_MODEL)
    Chroma.from_documents(documents=chunks, embedding=embeddings, persist_directory=CHROMA_DIR)
    print(f"Dictionary indexed to ./{CHROMA_DIR}")

if __name__ == "__main__":
    main()

