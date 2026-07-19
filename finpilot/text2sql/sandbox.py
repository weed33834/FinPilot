# -*- coding: utf-8 -*-
"""
SQL 安全沙箱
- 基于 sqlglot AST 解析校验 SQL 合法性
- 拒绝多语句 / 写操作 / 危险函数 / 非白名单表
- 提供 LIMIT 注入与租户过滤注入
"""
import sqlglot
from sqlglot import exp
from sqlglot import errors as sqlglot_errors

# 危险函数黑名单（大小写不敏感匹配）
_DANGEROUS_FUNCS = {"sleep", "pg_sleep", "benchmark", "xp_cmdshell"}

# 危险语句类型：写操作与 DDL
_DANGEROUS_STMT_TYPES = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Create,
    exp.Alter,
)


class SQLSandbox:
    """SQL 安全沙箱：解析 AST 后逐项校验"""

    def __init__(self, allowed_tables: list[str]) -> None:
        # 表名白名单统一转小写，匹配时大小写不敏感
        self.allowed_tables = {t.lower() for t in allowed_tables}

    def validate(self, sql: str) -> tuple[bool, str]:
        """校验 SQL 合法性，返回 (是否合法, 原因)"""
        if not sql or not sql.strip():
            return False, "空SQL"

        # 1. 解析全部语句：多条即拒绝（防止分号拼接注入）
        try:
            statements = sqlglot.parse(sql)
        except sqlglot_errors.ParseError as exc:  # 语法错误属于可预期的校验失败
            return False, f"SQL解析失败: {exc}"

        statements = [s for s in statements if s is not None]
        if len(statements) > 1:
            return False, "拒绝多语句"
        if not statements:
            return False, "空SQL"

        tree = statements[0]

        # 2. 拒绝写操作与 DDL（INSERT/UPDATE/DELETE/DROP/CREATE/ALTER）
        if isinstance(tree, _DANGEROUS_STMT_TYPES):
            return False, f"禁止的语句类型: {type(tree).__name__}"

        # 3. 只允许 SELECT（TRUNCATE 等非 SELECT 语句落在此分支被拒）
        if not isinstance(tree, exp.Select):
            return False, f"只允许SELECT语句, 当前: {type(tree).__name__}"

        # 4. 拒绝危险函数
        for func in tree.find_all(exp.Anonymous):
            if func.name and func.name.lower() in _DANGEROUS_FUNCS:
                return False, f"禁止的危险函数: {func.name}"

        # 5. 表名必须在白名单内
        for table in tree.find_all(exp.Table):
            if table.name.lower() not in self.allowed_tables:
                return False, f"表不在白名单内: {table.name}"

        return True, "校验通过"

    def prepare(self, sql: str, max_rows: int = 100) -> str:
        """校验通过后注入 LIMIT，返回可执行 SQL；已存在 LIMIT 则保留"""
        ok, reason = self.validate(sql)
        if not ok:
            raise ValueError(f"SQL校验失败: {reason}")

        tree = sqlglot.parse_one(sql)
        # 仅在无 LIMIT 时注入，避免重复
        if tree.args.get("limit") is None:
            tree = tree.limit(max_rows)
        return tree.sql()

    def inject_tenant_filter(self, sql: str, tenant_id: str) -> str:
        """注入租户过滤条件 financial_reports.tenant_id = tenant_id

        注：当前 financial_reports 表无 tenant_id 列，此处按多租户扩展约定注入。
        实际启用需为 financial_reports 增加 tenant_id 列；默认 execute 流程不调用此方法。
        """
        ok, reason = self.validate(sql)
        if not ok:
            raise ValueError(f"SQL校验失败: {reason}")

        tree = sqlglot.parse_one(sql)
        # 构造 tenant_id 等值条件，作用于 financial_reports 表
        cond = exp.EQ(
            this=exp.column("tenant_id", table="financial_reports"),
            expression=exp.Literal.string(tenant_id),
        )
        # where() 默认 append=True，已有 WHERE 时以 AND 合并
        tree = tree.where(cond)
        return tree.sql()
