import collections,hashlib,itertools,json
from pathlib import Path
from nurse_harness.costs import summarize
R=Path('runs/judge-expanded-20261029-r1');P=json.loads((R/'plan.json').read_text());K=json.loads((R/'private-key.json').read_text());REC=R/'measurement-recovery';A=Path('runs/judge-agreement-20261020-r1');B=Path('runs/judge-binary-20261020-r1')
def save(name,x):(R/name).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def basevalue(v,cond):return v if v is None or cond=='ternary' else int(v>=(1 if cond=='partial_counts' else 2))
BASE={x['review_id']:read(Path(x['baseline'])) for x in K};basemasks={(code,i['criterion_id']):i for code,b in BASE.items() for i in b['items']};bindings={(b['condition'],b['review_id']):b for b in P['bindings']}
# Never overlay or rerun a formally attempted root cell.
root_usage=[json.loads(l) for l in (R/'usage.jsonl').read_text().splitlines()] if (R/'usage.jsonl').exists() else []
attempted={(e['requested_model'],e['condition'],e['review_id']) for e in root_usage if e['role'] in ['judge','judge_repair']}
models=P['main_models']+list(P['compatibility_models']);ratings={};origins={};details=[];results={}
for model in models:
 ratings[model]={};results[model]={}
 for cond in P['conditions']:
  ratings[model][cond]={};pairs=[];pertrace=[];known_null=0;changednull=0;envchanged=0;censchanged=0;scopeeq=0
  for k in K:
   code=k['review_id'];f=R/model/cond/code/'rating.json';rf=REC/model/cond/code/'rating.json'
   if f.exists() and rf.exists():raise AssertionError('Duplicate scored cell')
   if not f.exists() and rf.exists():
    assert (model,cond,code) not in attempted,'Recovery overlapped a prior formal attempt';f=rf
   if not f.exists():continue
   x=read(f);binding=bindings[(cond,code)];assert x['messages_sha256']==binding['messages_sha256'] and x['packet_sha256']==binding['packet_sha256'];ratings[model][cond][code]=x;origins[(model,cond,code)]=str(f)
   pm={i['criterion_id']:i for i in x['items']};assert len(pm)==len(BASE[code]['items']) and set(pm)=={i['criterion_id'] for i in BASE[code]['items']}
   packet=read(R/'packets'/cond/f'{code}.json');ids={t['id'] for t in packet['actual_timeline']}|{e['id'] for e in packet['authoritative_event_index']};local=[]
   for item in BASE[code]['items']:
    a=pm[item['criterion_id']];v=basevalue(item['score'],cond);s=a['score'];assert all(i in ids for i in a['evidence_ids'])
    if a['status']=='observed':assert type(s) is int and s in ([0,1,2] if cond=='ternary' else [0,1])
    else:assert s is None and a['status'] in ['censored_not_observed','environment_unassessable']
    if v is not None:pairs.append((v,s));local.append((v,s))
    else:
     known_null+=1
     if s is not None:
      changednull+=1;envchanged+=int(item['status']=='environment_unassessable');censchanged+=int(item['status']=='censored_not_observed')
    scopeeq+=int((v is None)==(s is None))
    details.append({'model':model,'condition':cond,'review_id':code,'criterion_id':item['criterion_id'],'baseline':v,'judge':s,'baseline_status':item['status'],'judge_status':a['status'],'reason':a['reason'],'evidence_ids':a['evidence_ids'],'origin':str(f),'temperature':x['temperature']})
   pertrace.append({'review_id':code,'numeric_baseline_items':len(local),'joint_numeric':sum(b is not None for a,b in local),'exact':sum(a==b for a,b in local),'baseline_sum':sum(a for a,b in local),'judge_sum_on_joint':sum(b for a,b in local if b is not None)})
  full=len(ratings[model][cond])==6;numeric=[(a,b) for a,b in pairs if b is not None];exact=sum(a==b for a,b in pairs);n=len(numeric)
  m={'complete_six_trajectories':full,'valid_trajectories':len(pertrace),'expected_trajectories':6,'baseline_numeric_positions_with_rating':len(pairs),'joint_numeric_positions':n,'expected_fixed_numeric_positions':48,'exact':exact,'fixed48_agreement':exact/48 if full else None,'observed_joint_numeric_agreement':sum(a==b for a,b in numeric)/n if n else None,'mae':sum(abs(b-a) for a,b in numeric)/n if n else None,'bias':sum(b-a for a,b in numeric)/n if n else None,'new_null_on_baseline_numeric':sum(b is None for a,b in pairs),'baseline_null_observed_positions':known_null,'baseline_null_to_numeric':changednull,'environment_null_to_numeric':envchanged,'censored_null_to_numeric':censchanged,'numeric_null_agree_count':scopeeq,'rated_all_positions':sum(len(BASE[t]['items']) for t in ratings[model][cond]),'per_trace':pertrace,'temperature':P['compatibility_models'].get(model,{}).get('temperature',0),'cohort':'compatibility' if model in P['compatibility_models'] else 'main'}
  if cond!='ternary':
   m.update(baseline_positive=46 if cond=='partial_counts' else 13,baseline_negative=2 if cond=='partial_counts' else 35,positive_agree=sum(a==1 and b==1 for a,b in pairs),negative_agree=sum(a==0 and b==0 for a,b in pairs),confusion={f'{a}{b}':sum(x==a and y==b for x,y in numeric) for a in [0,1] for b in [0,1]})
  results[model][cond]=m
