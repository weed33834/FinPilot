<div align="center">
  <img src="docs/banner.svg" alt="FinPilot" width="720" />
</div>

<div align="center">

# FinPilot · ちゃんと計算する財務AIアシスタント

**口先だけじゃない。本当に調べて、計算して、レポートを出す。**

[![License](https://img.shields.io/badge/license-MIT-1E5BFF.svg?style=flat-square)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%20–%203.13-3776AB.svg?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688.svg?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19-61DAFB.svg?style=flat-square&logo=react&logoColor=white)](https://react.dev/)
[![LangGraph](https://img.shields.io/badge/LangGraph-1.x-1C3C3C.svg?style=flat-square)](https://github.com/langchain-ai/langgraph)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-1E5BFF.svg?style=flat-square)](CONTRIBUTING.md)

[クイックスタート](#クイックスタート) · [スクリーンショット](#スクリーンショット) · [特徴](#特徴) · [技術スタック](#技術スタック) · [ロードマップ](#ロードマップ) · [コントリビュート](#コントリビュート)

</div>

[English](README.md) · [中文](README.zh-CN.md) · **日本語**

---

## 先に言っておきます：以下はすべて本物です

「デモは派手だけど、中身は全部作り物」というプロジェクトに飽き飽きしているので、最初に断言します。

- クエリ画面のSQLは**実際のLLMが生成**し、**本当にデータベースで実行**しています。
- レポートの分析文は**実際のモデルが書いたもの**で、手打ちではありません。
- グラフの数字はすべて**コードが計算**したものです。モデルは説明を書くだけ。

> **数字はコードが計算し、文章はモデルが書き、すべての出力は出所まで追跡できます。**

---

## これは何？

一言で言えば：**聞けば、本当に計算してくれる。**

決算書をアップロードして、こう聞いてみてください：

> 「純利益が一番高い月はいつ？」

あなたの言葉をSQLに翻訳し、実際にデータベースを検索して、結果テーブルを見せて、モデルが解説を付けます。レポートが欲しければ、一言で生成・購読・承認まで一気に。

FinPilotが解決したいのは、AI財務分析のありがちな問題——**モデルはもっともらしく話すけど、数字は全部それっぽくでっち上げ**。数字はコードに戻し、モデルには人間の言葉で説明させる。それだけです。

---

## スクリーンショット

| ログイン | ダッシュボード |
|:---:|:---:|
| ![login](docs/screenshots/00-login-filled.png) | ![dashboard](docs/screenshots/dashboard.png) |

| チャット（実際のAI回答） | NL2SQLの実クエリ結果 |
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

## 特徴

1. **数字は本物。** DCF・WACC・バックテスト・レシオ… すべて決定的なコードで計算。モデルは説明だけ、でっち上げなし。
2. **全部追跡可能。** APIコール・Q&A・モジュール操作はすべて実行ログに残る。エージェントが何をしたか、なぜそうしたかを再生できる。
3. **チャットがコントロールパネル。** `/` を入力するとロールフィルタ付きコマンドパレットが出る。管理者はダイアログだけでシステム全体を操作でき、一般ユーザーは自分の権限内のものだけ見える。

あとは「定番だけどちゃんと作った」ものたち：RAGドキュメントQA（BM25+ベクター+RRF融合）、Excel/PDF/DOCX解析、ABACアクセス制御、TOTP二段階認証、モバイル対応、そして**どこが壊れたか教えてくれる**エラーシステム——「操作に失敗しました」だけじゃなく。

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

`http://localhost:5173` を開き、`.env` の `FINPILOT_ADMIN_EMAIL` / `FINPILOT_ADMIN_PASSWORD` でログインすれば、すぐに質問できます。

> LLMプロバイダーは「管理 → モデルプロバイダー」で設定（DB保存、環境変数はフォールバック）。OpenAI互換のエンドポイントなら何でもOK（Aliyun Bailian、DeepSeek、Zhipuなど）。

Docker: `docker compose up -d`。詳細は [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)。

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

Issue・PR歓迎。まず [CONTRIBUTING.md](CONTRIBUTING.md) を。セキュリティ問題は [SECURITY.md](SECURITY.md) へ（公開Issueでは報告しないでください）。

---

## ミラー

同じコードを3プラットフォームに同時公開。速い方を使ってください。

| プラットフォーム | URL |
|------|------|
| **GitHub** | https://github.com/weed33834/FinPilot |
| **GitCode** | https://gitcode.com/badhope/FinPilot |
| **Gitee** | https://gitee.com/badhope/FinPilot |

---

## License

MIT — [LICENSE](LICENSE) を参照。

> **免責事項：** 学習・研究目的のみ。投資助言ではありません。
