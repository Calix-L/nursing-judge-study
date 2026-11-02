import json,hashlib
from pathlib import Path
R=Path('runs/judge-binary-20261020-r1');OLD=Path('runs/judge-agreement-20261020-r1')
def save(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n');p.chmod(0o600)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
prev=json.loads((OLD/'plan.json').read_text());bindings=[]
for mode in ['partial_counts','complete_only']:
 for b in prev['bindings']:
  code=b['review_id'];packet=json.loads((OLD/'packets'/f'{code}.json').read_text());oldmessages=json.loads((OLD/'messages'/f'{code}.json').read_text())
  for c in packet['source_criteria']:
   anchors=c.pop('score_anchors')
   if mode=='partial_counts':c['binary_anchors']={'1':'At least partial achievement: satisfies either of these positive/partial descriptions: PARTIAL: '+anchors['1']+' COMPLETE: '+anchors['2'],'0':'No partial or complete achievement is demonstrated. Original non-achievement description: '+anchors['0']}
   else:c['binary_anchors']={'1':'Complete achievement ONLY: '+anchors['2'],'0':'Fails the complete-achievement requirement; includes partial or absent performance. PARTIAL: '+anchors['1']+' ABSENT: '+anchors['0']}
  system=oldmessages[0]['content']
  system=system.replace("Use each criterion's exact 0/1/2 anchors and observable behavior. Consider the whole criterion; partial coverage is generally 1, not automatic 2. Do not silently substitute a generic rubric.","Use ONLY the supplied binary anchors and observable behavior. Output scores0or1. Consider the whole criterion; do not invent additional requirements. Do not silently substitute a generic rubric.")
  system=system.replace('can score0 with status:observed','can score0 with status:observed').replace('Items with meaningful actual partial discussion may be scored even in censored encounters.','Items with meaningful actual discussion may be scored even in censored encounters, using the supplied binary rule. Untouched items in censored encounters remain null, not0.')
  system=system.replace('"score":0|1|2|null','"score":0|1|null').replace('status observed requires integer0/1/2','status observed requires integer0/1')
  system+='\nBINARY EXPERIMENT RULE: '+('Score1 for partial OR complete achievement, score0 for absence/failure. This is deliberately permissive and does not certify full or safe care.' if mode=='partial_counts' else 'Score1 ONLY for complete achievement of the supplied criterion. Meaningful partial performance scores0; items never observed before censorship remain null, NOT0.')+' Preserve the evidence/status boundary independently of the binary score. Do not guess any previous rating.'
  packet['binary_rule']=mode;messages=[{'role':'system','content':system},{'role':'user','content':json.dumps(packet,ensure_ascii=False,separators=(',',':'))}]
  save(R/'packets'/mode/f'{code}.json',packet);save(R/'messages'/mode/f'{code}.json',messages)
  bindings.append({'mode':mode,'review_id':code,'source_packet_sha256':b['packet_sha256'],'packet_sha256':sha(R/'packets'/mode/f'{code}.json'),'messages_sha256':sha(R/'messages'/mode/f'{code}.json')})
key=json.loads((OLD/'private-key.json').read_text());save(R/'private-key.json',key)
save(R/'plan.json',{'run_id':R.name,'date':'2026-10-20','source_run':str(OLD),'source_plan_sha256':sha(OLD/'plan.json'),'source_comparison_sha256':sha(OLD/'comparison.json'),'baseline':'Deterministic binary conversion of frozen assistant ternary ratings, not a new expert binary gold standard','judges':prev['judges'],'modes':{'partial_counts':'score>=1 maps1; score0 maps0; null staysnull','complete_only':'score2 maps1; scores0and1 map0; null staysnull'},'context_window':16384,'max_output_tokens':3072,'temperature':0,'thinking_type':'disabled','formal_repeats':1,'schema_repair_attempts':1,'modes_by_model':{'mimo-v2.5-pro':['complete_only','partial_counts'],'glm-5.2':['partial_counts','complete_only'],'deepseek-v4-flash':['complete_only','partial_counts']},'bindings':bindings,'metrics':['exact agreement on the fixed48 baseline numeric items','baseline-positive and baseline-negative agreement separately','mean signed bias and positive rate','numeric/null applicability disagreements on all87items','pairwise agreement on same48items','compare deterministic collapse with fresh direct binary API ratings separately'],'missing_policy':'If a judge emitsnull on a baseline numeric item, count it as primary fixed48 non-agreement and separately report common-numeric-only agreement. Do not drop such items to inflate agreement.','price_snapshot':prev['price_snapshot'],'privacy':'Private expert text and complete replies remain in ignored runs; aggregates only public.','qualification':'Fresh natural-text probe and actual-input provider qualification. Original nurse/patient trajectories not rerun; no baseline scores/masks/identities given to judges.'})
# No new calls: historical ternary-rating collapse, explicitly separate from direct binary experiment.
x=json.loads((OLD/'comparison.json').read_text());out={}
for mode,threshold in [('partial_counts',1),('complete_only',2)]:
 out[mode]={}
 for m in prev['judges']:
  rows=[d for d in x['details'] if d['judge']==m and d['baseline_score'] is not None and d['judge_score'] is not None]
  matrix={f'{a}{b}':sum(int(d['baseline_score']>=threshold)==a and int(d['judge_score']>=threshold)==b for d in rows) for a in [0,1] for b in [0,1]}
  out[mode][m]={'n':len(rows),'exact':matrix['00']+matrix['11'],'confusion_baseline_then_judge':matrix,'baseline_positive':matrix['10']+matrix['11'],'baseline_negative':matrix['00']+matrix['01'],'method':'deterministic posthoc mapping, no API calls'}
save(R/'remap-comparison.json',out)
print('prepared',len(bindings),'distinct inputs; baseline48 numeric/39 null preserved')
