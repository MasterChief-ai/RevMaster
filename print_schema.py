import sqlite3

conn = sqlite3.connect("rra.db")
for (name,) in conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
):
    cols = [f"{c[1]} {c[2]}" for c in conn.execute(f"PRAGMA table_info({name})")]
    n = conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
    print(f"{name} ({n} rows): " + ", ".join(cols))
conn.close()