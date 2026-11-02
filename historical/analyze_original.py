import hashlib,itertools,json,statistics
from pathlib import Path
from nurse_harness.costs import summarize
R=Path('runs/judge-agreement-20261020-r1');keys=json.loads((R/'private-key.json').read_text());plan=json.loads((R/'plan.json').read_text())
def save(name,x):(R/name).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def metrics(a,b):
 rows=list(zip(a,b));common=[(x,y) for x,y in rows if x['score'] is not None and y['score'] is not None];d=[y['score']-x['score'] for x,y in common];n=len(d)
 return {'all_items':len(rows),'common_numeric_items':n,'exact_numeric':sum(z==0 for z in d),'exact_numeric_rate':sum(z==0 for z in d)/n if n else None,'mae_0_to_2':sum(abs(z) for z in d)/n if n else None,'mean_signed_difference':sum(d)/n if n else None,'endpoint_disagreements':sum(abs(z)==2 for z in d),'numeric_null_agreement':sum((x['score'] is None)==(y['score'] is None) for x,y in rows),'raw_status_label_agreement':sum(x['status']==y['status'] for x,y in rows),'normalized_status_agreement':sum(('observed' if x['score'] is not None else x['status'])==('observed' if y['score'] is not None else y['status']) for x,y in rows),'null_becomes_numeric':sum(x['score'] is None and y['score'] is not None for x,y in rows),'numeric_becomes_null':sum(x['score'] is not None and y['score'] is None for x,y in rows),'common_baseline_points':sum(x['score'] for x,y in common),'common_judge_points':sum(y['score'] for x,y in common)}
summary={};details=[];ratings={};bases={}
for k in keys:
 b=json.loads(Path(k['baseline']).read_text());bases[k['review_id']]=b
for model in plan['judges']:
 allbase=[];alljudge=[];bytrace=[];available={}
 for k in keys:
  code=k['review_id'];p=R/model/code/'rating.json'
  if not p.exists():continue
  pred=json.loads(p.read_text());pmap={x['criterion_id']:x for x in pred['items']};b=bases[code];ordered=[pmap[x['criterion_id']] for x in b['items']]
  allbase+=b['items'];alljudge+=ordered;available[code]=ordered
  m=metrics(b['items'],ordered);m.update({'review_id':code,'nurse_model':k['nurse_model'],'case':k['case'],'baseline_points':sum(x['score'] or 0 for x in b['items']),'baseline_numeric':sum(x['score'] is not None for x in b['items']),'judge_points':sum(x['score'] or 0 for x in ordered),'judge_numeric':sum(x['score'] is not None for x in ordered)})
  bytrace.append(m)
  for a,c in zip(b['items'],ordered):
   details.append({'judge':model,'review_id':code,'case':k['case'],'nurse_model':k['nurse_model'],'criterion':a['criterion_id'],'baseline_score':a['score'],'judge_score':c['score'],'baseline_status':a['status'],'judge_status':c['status'],'baseline_reason':a['reason'],'judge_reason':c['reason'],'judge_evidence_ids':c['evidence_ids'],'numeric_difference':None if a['score'] is None or c['score'] is None else c['score']-a['score']})
 ratings[model]=available;summary[model]={**metrics(allbase,alljudge),'rated_trajectories':len(bytrace),'per_trajectory':bytrace}
pairwise=[]
for a,b in itertools.combinations(plan['judges'],2):
 common=sorted(set(ratings[a])&set(ratings[b]));x=[v for c in common for v in ratings[a][c]];y=[v for c in common for v in ratings[b][c]];pairwise.append({'judge_a':a,'judge_b':b,**metrics(x,y)})
