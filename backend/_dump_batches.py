import sqlite3
from pathlib import Path
p = Path(r'f:\UE_Projects\PHP\Plugins\AssetMetaExplorerBridge\open\data\app.db')
conn = sqlite3.connect(p)
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT id, batch_id, flow, task_id, status, output_file_id, processed_at, processing_owner, processing_heartbeat_at, error_text, updated_at FROM openai_batches WHERE flow='translate_name_tags' ORDER BY id").fetchall()
print('count', len(rows))
for r in rows:
    print(dict(r))
print('applied', conn.execute("SELECT batch_id, flow, task_id, rows_done, rows_error, applied_at FROM openai_batch_results_applied ORDER BY applied_at DESC LIMIT 20").fetchall())
conn.close()
