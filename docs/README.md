# docs index

docs直下は入口だけにし、実体は用途別ディレクトリに置く。

## よく見るもの

- デモ前の確認: [`qa/谷内さんデモ確認シート_20260528.md`](qa/谷内さんデモ確認シート_20260528.md)
- 6/8 E2E確認: [`qa/谷内さん環境E2E確認_20260608.md`](qa/谷内さん環境E2E確認_20260608.md)
- 直近の成果と次課題: [`qa/見せデッキ成果と次課題_20260529.md`](qa/見せデッキ成果と次課題_20260529.md)
- ロードマップ: [`planning/ロードマップ.md`](planning/ロードマップ.md)
- 無料管理画面の最小フロー: [`specs/無料管理画面_最小フロー.md`](specs/無料管理画面_最小フロー.md)
- 背景生成ガイドライン: [`specs/背景生成ガイドライン.md`](specs/背景生成ガイドライン.md)
- Render/API公開手順: [`deploy/公開デプロイ手順.md`](deploy/公開デプロイ手順.md)
- Custom GPT Action接続: [`gpt-action/Custom_GPT_Action接続手順.md`](gpt-action/Custom_GPT_Action接続手順.md)

## ディレクトリ

| ディレクトリ | 中身 |
| --- | --- |
| `api/` | OpenAPI schema、Action smoke payload、API仕様 |
| `deploy/` | Render/ngrokなど公開・デプロイ手順 |
| `gpt-action/` | Custom GPT InstructionsとAction接続手順 |
| `specs/` | パイプライン、入力データ、背景、PPTX出力などの仕様 |
| `planning/` | ロードマップ、事業計画 |
| `qa/` | 見た目QA、デモ確認、成果と次課題 |

## 置き場所ルール

- 手順書は `deploy/` か `gpt-action/` に置く。
- 実装の前提・仕様は `specs/` に置く。
- OpenAPI JSONやAPI確認用JSONは `api/` に置く。
- デモ確認、見た目確認、振り返りは `qa/` に置く。
- 日付つきの計画やメモは増やさず、`planning/ロードマップ.md` か `planning/事業計画書.md` に吸収する。
