import httpx, main
from db import get_db

BATCH_ID='batch_698c72f9b300819089ece23a5c8439a8'
FLOW='translate_name_tags'
conn=get_db(); settings=main.get_settings(conn); conn.close()
provider=(settings.get('provider') or 'openai').strip().lower()
api_key=main._provider_api_key(settings, provider)
api_base=main._provider_base_url(settings, provider).rstrip('/')
headers={'Authorization': f'Bearer {api_key}'} if api_key else {}

c=httpx.Client(timeout=httpx.Timeout(60.0, connect=60.0, read=60.0))
p=c.get(f"{api_base}/batches/{BATCH_ID}", headers=headers); p.raise_for_status(); out_id=p.json().get('output_file_id')
r=c.get(f"{api_base}/files/{out_id}/content", headers=headers); r.raise_for_status(); txt=r.text
c.close()
lines=[ln for ln in txt.splitlines() if ln.strip()]
print('total lines', len(lines))
for n in [50,100,200,400,800,1200]:
    t='\n'.join(lines[:n])
    try:
        s=main._apply_batch_output_for_flow(FLOW, t, settings, None)
        print('N', n, 'OK', s)
    except Exception as e:
        print('N', n, 'ERR', e)
        break
