"""FinPilot 内置演示数据集与极限测试用例。

本包提供：
1. **模拟企业财务数据集**：覆盖 5 类企业形态（初创 / 成长 / 成熟 / 衰退 / 舞弊），
   3 个行业（制造 / 零售 / 科技），共 15 家虚拟公司的年度财务报表 + 月度数据 + 凭证。
2. **20 个极限测试 case**：覆盖数据校验 / 风险预警 / Agent 鲁棒性 / 多智能体辩论 /
   可解释 AI / 权限越权 / SQL 性能 / 数据隔离 等企业级场景。

用法::

    from finpilot.demo import (
        list_companies, get_company, list_test_cases, run_test_case,
    )

所有数据均为虚构，仅用于演示与测试。
"""
from finpilot.demo.datasets import (
    get_company,
    list_companies,
    list_industries,
    list_stages,
)
from finpilot.demo.test_cases import (
    TEST_CASES,
    TestCase,
    TestCaseResult,
    get_test_case,
    list_test_cases,
    run_all_test_cases,
    run_test_case,
    run_test_case_by_id,
)

__all__ = [
    "TEST_CASES",
    "TestCase",
    "TestCaseResult",
    "get_company",
    "get_test_case",
    "list_companies",
    "list_industries",
    "list_stages",
    "list_test_cases",
    "run_all_test_cases",
    "run_test_case",
    "run_test_case_by_id",
]