entries=[json.loads(l) for l in (R/'usage.jsonl').read_text().splitlines()];cost=summarize(entries,json.loads(Path(plan['price_snapshot']).read_text()));save('complete-costs.json',cost)
report={'run_id':R.name,'baseline_not_gold':True,'judges':summary,'pairwise':pairwise,'details':details,'complete_clinical_total':None,'clinical_pass':None}
save('comparison.json',report)
lines=['# 同轨迹多裁判复评分歧实验','', '日期：2026-10-20。两份原生专家虚构病例、三个护士模型，共六条历史轨迹；不重跑护士或患者。对照是本助手上一轮已冻结的逐项 AI 评分，**不是专家金标准**。原轨迹、原自动分、原助手评分保持不变。','', '## 冻结配置与盲法','', '三个 API 裁判统一收到同一份英文源标准、病例真值、可用工具、完整已发生对话及权威事件投影。六条轨迹随机编码；不提供护士模型身份、上一轮分数、理由或可评掩码。温度0，thinking disabled，16,384上下文，3,072输出；每轨迹一次正式评分，仅JSON/结构错误允许一次修复。接口裁判可能在匿名情况下评价自己的轨迹；本轮不是双盲独立临床验证。','', '原基线共87项，其中48项数值评分、39项null。分开比较数值评分与可评/不可评判断，禁止混合不同分母排名。第二例存在患者事实漂移，相关评分仅是对话描述，不能作为护士模型能力排行榜。','', '## 各裁判与基线差异','', '| 裁判 | 轨迹数 | 共同数值条目 | 完全一致 | 平均绝对差（0–2） | 平均偏差（裁判−基线） | 可评/null一致 | 基线null改为数值 |','|---|---:|---:|---:|---:|---:|---:|---:|']
for name,m in summary.items():
 if not m['common_numeric_items']:continue
 lines.append(f"| {name} | {m['rated_trajectories']}/6 | {m['common_numeric_items']} | {m['exact_numeric']}/{m['common_numeric_items']}（{m['exact_numeric_rate']:.1%}） | {m['mae_0_to_2']:.3f} | {m['mean_signed_difference']:+.3f} | {m['numeric_null_agreement']}/{m['all_items']} | {m['null_becomes_numeric']} |")
lines+=['','## 每条轨迹原始分数及覆盖','', '以下仅展示原始合计及数值条目数；分母不同不能直接比较总分。共同掩码的合计保存在comparison.json。','', '| 护士轨迹 | 病例 | 本助手 | MiMo裁判 | GLM裁判 | Flash裁判 |','|---|---|---:|---:|---:|---:|']
for k in keys:
 b=bases[k['review_id']];n=sum(x['score'] is not None for x in b['items']);cols=[f"{sum(x['score'] or 0 for x in b['items'])}/{n*2} ({n}项)"]
 for model in plan['judges']:
  vals=ratings[model].get(k['review_id']);cols.append('未取得有效评分' if vals is None else f"{sum(x['score'] or 0 for x in vals)}/{2*sum(x['score'] is not None for x in vals)} ({sum(x['score'] is not None for x in vals)}项)")
 lines.append('| '+ ' | '.join([k['nurse_model'],k['case'],*cols])+' |')
lines+=['','## 逐项差异与证据','', '以下保存全部差异，不按裁判多数票覆盖基线。']
for d in details:
 if d['baseline_score']==d['judge_score'] and d['baseline_status']==d['judge_status']:continue
 lines += ['',f"### {d['judge']} / {d['nurse_model']} / {d['case']} / {d['criterion']}",f"- 基线：{d['baseline_score']}，{d['baseline_status']}。{d['baseline_reason']}",f"- 裁判：{d['judge_score']}，{d['judge_status']}。{d['judge_reason']}",f"- 裁判引用：{', '.join(d['judge_evidence_ids']) or '无'}。完整原文见packet和原轨迹。"]
lines+=['','## 用量与限制','', '完整请求账本usage.jsonl包括容量探针、输入测量、失败、正式评分及结构修复。complete-costs.json使用2026-09-14价格快照估算，非当前价格核验或账户账单。存在缺失用量时，已知费用区间不能当成完整账单上限。', '', 'GLM重复字符容量探针异常，首个自然文本探针超过本地16K预算而被拒绝；诊断保留，不作为评分。只有重新通过身份、容量及实际输入资格检查后才纳入正式评分。', '', '每裁判每轨迹仅一次正式有效评分，没有测同一裁判的重复稳定性；条目彼此相关、只有两个情境，不能泛化为裁判或护士模型总能力排名。所有临床结论待独立专家复核。完整数据为未经公开再分发授权的专家源材料，保留私有runs，公共仓库仅放汇总。']
(R/'report.md').write_text('\n'.join(lines)+'\n')
print(json.dumps({m:{k:v for k,v in x.items() if k!='per_trajectory'} for m,x in summary.items()},ensure_ascii=False,indent=2));print('COST',json.dumps(cost['total'],ensure_ascii=False))
