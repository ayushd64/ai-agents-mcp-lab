# chart_server.py — an MCP server that turns a SQL query into a Vega-Lite chart spec

import os, re, datetime
from decimal import Decimal

import duckdb
import altair as alt
from mcp.server.fastmcp import FastMCP

DATA_FILE = os.environ.get("DATA_FILE", "sample_data.csv")

mcp = FastMCP("Chart Maker")

con = duckdb.connect(database=":memory:")
con.execute(f"CREATE TABLE data AS SELECT * FROM read_csv_auto('{DATA_FILE}')")

MARK = {"bar": "mark_bar", "line": "mark_line", "scatter": "mark_point",
        "point": "mark_point", "area": "mark_area"}

def _safe(v):
    """Make a value JSON-serializable (Vega spec is JSON)."""
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (datetime.date, datetime.datetime)):
        return v.isoformat()
    return v

def _vega_type(value):
    """Tell Vega whether a field is a number, a date, or a category."""
    if isinstance(value, (int, float)):
        return "quantitative"
    if re.match(r"^\d{4}-\d{2}-\d{2}", str(value)):
        return "temporal"
    return "nominal"


@mcp.tool()
def make_chart(sql: str, chart_type: str, x: str, y: str, title: str = "") -> str:
    """Run a read-only SELECT and return a Vega-Lite chart spec (JSON) visualizing it.
    chart_type: one of bar, line, scatter, area. x and y MUST be output column names
    from the SELECT (use the exact aliases you put in the query)."""
    clean = sql.strip().rstrip(";").strip()

    # --- same read-only guardrail as the SQL server ---
    if not (clean.lower().startswith("select") or clean.lower().startswith("with")):
        return "Error: only read-only SELECT queries are allowed."
    if ";" in clean:
        return "Error: only one statement is allowed."
    if chart_type not in MARK:
        return f"Error: chart_type must be one of {list(MARK)}."

    try:
        cur = con.execute(clean)
        columns = [d[0] for d in cur.description]
        if x not in columns or y not in columns:
            return f"Error: x and y must be output columns. Available: {columns}"

        records = [dict(zip(columns, [_safe(v) for v in row])) for row in cur.fetchall()]
        if not records:
            return "Query returned no rows to chart."

        base = getattr(alt.Chart(alt.Data(values=records), title=title), MARK[chart_type])()
        chart = base.encode(
            x=alt.X(field=x, type=_vega_type(records[0][x])),
            y=alt.Y(field=y, type=_vega_type(records[0][y])),
        )
        return chart.to_json()          # Vega-Lite JSON, data embedded
    except Exception as e:
        return f"Chart error: {e}"


if __name__ == "__main__":
    mcp.run()

