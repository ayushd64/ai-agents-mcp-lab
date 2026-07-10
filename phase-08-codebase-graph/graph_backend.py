# graph_backend.py — RepoGraph: interactive code graph + agentic Q&A

import os, json, hashlib
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_text_splitters import RecursiveCharacterTextSplitter, Language
from langchain_core.documents import Document

from analyze_repo import (get_repo, build_graph, files_only, render, graph_stats,
                          py_files, doc_files, rel_id, connections_text)

load_dotenv(override=True)
app = FastAPI()

GRAPH_CACHE = {}     # url -> NetworkX graph
ROOT_CACHE  = {}     # url -> local repo path
INDEX_CACHE = {}     # url -> FAISS index (in memory)
BIG_GRAPH   = 1500
INDEX_DIR   = "faiss_cache"

llm = ChatOpenAI(model=os.environ["MODEL"], base_url=os.environ["OPENAI_BASE_URL"],
                 api_key=os.environ["OPENAI_API_KEY"], temperature=0)
embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")


def sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"

def _read(fp: str):
    try:
        return open(fp, encoding="utf-8", errors="ignore").read()
    except OSError:
        return None


# ---------------- page ----------------
@app.get("/")
def home():
    return FileResponse("graph_index.html")


# ---------------- analyze (streamed) ----------------
@app.get("/analyze")
def analyze(url: str):
    def stream():
        try:
            if url not in GRAPH_CACHE:
                yield sse("progress", "Cloning repository…  (first load can take ~10–30s)")
                root = get_repo(url)
                ROOT_CACHE[url] = root
                n = sum(1 for _ in py_files(root))
                yield sse("progress", f"Parsing {n} files and building the graph…")
                GRAPH_CACHE[url] = build_graph(root)
            else:
                yield sse("progress", "Loading from cache…")
            G = GRAPH_CACHE[url]
            yield sse("stats", graph_stats(G))
            yield sse("done", {"big": G.number_of_nodes() > BIG_GRAPH})
        except Exception as e:
            yield sse("failed", f"{type(e).__name__}: {e}")
    return StreamingResponse(stream(), media_type="text/event-stream")


# ---------------- graph view ----------------
NODE_CLICK_JS = """
<script>
window.addEventListener('load', function(){
  var t=0, iv=setInterval(function(){
    if(window.network){ clearInterval(iv);
      window.network.on('click', function(p){
        if(p.nodes.length){ parent.postMessage({type:'nodeClick', node:p.nodes[0]}, '*'); }
      });
    } else if(++t>60){ clearInterval(iv); }
  }, 100);
});
</script>"""

@app.get("/graph", response_class=HTMLResponse)
def graph(url: str, view: str = "detailed"):
    try:
        if url not in GRAPH_CACHE:
            root = get_repo(url); ROOT_CACHE[url] = root
            GRAPH_CACHE[url] = build_graph(root)
        G = GRAPH_CACHE[url]

        note = ""
        if view == "architecture":
            G = files_only(G)
        elif G.number_of_nodes() > BIG_GRAPH:
            G = files_only(G)
            note = ("<div style='position:fixed;bottom:12px;left:12px;z-index:999;background:#3a2f16;"
                    "color:#f5d590;padding:8px 12px;border:1px solid #7a6320;border-radius:8px;"
                    "font-family:sans-serif;font-size:12px'>Large repo — showing the Architecture "
                    "view for performance.</div>")

        html = render(G)
        if note:
            html = html.replace("<body>", "<body>" + note)
        return html.replace("</body>", NODE_CLICK_JS + "</body>")
    except Exception as e:
        return HTMLResponse(
            f"<body style='background:#0e1117;color:#e6e6e6;font-family:sans-serif;padding:40px'>"
            f"<h3>Couldn't analyze that repo</h3><p>{type(e).__name__}: {e}</p></body>")


# ---------------- RAG index (code + docs, persisted) ----------------
def _index_path(url: str) -> str:
    return os.path.join(INDEX_DIR, hashlib.sha1(url.encode()).hexdigest()[:12])

