# -*- coding: utf-8 -*-
"""研报路由 — 前端 ReportsPage 契约 + FinPilot equity 研报管线.

前端契约（``frontend/src/types/report.ts``）：
- GET    /                  → {code, message, data: {total, page, page_size, items: Report[]}}
- POST   /                  → {code, message, data: Report}  （创建并异步生成）
- GET    /{id}              → {code, message, data: Report}
- POST   /{id}/export       → {code, message, data: {content_url}}

FinPilot equity 研报管线（保留兼容，前端不直接调用）：
- POST   /generate          → {task_id, status: "pending"}
- GET    /equity/{task_id}  → 研报详情
- GET    /equity/{task_id}/html → 研报 HTML
"""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from finpilot.api.deps import get_current_user, get_db_session
from finpilot.database.models import Report as ReportORM

from .schemas import ReportRequest as ReportRequestSchema

router = APIRouter(prefix="/reports", tags=["reports"])

# FinPilot equity 路径（基于本文件位置推算）
_FINPILOT_ROOT = Path(__file__).resolve().parents[2]
_CORE_DIR = _FINPILOT_ROOT / "finpilot_equity" / "core"
_SRC_DIR = _CORE_DIR / "src"
_OUTPUT_DIR = _CORE_DIR / "output"
_CONFIG_DIR = _CORE_DIR / "config"


# ---------------------------------------------------------------------------
# 响应包装 & 序列化
# ---------------------------------------------------------------------------


def _ok(data: Any, message: str = "ok") -> dict[str, Any]:
    return {"code": 0, "message": message, "data": data}


