# Experiment 1 (New): LLM-Adaptive vs Static SCE-UA Calibration

## 1. 科学问题

LLM 作为 SCE-UA 超参数和参数范围的自适应控制器,能否比静态强基准更高效地率定 GR4J?

核心对比:
- **M0 (静态基准)**: 固定 ngs=20 + 宽范围,跑到收敛,单次
- **M2 (LLM 自适应)**: LLM 每代生成 5 组不同的 {ngs, param_ranges, seed},并行跑,取最优反馈下一代,最多 10 代
- **M1 (人工对比)**: 相同决策时间内,人选 1 组 vs LLM 选 5 组,时间匹配法

## 2. 流域池 (20 basins)

16 个 HUC-02 各一个(跳过 HUC08/13) + 2 个湿润补充 + 2 个好流域补充:

| basin_id  | HUC | 区域              | 难度   | screen NSE |
|-----------|-----|-------------------|--------|-----------|
| 12025000  | 17  | Pacific NW        | easy   | 0.75      |
| 11532500  | 18  | California        | easy   | 0.74      |
| 02246000  | 03  | South Atl-Gulf    | easy   | 0.73      |
| 11482500  | 18  | California(2nd)   | easy   | 0.68      |
| 05495000  | 07  | Upper Mississippi  | easy   | 0.58      |
| 03574500  | 06  | Tennessee(2nd)    | easy   | 0.56      |
| 05595730  | 07  | Upper Miss(2nd)   | easy   | 0.55      |
| 02472500  | 03  | South Atl(2nd)    | medium | 0.31      |
| 01543000  | 02  | Mid-Atlantic      | medium | 0.47      |
| 07197000  | 11  | Ark-White-Red     | medium | 0.47      |
| 06885500  | 10  | Missouri          | medium | 0.44      |
| 03049000  | 05  | Ohio              | medium | 0.42      |
| 01169000  | 01  | New England       | hard   | 0.08      |
| 05057200  | 09  | Souris-Red        | hard   | 0.02      |
| 09508300  | 15  | Lower Colorado    | hard   | -0.02     |
| 09378630  | 14  | Upper Colorado    | hard   | -0.05     |
| 10336660  | 16  | Great Basin       | hard   | -0.06     |
| 04197170  | 04  | Great Lakes       | hard   | -0.36     |
| 08101000  | 12  | Texas-Gulf        | hard   | -0.62     |
| 03439000  | 06  | Tennessee         | hard   | -0.87     |

选择原则:
- 地理散布: 覆盖 16/18 HUC 区域
- 难度真实分布: easy 7 / medium 5 / hard 8
- GR4J 适用区集群: HUC17/18/03/06/07 湿润区多选
- exp2/3/4 anchor 保留: 12025000, 11532500, 03439000

## 3. SCE-UA 超参设计

### 统一原则
- **rep=100000** (纯上限,不该被触到)
- 收敛靠 kstop/peps/pcento 自然早停
- seed 每次不同,保证随机性

### M0 固定参数
| 参数    | 值     | 含义                       |
|---------|--------|---------------------------|
| ngs     | 20     | 复合体数 (Duan GR4J 推荐)  |
| kstop   | 50     | 连续 50 轮无改进则停        |
| peps    | 0.01   | 参数空间收缩到 1% 则停      |
| pcento  | 0.1    | 目标函数改进 <0.1% 则停     |
| ranges  | 宽范围  | x1[1,2500] x2[-15,15] x3[1,700] x4[0.5,12] |

### M2 LLM 可调参数
| 参数         | LLM 可调范围    | 说明                    |
|--------------|----------------|------------------------|
| ngs          | 10-200         | 搜索广度                |
| param_ranges | 物理硬界内自由   | x1-x4 各自的 [min,max]  |
| seed         | 自动不同        | 每组不同 seed           |
| kstop/peps/pcento | 固定同 M0 | 不让 LLM 调收敛条件     |

## 4. M2 并行迭代设计

```
每流域最多 10 代:
  代 k:
    1. LLM 接收: 流域属性 + 前 k-1 代的全部记录(5组×(k-1)代)
    2. LLM 输出: 5 组不同的 {ngs, param_ranges}
    3. 并行: 5 组同时跑 SCE-UA (5 路 multiprocessing)
    4. 记录: 所有 5 组的 NSE/params/wall_time
    5. 反馈: 5 组中 best NSE 作为本代代表,全部记录供下代参考
    6. 早停: 连续 3 代 best NSE 提升 < 0.005 则停
```

## 5. M2 与 Exp2 数据复用

M2 的迭代调参过程本质上就是 exp2 要展示的"LLM 智能率定"能力。
数据结构设计为: 每条 trial record 包含完整的 decision + result,
exp2 直接读 M2 的 trials.jsonl 作为数据源,无需重跑。

关键字段:
- generation_idx, variant_idx (代次, 组内编号)
- decision: {ngs, param_ranges, seed, notes}
- result: {test_NSE, train_NSE, best_params, boundary_hits, icall, wall_time_s}
- llm_tokens: {prompt_tokens, completion_tokens, total_tokens, decision_elapsed_s}

## 6. M1 人工对比 (时间匹配法)

- 选 3-5 个代表流域(易/中/难)
- 操作者看流域属性 + GR4J 物理,选一组 {ngs, param_ranges}
- 记录决策时间 T_human (秒)
- 论文论点: T_human 内 LLM 能生成 ~T_human/3 代 × 5 组 = N 组参数组合
- 人工: 1 组 -> 1 个 NSE
- LLM: N 组 -> best of N 个 NSE

## 7. 绘图计划

1. **Per-basin M0 vs M2 对比**: 20 流域,M0 NSE vs M2 best NSE,按难度排序
2. **M2 逐代收敛曲线**: best-so-far NSE vs generation,每流域一条线
3. **M2 每代 5 组 NSE 分布**: 箱型图/散点,展示 LLM 探索多样性
4. **超参变化轨迹**: M2 每代 ngs + x1-x4 范围如何自适应变化
5. **时间效率**: M0 wall_time vs M2 total wall_time,含 LLM 决策时间
6. **地理分布图**: 20 流域在 CONUS 上标注 + M0/M2 NSE 着色

## 8. 目录结构

```
experiment/exp1_new/
  DESIGN.md              <- 本文件
  common.py              <- 20 流域池 + 超参定义 + run_trial
  run_m0_baseline.py     <- M0 并行 runner
  run_m2_adaptive.py     <- M2 LLM 自适应 runner (每代 5 组并行)
  compile_results.py     <- 结果编译
  plot_results.py        <- 绘图
  results/
    m0_baseline/         <- M0 SCE-UA 过程 + 结果
    m2_adaptive/         <- M2 迭代过程 + 结果
  tables/                <- 编译后 CSV
  figures/               <- 图
```