def build_index(url: str) -> FAISS:
    path = _index_path(url)
    if os.path.exists(path):
        return FAISS.load_local(path, embeddings, allow_dangerous_deserialization=True)

    root = ROOT_CACHE.get(url) or get_repo(url); ROOT_CACHE[url] = root
    py_split  = RecursiveCharacterTextSplitter.from_language(Language.PYTHON, chunk_size=1000, chunk_overlap=150)
    doc_split = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)

    docs = []
    for fp in py_files(root):
        text = _read(fp)
        if text:
            fid = rel_id(root, fp)
            docs += [Document(page_content=c, metadata={"source": fid}) for c in py_split.split_text(text)]
    for fp in doc_files(root):
        text = _read(fp)
        if text:
            fid = rel_id(root, fp)
            docs += [Document(page_content=c, metadata={"source": fid}) for c in doc_split.split_text(text)]
    if not docs:
        docs = [Document(page_content="(empty repository)", metadata={"source": "none"})]

    idx = FAISS.from_documents(docs, embeddings)
    os.makedirs(INDEX_DIR, exist_ok=True)
    idx.save_local(path)
    return idx


def _stream_llm(system: str, user: str):
    for chunk in llm.stream([{"role": "system", "content": system},
                             {"role": "user", "content": user}]):
        if chunk.content:
            yield sse("token", chunk.content)
    yield sse("done", "")


# ---------------- ask (RAG over the repo) ----------------
@app.get("/ask")
def ask(url: str, q: str):
    def stream():
        try:
            if url not in GRAPH_CACHE:
                yield sse("token", "Please analyze a repo first."); yield sse("done", ""); return
            if url not in INDEX_CACHE:
                yield sse("status", "Indexing the code for search… (first question only)")
                INDEX_CACHE[url] = build_index(url)

            G = GRAPH_CACHE[url]
            yield sse("status", "Searching the codebase…")
            hits = INDEX_CACHE[url].similarity_search(q, k=5)

            files, snippets = [], []
            for d in hits:
                src = d.metadata.get("source", "?")
                if src not in files:
                    files.append(src)
                snippets.append(f"--- {src} ---\n{d.page_content}")
            yield sse("sources", files)

            structure = "\n".join(connections_text(G, f) for f in files if f in G)
            system = ("You are a senior engineer explaining a codebase. Answer ONLY from the provided "
                      "code snippets and structural context. Cite the file paths you used in backticks "
                      "like `path/to/file.py`. If the snippets don't contain the answer, say so plainly.")
            user = (f"Question: {q}\n\nRelevant code:\n" + "\n".join(snippets) +
                    f"\n\nStructural connections (from the import graph):\n{structure}")
            yield from _stream_llm(system, user)
        except Exception as e:
            yield sse("token", f"\n\n[error] {type(e).__name__}: {e}"); yield sse("done", "")
    return StreamingResponse(stream(), media_type="text/event-stream")


# ---------------- explain a clicked node ----------------
EXPLAIN_SYS = ("You are a senior engineer. Explain the given code file (or symbol) clearly and concisely: "
               "its purpose, key responsibilities, and how it fits the wider codebase using the structural "
               "context. Cite the file path in backticks.")

@app.get("/explain")
def explain(url: str, node: str):
    def stream():
        try:
            if url not in GRAPH_CACHE:
                yield sse("token", "Analyze a repo first."); yield sse("done", ""); return
            G = GRAPH_CACHE[url]
            file_id, symbol = (node.split("::", 1) + [None])[:2]

            root = ROOT_CACHE.get(url) or get_repo(url); ROOT_CACHE[url] = root
            content = _read(os.path.join(root, file_id.replace("/", os.sep))) or "(could not read file)"
            structure = connections_text(G, file_id) if file_id in G else ""

            yield sse("sources", [file_id])
            focus = f"the symbol `{symbol}` in " if symbol else "the file "
            user = f"Explain {focus}`{file_id}`.\n\nCode:\n{content[:5000]}\n\nStructural context:\n{structure}"
            yield from _stream_llm(EXPLAIN_SYS, user)
        except Exception as e:
            yield sse("token", f"[error] {type(e).__name__}: {e}"); yield sse("done", "")
    return StreamingResponse(stream(), media_type="text/event-stream")

