# analyze_repo.py — turn a Python repo into an interactive graph (files + functions/classes)
LEGEND_HTML = """
<div style="position:fixed;top:16px;left:16px;z-index:999;background:rgba(255,255,255,0.85);
            backdrop-filter:blur(10px);color:#1a2233;padding:12px 16px;border:1px solid #e2e8f0;
            border-radius:14px;box-shadow:0 8px 24px rgba(79,70,229,0.10);font-family:'Inter',sans-serif;font-size:13px">
  <b style="color:#4f46e5">Legend</b><br>
  <span style="color:#4f46e5">●</span> File &nbsp;
  <span style="color:#ec4899">●</span> Class &nbsp;
  <span style="color:#f59e0b">●</span> Function<br>
  <span style="color:#6366f1">—</span> imports &nbsp;
  <span style="color:#cbd5e1">—</span> contains<br>
  <small style="color:#64748b">Bigger node = more connected</small>
</div>"""



import ast, os, sys, subprocess, tempfile
import networkx as nx
from pyvis.network import Network

SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules", ".mypy_cache"}


def get_repo(source: str) -> str:
    """Return a local path. If `source` is a GitHub URL, shallow-clone it to a temp dir."""
    if source.startswith("http") or source.endswith(".git"):
        dest = tempfile.mkdtemp(prefix="repo_")
        print(f"Cloning {source} ...")
        subprocess.run(["git", "clone", "--depth", "1", source, dest], check=True)
        return dest
    return source  # already a local folder


def py_files(root: str):
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]      # prune noise folders
        for fn in files:
            if fn.endswith(".py"):
                yield os.path.join(dirpath, fn)


DOC_EXTS = {".md", ".rst", ".txt"}

def doc_files(root: str):
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fn in files:
            if os.path.splitext(fn)[1].lower() in DOC_EXTS:
                yield os.path.join(dirpath, fn)




def rel_id(root: str, path: str) -> str:
    """A clean, forward-slash relative path used as a node id."""
    return os.path.relpath(path, root).replace(os.sep, "/")


def module_name(root: str, path: str) -> str:
    """Turn a file path into a dotted module name, e.g. pkg/utils.py -> pkg.utils."""
    rel = rel_id(root, path)[:-3]              # strip '.py'
    parts = rel.split("/")
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def build_graph(root: str) -> nx.DiGraph:
    files = list(py_files(root))
    mod_to_file = {module_name(root, fp): rel_id(root, fp) for fp in files}

    G = nx.DiGraph()
    for fp in files:
        fid = rel_id(root, fp)
        this_mod = module_name(root, fp)                # e.g. "pkg.sub.thing"
        pkg_parts = this_mod.split(".")[:-1]            # the file's package: ["pkg","sub"]

        G.add_node(fid, kind="file", label=os.path.basename(fid))
        try:
            with open(fp, encoding="utf-8", errors="ignore") as f:
                tree = ast.parse(f.read(), filename=fp)
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                nid = f"{fid}::{node.name}()"
                G.add_node(nid, kind="function", label=node.name + "()")
                G.add_edge(fid, nid, kind="contains")
            elif isinstance(node, ast.ClassDef):
                nid = f"{fid}::{node.name}"
                G.add_node(nid, kind="class", label=node.name)
                G.add_edge(fid, nid, kind="contains")
            elif isinstance(node, ast.ImportFrom):
                target = node.module                     # None for "from . import x"
                if node.level and node.level > 0:        # RELATIVE import
                    base = pkg_parts[:len(pkg_parts) - (node.level - 1)]  # climb up per dot
                    target = ".".join(base + ([node.module] if node.module else []))
                if target and target in mod_to_file and mod_to_file[target] != fid:
                    G.add_edge(fid, mod_to_file[target], kind="imports")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in mod_to_file and mod_to_file[alias.name] != fid:
                        G.add_edge(fid, mod_to_file[alias.name], kind="imports")
    return G


def render(G: nx.DiGraph, out: str = None) -> str:
    import tempfile
    centrality = nx.degree_centrality(G)
    cmax = max(centrality.values()) if centrality else 1

    net = Network(height="100vh", width="100%", directed=True,
                  bgcolor="#f7f8fc", font_color="#1a2233")      # light bg, dark text
    net.barnes_hut()
    color = {"file": "#4f46e5", "function": "#f59e0b", "class": "#ec4899"}  # indigo / amber / pink

    for n, d in G.nodes(data=True):
        k = d.get("kind", "file")
        base = {"file": 16, "class": 12, "function": 8}[k]
        boost = 40 * (centrality.get(n, 0) / cmax)
        net.add_node(n, label=d.get("label", n), color=color[k], size=base + boost,
                     group=k, title=f"{k}: {n}\nconnections: {G.degree(n)}")

    for u, v, d in G.edges(data=True):
        is_import = d.get("kind") == "imports"
        net.add_edge(u, v, color="#6366f1" if is_import else "#cbd5e1",   # indigo imports, soft grey contains
                     width=3 if is_import else 1, title=d.get("kind", ""))

    net.show_buttons(filter_=['physics'])
    tmp = out or os.path.join(tempfile.mkdtemp(), "g.html")
    net.write_html(tmp, notebook=False)
    with open(tmp, encoding="utf-8") as f:
        html = f.read()
    html = html.replace("<body>", "<body>" + LEGEND_HTML)
    if out:
        with open(out, "w", encoding="utf-8") as f:
            f.write(html)
    return html




def graph_stats(G: nx.DiGraph) -> dict:
    """Summary numbers + the most-connected files ('god nodes')."""
    files = [n for n, d in G.nodes(data=True) if d.get("kind") == "file"]
    cent = nx.degree_centrality(G)
    top = sorted(files, key=lambda n: cent.get(n, 0), reverse=True)[:5]
    return {
        "nodes": G.number_of_nodes(),
        "edges": G.number_of_edges(),
        "files": len(files),
        "top": [{"name": n, "connections": G.degree(n)} for n in top],
    }


def connections_text(G, file_id: str) -> str:
    """Plain-language structural context for a file, pulled from the graph."""
    imports = [v for _, v, d in G.out_edges(file_id, data=True) if d.get("kind") == "imports"]
    imported_by = [u for u, _, d in G.in_edges(file_id, data=True) if d.get("kind") == "imports"]
    parts = []
    if imports:     parts.append(f"{file_id} imports: {', '.join(imports)}")
    if imported_by: parts.append(f"{file_id} is imported by: {', '.join(imported_by)}")
    return " | ".join(parts) or f"{file_id}: no internal import links"



def files_only(G: nx.DiGraph) -> nx.DiGraph:
    """A clean architecture view: only files + their import relationships."""
    keep = [n for n, d in G.nodes(data=True) if d.get("kind") == "file"]
    H = G.subgraph(keep).copy()
    # drop any leftover non-import edges
    H.remove_edges_from([(u, v) for u, v, d in H.edges(data=True) if d.get("kind") != "imports"])
    return H



if __name__ == "__main__":
    source = sys.argv[1] if len(sys.argv) > 1 else "."
    root = get_repo(source)
    G = build_graph(root)
    print(f"Full graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
    render(G, "graph.html")                       # detailed view (files + functions)
    render(files_only(G), "architecture.html")    # clean view (files + imports only)


