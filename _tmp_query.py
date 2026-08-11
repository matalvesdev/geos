import sqlite3

db_path = r'C:\Users\Mateus Alves Bassane\Documents\Zetra 2\.geos\geos.db'
db = sqlite3.connect(db_path)
db.row_factory = sqlite3.Row

# Check all opportunities
rows = db.execute("SELECT id, problem, status FROM opportunities").fetchall()
print(f"Total opportunities: {len(rows)}")
for r in rows[:5]:
    print(f"  {r['id'][:16]}... | {r['status']} | {r['problem'][:70]}")

# Try different search patterns
print("\nSearch patterns:")
patterns = [
    "%origem%",
    "%crédito%",
    "%credito%",
    "%bancário%",
    "%bancario%",
]
for p in patterns:
    count = db.execute("SELECT COUNT(*) FROM opportunities WHERE problem LIKE ?", (p,)).fetchone()[0]
    print(f"  '{p}': {count} matches")

db.close()
