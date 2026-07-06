# preview_chart.py — generate a chart spec and write an HTML file you can open in a browser

import chart_server as cs

spec = cs.make_chart(
    sql="SELECT region, SUM(revenue) AS total FROM data GROUP BY region ORDER BY total DESC",
    chart_type="bar", x="region", y="total", title="Revenue by region",
)

html = f"""<!DOCTYPE html><html><head>
<script src="https://cdn.jsdelivr.net/npm/vega@5"></script>
<script src="https://cdn.jsdelivr.net/npm/vega-lite@5"></script>
<script src="https://cdn.jsdelivr.net/npm/vega-embed@6"></script>
</head><body style="font-family:sans-serif;padding:24px">
<h3>Chart preview</h3><div id="chart"></div>
<script>vegaEmbed('#chart', {spec});</script>
</body></html>"""

with open("chart_preview.html", "w", encoding="utf-8") as f:
    f.write(html)
print("Wrote chart_preview.html — open it in your browser to see the chart.")

