import traceback
import main
print('start')
try:
    r = main._recover_openai_batches_once(limit=500, flow='translate_name_tags', task_id=123, stale_minutes=0)
    print('result', r)
except Exception as e:
    print('EXC', e)
    traceback.print_exc()
print('end')
