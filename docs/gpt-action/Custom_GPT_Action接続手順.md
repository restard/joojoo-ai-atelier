# Custom GPT / Action検証メモ

最終更新: 2026年5月30日

## 目的

Custom GPTからgenDeck用のdeck JSONを作るための設定と、Custom GPT Actions検証結果をまとめる。

6/8デモでは、Custom GPT Actionsを本線にしない。PPTX化は、Custom GPTが出力したdeck JSONをgenDeckの管理画面、API、またはローカル実行に渡して行う。

参考: [Configuring actions in GPTs](https://help.openai.com/en/articles/9442513-configuring-actions-in-gpts)

## 現行方針

- Custom GPTの主役割は「PPTXを直接生成すること」ではなく、genDeck用deck JSONを作ること
- 6/8時点ではCustom GPT Actionsを本線にしない
- Custom GPTは、谷内さんがその場で別資料について相談し、会話しながら5〜10枚程度の構成を決め、PPTX生成に渡せるdeck JSONを作る
- PPTX化は、作成したdeck JSONをじゅじゅが管理画面、API、またはローカル実行に渡して行う
- 53枚規模のフルデッキも、まずはGPTがdeck JSONを作るところまでを主なデモにする

## Action検証の結論

2026年5月時点の検証では、Custom GPT ActionsからのPPTX生成は6/8デモの本線にしない。

理由:

- `POST /generate` はCustom GPT Actions側で `ClientResponseError` になり、APIへ届かないケースがあった
- `GET /generate-json` は回避策として用意したが、deck JSONをquery parameterで渡すため長いデッキに向かない
- ChatGPT内でPPTXファイルを直接扱う体験も不安定になりやすい

そのため、Actionsは将来の再検証枠とし、6/8では「GPTでJSON作成 → genDeck側でPPTX生成」を正式な導線にする。

## 6/8デモの実行導線

### 1. Custom GPT

GPTのInstructionsには、`docs/gpt-action/custom_gpt_instructions.md` の内容を入れる。

Actionsは設定しない。

### 2. 会話デモ

谷内さんがその場で別資料について相談し、GPTが目的、対象者、ページ数、章立てを確認する。

5〜10枚程度の短い資料に整理し、最後にボタン風の確認を出す。

```text
この内容でdeck JSONを出力してもよろしいですか？

[はい、JSONを出力する]
[まだ修正する]
```

同意後、コピーしやすい `json` コードブロック形式でdeck JSONを出力する。

### 3. PPTX生成

出力されたdeck JSONを、じゅじゅが管理画面、API、またはローカル実行に渡してPPTX化する。

ローカルで直接生成する場合:

```bash
python build_deck.py specs/deck_sample.json
```

API経由で生成する場合は、`gen_api.py` を起動して管理画面またはAPIにdeck JSONを渡す。

## Custom GPT側の設定

### Instructions

GPTのInstructionsには、`docs/gpt-action/custom_gpt_instructions.md` の内容を入れる。

6/8時点では、谷内さんがその場で別資料を相談し、会話で構成を決め、5〜10枚程度のPPTX生成に渡せるdeck JSONまで作れることを見せる。PPTX生成は、そのJSONをgenDeck側に渡して行う。

### Actions

6/8デモではActionsを設定しない。

## Action再検証用メモ

以下は将来再検証する場合だけ使う。6/8デモでは使わない。

### 1. ngrok

```bash
ngrok http 8787
```

表示されたHTTPS URLを控える。

例:

```text
https://xxxx.ngrok-free.dev
```

### 2. genDeck API

別ターミナルで起動する。

```bash
python3 gen_api.py --host 127.0.0.1 --port 8787 \
  --public-url https://xxxx.ngrok-free.dev
```

### 3. schema確認

```bash
curl http://127.0.0.1:8787/openapi.json
```

`servers[0].url` がngrok URLになっていればOK。

### 4. Actions設定

GPT editorでActionsを開き、Create new actionを選ぶ。

設定:

- Authentication: `None`
- Schema: `http://127.0.0.1:8787/openapi.json` のJSONを貼り付ける

注意:

- schema内の `servers[0].url` は必ずngrok URLになっていること
- ngrokを再起動するとURLが変わる場合がある。その場合はAPIを `--public-url` 付きで起動し直し、schemaも貼り直す
- WorkspaceのAction domain制限がある場合、ngrokドメインがブロックされる可能性がある

### Previewで試す入力

まずはPPTX全体生成ではなく、1枚だけの小さいJSONで呼び出し確認する。

```text
次のdeck JSONを文字列として `deck_json` に入れて、generateDeckFromJsonQueryを呼んでください。

{
  "deck_title": "action_smoke_test",
  "color": "terracotta",
  "slides": [
    {
      "type": "statement",
      "color": "deep_green",
      "content": {
        "eyebrow": "Action test",
        "lines": ["接続テスト", "PPTX生成"]
      }
    }
  ]
}
```

成功したら、顧客情報を含まないサンプル化済みJSONで試す。共有用には `specs/deck_sample.json` を使う。

### 成功条件

- GPT Previewから `generateDeckFromJsonQuery` が呼べる
- API側ログに `/generate-json` のGETが出る
- `dist/api/` にPPTXが保存される
- レスポンスに `download_url` が返る

## 2026-05-27 接続テスト結果

Custom GPT `genDeck Planner` を作成し、ngrok URL `https://craftwork-relearn-pectin.ngrok-free.dev` でAction接続を試した。

確認できたこと:

- ローカルAPIは `HTTP/1.1` で応答するよう修正済み
- ngrok経由の `GET /health` / `GET /openapi.json` / `POST /generate` はcurlで成功
- curlからの `POST /generate` では `dist/api/action_smoke_test.pptx` が生成される
- Custom GPT側では `generateDeck` の呼び出し時に `ClientResponseError` が発生
- ngrokのリクエスト履歴には、Custom GPTからの最新 `POST /generate` が出ていない

現時点の判断:

- `gen_api.py` とngrok公開自体は動いている
- 障害箇所はAPI内部ではなく、Custom GPT Actionsの実行層、スキーマ解釈、またはngrok無料ドメイン/Workspace制限の可能性が高い
- 6/8のE2Eでは、必要に応じてローカルcurl実演をフォールバックにする

試したschema:

- `docs/api/action_openapi_current.json`
- `docs/api/action_openapi_smoke_only.json`
- `docs/api/action_openapi_generate_only_minimal.json`

## 2026-05-28 Render接続後のPOST対策

Render公開後、Custom GPT Actionsから `generateSmokeDeck` は成功したが、`generateDeck` は `ClientResponseError` になった。Render logsには該当POSTが出ていなかったため、API生成処理ではなくActions側のPOSTスキーマ解釈で止まっている可能性が高い。

対策として、`generateDeck` のrequest bodyをネストしたdeck JSONではなく、`deck_json` という1つの文字列に変更した。GPTにはdeck JSON全体を文字列として渡させ、API側でJSONに戻して既存のPPTX生成処理へ渡す。

その後もCustom GPT Actions側で `generateDeck` のPOSTがAPIへ届かなかったため、GET版の `generateDeckFromJsonQuery` も追加した。ただしGET queryでdeck JSONを渡す方式は長いデッキに向かないため、6/8デモの本線からは外す。

通常チャット側でPOST Actionの混線が疑われたため、OpenAPI schemaからPOSTの `generateDeck` は外した。Custom GPTに見せるActionsは `generateSmokeDeck` と `generateDeckFromJsonQuery` の2つだけにする。

## 次の解決ルート

ngrokでCustom GPT Actionsが外へ出る前に失敗している可能性が高いため、次はRenderの通常HTTPS URLで再検証する。

Render向けの手順は `docs/deploy/公開デプロイ手順.md` を参照。

追加対応:

- DockerベースでRenderへ置けるようにした
- Render/Linux用にNoto CJKフォントへフォールバックするようにした
- `/openapi.json` がRenderの公開Hostから `servers[0].url` を推定できるようにした

## 失敗時に見るところ

### Action domain制限

GPT workspace側でngrokドメインが許可されない場合、Actionが実行できない。

対応:

- 障害として記録する
- ローカルcurl実演に切り替える
- 次候補としてRender/Fly.io等の恒久URLを検討する

### schemaのserver URLがローカルのまま

`servers[0].url` が `http://127.0.0.1:8787` だとChatGPTから呼べない。

対応:

- `gen_api.py` を `--public-url` 付きで起動し直す
- `/openapi.json` を再取得して貼り直す

### ファイルレスポンスがChatGPT側で扱いにくい

Actionは呼べても、PPTXファイルをChatGPT側でうまく受け取れない可能性がある。

対応:

- API到達は成功として記録する
- サーバー側に保存された `dist/api/{deck_title}.pptx` を手動で渡す
- 次フェーズで「ファイルURLを返すAPI」に変えるか判断する
