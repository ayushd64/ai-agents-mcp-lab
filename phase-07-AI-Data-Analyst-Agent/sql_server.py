# sql_server.py — an MCP server giving the agent safe, read-only access to the data

import os
import duckdb
from mcp.server.fastmcp import FastMCP

DATA_FILE = os.environ.get("DATA_FILE", "sample_data.csv")

mcp = FastMCP("SQL Data Analyst")

# One in-process DuckDB connection, with the CSV loaded as a table "data" at startup.
con = duckdb.connect(database=":memory:")
con.execute(f"CREATE TABLE data AS SELECT * FROM read_csv_auto('{DATA_FILE}')")


@mcp.tool()
def list_tables() -> str:
    """List the tables available to query."""
    rows = con.execute("SHOW TABLES").fetchall()
    return "\n".join(r[0] for r in rows) or "No tables found."


@mcp.tool()
def get_schema(table: str = "data") -> str:
    """Get the column names and types for a table. Call this before writing a query."""
    rows = con.execute(f"DESCRIBE {table}").fetchall()
    return "\n".join(f"{name} ({dtype})" for name, dtype, *_ in rows)


@mcp.tool()
def run_query(sql: str) -> str:
    """Run a READ-ONLY SQL query (SELECT only) and return the result as a table."""
    clean = sql.strip().rstrip(";").strip()
    lowered = clean.lower()

    # --- guardrail: only allow read-only SELECT / WITH queries ---
    if not (lowered.startswith("select") or lowered.startswith("with")):
        return "Error: only read-only SELECT queries are allowed."
    if ";" in clean:
        return "Error: only one statement is allowed."

    try:
        cur = con.execute(clean)                       # run the query
        columns = [d[0] for d in cur.description]      # column names
        rows = cur.fetchall()                          # plain Python rows — no pandas
        if not rows:
            return "Query ran, but returned no rows."

        # Build a simple text table
        header = " | ".join(columns)
        body = "\n".join(" | ".join(str(v) for v in row) for row in rows[:50])
        extra = f"\n... ({len(rows)} rows total)" if len(rows) > 50 else ""
        return f"{header}\n{body}{extra}"
    except Exception as e:
        return f"Query error: {e}"




if __name__ == "__main__":
    mcp.run()

