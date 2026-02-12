import httpx, traceback
import main
from db import get_db

BATCH_ID='batch_698c72f9b300819089ece23a5c8439a8'
FLOW='translate_name_tags'

conn=get_db(); settings=main.get_settings(conn); conn.close()
provider=(settings.get('provider') or 'openai').strip().lower()
api_key=main._provider_api_key(settings, provider)
api_base=main._provider_base_url(settings, provider).rstrip('/')
headers={'Authorization': f'Bearer {api_key}'} if api_key else {}

c=httpx.Client(timeout=httpx.Timeout(60.0, connect=60.0, read=60.0))
try:
    p=c.get(f"{api_base}/batches/{BATCH_ID}", headers=headers); p.raise_for_status(); j=p.json()
    print('status', j.get('status'), 'file', j.get('output_file_id'))
    out_id=j.get('output_file_id')
    r=c.get(f"{api_base}/files/{out_id}/content", headers=headers); r.raise_for_status()
    txt=r.text
    print('content_len', len(txt))
finally:
    c.close()

try:
    stats=main._apply_batch_output_for_flow(FLOW, txt, settings, None)
    print('apply ok', stats)
except Exception as e:
    print('apply EXC', e)
    traceback.print_exc()

try:
    main._openai_batch_mark_applied(batch_id=BATCH_ID, flow=FLOW, task_id=123, rows_done=0, rows_error=0)
    print('mark_applied ok')
except Exception as e:
    print('mark_applied EXC', e)
    traceback.print_exc()

try:
    main._openai_batch_mark_processed(BATCH_ID)
    print('mark_processed ok')
except Exception as e:
    print('mark_processed EXC', e)
    traceback.print_exc()
