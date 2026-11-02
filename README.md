# Nursing Judge Study

两份糖尿病护理场景的事后 AI 判分复现实验。包含完整案例、六条已发生的交互轨迹、三套评分提示、冻结 AI 基线和 141 份有效裁判结果。

这个仓库用于检查**裁判如何根据证据逐项判分，以及不同裁判为何产生分歧**。病例仍是专家项目中的虚构草稿，基线是 AI 复核，均未构成独立临床金标准。

## 先看哪里

| 入口 | 内容 |
| --- | --- |
| [judge.py](judge.py) | 独立复现入口：导出请求、检查判分、重算一致率和 Kappa、显式调用 API |
| [cases/](cases/) | 两个实际实验所用的完整冻结病例包，含原始场景、患者事实、rubric、工具和角色契约 |
| [prompts/](prompts/) | 三套当时实际使用的裁判系统提示，原文保留 |
| [data/study.json](data/study.json) | 六条完整证据时间线、逐项 AI 基线、141 份有效判分及来源绑定 |
| [historical/](historical/) | 当时实际运行的原始判分脚本，按字节保存，非新编写的替代实现 |
| [METHODS.md](METHODS.md) | 输入、输出、未评规则、失败修复、统计口径和局限 |
| [NOTICE.md](NOTICE.md) | 来源、许可范围和私有审阅边界 |

## 离线复现

Python 3.10+，独立入口只用标准库，不需要原主项目、GPU 或 API key。在仓库根目录运行：

```bash
python3 judge.py verify
python3 judge.py compare --condition complete_only
python3 judge.py compare --condition ternary
python3 -m unittest discover -s tests -v
```

`verify` 检查导出文件 SHA256、18 组历史评审消息内容、全部有效判分结构及历史一致率是否能重算一致。通过只表示软件与档案一致，不表示临床判断正确。

导出一个真实评审请求，不发送 API：

```bash
python3 judge.py request --review R01 --condition ternary > review-request.json
```

返回的 `messages` 与历史对应目标逐字符一致。一次正式判分请求包含**整条已发生轨迹和全部条目**，并非每个条目单独请求模型。

## 两个案例与六条轨迹

| 案例 | 任务主题 | 护士轨迹 |
| --- | --- | --- |
| D02-CARD-001 | 新确诊后的首次教育：情绪准备、教育节奏、自我管理支持 | R01：GLM 5.2；R02：MiMo v2.5 Pro；R05：DeepSeek Flash |
| D02-CARD-002 | 出院首周居家管理复核：胰岛素、监测、锐器处置及随访 | R03：GLM 5.2；R04：MiMo v2.5 Pro；R06：DeepSeek Flash |

即两个场景 × 三个护士模型各运行一次。部分运行中断；第二例存在患者事实漂移。轨迹保留原状，不能据此进行公平的护士能力排名。患者不是 MIMIC 患者，本实验使用云端患者表达与事件路由，不能用于证明微调患者模型的效果。

每个病例文件中的 `design_blueprint.scenario_draft` 是原始场景定义，`expert_contract` 保存评估及患者披露契约，`case` 保存运行视图。审核状态仍为待独立复核。这里只复现事后判分，未复制整个护士/患者仿真运行时。

## 三套规则

| 源表现 | ternary | partial_counts | complete_only |
| --- | ---: | ---: | ---: |
| 未达到要求 | 0 | 0 | 0 |
| 部分达到要求 | 1 | 1 | 0 |
| 完整达到要求 | 2 | 1 | 1 |
| 未评 | null | null | null |

两套二值提示由原锚点合并，未将复合标准拆成专家审定的原子条目。`null` 判断及语义充分性在历史实验中仍主要由裁判模型解释，代码只检查状态/分数关系和引用存在性。

## 显式调用一个裁判

只有 `score` 会调用外部 API。先在本机设置 `API_KEY` 环境变量，勿写入仓库。示例：

```bash
read -s API_KEY
export API_KEY
python3 judge.py score --model glm-5.2 --review R01 --condition ternary --output runs/glm52-r01
```

默认接口是 `https://kspmas.ksyun.com/v1/chat/completions`，可用 `--endpoint` 指定兼容接口。模型是否仍可用取决于当前账户权限；本次打包没有重新调用付费模型。

便利入口执行一次输入长度测量和一次判分，保存原始响应、用量、失败与最终结构有效结果。使用 16,384 上下文预算、3,072 输出预算、温度 0、请求关闭思考；实际返回身份必须与请求模型一致。Kimi K3 的历史温度 0.6 结果单列，不能混入温度 0 主组。

**便利入口与历史调度器有明确区别：**不自动修复、不重试、不批量运行，也不完成完整的部署容量资格验证；新结果属于显式 smoke，不自动并入冻结实验。输出目录必须是新目录，避免覆盖记录。输入长度测量即使返回空文本，只要身份与有效用量通过，也可用于预算检查；正式判分必须返回可解析结果。

## 结果与计量

冻结扩展实验包含主组 123 份、Kimi 兼容组 18 份有效判分。缺失和失败覆盖见 [data/coverage.json](data/coverage.json)，并未以零分补齐。

`compare` 固定原基线 48 个数值位置；不足六条有效轨迹的模型不给完整一致率。原 39 个未评位置另报范围分歧。Kappa 仅在双方有数值的条目上计算，明确附带其分母；它与固定分母的一致率不是完全相同的口径。类别恒定导致分母为零时返回 null。三档另给线性加权 Kappa；两病例内条目相关，不报告把条目假定独立的置信区间。

354 次历史 API 请求账本保存在 [data/usage.jsonl](data/usage.jsonl)。回执总计 3,226,977 token；349 次可计价请求的历史目录价估费约人民币 20.20–22.11 元，另 2 次 HTTP 错误缺用量、3 次回执用量不一致未计价。该区间不是完整账单上限，详见 [data/accounting.json](data/accounting.json)。新调用只保存服务商用量，不将旧价格自动当成当前价格。

## 来源

主项目：[Calix-L/diabetes-care-bench](https://github.com/Calix-L/diabetes-care-bench)。场景来源固定为 [ntcgeorge/diabetic-nursing-harness@3118f1f](https://github.com/ntcgeorge/diabetic-nursing-harness/tree/3118f1ff345ce0b5400be7538b7f4a87f8b27942)。来源提交、脚本字节散列和病例包绑定见 [data/provenance.json](data/provenance.json)。
