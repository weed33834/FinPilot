<div align="center">
  <img src="docs/banner.svg" alt="FinPilot" width="720" />
</div>

<div align="center">

# FinPilot · エンタープライズ向けAI財務分析プラットフォーム

**オープンソースのエンタープライズ向け AI 財務分析プラットフォーム**

[![License](https://img.shields.io/badge/license-MIT-1E5BFF.svg?style=flat-square)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%20–%203.13-3776AB.svg?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688.svg?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19-61DAFB.svg?style=flat-square&logo=react&logoColor=white)](https://react.dev/)
[![LangGraph](https://img.shields.io/badge/LangGraph-1.x-1C3C3C.svg?style=flat-square)](https://github.com/langchain-ai/langgraph)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-1E5BFF.svg?style=flat-square)](CONTRIBUTING.md)

**財務データを自然言語で照会。計算され、追跡可能で、監査可能な結果を。**

[クイックスタート](#クイックスタート) · [コア機能](#コア機能) · [製品紹介](#製品紹介) · [主な差別化要因](#主な差別化要因) · [技術スタック](#技術スタック) · [ロードマップ](#ロードマップ) · [コントリビュート](#コントリビュート)

</div>

[English](README.md) · [中文](README.zh-CN.md) · **日本語**

---

## 製品概要

FinPilot は、オープンソースのエンタープライズ向け AI 財務分析プラットフォームです。構造化されたエージェントパイプラインを通じて大規模言語モデルと財務データを接続し、財務チームに以下を提供します：

- **自然言語でのデータ照会** — 自然言語の質問を SQL に変換し、データベースで実際に実行；
- **レポートの自動生成** — テンプレートベースのレポート生成、購読配信、承認ワークフロー；
- **ドキュメントQA** — RAG による Excel / PDF / CSV / DOCX ドキュメントへの質問応答；
- **財務モデリング** — DCF・DDM・LBO・WACC・比較企業分析・モンテカルロシミュレーションを決定的なコードで実行。

すべての出力は**コードによって計算され、モデルによって解説され**、完全な実行ログにより追跡・監査が可能です。

---

## コア機能

| 分野 | 機能 |
| :--- | :--- |
| 🤖 対話型QA | チャットで Excel/PDF/CSV/DOCX をアップロード、SSE ストリーミング、推論ステップをリアルタイム表示 |
| 📊 財務モデリング | DCF・DDM・LBO・WACC・比較企業分析・モンテカルロ — 決定的な純Python計算機 |
| 📑 レポートセンター | テンプレート化レポート、購読配信、承認ワークフロー |
| 🔍 RAG ドキュメントQA | BM25 + ベクター + RRF 融合検索、マルチフォーマット解析 |
| 🛡 セキュリティとコンプライアンス | ABAC アクセス制御、TOTP 二段階認証、PII マスキング、インジェクション対策、監査ログ、ロール階層 |
| 📡 実行ログ | リアルタイム監視：ログ / QA再生 / モジュール状態 / 統計 |
| 🧰 拡張性 | ツール・スキル・MCPサーバー・コードサンドボックス・プロンプト管理 |
| 💬 チャット＝コンソール | スラッシュコマンド、ロールフィルター付き、チャットからシステム全体を管理可能 |
| 📱 モバイルファースト | レスポンシブなモバイルシェル、デスクトップページは段階的に縮退 |
| 🚨 精密なエラー処理 | レイヤー別エラーシステム（ネットワーク/認証/クライアント/サーバー）、実用的な診断情報を提供 |

---

## 製品紹介

**製品デモ（5:21、ナレーションなし）：** 実環境での実行記録——実際のログイン、実際のLLM呼び出し、実際のDBへの実クエリ。

<video controls src="docs/media/finpilot_demo.mp4" width="100%"></video>

<sub>[⬇ mp4をダウンロード](docs/media/finpilot_demo.mp4)（インライン再生できない場合）</sub>

| ログイン | ダッシュボード |
|:---:|:---:|
| ![login](docs/screenshots/00-login-filled.png) | ![dashboard](docs/screenshots/dashboard.png) |

| 対話型QA | NL2SQLの実クエリ結果 |
|:---:|:---:|
| ![agent](docs/screenshots/agent-answer.png) | ![queries](docs/screenshots/queries-result.png) |

| AI生成レポート | ドキュメント管理 |
|:---:|:---:|
| ![reports](docs/screenshots/reports-generated.png) | ![documents](docs/screenshots/documents.png) |

| セキュリティ（2FA設定） | システム設定 |
|:---:|:---:|
| ![security](docs/screenshots/security-2fa-setup.png) | ![settings](docs/screenshots/admin_settings.png) |

| LLMプロバイダー（例: Aliyun Bailian） | MCPサーバー |
|:---:|:---:|
| ![providers](docs/screenshots/llm-providers.png) | ![mcp](docs/screenshots/admin_mcp-servers.png) |

---

## 主な差別化要因

1. **計算であって生成ではない。** DCF・WACC・バックテスト・レシオなどはすべて決定的なコードで実行。モデルは結果を解説するだけで、数値をでっち上げません。
2. **完全に追跡可能。** APIコール・QAターン・モジュール操作はすべて実行ログに記録され、ステップごとの再生と監査が可能です。
3. **チャット＝コントロールプレーン。** ロールフィルター付きコマンドパレット（`/`）により、管理者は会話からシステム全体を操作でき、一般ユーザーは権限内の機能のみ利用できます。

その他のエンタープライズ機能：RAGドキュメントQA（BM25+ベクター+RRF融合）、Excel/PDF/DOCX解析、ABACアクセス制御、TOTP二段階認証、モバイル対応、故障レイヤーを特定できるエラーシステム。

---

## クイックスタート

```bash
git clone https://github.com/weed33834/FinPilot.git   # または下記ミラー
cd FinPilot

# バックエンド
python3 -m venv venv && source venv/bin/activate
pip install -e .
cp .env.example .env        # LLM APIキーを設定
uvicorn finpilot.api.router:app --host 0.0.0.0 --port 8001

# フロントエンド
cd frontend && npm install && npm run dev
```

`http://localhost:5173` を開き、`.env` の自動生成管理者アカウント（`FINPILOT_ADMIN_EMAIL` / `FINPILOT_ADMIN_PASSWORD`）でログインすれば、すぐに照会を開始できます。

> LLMプロバイダーは「管理 → モデルプロバイダー」で設定（DB保存、環境変数はフォールバック）。OpenAI 互換エンドポイントをサポート（Aliyun Bailian、DeepSeek、Zhipu など）。

Docker デプロイ：`docker compose up -d`（Redis + PostgreSQL + バックエンド + フロントエンド）。詳細は [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)。

---

## 技術スタック

Python 3.10–3.13 · FastAPI · LangGraph · SQLAlchemy · Pydantic · React 19 · Vite · TypeScript · Tailwind 4 · Zustand · Recharts · i18next · pdfplumber · openpyxl · BM25 · SQLite/PostgreSQL · Redis · Docker

---

## ロードマップ

- ✅ **v1/v2** — 会話QA、RAG、実行ログ、レポートと承認、セキュリティ基盤、スラッシュコマンド、財務検証エンジン、マルチエージェント討論、バックテストとファクターマイニング、MCP/スキル/ツール管理、i18n（英/中）、モバイル対応
- 🚧 **v2.1** — リアルタイム相場、知識グラフ統合、エンタープライズSSO

詳細は [CHANGELOG.md](CHANGELOG.md)。

---

## コントリビュート

Issue・PR 歓迎。まず [CONTRIBUTING.md](CONTRIBUTING.md) を参照してください。セキュリティ問題は [SECURITY.md](SECURITY.md) へ報告してください（公開Issueでの開示はご遠慮ください）。

---

## ミラー

同一コードベースを3プラットフォームで同期運用しています。利用しやすい環境をお選びください。

| プラットフォーム | URL |
|------|------|
| **GitHub** | https://github.com/weed33834/FinPilot |
| **GitCode** | https://gitcode.com/badhope/FinPilot |
| **Gitee** | https://gitee.com/badhope/FinPilot |

---

## License

MIT — [LICENSE](LICENSE) を参照。

> **免責事項：** 学習・研究目的のみ。投資助言を提供するものではありません。
