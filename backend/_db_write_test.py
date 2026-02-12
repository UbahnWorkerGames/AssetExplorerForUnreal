import sqlite3
from pathlib import Path
p = Path(r'f:\UE_Projects\PHP\Plugins\AssetMetaExplorerBridge\open\data\app.db')
conn=sqlite3.connect(p)
conn.execute('PRAGMA busy_timeout=30000')
conn.execute("UPDATE settings SET value = value WHERE key='provider'")
conn.commit()
conn.close()
print('ok')
