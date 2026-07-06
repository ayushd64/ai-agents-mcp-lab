# explore.py — a 10-line proof that DuckDB can query our CSV

import duckdb

# An in-memory database (nothing written to disk; lives only while this runs)
con = duckdb.connect(database=":memory:")

# Load the CSV into a table called "data". read_csv_auto figures out columns + types for us.
con.execute("CREATE TABLE data AS SELECT * FROM read_csv_auto('sample_data.csv')")

# 1. What do the columns look like?
print("Schema:")
print(con.execute("DESCRIBE data").fetchdf())

# 2. A real analytical query: total revenue per region
print("\nRevenue by region:")
print(con.execute(
    "SELECT region, SUM(revenue) AS total FROM data GROUP BY region ORDER BY total DESC"
).fetchdf())
