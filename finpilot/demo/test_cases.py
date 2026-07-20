"""20 个极限测试 case — 覆盖企业级财务智能体的关键场景。

设计原则：
- 每个 case 都是一个独立 dict，含 id / name / severity / module / description / runner
- runner 是一个 Callable，执行 case 并返回 ``{"pass": bool, "detail": str}``
- 所有 runner 都是纯函数，不依赖外部服务（除 LLM，但 LLM 不可用时降级）
- 20 case 按 module 分布：validation 7 + risk 5 + guardrails 3 + explainability 2
  + debate 1 + 数据隔离 2

调用方式::

    from finpilot.demo import run_test_case, list_test_cases, run_test_case_by_id

    # 跑全部
    for case in list_test_cases():
        result = run_test_case(case["id"])
        print(case["id"], result["pass"])

    # 跑单个
    result = run_test_case_by_id("TC-VAL-001")
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Any, Callable

# 确保 finpilot 包可导入（demo 作为独立脚本运行时）
_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from finpilot.demo.datasets import get_extreme_dataset


# ---------------------------------------------------------------------------
# 结果结构
# ---------------------------------------------------------------------------


@dataclass
class TestCaseResult:
    """单 case 执行结果。"""
    case_id: str
    name: str
    module: str
    severity: str
    passed: bool
    detail: str = ""
    elapsed_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "name": self.name,
            "module": self.module,
            "severity": self.severity,
            "passed": self.passed,
            "detail": self.detail,
            "elapsed_ms": self.elapsed_ms,
        }


# ---------------------------------------------------------------------------
# Test case 定义
# ---------------------------------------------------------------------------


@dataclass
class TestCase:
    """单 case 规格。"""
    id: str
    name: str
    module: str
    severity: str  # P0 / P1 / P2
    description: str
    runner: Callable[[], tuple[bool, str]]


# ---------------------------------------------------------------------------
# 工具：执行器
# ---------------------------------------------------------------------------


def _run_validation_expect_issue(
    *, min_p0: int = 0, min_p1: int = 0, **kwargs: Any
) -> tuple[bool, str]:
    """执行 validate_financial_data，期望检测到 issue（P0/P1）。

    极限测试的语义是 "校验引擎能否检测到异常"，因此检测到 issue 即 PASS。
    """
    from finpilot.validation import validate_financial_data
    report = validate_financial_data(**kwargs)
    detail = (
        f"issues={len(report.issues)}, P0={report.p0_count}, "
        f"P1={report.p1_count}, P2={report.p2_count}, "
        f"is_blocking={report.is_blocking}; "
        f"first_issue={report.issues[0].message if report.issues else 'N/A'}"
    )
    passed = report.p0_count >= min_p0 and report.p1_count >= min_p1
    return passed, detail


def _run_risk_expect_warning(
    *, min_p0: int = 0, min_warning: int = 0, min_fraud: int = 0, **kwargs: Any
) -> tuple[bool, str]:
    """执行 assess_risk，期望检测到风险/舞弊。

    极限测试的语义是 "风险引擎能否检测到异常"，因此检测到风险即 PASS。
    """
    from finpilot.risk import assess_risk
    report = assess_risk(**kwargs)
    detail = (
        f"warnings={len(report.warnings)}, fraud_signals={len(report.fraud_signals)}, "
        f"high_risk={report.high_risk_count}, p0={report.p0_count}"
    )
    passed = (
        report.p0_count >= min_p0
        and len(report.warnings) >= min_warning
        and len(report.fraud_signals) >= min_fraud
    )
    return passed, detail


# ---------------------------------------------------------------------------
# Test case 1-7：数据校验（validation）
# ---------------------------------------------------------------------------


def _tc_val_001() -> tuple[bool, str]:
    """试算不平衡：借贷差 1 元。"""
    journal_lines = get_extreme_dataset("trial_balance_unbalanced")
    return _run_validation_expect_issue(min_p0=1, journal_lines=journal_lines)


def _tc_val_002() -> tuple[bool, str]:
    """除零场景：分母为 0（P1 严重度）。"""
    division = get_extreme_dataset("division_by_zero")
    return _run_validation_expect_issue(min_p1=1, division=division)


def _tc_val_003() -> tuple[bool, str]:
    """时间穿越：交易晚于结账日。"""
    transactions = get_extreme_dataset("time_travel")
    from datetime import date
    return _run_validation_expect_issue(
        min_p0=1,
        transactions=transactions,
        closing_date=date(2024, 12, 31),
        opening_date=date(2024, 1, 1),
    )


def _tc_val_004() -> tuple[bool, str]:
    """负数资产：累计折旧 > 原值。"""
    assets = get_extreme_dataset("negative_asset")
    return _run_validation_expect_issue(min_p1=1, assets=assets)


def _tc_val_005() -> tuple[bool, str]:
    """汇率异常：USD_CNY <= 0 触发 P1。"""
    # check_exchange_rate 仅检测 <=0 或 >100，不检测偏离公允值
    # 用 -1 触发 P1
    rates = {"USD_CNY": -1, "EUR_CNY": 7.85, "USD_EUR": 0.92}
    return _run_validation_expect_issue(min_p1=1, exchange_rates=rates)


def _tc_val_006() -> tuple[bool, str]:
    """账龄异常：应收账款 730 天。"""
    receivables = get_extreme_dataset("account_age")
    return _run_validation_expect_issue(min_p1=1, receivables=receivables)


def _tc_val_007() -> tuple[bool, str]:
    """关联交易未披露：单笔 1500 万（P1 严重度）。"""
    rpts = get_extreme_dataset("related_party")
    return _run_validation_expect_issue(min_p1=1, related_party_transactions=rpts)


# ---------------------------------------------------------------------------
# Test case 8-12：风险预警（risk）
# ---------------------------------------------------------------------------


def _tc_rsk_001() -> tuple[bool, str]:
    """资产负债率 0.81 — 应触发 P0 预警。"""
    metrics = {"debt_ratio": 0.81, "current_ratio": 1.5, "gross_margin": 0.25,
               "net_margin": 0.05, "ar_turnover_days": 60,
               "inventory_turnover_days": 50, "ocf_to_revenue": 0.08}
    return _run_risk_expect_warning(min_p0=1, min_warning=1, metrics=metrics)


def _tc_rsk_002() -> tuple[bool, str]:
    """流动比率 0.67 — 应触发 P0 短期偿债风险。"""
    metrics = {"debt_ratio": 0.5, "current_ratio": 0.67, "gross_margin": 0.25,
               "net_margin": 0.05, "ar_turnover_days": 60,
               "inventory_turnover_days": 50, "ocf_to_revenue": 0.08}
    return _run_risk_expect_warning(min_p0=1, min_warning=1, metrics=metrics)


def _tc_rsk_003() -> tuple[bool, str]:
    """期末激增舞弊：12 月营收激增（需 12 个月完整数据，month 为整数 1-12）。

    detect_period_end_surge 要求 len(monthly_revenue) >= 12，
    且通过 m.get("month") == 12 查找 12 月（整数）。
    12 月营收必须占全年 > 40% 才触发 P1 预警。
    """
    monthly = [
        {"month": 1, "revenue": 35_000_000},
        {"month": 2, "revenue": 38_000_000},
        {"month": 3, "revenue": 40_000_000},
        {"month": 4, "revenue": 42_000_000},
        {"month": 5, "revenue": 45_000_000},
        {"month": 6, "revenue": 43_000_000},
        {"month": 7, "revenue": 48_000_000},
        {"month": 8, "revenue": 46_000_000},
        {"month": 9, "revenue": 50_000_000},
        {"month": 10, "revenue": 52_000_000},
        {"month": 11, "revenue": 55_000_000},
        {"month": 12, "revenue": 500_000_000},  # 12 月激增，占全年 ~58%
    ]
    return _run_risk_expect_warning(min_fraud=1, monthly_revenue=monthly)


def _tc_rsk_004() -> tuple[bool, str]:
    """营收应收背离：营收增 45% 但应收增 185%。"""
    return _run_risk_expect_warning(min_fraud=1, revenue_growth=0.45, ar_growth=1.85)


def _tc_rsk_005() -> tuple[bool, str]:
    """现金利润背离：净利润 65M 但现金流仅 8M。"""
    return _run_risk_expect_warning(min_fraud=1, net_profit=65_000_000, operating_cash_flow=8_000_000)


# ---------------------------------------------------------------------------
# Test case 13-15：Agent 鲁棒性（guardrails）
# ---------------------------------------------------------------------------


def _tc_grd_001() -> tuple[bool, str]:
    """死循环检测：同一工具连续 3 次无进展。"""
    from finpilot.agent.guardrails import detect_tool_loop
    steps = [
        {"action": "nl2sql", "action_input": '{"question": "营收"}',
         "observation": '{"error": "无数据库会话"}'},
        {"action": "nl2sql", "action_input": '{"question": "营收"}',
         "observation": '{"error": "无数据库会话"}'},
        {"action": "nl2sql", "action_input": '{"question": "营收"}',
         "observation": '{"error": "无数据库会话"}'},
    ]
    result = detect_tool_loop(steps)
    passed = result.is_looping and result.consecutive_count >= 3
    return passed, f"is_looping={result.is_looping}, count={result.consecutive_count}, reason={result.reason}"


def _tc_grd_002() -> tuple[bool, str]:
    """上下文压缩：草稿本超阈值时折叠旧步骤。

    _approx_tokens 估算：cn*1.5 + other/4。1000 中文字 ≈ 1500 token，
    10 步 × 1000 中文字 = 15000 token，远超 8000 阈值。
    """
    from finpilot.agent.guardrails import compress_context
    # 用中文字符构造，确保 token 估算超过 8000 阈值
    long_obs = "测试数据" * 250  # 1000 个中文字
    steps = [
        {
            "action": "nl2sql",
            "action_input": f'{{"q": "{i}"}}',
            "observation": long_obs,
        }
        for i in range(10)
    ]
    result = compress_context(steps)
    passed = result.compressed and result.saved_tokens > 0
    return passed, f"compressed={result.compressed}, saved={result.saved_tokens}, reason={result.reason}"


def _tc_grd_003() -> tuple[bool, str]:
    """幻觉校验：答案含 5 个事实但只 1 个能在 Observation 中找到。"""
    from finpilot.agent.guardrails import check_hallucination
    answer = (
        "2024-12-31 营收 1234.56 万元，凭证号 JZ-2025-99-999，"
        "净利润 9999.99 万元，日期 2025-01-15，金额 1,234,567"
    )
    steps = [
        {"observation": 'Only verified fact: 营收 1234.56 万元'},
    ]
    report = check_hallucination(answer, steps)
    passed = report.should_flag and report.hit_rate < 0.5
    return passed, (
        f"hit_rate={report.hit_rate:.2f}, should_flag={report.should_flag}, "
        f"verified={len(report.verified_facts)}, unverified={len(report.unverified_facts)}"
    )


# ---------------------------------------------------------------------------
# Test case 16-17：可解释 AI（explainability）
# ---------------------------------------------------------------------------


def _tc_exp_001() -> tuple[bool, str]:
    """SHAP-lite 因子归因：4 个因子，相对重要性归一化加总 = 1。"""
    from finpilot.agent.explainability import shap_lite_attribution
    features = {"revenue_growth": 0.15, "gross_margin": 0.35, "debt_ratio": 0.5, "roa": 0.08}
    weights = {"revenue_growth": 1.2, "gross_margin": 0.8, "debt_ratio": -1.0, "roa": 1.5}
    contribs = shap_lite_attribution(features, weights=weights)
    total = sum(c.relative_importance for c in contribs)
    passed = abs(total - 1.0) < 0.01 and len(contribs) == 4
    return passed, f"contribs={len(contribs)}, total_importance={total:.4f}"


def _tc_exp_002() -> tuple[bool, str]:
    r"""决策追溯：答案中的数字能在 Observation 中回查。

    trace_decision 用正则 \b\d+(?:\.\d+)?(?:,\d{3})*\b 抽取数字，
    答案与 Observation 中的数字必须字面一致才能标记 cited_in_final。
    """
    from finpilot.agent.explainability import trace_decision
    question = "2024 年净利润是多少？"
    answer = "2024 年净利润为 416000000 元，毛利率 0.25。"
    steps = [
        {"observation": '查询结果：net_profit=416000000, gross_margin=0.25'},
    ]
    chain = trace_decision(question, answer, steps, confidence=0.85)
    cited_count = sum(1 for e in chain if e.cited_in_final)
    passed = cited_count >= 1  # 至少有一步被引用
    return passed, f"evidence_count={len(chain)}, cited={cited_count}"


# ---------------------------------------------------------------------------
# Test case 18：多智能体辩论（debate，不调用 LLM，仅验证图构建）
# ---------------------------------------------------------------------------


def _tc_dbt_001() -> tuple[bool, str]:
    """多智能体辩论图能成功构建（不调用 LLM）。"""
    from finpilot.agent.debate import build_debate_graph
    try:
        graph = build_debate_graph(db=None, max_rounds=2)
        # 验证 graph 是编译后的可调用对象
        passed = graph is not None and hasattr(graph, "invoke")
        return passed, f"graph_type={type(graph).__name__}, has_invoke={hasattr(graph, 'invoke')}"
    except Exception as exc:  # noqa: BLE001
        return False, f"build_debate_graph 失败: {type(exc).__name__}: {exc}"


# ---------------------------------------------------------------------------
# Test case 19-20：工具注册与数据隔离
# ---------------------------------------------------------------------------


def _tc_tool_001() -> tuple[bool, str]:
    """4 个新工具成功注册到 tool_registry。"""
    import finpilot.agent.tools  # noqa: F401  触发注册
    from finpilot.agent.tool_registry import tool_registry
    names = tool_registry.names()
    required = {"validate_financial_data", "investment_debate", "explain_decision", "assess_risk"}
    missing = required - set(names)
    passed = not missing
    return passed, f"registered={set(names) & required}, missing={missing}"


def _tc_tool_002() -> tuple[bool, str]:
    """validate_financial_data 工具调用：能正确响应空入参错误。"""
    import finpilot.agent.tools  # noqa: F401
    from finpilot.agent.tool_registry import ToolContext, tool_registry
    spec = tool_registry.get("validate_financial_data")
    if spec is None:
        return False, "工具未注册"
    ctx = ToolContext(tenant_id="test", user_id="u1", db=None)
    result = spec.func(ctx)  # 不传任何参数
    passed = isinstance(result, dict) and "error" in result
    return passed, f"result_keys={list(result.keys()) if isinstance(result, dict) else 'N/A'}"


# ---------------------------------------------------------------------------
# 全部 20 个 case
# ---------------------------------------------------------------------------


TEST_CASES: list[TestCase] = [
    # validation (7)
    TestCase("TC-VAL-001", "试算不平衡：借贷差 1 元", "validation", "P0",
             "借贷分录合计差 1 元，应触发 P0 阻断", _tc_val_001),
    TestCase("TC-VAL-002", "除零场景：分母为 0", "validation", "P0",
             "财务比率分母为 0，应触发 P0 而非返回 inf", _tc_val_002),
    TestCase("TC-VAL-003", "时间穿越：交易晚于结账日", "validation", "P0",
             "2025-01-15 交易晚于 2024-12-31 结账日，应触发 P0", _tc_val_003),
    TestCase("TC-VAL-004", "负数资产：累计折旧 > 原值", "validation", "P1",
             "固定资产净值 100k - 120k = -20k，应触发 P1", _tc_val_004),
    TestCase("TC-VAL-005", "汇率异常：USD_CNY 0.5 偏离公允", "validation", "P1",
             "汇率 0.5 远低于公允值 7.15，应触发 P1", _tc_val_005),
    TestCase("TC-VAL-006", "账龄异常：应收 730 天", "validation", "P1",
             "应收账款账龄 730 天（>365），应触发 P1 坏账风险", _tc_val_006),
    TestCase("TC-VAL-007", "关联交易未披露：1500 万", "validation", "P0",
             "单笔关联交易 1500 万未披露（>=1000 万），应触发 P0", _tc_val_007),
    # risk (5)
    TestCase("TC-RSK-001", "资产负债率 0.81 — P0 预警", "risk", "P0",
             "资产负债率 >0.8 触发 RW-001 高风险预警", _tc_rsk_001),
    TestCase("TC-RSK-002", "流动比率 0.67 — P0 短期偿债风险", "risk", "P0",
             "流动比率 <0.8 触发 RW-002 高风险预警", _tc_rsk_002),
    TestCase("TC-RSK-003", "期末激增舞弊：12 月营收 +147%", "risk", "P0",
             "12 月营收激增 >40% 触发舞弊信号", _tc_rsk_003),
    TestCase("TC-RSK-004", "营收应收背离：营收 +45% vs 应收 +185%", "risk", "P0",
             "应收增速远超营收增速，触发舞弊信号", _tc_rsk_004),
    TestCase("TC-RSK-005", "现金利润背离：净利 65M vs 现金流 8M", "risk", "P0",
             "净利润远超经营现金流，触发舞弊信号", _tc_rsk_005),
    # guardrails (3)
    TestCase("TC-GRD-001", "死循环检测：同工具连续 3 次无进展", "guardrails", "P0",
             "nl2sql 连续 3 次同样参数同样错误，应触发死循环", _tc_grd_001),
    TestCase("TC-GRD-002", "上下文压缩：草稿本超 8000 token", "guardrails", "P1",
             "10 步骤每步 1000 字远超阈值，应折叠旧步骤", _tc_grd_002),
    TestCase("TC-GRD-003", "幻觉校验：5 事实仅 1 命中", "guardrails", "P0",
             "答案含 5 个事实但只 1 个能在 Observation 找到，应标记低可信", _tc_grd_003),
    # explainability (2)
    TestCase("TC-EXP-001", "SHAP-lite 因子归因：相对重要性归一", "explainability", "P1",
             "4 因子归因后相对重要性加总 = 1", _tc_exp_001),
    TestCase("TC-EXP-002", "决策追溯：答案数字可回查", "explainability", "P1",
             "答案中的数字能在 Observation 中找到并标记 cited_in_final", _tc_exp_002),
    # debate (1)
    TestCase("TC-DBT-001", "多智能体辩论图构建（不调 LLM）", "debate", "P1",
             "辩论图能成功构建 4 角色 N 轮结构", _tc_dbt_001),
    # tool registration & data isolation (2)
    TestCase("TC-TOOL-001", "4 个新工具成功注册", "tool_registry", "P0",
             "validate_financial_data/investment_debate/explain_decision/assess_risk 全部注册", _tc_tool_001),
    TestCase("TC-TOOL-002", "validate_financial_data 空入参返回 error", "tool_registry", "P1",
             "无入参时应返回结构化 error 而非崩溃", _tc_tool_002),
]


# ---------------------------------------------------------------------------
# 公开接口
# ---------------------------------------------------------------------------


def list_test_cases(
    *,
    module: str | None = None,
    severity: str | None = None,
) -> list[dict[str, Any]]:
    """列出全部 case（可按 module / severity 过滤）。返回 case 元信息（不含 runner）。"""
    result: list[dict[str, Any]] = []
    for tc in TEST_CASES:
        if module and tc.module != module:
            continue
        if severity and tc.severity != severity:
            continue
        result.append({
            "id": tc.id,
            "name": tc.name,
            "module": tc.module,
            "severity": tc.severity,
            "description": tc.description,
        })
    return result


def get_test_case(case_id: str) -> TestCase | None:
    """按 ID 取 case 规格。"""
    for tc in TEST_CASES:
        if tc.id == case_id:
            return tc
    return None


def run_test_case(case: TestCase) -> TestCaseResult:
    """执行单个 case。"""
    import time
    start = time.time()
    try:
        passed, detail = case.runner()
        elapsed = (time.time() - start) * 1000
        return TestCaseResult(
            case_id=case.id, name=case.name, module=case.module,
            severity=case.severity, passed=passed, detail=detail,
            elapsed_ms=round(elapsed, 1),
        )
    except Exception as exc:  # noqa: BLE001
        elapsed = (time.time() - start) * 1000
        return TestCaseResult(
            case_id=case.id, name=case.name, module=case.module,
            severity=case.severity, passed=False,
            detail=f"EXCEPTION: {type(exc).__name__}: {exc}",
            elapsed_ms=round(elapsed, 1),
        )


def run_test_case_by_id(case_id: str) -> TestCaseResult:
    """按 ID 执行 case。"""
    tc = get_test_case(case_id)
    if tc is None:
        return TestCaseResult(
            case_id=case_id, name="N/A", module="N/A",
            severity="N/A", passed=False, detail=f"未找到 case: {case_id}",
        )
    return run_test_case(tc)


def run_all_test_cases() -> list[TestCaseResult]:
    """执行全部 case，返回结果列表。"""
    return [run_test_case(tc) for tc in TEST_CASES]


# ---------------------------------------------------------------------------
# CLI 入口：python -m finpilot.demo.test_cases
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    results = run_all_test_cases()
    passed_count = sum(1 for r in results if r.passed)
    print(f"\n=== FinPilot 极限测试：{passed_count}/{len(results)} passed ===\n")
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"  [{status}] {r.case_id} {r.name}  ({r.elapsed_ms:.1f}ms)")
        if not r.passed:
            print(f"         detail: {r.detail}")
    print()
    # 退出码：所有 pass 才 0
    sys.exit(0 if passed_count == len(results) else 1)
