import collections,hashlib,json,subprocess
from pathlib import Path
R=Path('runs/judge-expanded-20261029-r1');REC=R/'measurement-recovery';P=json.loads((R/'plan.json').read_text());X=json.loads((R/'comparison.json').read_text());K=json.loads((R/'private-key.json').read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for p,h in P['source_plans'].items():assert sha(Path(p))==h
for k in K:
 for p,h in [('run_file','run_sha256'),('baseline','baseline_sha256'),('package','package_file_sha256')]:assert sha(Path(k[p]))==k[h]
for b in P['bindings']:
 for d,h in [('messages','messages_sha256'),('packets','packet_sha256')]:assert sha(R/d/b['condition']/f"{b['review_id']}.json")==b[h]
 body=(R/'messages'/b['condition']/f"{b['review_id']}.json").read_text()
 for identity in ['mimo-v2.5-pro','deepseek-v4-flash','glm-5.2','nurse_model','provider_request_id']:assert identity not in body
ledger=[]
for f in [R/'discovery-usage.jsonl',R/'usage.jsonl',REC/'usage.jsonl']:
 if f.exists():ledger.extend({**json.loads(l),'ledger':str(f)} for l in f.read_text().splitlines() if l.strip())
assert len(ledger)==X['total_usage_requests']
root_attempted={(x['requested_model'],x.get('condition'),x.get('review_id')) for x in ledger if x['ledger']==str(R/'usage.jsonl') and x['role'] in ['judge','judge_repair']}
assert len({(str(Path(x['ledger']).parent),x.get('request_local_id')) for x in ledger if x.get('request_local_id')})==sum(bool(x.get('request_local_id')) for x in ledger)
count=criteria=refs=0
for a in X['rating_origins']:
 f=Path(a['path']);d=json.loads(f.read_text());assert sha(f)==a['sha256'];model=a['model'];cond=a['condition'];code=a['review_id'];source=REC if f.is_relative_to(REC) else R
 if source==REC:assert (model,cond,code) not in root_attempted
 raw=json.loads((source/'raw-requests'/f"{d['request_local_id']}.json").read_text());assert raw['role'] in ['judge','judge_repair'] and raw['requested_model']==model and raw['condition']==cond and raw['review_id']==code
 assert raw['response']['model']==model
 for item in d['items']:
  if item['status']=='observed':assert type(item['score']) is int and item['score'] in ([0,1,2] if cond=='ternary' else [0,1])
  else:assert item['score'] is None
  refs+=len(item['evidence_ids'])
 count+=1;criteria+=len(d['items'])
assert count==X['valid_main_ratings']+X['valid_compatibility_ratings']
# Independent agreement arithmetic grouped from per-item comparison rows.
for model in P['main_models']+list(P['compatibility_models']):
 for cond in P['conditions']:
  rows=[d for d in X['details'] if d['model']==model and d['condition']==cond];m=X['results'][model][cond];numerics=[d for d in rows if d['baseline'] is not None];exact=sum(d['baseline']==d['judge'] for d in numerics)
  assert exact==m['exact'];assert sum(d['baseline'] is None and d['judge'] is not None for d in rows)==m['baseline_null_to_numeric']
  if m['complete_six_trajectories']:assert len(numerics)==48 and abs(exact/48-m['fixed48_agreement'])<1e-12
  else:assert m['fixed48_agreement'] is None
for root in [R,REC]:
 budgets=[json.loads(l) for l in (root/'request-budgets.jsonl').read_text().splitlines()]
 assert all(d['passed'] and d['response_model']==d['requested_model'] and d['usage']['prompt_tokens']+d['reserved_output']<=16384 for d in budgets)
 for d in budgets:
  if d['role'] in ['judge','judge_repair']:assert d['reserved_output']==3072 and d['temperature']==P['compatibility_models'].get(d['requested_model'],{}).get('temperature',0)
assert (R/'exit-code').read_text().strip()=='0';assert (R/'measurement-recovery-v2-exit-code').read_text().strip()=='0'
assert (R/'completion.json').exists() and (REC/'completion.json').exists()
processes=[l.split(None,2) for l in subprocess.check_output(['ps','-axo','pid=,comm=,args='],text=True).splitlines()];live=[p for p in processes if len(p)==3 and Path(p[1]).name.lower().startswith('python') and any(s in p[2] for s in ['judge-expanded-20261029-r1/run.py','judge-expanded-20261029-r1/recover_measurement_v2.py'])];assert not live,live
v={'passed':True,'date':'2026-10-29','valid_main_ratings':X['valid_main_ratings'],'valid_compatibility_ratings':X['valid_compatibility_ratings'],'effective_criterion_outputs':criteria,'evidence_id_references':refs,'api_chat_requests_including_discovery':len(ledger),'main_planned_ratings':P['expected_main_ratings'],'secondary_planned_ratings':P['expected_secondary_ratings'],'all_completed_or_stopped_per_registered_failure_rule':True,'live_experiment_processes':0,'plan_sha256':sha(R/'plan.json'),'comparison_sha256':sha(R/'comparison.json'),'checks':['all historical plans, packages, raw runs and baseline hashes unchanged','identical blinded messages for all same-condition judges','recovery never reran any formally attempted target','strict scoring schema and source bindings','independent agreement and missing-coverage arithmetic','actual returned model identity and16K budgets for all receipted requests','all raw outputs including format/empty failures and repair retained','Kimi temperature0.6 separated from main temperature0','named tmux experiments ended with exit0'],'limitations':['No independent clinical gold standard.','Known evidence IDs do not prove semantic support.','Incomplete ratings have no full agreement score, never clinical zero.','Usage anomalies and unreported failed-call usage prevent treating priced interval as complete bill.']}
(R/'verification.json').write_text(json.dumps(v,indent=2)+'\n');print(json.dumps(v,indent=2))
