# FinPilot 开发与发布质量保障指南

本文档汇总本项目在开发/发布过程中遇到并解决的**已知问题与防范措施**，供克隆后快速上手、避免重复踩坑。

## 1. 本地环境

```bash
python3 -m venv venv && source venv/bin/activate   # Python 3.10–3.13
pip install -e .
cp .env.example .env        # 配置 LLM API Key
uvicorn finpilot.api.router:app --host 0.0.0.0 --port 8001   # 后端
cd frontend && npm install && npm run dev                    # 前端
```

> 依赖说明：`setup.py` 声明 `python_requires=">=3.10, <3.14"`，CI 在 3.10/3.11/3.12/3.13 四版本矩阵上验证。

## 2. 提交前本地验证（防止 CI 红叉）

```bash
# 后端：import 冒烟（能抓出 Python 版本兼容问题，如 datetime.UTC）
python -c "import finpilot.api.router; import finpilot.agent.graph; import finpilot_equity.web_app.main; print('imports ok')"

# 后端：单元测试
pip install pytest
python -m pytest tests/test_react_parser.py -q

# 前端：类型检查 + 构建
cd frontend && npx tsc --noEmit && npm run build
```

CI 工作流（`.github/workflows/ci.yml`）会重复执行以上检查：后端 4 个 Python 版本矩阵 + 前端 tsc/build。

## 3. Python 版本兼容（重点防范）

- **`datetime.UTC` 是 Python 3.11+ 专属 API**。3.10 会 `ImportError`。本项目 10 个文件曾因此全部崩溃。
- 兼容写法（保持 `UTC` 标识符，使用处不动）：
  ```python
  from datetime import datetime
  try:
      from datetime import UTC
  except ImportError:  # Python 3.10 lacks datetime.UTC
      from datetime import timezone
      UTC = timezone.utc
  ```
- 新代码若用到 3.11+ 特性（`tomllib`、`StrEnum`、`datetime.UTC` 等），必须同时提供 3.10 兼容路径，并确认 CI 3.10 矩阵通过。

## 4. CI 工作流编写规范

- **严禁在 YAML 内嵌大段 Python 代码**（`run: python - <<'PY' ... PY`）。2026-08-05 曾因 YAML heredoc 中字符串编码损坏（闭合标签 `<` 丢失 + 乱码）导致 CI 连续 11 次失败，且本地难以复现。
- 单测一律写入 `tests/` 目录的 pytest 文件，CI 只引用文件：`python -m pytest tests/test_react_parser.py -q`。

## 5. 三平台发布

仓库同一代码同步到三个平台：GitHub（`weed33834/FinPilot`）、GitCode（`badhope/FinPilot`）、Gitee（`badhope/FinPilot`）。

### 推送代码/标签

```bash
bash scripts/sync_all.sh            # 推 main 并实证三平台
bash scripts/sync_all.sh v2.1.0     # 推 tag 并实证
```

脚本会**每平台独立 push**（GitHub 经本地 Steam++ 反代可能 3–7 分钟、偶发僵死，独立 push 避免卡死整条链），结束后**强制 ls-remote 实证**三平台 SHA 一致。

### 发布 Release（三平台 API 细节）

- **GitHub**：`POST/PATCH /repos/weed33834/FinPilot/releases`，`Authorization: Bearer <PAT>`，`verify=False`（本地反代自签证书）。
- **GitCode**：`POST/PATCH /api/v5/repos/badhope/FinPilot/releases`，`Authorization: Bearer <PAT>`，**Content-Type 必须带 `charset=utf-8`**（中文乱码坑）；**release 对象无 id 字段，PATCH 用 tag 路径** `/releases/{tag_name}`。
- **Gitee**：`POST/PATCH /api/v5/repos/badhope/FinPilot/releases`，`access_token` 参数；**创建必须带 `target_commitish`**（默认分支，缺失报 400）；**PATCH 必须带 `tag_name`**（缺失报 400）。

## 6. 已知环境坑（本机）

- **GitHub push 走 Steam++ 反代**：3–7 分钟属正常；超过 10 分钟无进展 → `curl -sk` 自检 HTTP 层（401/200=链路正常），杀掉残留 `git-remote-https.exe` 后重推即可秒过。
- **git 提示语不可靠**："Everything up-to-date" / "nothing to commit" 可能与实际不符，**以 `git ls-remote` 实证为准**（sync_all.sh 已内置）。
- 禁止在 `python - <<'PY'` heredoc 内用多行字符串写文件（换行转义会被破坏）；需写文件时用独立脚本文件。
