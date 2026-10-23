# CN-HK Valuation Skill

一套面向中国 A 股和港股的通用估值 Skill。输入股票代码后：先做基本面体检，再按公司类型路由到合适的估值模型，计算熊/基/牛价值区间，并给出敏感性、盈亏平衡参数和分歧诊断。数据不足或模型不适用时拒绝估值，不编造数字。

## 内容

- `SKILL.md`：入口与主执行流程（七步工作流 + 路由摘要表）。
- `references/`：按需加载的参考模块。
  - `model-routing.md`：八类公司类型的路由表、覆盖原则、拒绝条件、模型分歧规则。
  - `models-banks-insurers.md`：银行 DDM / 剩余收益、保险 P/EV 的公式与跟踪指标。
  - `models-cashflow.md`：FCFF-DCF、FCFE-DCF、中周期正常化、分阶段/情景 DCF、反向 DCF、可比倍数。
  - `models-assetbased.md`：NAV、资产重估、债务压力情景、REITs AFFO 与物业层 NOI/cap rate 两种口径。
  - `ke-and-uncertainty.md`：Ke / 隐含 Ke / 目标收益率的概念区分与不确定性纪律。
  - `ke-wacc-estimation.md`：Ke/WACC 可审计估计方法、溯源规则、数据来源约定与局限性。
  - `china-market.md`：A 股/港股数据口径、数据核验流程与最低记录格式、A/H、股息税务、分行业披露注意事项。
  - `snapshot-format.md`：输入快照格式（冻结一套带溯源的期间数据）、检查闸门与新旧快照 diff 语义。
  - `report-template.md`：九节报告结构（含路由记录、参数审计、分歧诊断、估值留痕）。
- `scripts/valuation.py`：全部估值计算器与反向求解器，只使用 Python 标准库；无效输入一律抛错，不猜测。
- `scripts/ke_wacc.py`：Ke/WACC 可审计估计（CAPM、build-up、bottom-up beta、WACC、情景），只使用标准库；无默认参数，缺失即拒绝。
- `scripts/audit_ledger.py`：研究台账来源审计闸门——计算前先跑一遍，缺溯源、缺理由、占位文本一律报错或警告。
- `scripts/snapshot.py`：输入快照闸门（`check`）与快照对比（`diff`），用于月度更新时定位到底哪一项数字变了、是否由新披露解释。
- `tests/`：公式手算对照、边界拒绝、路由表一致性、Ke/WACC 溯源与拒绝、反向求解往返、台账审计、快照校验与 diff、六类案例端到端测试。
- `examples/`：JSON 输入示例（每个模型至少一个，外加研究台账与快照示例）。

## 模型清单

| Payload `model` | 用途 | 折现依据 |
|---|---|---|
| `dcf_fcff` | FCFF-DCF，含企业价值到股权价值桥接；终值可选 Gordon 增长或退出倍数 | WACC |
| `fcfe` | 股权自由现金流折现 | Ke |
| `ddm` | 股息折现（银行、稳定高股息主模型） | Ke |
| `residual_income` | 剩余收益 / PB-ROE（银行、保险交叉验证） | Ke |
| `pev` | 保险 P/EV | 可比倍数（禁止用现价反解充当验证） |
| `nav` | 资产净值 / 重估（房地产、资产持有型），支持压力情景 | 资产市值 |
| `reit_noi` | REIT 物业层估值：NOI / 物业资本化率，再走 nav 桥接 | 物业 cap rate（与 AFFO 口径不可混用） |
| `affo` | REITs AFFO 估值 | 股权层资本化率或可比倍数（二选一） |
| `normalize_cycle` | 中周期正常化（周期股前置步骤） | — |
| `comparable_multiples` | P/E、P/B、EV/EBITDA、P/AFFO 可比交叉验证 | 可比倍数（需注明可比组与日期） |
| `dcf_sensitivity` / `ddm_sensitivity` | 敏感性矩阵 | 变动参数 |
| `reverse_dcf_growth` | 反解现价隐含的永续增长率 | 求解 |
| `reverse_dcf_wacc` | 反解盈亏平衡 WACC | 求解 |
| `reverse_dcf_fcff_scale` | 反解现价隐含的现金流缩放倍数 | 求解 |
| `reverse_ddm_ke` | 反解盈亏平衡 Ke | 求解 |
| `capm_ke` / `build_up_ke` | Ke 估计（CAPM / build-up），带溯源与警告 | — |
| `unlever_beta` / `relever_beta` / `bottom_up_beta` | Beta 去杠杆、重新加杠杆、可比公司自下而上 | — |
| `wacc` | WACC 估计（债务成本 basis 校验、金融企业拒绝） | — |
| `ke_scenario` | 熊/基/牛 Ke 情景（每个情景须有理由） | — |
| `route` | 按公司类型查默认路由 | — |

