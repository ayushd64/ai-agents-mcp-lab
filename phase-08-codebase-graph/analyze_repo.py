# analyze_repo.py — turn a Python repo into an interactive graph (files + functions/classes)

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




def render(G: nx.DiGraph, out: str = "graph.html"):
    # importance = how connected a node is. Files that many others import get big.
    centrality = nx.degree_centrality(G)
    cmax = max(centrality.values()) if centrality else 1

    net = Network(height="820px", width="100%", directed=True,
                  bgcolor="#0e1117", font_color="#e6e6e6")
    net.barnes_hut()
    color = {"file": "#4c8bf5", "function": "#f5a623", "class": "#e0508a"}

    for n, d in G.nodes(data=True):
        k = d.get("kind", "file")
        # base size per kind, scaled up by how central the node is
        base = {"file": 16, "class": 12, "function": 8}[k]
        boost = 40 * (centrality.get(n, 0) / cmax)     # 0..40 extra by importance
        net.add_node(n, label=d.get("label", n), color=color[k],
                     size=base + boost, group=k,
                     title=f"{k}: {n}\connections: {G.degree(n)}")
    for u, v, d in G.edges(data=True):
        is_import = d.get("kind") == "imports"
        net.add_edge(u, v, color="#3ad1c8" if is_import else "#444",
                     title=d.get("kind", ""))
    net.write_html(out, notebook=False)
    print(f"Wrote {out} — open it in your browser.")
    # built-in interactive controls (physics sliders, node/edge options)
    net.show_buttons(filter_=['physics'])

    net.write_html(out, notebook=False)

    # inject a small color legend into the generated HTML
    legend = """
    <div style="position:fixed;top:12px;left:12px;z-index:999;background:#161b22;
                color:#e6e6e6;padding:10px 14px;border:1px solid #30363d;border-radius:8px;
                font-family:sans-serif;font-size:13px">
      <b>Legend</b><br>
      <span style="color:#4c8bf5">●</span> File &nbsp;
      <span style="color:#e0508a">●</span> Class &nbsp;
      <span style="color:#f5a623">●</span> Function<br>
      <span style="color:#3ad1c8">—</span> imports &nbsp;
      <span style="color:#888">—</span> contains<br>
      <small>Bigger node = more connected</small>
    </div>"""
    with open(out, encoding="utf-8") as f:
        html = f.read()
    html = html.replace("<body>", "<body>" + legend)
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Wrote {out} — open it in your browser.")


if __name__ == "__main__":
    source = sys.argv[1] if len(sys.argv) > 1 else "."
    root = get_repo(source)
    G = build_graph(root)
    print(f"Graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
    render(G)

