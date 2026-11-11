r"""Database admin CLI.  Usage (PowerShell):
    python scripts\db_admin.py init                 # create/upgrade tables + seed (idempotent, additive)
    python scripts\db_admin.py backup               # consistent backup into backups\
    python scripts\db_admin.py restore <file.db>    # current DB is copied aside first, then replaced
Environment: CARBONAI_DB_PATH (default data\carbonai.db)
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db.connection import backup_file, connect, db_path, restore_file
from db.schema import init_db
from db.seed import seed_all

cmd = sys.argv[1] if len(sys.argv) > 1 else "init"
if cmd == "init":
    con = connect(); init_db(con); print("seeded (new rows only):", seed_all(con)); print("db:", db_path())
elif cmd == "backup":
    print("backup written:", backup_file(label="manual"))
elif cmd == "restore" and len(sys.argv) > 2:
    print("restored:", restore_file(sys.argv[2]), "(previous DB saved in backups\\ as *_pre_restore_*)")
else:
    print(__doc__)
