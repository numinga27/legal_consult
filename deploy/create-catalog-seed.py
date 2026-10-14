"""Build a fresh SQLite file containing legal catalogue data only.

Usage: python create-catalog-seed.py source.sqlite3 new-catalog.sqlite3
Authentication, payments, sessions, generated documents, and AI credentials
are never selected from the source. Empty historical schemas are retained so
Django can apply its remaining migrations normally.
"""
import json
import sqlite3
import sys
from pathlib import Path

source_path, target_path = map(lambda p: Path(p).resolve(), sys.argv[1:])
if target_path.exists():
    raise SystemExit('Refusing to replace an existing recovery file.')
target_path.parent.mkdir(parents=True, exist_ok=True)
allowed = {
    'django_migrations', 'core_legaldirection', 'core_questionnaire',
    'core_question', 'core_answer', 'core_conclusion',
    'core_answerconclusion', 'core_documenttemplate',
}
source = sqlite3.connect(source_path.as_uri() + '?mode=ro', uri=True)
assert source.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
with sqlite3.connect(target_path) as target:
    schemas = source.execute("SELECT name,sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()
    for name, sql in schemas:
        target.execute(sql)
    counts = {}
    for name, _ in schemas:
        if name not in allowed:
            continue
        cursor = source.execute('SELECT * FROM "' + name + '"')
        columns = ','.join('"' + col[0] + '"' for col in cursor.description)
        rows = cursor.fetchall()
        placeholders = ','.join('?' for _ in cursor.description)
        target.executemany('INSERT INTO "' + name + '" (' + columns + ') VALUES (' + placeholders + ')', rows)
        counts[name] = len(rows)
    for (sql,) in source.execute("SELECT sql FROM sqlite_master WHERE type='index' AND sql IS NOT NULL"):
        target.execute(sql)
    assert target.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    assert not target.execute('PRAGMA foreign_key_check').fetchall()
    for name, _ in schemas:
        if name not in allowed:
            assert target.execute('SELECT count(*) FROM "' + name + '"').fetchone()[0] == 0, name
    target.commit()
source.close()
print(json.dumps({'copied_tables': counts, 'all_other_tables': 'EMPTY', 'integrity': 'ok'}))