pairs_out=[]
for cond in P['conditions']:
 for a,b in itertools.combinations(P['main_models'],2):
  if not results[a][cond]['complete_six_trajectories'] or not results[b][cond]['complete_six_trajectories']:continue
  pairs=[];scope=[]
  for k in K:
   code=k['review_id'];am={i['criterion_id']:i['score'] for i in ratings[a][cond][code]['items']};bm={i['criterion_id']:i['score'] for i in ratings[b][cond][code]['items']}
   for i in BASE[code]['items']:
    if i['score'] is not None:pairs.append((am[i['criterion_id']],bm[i['criterion_id']]))
  joint=[(x,y) for x,y in pairs if x is not None and y is not None]
  pairs_out.append({'condition':cond,'a':a,'b':b,'fixed_positions':48,'joint_numeric':len(joint),'exact_joint_numeric':sum(x==y for x,y in joint),'fixed48_numeric_agreement':sum(x==y for x,y in joint)/48,'joint_numeric_agreement':sum(x==y for x,y in joint)/len(joint) if joint else None,'both_null':sum(x is None and y is None for x,y in pairs)})
# Historical controls remain separate dates; compare first-original frozen results, not pooled repeats.
historical={'ternary':read(A/'comparison.json')['judges'],'binary':read(B/'comparison.json')['results']};control_deltas=[]
for m in P['concurrent_historical_controls']:
 for cond in P['conditions']:
  new=results[m][cond]
  if not new['complete_six_trajectories']:continue
  old=historical['ternary'][m]['exact_numeric_rate'] if cond=='ternary' else historical['binary'][cond][m]['fixed_mask_agreement'];control_deltas.append({'model':m,'condition':cond,'historical_date':'2026-10-20','contemporary_date':'2026-10-29','old_agreement':old,'new_agreement':new['fixed48_agreement'],'delta_percentage_points':(new['fixed48_agreement']-old)*100})
usage=[]
for f in [R/'discovery-usage.jsonl',R/'usage.jsonl',REC/'usage.jsonl']:
 if f.exists():usage.extend({**json.loads(l),'ledger':str(f)} for l in f.read_text().splitlines() if l.strip())
costs=summarize(usage,read(R/P['price_snapshot']));save('aggregate-costs.json',costs)
rawtokens=collections.Counter();anomalies=[]
for e in usage:
 u=e.get('usage')
 if isinstance(u,dict) and all(type(u.get(k)) is int for k in ['prompt_tokens','completion_tokens','total_tokens']):
  rawtokens.update({k:u[k] for k in ['prompt_tokens','completion_tokens','total_tokens']})
  cd=u.get('completion_tokens_details')
  if isinstance(cd,dict) and type(cd.get('reasoning_tokens')) is int and cd['reasoning_tokens']>u['completion_tokens']:anomalies.append({'model':e['requested_model'],'role':e['role'],'request_local_id':e.get('request_local_id'),'ledger':e['ledger'],'issue':'reported_reasoning_tokens_exceed_completion_tokens','usage':u})