def _report_to_dict(r: ReportORM) -> dict[str, Any]:
    """ORM → dict（与前端 Report 接口对齐）."""
    return {
        "id": str(r.id),
        "title": r.title,
        "report_type": r.report_type,
        "status": r.status,
        "parameters": r.parameters or {},
        "content": r.content,
        "content_url": r.content_url,
        "summary": r.summary,
        "error_message": r.error_message,
        "template_id": str(r.template_id) if r.template_id is not None else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


# ---------------------------------------------------------------------------
# 前端契约路由
# ---------------------------------------------------------------------------


@router.get("")
def list_reports(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """列出当前用户的研报（分页，按创建时间倒序）."""
    tenant_id = str(current_user.get("user_id", "default"))
    query = db.query(ReportORM).filter(ReportORM.tenant_id == tenant_id)
    total = query.count()
    items = (
        query.order_by(ReportORM.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return _ok({
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [_report_to_dict(r) for r in items],
    })


@router.post("", status_code=status.HTTP_201_CREATED)
def create_report(
    payload: dict[str, Any],
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """创建研报并异步生成内容.

    payload: {title, report_type, parameters?, template_id?}
    """
    title = (payload.get("title") or "").strip()
    report_type = (payload.get("report_type") or "custom").strip()
    if not title:
        raise HTTPException(status_code=400, detail="title 不能为空")

    tenant_id = str(current_user.get("user_id", "default"))
    report = ReportORM(
        tenant_id=tenant_id,
        created_by=current_user.get("user_id"),
        title=title,
        report_type=report_type,
        parameters=payload.get("parameters") or {},
        template_id=payload.get("template_id"),
        status="processing",
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    # 异步生成报告内容
    background_tasks.add_task(
        _generate_report_content,
        report_id=report.id,
        tenant_id=tenant_id,
    )
    return _ok(_report_to_dict(report), "报告已创建，正在生成")


@router.get("/{report_id}")
def get_report(
    report_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """获取研报详情."""
    tenant_id = str(current_user.get("user_id", "default"))
    try:
        rid = int(report_id)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="研报不存在") from exc
    report = (
        db.query(ReportORM)
        .filter(ReportORM.id == rid, ReportORM.tenant_id == tenant_id)
        .first()
    )
    if not report:
        raise HTTPException(status_code=404, detail="研报不存在")
    return _ok(_report_to_dict(report))


@router.post("/{report_id}/export")
def export_report(
    report_id: str,
    format: str = Query(default="markdown"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """导出研报（生成下载 URL；当前以 data: URI 返回）."""
    tenant_id = str(current_user.get("user_id", "default"))
    try:
        rid = int(report_id)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="研报不存在") from exc
    report = (
        db.query(ReportORM)
        .filter(ReportORM.id == rid, ReportORM.tenant_id == tenant_id)
        .first()
    )
    if not report:
        raise HTTPException(status_code=404, detail="研报不存在")

    # 简化导出：把 content 序列化为 markdown data URI
    import json
    import urllib.parse

    content = report.content or {}
    md_lines = [f"# {report.title}", ""]
    if report.summary:
        md_lines.append(f"**摘要**: {report.summary}")
        md_lines.append("")
    for section in content.get("sections", []):
        md_lines.append(f"## {section.get('name', '')}")
        md_lines.append(f"值: {section.get('value', 'N/A')}")
        md_lines.append("")

    md_text = "\n".join(md_lines)
    encoded = urllib.parse.quote(md_text)
    content_url = f"data:text/markdown;charset=utf-8,{encoded}"

    report.content_url = content_url
    db.commit()
    return _ok({"content_url": content_url, "format": format})


# ---------------------------------------------------------------------------
# 报告生成（后台任务）
# ---------------------------------------------------------------------------

# 指标 → 财务科目类别映射
_METRIC_MAP: dict[str, list[str]] = {
    "revenue": ["营业收入", "营业总收入"],
    "operating_cost": ["营业成本", "营业总成本"],
    "operating_profit": ["营业利润"],
    "net_profit": ["净利润", "归属于母公司股东的净利润"],
    "total_assets": ["资产总计", "总资产"],
    "total_liabilities": ["负债合计", "总负债"],
    "owner_equity": ["所有者权益合计", "股东权益合计"],
    "cash_flow_operating": ["经营活动产生的现金流量净额"],
}


def _generate_report_content(report_id: int, tenant_id: str) -> None:
    """后台生成报告内容：从 FinancialReport/FinancialAccount 聚合数据 + LLM 摘要."""
    from finpilot.database import SessionLocal
    from finpilot.database.models import FinancialAccount, FinancialReport

    db = SessionLocal()
    try:
        report = db.get(ReportORM, report_id)
        if not report:
            return

        try:
            params = report.parameters or {}
            year = params.get("year")
            period = params.get("period", "annual")

            # 取最新一条财务报表作为数据源
            fin_q = db.query(FinancialReport)
            if year:
                fin_q = fin_q.filter(FinancialReport.period.like(f"{year}%"))
            fin_report = fin_q.order_by(FinancialReport.created_at.desc()).first()

            sections: list[dict[str, Any]] = []
            if fin_report:
                accounts = (
                    db.query(FinancialAccount)
                    .filter(FinancialAccount.report_id == fin_report.id)
                    .all()
                )
                acct_by_name = {a.account_name: a.balance for a in accounts}

                for metric, names in _METRIC_MAP.items():
                    value = None
                    for name in names:
                        if name in acct_by_name and acct_by_name[name] is not None:
                            value = float(acct_by_name[name])
                            break
                    if value is not None:
                        sections.append({
                            "name": names[0],
                            "metric": metric,
                            "value": value,
                        })

            period_label = f"{year} {period}" if year else period
            content = {
                "title": report.title,
                "year": year,
                "period": period,
                "period_label": period_label,
                "sections": sections,
                "summary": "",
            }

            # LLM 摘要（demo fallback 会自动接管真实 LLM 不可用时的情况）
            summary = ""
            try:
                from finpilot.llm.client import LLMClient, LLMUnavailableError
                from finpilot.llm.config import get_default_config

                config = get_default_config(db)
                if config:
                    client = LLMClient(config)
                    data_text = "\n".join(
                        f"- {s['name']}: {s['value']}" for s in sections
                    ) or "（无可用财务数据）"
                    summary = client.chat(
                        f"你是财务分析师。请基于以下数据写一段 100 字以内的摘要：\n{data_text}",
                        f"报告类型: {report.report_type}, 期间: {period_label}",
                        max_tokens=200,
                    )
            except LLMUnavailableError:
                summary = "（LLM 不可用，摘要未生成）"
            except Exception:  # noqa: BLE001
                summary = ""

            content["summary"] = summary
            report.content = content
            report.summary = summary
            report.status = "reviewing"
            db.commit()

        except Exception as exc:  # noqa: BLE001
            report.status = "failed"
            report.error_message = str(exc)[:500]
            db.commit()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# FinPilot equity 研报管线（保留兼容）
# ---------------------------------------------------------------------------


def _fp_db():
    """获取 FinPilot equity 数据库会话"""
    from finpilot_equity.web_app.database.connection import SessionLocal as FinPilotSessionLocal

    return FinPilotSessionLocal()


def _run_report_pipeline(task_id: str, ticker: str, company_name: str, peers: list[str]) -> None:
    """后台执行 FinPilot equity 研报生成管线（子进程调用 core 脚本）"""
    from finpilot_equity.web_app.database.crud import update_report_request

    def _set_status(st: str, err: str | None = None) -> None:
        db = _fp_db()
        try:
            update_report_request(db, task_id, st, err)
        finally:
            db.close()

    _set_status("running")

    python_exe = sys.executable
    config_file = _CONFIG_DIR / "config.ini"
    if not config_file.exists():
        config_file = _CONFIG_DIR / "config.ini.example"
    config_arg = ["--config-file", str(config_file)] if config_file.exists() else []

    analysis_dir = _OUTPUT_DIR / ticker / "analysis"
    report_dir = _OUTPUT_DIR / ticker / "report"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    cmd_analysis = [
        python_exe, str(_SRC_DIR / "generate_financial_analysis.py"),
        "--company-ticker", ticker,
        "--company-name", company_name,
        "--years-limit", "5",
        "--output-dir", str(analysis_dir),
        "--generate-text-sections",
    ] + config_arg
    if peers:
        cmd_analysis += ["--peer-tickers"] + peers

    r1 = subprocess.run(
        cmd_analysis, cwd=str(_SRC_DIR), capture_output=True,
        text=True, encoding="utf-8", errors="replace",
    )
    if r1.returncode != 0:
        _set_status("failed", f"财务分析失败: {(r1.stderr or '')[-500:]}")
        return

    cmd_report = [
        python_exe, str(_SRC_DIR / "create_equity_report.py"),
        "--company-ticker", ticker,
        "--company-name", company_name,
        "--analysis-csv", str(analysis_dir / "financial_metrics_and_forecasts.csv"),
        "--ratios-csv", str(analysis_dir / "ratios_raw_data.csv"),
        "--tagline-file", str(analysis_dir / "tagline.txt"),
        "--company-overview-file", str(analysis_dir / "company_overview.txt"),
        "--investment-overview-file", str(analysis_dir / "investment_overview.txt"),
        "--valuation-overview-file", str(analysis_dir / "valuation_overview.txt"),
        "--risks-file", str(analysis_dir / "risks.txt"),
        "--competitor-analysis-file", str(analysis_dir / "competitor_analysis.txt"),
        "--major-takeaways-file", str(analysis_dir / "major_takeaways.txt"),
        "--output-dir", str(report_dir),
        "--enable-text-regeneration",
    ] + config_arg
    if peers:
        cmd_report += [
            "--peer-ebitda-csv", str(analysis_dir / "peer_ebitda_comparison.csv"),
            "--peer-ev-ebitda-csv", str(analysis_dir / "peer_ev_ebitda_comparison.csv"),
        ]

    r2 = subprocess.run(
        cmd_report, cwd=str(_SRC_DIR), capture_output=True,
        text=True, encoding="utf-8", errors="replace",
    )
    if r2.returncode != 0:
        _set_status("failed", f"研报生成失败: {(r2.stderr or '')[-500:]}")
        return

    _set_status("completed")


@router.post("/generate", status_code=status.HTTP_202_ACCEPTED)
def generate_equity_report(
    req: ReportRequestSchema,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    """触发 FinPilot equity 研报生成（异步），返回 task_id"""
    import uuid

    from finpilot_equity.web_app.database import crud as fp_crud

    task_id = str(uuid.uuid4())
    db = _fp_db()
    try:
        fp_crud.create_report_request(
            db,
            user_id=current_user["user_id"],
            task_id=task_id,
            ticker=req.ticker,
            company_name=req.company_name,
            peers=",".join(req.peer_tickers) if req.peer_tickers else None,
        )
    finally:
        db.close()

    background_tasks.add_task(
        _run_report_pipeline, task_id, req.ticker, req.company_name, req.peer_tickers
    )
    return {"task_id": task_id, "status": "pending"}


@router.get("/equity/{task_id}")
def get_equity_report(
    task_id: str,
    current_user: dict = Depends(get_current_user),
):
    """获取 FinPilot equity 研报详情"""
    from finpilot_equity.web_app.database.models import ReportRequest

    db = _fp_db()
    try:
        report = (
            db.query(ReportRequest)
            .filter(ReportRequest.task_id == task_id)
            .first()
        )
    finally:
        db.close()
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="研报不存在")
    return {
        "task_id": report.task_id,
        "ticker": report.ticker,
        "company_name": report.company_name,
        "status": report.status,
        "created_at": report.created_at.isoformat() if report.created_at else None,
        "completed_at": report.completed_at.isoformat() if report.completed_at else None,
        "error_message": report.error_message,
    }


@router.get("/equity/{task_id}/html", response_class=HTMLResponse)
def get_equity_report_html(
    task_id: str,
    current_user: dict = Depends(get_current_user),
):
    """获取 FinPilot equity 研报 HTML 内容"""
    from finpilot_equity.web_app.database.models import ReportRequest

    db = _fp_db()
    try:
        report = (
            db.query(ReportRequest)
            .filter(ReportRequest.task_id == task_id)
            .first()
        )
    finally:
        db.close()
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="研报不存在")

    report_dir = _OUTPUT_DIR / report.ticker / "report"
    html_path = _find_html(report_dir)
    if html_path is None:
        flat = _OUTPUT_DIR / f"{report.ticker}_Equity_Research_Report.html"
        if flat.exists():
            html_path = flat
    if html_path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="研报 HTML 尚未生成")
    return HTMLResponse(content=html_path.read_text(encoding="utf-8", errors="replace"))


def _find_html(directory: Path) -> Path | None:
    """在目录中查找 HTML 文件，优先返回含 Professional 的"""
    if not directory.exists():
        return None
    htmls = sorted(directory.glob("*.html"))
    if not htmls:
        return None
    for h in htmls:
        if "Professional" in h.name:
            return h
    return htmls[0]
