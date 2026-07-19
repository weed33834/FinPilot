"""
示例财务数据初始化 - 创建3张示例财务报表及科目
报表：资产负债表、利润表、现金流量表（科目名称支持中文）
"""
from typing import Optional

from sqlalchemy.orm import Session

from .models import FinancialReport, FinancialAccount

# 科目元组结构：(account_name, account_category, debit_amount, credit_amount, balance)
COMPANY_NAME = "示例科技有限公司"
COMPANY_TICKER = "EXMP"
COMPANY_PERIOD = "2024-FY"

REPORTS_DATA = [
    {
        "report_name": "资产负债表",
        "report_type": "balance_sheet",
        "accounts": [
            # 流动资产
            ("货币资金", "流动资产", 0.0, 0.0, 1250000.00),
            ("应收账款", "流动资产", 0.0, 0.0, 860000.00),
            ("存货", "流动资产", 0.0, 0.0, 540000.00),
            ("预付账款", "流动资产", 0.0, 0.0, 120000.00),
            ("其他应收款", "流动资产", 0.0, 0.0, 90000.00),
            # 非流动资产
            ("固定资产", "非流动资产", 0.0, 0.0, 3200000.00),
            ("无形资产", "非流动资产", 0.0, 0.0, 680000.00),
            ("长期股权投资", "非流动资产", 0.0, 0.0, 450000.00),
            # 流动负债
            ("短期借款", "流动负债", 0.0, 0.0, 500000.00),
            ("应付账款", "流动负债", 0.0, 0.0, 430000.00),
            ("应付职工薪酬", "流动负债", 0.0, 0.0, 180000.00),
            # 非流动负债
            ("长期借款", "非流动负债", 0.0, 0.0, 1500000.00),
            # 所有者权益
            ("实收资本", "所有者权益", 0.0, 0.0, 2000000.00),
            ("资本公积", "所有者权益", 0.0, 0.0, 800000.00),
            ("未分配利润", "所有者权益", 0.0, 0.0, 1780000.00),
        ],
    },
    {
        "report_name": "利润表",
        "report_type": "income_statement",
        "accounts": [
            # 收入
            ("营业收入", "营业收入", 0.0, 8500000.00, 8500000.00),
            # 成本费用
            ("营业成本", "营业成本费用", 5200000.00, 0.0, 5200000.00),
            ("税金及附加", "营业成本费用", 320000.00, 0.0, 320000.00),
            ("销售费用", "营业成本费用", 680000.00, 0.0, 680000.00),
            ("管理费用", "营业成本费用", 750000.00, 0.0, 750000.00),
            ("研发费用", "营业成本费用", 920000.00, 0.0, 920000.00),
            ("财务费用", "营业成本费用", 150000.00, 0.0, 150000.00),
            # 利润小计
            ("营业利润", "利润", 0.0, 0.0, 480000.00),
            ("营业外收入", "营业外收支", 0.0, 50000.00, 50000.00),
            ("营业外支出", "营业外收支", 30000.00, 0.0, 30000.00),
            ("利润总额", "利润", 0.0, 0.0, 500000.00),
            ("所得税费用", "税费", 125000.00, 0.0, 125000.00),
            ("净利润", "利润", 0.0, 0.0, 375000.00),
        ],
    },
    {
        "report_name": "现金流量表",
        "report_type": "cash_flow",
        "accounts": [
            # 经营活动
            ("销售商品提供劳务收到的现金", "经营活动现金流入", 0.0, 9200000.00, 9200000.00),
            ("收到的税费返还", "经营活动现金流入", 0.0, 150000.00, 150000.00),
            ("收到其他与经营活动有关的现金", "经营活动现金流入", 0.0, 80000.00, 80000.00),
            ("购买商品接受劳务支付的现金", "经营活动现金流出", 5800000.00, 0.0, 5800000.00),
            ("支付给职工以及为职工支付的现金", "经营活动现金流出", 1200000.00, 0.0, 1200000.00),
            ("支付的各项税费", "经营活动现金流出", 480000.00, 0.0, 480000.00),
            ("经营活动产生的现金流量净额", "经营活动净额", 0.0, 0.0, 1950000.00),
            # 投资活动
            ("投资活动产生的现金流量净额", "投资活动净额", 0.0, 0.0, -800000.00),
            # 筹资活动
            ("筹资活动产生的现金流量净额", "筹资活动净额", 0.0, 0.0, -500000.00),
            # 现金净增加额
            ("现金及现金等价物净增加额", "现金净增加额", 0.0, 0.0, 650000.00),
            ("期初现金及现金等价物余额", "现金余额", 0.0, 0.0, 600000.00),
            ("期末现金及现金等价物余额", "现金余额", 0.0, 0.0, 1250000.00),
        ],
    },
]


def seed_financial_data(db: Session) -> None:
    """向数据库写入示例财务数据：资产负债表、利润表、现金流量表"""
    # 已存在报表则跳过，避免重复初始化
    if db.query(FinancialReport).count() > 0:
        print("示例财务数据已存在，跳过初始化。")
        return

    for report_cfg in REPORTS_DATA:
        report = FinancialReport(
            report_name=report_cfg["report_name"],
            company_name=COMPANY_NAME,
            ticker=COMPANY_TICKER,
            report_type=report_cfg["report_type"],
            period=COMPANY_PERIOD,
        )
        db.add(report)
        db.flush()  # 拿到 report.id 后再批量挂载科目

        for account_name, category, debit, credit, balance in report_cfg["accounts"]:
            db.add(
                FinancialAccount(
                    report_id=report.id,
                    account_name=account_name,
                    account_category=category,
                    period=COMPANY_PERIOD,
                    debit_amount=debit,
                    credit_amount=credit,
                    balance=balance,
                )
            )

    db.commit()
    print("示例财务数据初始化完成：3 张报表，共 "
          f"{sum(len(r['accounts']) for r in REPORTS_DATA)} 个科目。")


if __name__ == "__main__":
    # 直接运行：先建表再写入示例数据
    from .connection import SessionLocal, init_db

    init_db()
    with SessionLocal() as session:
        seed_financial_data(session)