summary={'run_id':R.name,'date':'2026-10-29','main_models':P['main_models'],'compatibility_models':P['compatibility_models'],'results':results,'pairwise_main_only':pairs_out,'historical_control_deltas':control_deltas,'details':details,'rating_origins':[{'model':m,'condition':c,'review_id':code,'path':p,'sha256':sha(Path(p))} for (m,c,code),p in origins.items()],'raw_reported_token_totals':dict(rawtokens),'usage_anomalies':anomalies,'api_usage_statuses':dict(collections.Counter(e['status'] for e in usage)),'usage_roles':dict(collections.Counter(e['role'] for e in usage)),'total_usage_requests':len(usage),'valid_main_ratings':sum(len(ratings[m][c]) for m in P['main_models'] for c in P['conditions']),'valid_compatibility_ratings':sum(len(ratings[m][c]) for m in P['compatibility_models'] for c in P['conditions']),'clinical_pass':None,'nurse_ranking':None}
save('comparison.json',summary)
lines=['# 扩展模型裁判对照实验','', '日期2026-10-29。同一组两例、六段轨迹，不重跑护士或患者。原AI基线不是专家金标准。下面只对完成六条轨迹的单元给固定48项一致率，缺失单元不记临床0分。','', '| 模型 | 温度 | 三档一致率 | 部分即可一致率 | 完整才算一致率 | 有效判分 |','|---|---:|---:|---:|---:|---:|']
for m in models:
 vals=[]
 for c in P['conditions']:
  a=results[m][c];vals.append(f"{a['exact']}/48 ({a['fixed48_agreement']:.2%})" if a['complete_six_trajectories'] else f"不完整 {a['valid_trajectories']}/6")
 lines.append('| '+' | '.join([m,str(P['compatibility_models'].get(m,{}).get('temperature',0)),*vals,str(sum(results[m][c]['valid_trajectories'] for c in P['conditions']))+'/18'])+' |')
lines+=['','## 未评范围差异','', '| 模型 | 三档null改数值 | 部分即可 | 完整才算 |','|---|---:|---:|---:|']
for m in models:
 vals=[str(results[m][c]['baseline_null_to_numeric'])+'/'+str(results[m][c]['baseline_null_observed_positions']) for c in P['conditions']];lines.append('| '+' | '.join([m,*vals])+' |')
lines+=['','## 方法与限制','', '使用原样复制的三套评分输入，绑定原消息/病例包/轨迹/基线SHA256；16K、3072输出、主实验温度0、thinking请求disabled。不同服务是否遵从关闭思考不作假设，保留实际finish_reason和reasoning用量。KimiK3只支持0.6，作为兼容性分组，不能混入同采样主实验。','', '原MiMo当前404，缺失不记0。只对因输入长度测量空content而从未正式判分的目标做测量兼容恢复：有有效prompt用量即可测长，正式评分仍须有非空content。已正式尝试的目标不重跑。恢复日志与原失败记录独立保留。','', '低覆盖或结构无效不能当临床低分。共同基线48项用于数值比较，全部87位置用于范围比较。原39个null包含环境不可执行和中断未观察；范围不同不全部等于模型错误。宽松基线46/48为1、严格基线35/48为0，不能只看总一致率。','', '只有两情境、六轨迹，第二例患者事实偏移、四条患者侧中断；单次判分，条目非独立。同期旧模型对照用来描述日期差异，不能消除随机性或证明因果。','', '费用依据本轮官方目录价快照，非账户账单。aggregate-costs.json按已知有效用量估价；异常或缺失用量单独保留，已知区间不是完整账单上限。']
(R/'report.md').write_text('\n'.join(lines)+'\n')
print('valid main',summary['valid_main_ratings'],'compat',summary['valid_compatibility_ratings'],'all API requests',len(usage),'raw tokens',dict(rawtokens),'usage anomalies',len(anomalies))
for m in models:print(m,[(c,results[m][c]['valid_trajectories'],results[m][c]['fixed48_agreement']) for c in P['conditions']])
