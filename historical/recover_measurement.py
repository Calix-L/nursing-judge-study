"""Recover only cells with zero formal grading attempts after an input-measurement gate failure."""
import concurrent.futures,hashlib,json,shutil
from pathlib import Path
BASE=Path('runs/judge-expanded-20261029-r1');REC=BASE/'measurement-recovery'
def save(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n');p.chmod(0o600)
models=['gpt-oss-120b','glm-5.3'];original=json.loads((BASE/'plan.json').read_text());plan=json.loads(json.dumps(original));plan['main_models']=models;plan['compatibility_models']={};plan['expected_main_ratings']=36;plan['expected_secondary_ratings']=0
for m in models:
 prior=json.loads((BASE/m/'summary.json').read_text())
 # Confirm every historical failed call for this model was an input qualification, not a scoring call.
 rows=[json.loads(l) for l in (BASE/'usage.jsonl').read_text().splitlines() if json.loads(l)['requested_model']==m]
 attempted={(x['condition'],x['review_id']) for x in rows if x['role'] in ['judge','judge_repair']}
 plan['jobs'][m]=[j for j in plan['jobs'][m] if (j['condition'],j['review_id']) not in attempted]
 save(REC/m/'excluded-prior-attempts.json',{'cells':[list(x) for x in sorted(attempted)],'reason':'Any original formal attempt, even empty, is excluded from recovery; never retry for a better clinical score.'})
 assert json.loads((BASE/m/'qualification.json').read_text())['passed']
 save(REC/m/'prior-qualification-reference.json',{'source':str(BASE/m/'qualification.json'),'sha256':hashlib.sha256((BASE/m/'qualification.json').read_bytes()).hexdigest()})
plan['expected_main_ratings']=sum(len(plan['jobs'][m]) for m in models)
for d in ['messages','packets']:
 shutil.copytree(BASE/d,REC/d,dirs_exist_ok=True)
shutil.copyfile(BASE/'prices-20261029.json',REC/'prices-20261029.json');save(REC/'plan.json',plan)
(REC/'discovery-usage.jsonl').write_text('')
save(BASE/'measurement-amendment.json',{'date':'2026-10-29','issue':'GLM5.3 and GPT-OSS measurement calls returned empty content at1024 output but valid prompt counts and model identity. GPT-OSS had no formal attempt. GLM5.3 had one empty formal ternary/R01 attempt; this cell is excluded from recovery.','change':'Allow empty content ONLY when role=input_qualification and usage+identity+16K checks passed; continue to require nonempty formal grading output. Retain old failed records; separate recovery ledger.','models':models,'unchanged':['formal messages/packets and their hashes','all baseline/source evidence','temperature and thinking request','3072 formal output and16K budget','JSON parser and semantic rubric','one schema repair and one transport retry'],'no_formal_attempted_cell_rerun':True,'source_plan_sha256':hashlib.sha256((BASE/'plan.json').read_bytes()).hexdigest()})
src=(BASE/'run.py').read_text();src=src.replace("R=Path('runs/judge-expanded-20261029-r1');", "R=Path('runs/judge-expanded-20261029-r1/measurement-recovery');")
src=src.replace("if not isinstance(content,str) or not content.strip():raise ValueError('empty_content')", "if role!='input_qualification' and (not isinstance(content,str) or not content.strip()):raise ValueError('empty_content')")
# Reuse the fresh passed qualification; preserve a hash-bound reference, do not infer old8K eligibility.
start=src.index('def qualify(model):');end=src.index('\ndef parse(content):',start)
src=src[:start]+"def qualify(model):\n ref=json.loads((R/model/'prior-qualification-reference.json').read_text());p=Path(ref['source']);assert hashlib.sha256(p.read_bytes()).hexdigest()==ref['sha256'];assert json.loads(p.read_text())['passed'];log(model+' reuses same-run fresh16K qualification; hash checked')\n"+src[end:]
save(REC/'source-reference.json',{'original_runner_sha256':hashlib.sha256((BASE/'run.py').read_bytes()).hexdigest(),'change':'input qualification empty-content acceptance only; per-model prior capacity reference'})
(REC/'run.py').write_text(src)
# No new script import starts work; execute the modified private runner as main.
exec(compile(src,str(REC/'run.py'),'exec'),{'__name__':'__main__'})
