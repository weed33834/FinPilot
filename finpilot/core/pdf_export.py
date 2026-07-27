# -*- coding: utf-8 -*-
"""报表 PDF 导出 — reportlab 生成资产负债表/利润表/现金流量表 PDF + 三表联动投影多页 PDF。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle


def _make_table(data: list[list], header_color: str = "#1a237e") -> Table:
    style = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(header_color)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ])
    table = Table(data, colWidths=[80 * mm, 55 * mm])
    table.setStyle(style)
    return table


def _make_data_table(
    data: list[list],
    header_color: str = "#1a237e",
    num_cols: int = 0,
    font_size: int = 8,
) -> Table:
    """多列表格渲染器，自动按 A4 可用宽度均分列宽。"""
    n = num_cols or (len(data[0]) if data else 2)
    usable_width = 170 * mm  # A4 宽 210 mm − 左右边距各 20 mm
    col_width = usable_width / n
    widths = [col_width] * n

    style = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(header_color)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), font_size),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ])
    table = Table(data, colWidths=widths)
    table.setStyle(style)
    return table


# ---------------------------------------------------------------------------
# 原有三表 PDF（保留兼容）
# ---------------------------------------------------------------------------


def export_balance_sheet(bs, output_path: str) -> str:
    doc = SimpleDocTemplate(output_path, pagesize=A4, leftMargin=20*mm, rightMargin=20*mm, topMargin=15*mm)
    styles = getSampleStyleSheet()
    story = [
        Paragraph("Balance Sheet", styles["Title"]),
        Paragraph(f"As of: {bs.period_end.strftime('%Y-%m-%d') if hasattr(bs, 'period_end') else 'N/A'}", styles["Normal"]),
        Spacer(1, 8 * mm),
    ]
    items = [
        ("Current Assets", bs.current_assets if bs else 0),
        ("Non-Current Assets", bs.non_current_assets if bs else 0),
        ("Total Assets", bs.total_assets if bs else 0),
        ("Current Liabilities", bs.current_liabilities if bs else 0),
        ("Non-Current Liabilities", bs.non_current_liabilities if bs else 0),
        ("Total Liabilities", bs.total_liabilities if bs else 0),
        ("Total Equity", bs.total_equity if bs else 0),
        ("Retained Earnings", bs.retained_earnings if bs else 0),
    ]
    data = [["Item", "Amount"]]
    for name, val in items:
        data.append([name, f"{val:,.2f}"])
    story.append(_make_table(data))
    doc.build(story)
    return output_path


def export_income_statement(ist, output_path: str) -> str:
    doc = SimpleDocTemplate(output_path, pagesize=A4, leftMargin=20*mm, rightMargin=20*mm, topMargin=15*mm)
    styles = getSampleStyleSheet()
    story = [
        Paragraph("Income Statement", styles["Title"]),
        Paragraph(f"Period ending: {ist.period_end.strftime('%Y-%m-%d') if hasattr(ist, 'period_end') else 'N/A'}", styles["Normal"]),
        Spacer(1, 8 * mm),
    ]
    items = [
        ("Revenue", ist.revenue if ist else 0),
        ("Operating Cost", ist.operating_cost if ist else 0),
        ("Gross Profit", ist.gross_profit if ist else 0),
        ("Operating Expenses", ist.operating_expenses if ist else 0),
        ("Operating Income", ist.operating_income if ist else 0),
        ("Net Income", ist.net_income if ist else 0),
        ("EPS", ist.eps if ist else 0),
    ]
    data = [["Item", "Amount"]]
    for name, val in items:
        data.append([name, f"{val:,.2f}"])
    story.append(_make_table(data, "#2e7d32"))
    doc.build(story)
    return output_path


def export_cash_flow(cfs, output_path: str) -> str:
    doc = SimpleDocTemplate(output_path, pagesize=A4, leftMargin=20*mm, rightMargin=20*mm, topMargin=15*mm)
    styles = getSampleStyleSheet()
    story = [
        Paragraph("Cash Flow Statement", styles["Title"]),
        Paragraph(f"Period ending: {cfs.period_end.strftime('%Y-%m-%d') if hasattr(cfs, 'period_end') else 'N/A'}", styles["Normal"]),
        Spacer(1, 8 * mm),
    ]
    items = [
        ("Operating Activities", cfs.operating_activities if cfs else 0),
        ("Investing Activities", cfs.investing_activities if cfs else 0),
        ("Financing Activities", cfs.financing_activities if cfs else 0),
        ("Net Cash Change", cfs.net_cash_change if cfs else 0),
        ("Beginning Cash", cfs.beginning_cash if cfs else 0),
        ("Ending Cash", cfs.ending_cash if cfs else 0),
    ]
    data = [["Item", "Amount"]]
    for name, val in items:
        data.append([name, f"{val:,.2f}"])
    story.append(_make_table(data, "#e65100"))
    doc.build(story)
    return output_path


# ---------------------------------------------------------------------------
# P1-8 三表联动投影 PDF 导出
# ---------------------------------------------------------------------------


def _fmt(value: Any) -> str:
    """安全格式化数值 → 千分位整数字符串。"""
    if value is None:
        return "—"
    try:
        return f"{float(value):,.0f}"
    except (TypeError, ValueError):
        return str(value)


def export_projection_pdf(
    is_df: list[dict],
    bs_df: list[dict],
    cf_df: list[dict],
    output_path: str,
    company_name: str = "FinPilot Corp",
) -> str:
    """将三表联动投影结果渲染为格式化多页 PDF。

    参数
    ----
    is_df : 收入表投影记录列表（dict keys: period, revenue, cogs, gross_profit,
            operating_expenses, operating_income, tax_expense, net_income）
    bs_df : 资产负债表投影记录列表（dict keys: period, total_assets, current_assets,
            non_current_assets, total_liabilities, current_liabilities,
            non_current_liabilities, total_equity, retained_earnings）
    cf_df : 现金流量表投影记录列表（dict keys: period, operating_cf, investing_cf,
            financing_cf, net_change_in_cash, ending_cash）
    output_path : 输出 PDF 文件路径
    company_name : 页眉公司名称

    返回
    ----
    output_path
    """
    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm, topMargin=15 * mm,
    )
    styles = getSampleStyleSheet()
    story: list = []
    today_str = datetime.now().strftime("%Y-%m-%d")

    # ── 全局标题 ──
    story.append(Paragraph("Financial Projection Report", styles["Title"]))
    story.append(Paragraph(f"{company_name}  |  {today_str}", styles["Normal"]))
    story.append(Spacer(1, 5 * mm))

    # ── 第 1 页：收入表 (Income Statement) ──
    story.append(Paragraph("Income Statement", styles["Heading2"]))
    story.append(Spacer(1, 3 * mm))

    is_headers = [
        "Period", "Revenue", "COGS", "Gross Profit",
        "OpEx", "Operating Income", "Tax", "Net Income",
    ]
    is_data: list[list] = [is_headers]
    for row in is_df:
        is_data.append([
            str(row.get("period", "")),
            _fmt(row.get("revenue")),
            _fmt(row.get("cogs")),
            _fmt(row.get("gross_profit")),
            _fmt(row.get("operating_expenses")),
            _fmt(row.get("operating_income")),
            _fmt(row.get("tax_expense")),
            _fmt(row.get("net_income")),
        ])
    story.append(_make_data_table(is_data, "#1a237e"))
    story.append(Spacer(1, 8 * mm))

    # ── 第 2 页：资产负债表 (Balance Sheet) ──
    story.append(Paragraph("Balance Sheet", styles["Heading2"]))
    story.append(Spacer(1, 3 * mm))

    bs_headers = [
        "Period", "Total Assets", "Current Assets", "Non-current Assets",
        "Total Liabilities", "Current Liabilities", "Non-current Liabilities",
        "Total Equity", "Retained Earnings",
    ]
    bs_data: list[list] = [bs_headers]
    for row in bs_df:
        bs_data.append([
            str(row.get("period", "")),
            _fmt(row.get("total_assets")),
            _fmt(row.get("current_assets")),
            _fmt(row.get("non_current_assets")),
            _fmt(row.get("total_liabilities")),
            _fmt(row.get("current_liabilities")),
            _fmt(row.get("non_current_liabilities")),
            _fmt(row.get("total_equity")),
            _fmt(row.get("retained_earnings")),
        ])
    story.append(_make_data_table(bs_data, "#2e7d32"))
    story.append(Spacer(1, 8 * mm))

    # ── 第 3 页：现金流量表 (Cash Flow Statement) ──
    story.append(Paragraph("Cash Flow Statement", styles["Heading2"]))
    story.append(Spacer(1, 3 * mm))

    cf_headers = [
        "Period", "Operating CF", "Investing CF", "Financing CF",
        "Net Change in Cash", "Ending Cash",
    ]
    cf_data: list[list] = [cf_headers]
    for row in cf_df:
        cf_data.append([
            str(row.get("period", "")),
            _fmt(row.get("operating_cf")),
            _fmt(row.get("investing_cf")),
            _fmt(row.get("financing_cf")),
            _fmt(row.get("net_change_in_cash")),
            _fmt(row.get("ending_cash")),
        ])
    story.append(_make_data_table(cf_data, "#e65100"))

    doc.build(story)
    return output_path