## 测试

```bash
python -m unittest discover -s tests -v
```

## 运行示例

```bash
python scripts/valuation.py examples/ddm-example.json
python scripts/valuation.py examples/dcf-example.json
python scripts/valuation.py examples/dcf-exit-multiple-example.json
python scripts/valuation.py examples/fcfe-example.json
python scripts/valuation.py examples/ri-example.json
python scripts/valuation.py examples/pev-example.json
python scripts/valuation.py examples/nav-example.json
python scripts/valuation.py examples/nav-stress-example.json
python scripts/valuation.py examples/affo-example.json
python scripts/valuation.py examples/reit-noi-example.json
python scripts/valuation.py examples/multiples-example.json
python scripts/valuation.py examples/reverse-dcf-example.json
python scripts/valuation.py examples/ke-capm-example.json
python scripts/valuation.py examples/ke-scenario-example.json
python scripts/valuation.py examples/wacc-example.json
```

快照工作流：

```bash
python scripts/snapshot.py check examples/snapshot-example.json
python scripts/snapshot.py diff snapshots/600036-2026H1.json snapshots/600036-2026Q3.json
```

输入数值必须使用一致的货币和单位。例如现金流以"百万元"为单位、股数以"百万股"为单位，则输出每股价值为相应货币/股。payload 中可声明 `currency` / `unit` / `as_of`，结果会回显原始输入（`input_echo`）以保证可复现。

## 数据边界

本 Skill 不含实时行情或财务数据 API。运行时应使用 WorkBuddy 已有的数据工具和官方公告来源（CNINFO、上交所、深交所、HKEXnews）；计算脚本只负责可复核的数学运算，不会自动抓取数据，也不会在输入缺失时编造数值。

## 历史

由 `cn-hk-dcf-ddm`（FCFF-DCF + DDM）扩展而来：保留原四个模型与全部测试，新增 FCFE、剩余收益、P/EV、NAV、AFFO、正常化与路由表；参考文档重组为入口 + 路由 + 三个按需模型模块。

2026-10-23 升级：新增 `scripts/ke_wacc.py`（Ke/WACC 可审计估计：CAPM、build-up、bottom-up beta、WACC、熊基牛情景；无默认参数、溯源强制、金融企业拒绝 WACC）、四个反向求解器（隐含永续增长率 / 盈亏平衡 WACC / 隐含现金流缩放 / 盈亏平衡 Ke）、`reit_noi`（物业层 NOI/cap rate 口径，与 AFFO 股权层口径明确区分）、`comparable_multiples`（P/E、P/B、EV/EBITDA、P/AFFO 交叉验证）、payload 元数据声明与输入回显；新增 `references/ke-wacc-estimation.md`；测试从 55 个扩充到 126 个。

2026-10-23 第二次迭代：`dcf_fcff` 支持 `terminal_method: "exit_multiple"`（退出倍数终值，并反解隐含永续增长率作为一致性检查）；新增 `scripts/snapshot.py` 与 `references/snapshot-format.md`（输入快照格式、`check` 闸门、`diff` 变更归因）；`china-market.md` 补 A 股差别化红利税与港股通 20% 的具体口径，DDM 要求显式声明税前/税后口径；测试从 126 个扩充到 198 个。
