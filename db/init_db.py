import sqlite3
con = sqlite3.connect("rra.db")
con.executescript(open("db/schema.sql").read())
print(con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall())