# CN-HK Valuation Skill

一套面向中国 A 股和港股的通用估值 Skill。输入股票代码后：先做基本面体检，再按公司类型路由到合适的估值模型，计算熊/基/牛价值区间，并给出敏感性、盈亏平衡参数和分歧诊断。数据不足或模型不适用时拒绝估值，不编造数字。

## 内容

- `SKILL.md`：入口与主执行流程（七步工作流 + 路由摘要表）。
- `references/`：按需加载的参考模块。
  - `model-routing.md`：八类公司类型的路由表、覆盖原则、拒绝条件、模型分歧规则。
  - `models-banks-insurers.md`：银行 DDM / 剩余收益、保险 P/EV 的公式与跟踪指标。
  - `models-cashflow.md`：FCFF-DCF、FCFE-DCF、中周期正常化、分阶段/情景 DCF。
  - `models-assetbased.md`：NAV、资产重估、债务压力情景、REITs AFFO。
  - `ke-and-uncertainty.md`：Ke/WACC/资本化率/倍数的估计纪律与不确定性处理。
  - `china-market.md`：A 股/港股数据口径、A/H、股息税务、分行业披露注意事项。
  - `report-template.md`：九节报告结构（含路由记录、分歧诊断、估值留痕）。
- `scripts/valuation.py`：全部计算器，只使用 Python 标准库；无效输入一律抛错，不猜测。
- `tests/`：公式手算对照、边界拒绝、路由表一致性、六类案例端到端测试。
- `examples/`：JSON 输入示例（每个模型至少一个）。

## 模型清单

| Payload `model` | 用途 | 折现依据 |
|---|---|---|
| `dcf_fcff` | FCFF-DCF，含企业价值到股权价值桥接 | WACC |
| `ddm` | 股息折现（银行、稳定高股息主模型） | Ke |
| `fcfe` | 股权自由现金流折现 | Ke |
| `residual_income` | 剩余收益 / PB-ROE（银行、保险交叉验证） | Ke |
| `pev` | 保险 P/EV | 可比倍数（禁止用现价反解充当验证） |
| `nav` | 资产净值 / 重估（房地产、资产持有型），支持压力情景 | 资产市值 |
| `affo` | REITs AFFO 估值 | 资本化率或可比倍数（二选一） |
| `normalize_cycle` | 中周期正常化（周期股前置步骤） | — |
| `dcf_sensitivity` / `ddm_sensitivity` | 敏感性矩阵 | 变动参数 |
| `route` | 按公司类型查默认路由 | — |

## 测试

```bash
python -m unittest discover -s tests -v
```

## 运行示例

```bash
python scripts/valuation.py examples/ddm-example.json
python scripts/valuation.py examples/dcf-example.json
python scripts/valuation.py examples/fcfe-example.json
python scripts/valuation.py examples/ri-example.json
python scripts/valuation.py examples/pev-example.json
python scripts/valuation.py examples/nav-example.json
python scripts/valuation.py examples/affo-example.json
python scripts/valuation.py examples/route-example.json
```

输入数值必须使用一致的货币和单位。例如现金流以"百万元"为单位、股数以"百万股"为单位，则输出每股价值为相应货币/股。

## 数据边界

本 Skill 不含实时行情或财务数据 API。运行时应使用 WorkBuddy 已有的数据工具和官方公告来源（CNINFO、上交所、深交所、HKEXnews）；计算脚本只负责可复核的数学运算，不会自动抓取数据，也不会在输入缺失时编造数值。

## 历史

由 `cn-hk-dcf-ddm`（FCFF-DCF + DDM）扩展而来：保留原四个模型与全部测试，新增 FCFE、剩余收益、P/EV、NAV、AFFO、正常化与路由表；参考文档重组为入口 + 路由 + 三个按需模型模块。
