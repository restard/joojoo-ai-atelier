# genDeck

顧客ごとの世界観を反映した背景プールを作り、その背景を使ってスライド画像とPPTXを生成するパイプラインです。

実行時に画像生成APIは呼びません。背景はセットアップ時に `image_api.py` で作り置きし、デッキ生成時は `build_deck.py` が背景プールから選びます。

## 構成

| ファイル | 役割 |
| --- | --- |
| `image_api.py` | OpenAI Images APIで背景プールを生成する |
| `slide_render.py` | 背景画像とコンテンツから各スライド画像を描画する |
| `build_deck.py` | deck JSONを読み、スライド画像を生成してPPTXにまとめる |
| `gen_api.py` | deck JSONを受け取りPPTXを返すローカルAPI |
| `specs/` | デッキ内容のJSON仕様・サンプル/実データ |
| `docs/` | 仕様、運用手順、計画、QAメモ。入口は `docs/README.md` |
| `dist/` | 生成済みPPTX |
| `backgrounds/` | 生成済み背景プール |
| `assets/` | 写真、仮画像、message用フォールバック背景など |
| `_slides/` | PPTX化前の中間スライドPNG出力先 |

## セットアップ

```bash
pip install openai pillow numpy python-pptx qrcode
```

背景生成を行う場合は、OpenAI APIキーを設定します。

```bash
export OPENAI_API_KEY="sk-..."
```

## 背景を生成する

全タイプの背景を3色分作る場合:

```bash
python image_api.py --type all --count 3
```

特定タイプだけ作る場合:

```bash
python image_api.py --type cover --count 3
python image_api.py --type statement --count 6
```

色を指定して作る場合:

```bash
python image_api.py --type cover --count 3 --color terracotta
python image_api.py --type statement --count 3 --color cream
python image_api.py --type all --count 2 --color deep_green
```

参照画像を使って世界観を寄せる場合:

```bash
python image_api.py --type all --count 3 --refs refs/
```

### 色バリエーション

`--count` は枚数であり、同時に色順の指定にもなります。

1. `terracotta`: メインカラー
2. `cream`: ベースカラー
3. `deep_green`: テラコッタの補色
4. 以降は同じ順番を繰り返し

`--color` を指定した場合は、指定した色だけで `--count` 枚生成します。

保存先は色ごとのフォルダです。

```text
backgrounds/terracotta/cover.png
backgrounds/cream/cover.png
backgrounds/deep_green/cover.png
```

同じ色・同じ型が複数枚になる場合は連番が付きます。

```text
backgrounds/terracotta/cover_02.png
```

### モチーフ

`image_api.py` の `MOTIFS` から、生成ごとに4〜5個だけランダムに選ばれます。全部盛りになりすぎず、寂しくもなりすぎないようにするためです。

`message` 背景では人物が入ってもよいですが、必須ではありません。入る場合も、後ろ姿・手元・遠景のシルエットなどの補助要素に留め、人物ポートレートにはしない方針です。

## デッキを生成する

```bash
python build_deck.py specs/deck_taniuchi.json
```

色プールを指定して生成する場合:

```bash
python build_deck.py specs/deck_taniuchi.json --color terracotta
python build_deck.py specs/deck_taniuchi.json --color cream
python build_deck.py specs/deck_taniuchi.json --color deep_green
```

出力:

```text
2026プランニング会_terracotta.pptx
_slides/slide_01.png
_slides/slide_02.png
...
```

`build_deck.py` は指定された色プールから背景を読みます。

```text
backgrounds/{color}/{type}.png
```

旧形式も一応読めます。

```text
backgrounds/{type}/bg_01.png
```

## deck JSONの基本形

```json
{
  "deck_title": "2026プランニング会",
  "slides": [
    {
      "color": "cream",
      "type": "cover",
      "content": {
        "eyebrow": "2026 Planning flight",
        "title": ["未来を旅する", "プランニング会"],
        "subtitle": "ーわたしの2026年へ出発する120分ー",
        "presenter": "Presented By : HITOMI TANIUCHI"
      }
    }
  ]
}
```

`color` はデッキ全体にも、各スライドにも指定できます。

デッキ全体に指定する場合:

```json
{
  "deck_title": "2026プランニング会",
  "color": "terracotta",
  "slides": []
}
```

各スライドに指定する場合:

```json
{
  "type": "message",
  "color": "deep_green",
  "content": {
    "eyebrow": "My Vision",
    "lines": ["ビジョン", "右脳と感覚で生きる人を", "もっと自由に"]
  }
}
```

優先順は `background` の明示指定 → スライドの `color` → デッキ全体の `color` → CLIの `--color` です。

背景画像をURLで直接指定する場合:

```json
{
  "type": "statement",
  "background": {
    "url": "https://example.com/background.png"
  },
  "content": {
    "lines": ["URL背景で", "PPTXを生成"]
  }
}
```

`background.url` は `http` / `https` の画像URLに対応しています。生成時に一時ダウンロードして既存レンダラーへ渡します。

対応している `type`:

```text
cover
list
statement
message
multi_image
before_after
three_column
person
cta
```

`before_after` は専用背景がない場合 `multi_image` 背景を使います。`three_column` は専用背景がない場合 `statement` 背景を使います。

## ローカルAPIを起動する

Custom GPT / Action 接続の最小確認用に、標準ライブラリだけのAPIを用意しています。

```bash
python3 gen_api.py --host 127.0.0.1 --port 8787
```

ngrokなどで公開URLがある場合:

```bash
python3 gen_api.py --host 127.0.0.1 --port 8787 \
  --public-url https://xxxx.ngrok-free.app
```

Render/Fly.ioなどの公開環境では、`PORT` / `HOST` / `PUBLIC_URL` 環境変数も使えます。

```bash
HOST=0.0.0.0 PORT=8787 PUBLIC_URL=https://example.onrender.com python3 gen_api.py
```

`PUBLIC_URL` を指定しない場合でも、プロキシ経由の `/openapi.json` では `X-Forwarded-Proto` と `Host` から公開URLを推定します。

生成済みPPTXをCloudflare R2へ保存する場合は、次の環境変数を設定します。未設定の場合は従来通りローカルの `/files/...` URLを返します。

```bash
export R2_ACCOUNT_ID="..."
export R2_BUCKET="gendeck"
export R2_ACCESS_KEY_ID="..."
export R2_SECRET_ACCESS_KEY="..."
export R2_PUBLIC_URL="https://files.example.com"
```

任意で `R2_ENDPOINT_URL`、`R2_PREFIX`、`R2_REGION` も指定できます。`R2_PUBLIC_URL` がある場合、APIレスポンスの `download_url` はR2の公開URLになります。

確認:

```bash
curl http://127.0.0.1:8787/health
curl http://127.0.0.1:8787/openapi.json
```

管理画面:

```text
http://127.0.0.1:8787/admin
```

PPTX生成:

```bash
curl -X POST http://127.0.0.1:8787/generate \
  -H "Content-Type: application/json" \
  --data-binary @specs/deck_sample.json \
  -o dist/api/sample_deck_api.pptx
```

`assets/`、`backgrounds/`、顧客用の `specs/` は顧客情報を含む可能性があるため、Git管理から外しています。背景プールがない公開環境では、`gen_api.py` が安全なデモ背景を自動生成します。

## Renderへデプロイする

Custom GPT Actionsがngrok無料ドメインで失敗する場合に備え、DockerベースでRenderへ置けるようにしています。

使うファイル:

| ファイル | 役割 |
| --- | --- |
| `Dockerfile` | Python実行環境とNoto CJKフォントを入れる |
| `requirements.txt` | PPTX生成に必要なPython依存 |
| `render.yaml` | Render Blueprint用の最小設定 |
| `.dockerignore` | デプロイ不要な生成物を除外 |

手順は `docs/deploy/公開デプロイ手順.md` を参照してください。

## 生成の流れ

```text
deck JSON
  + backgrounds/
  + assets/
      ↓
slide_render.py
      ↓
_slides/*.png
      ↓
build_deck.py
      ↓
PPTX
```

## よく触る場所

| 目的 | 触る場所 |
| --- | --- |
| 世界観を変える | `image_api.py` の `AESTHETIC` |
| モチーフ候補を変える | `image_api.py` の `MOTIFS` |
| 色の方向性を変える | `image_api.py` の `COLOR_VARIANTS` |
| 背景の余白・実寸スケールのルールを変える | `image_api.py` の `COMPOSITION` / `COVER_COMPOSITION` |
| スライド文言や写真を変える | `specs/deck_taniuchi.json` |
| レイアウトや描画を変える | `slide_render.py` |

## 注意

- `image_api.py` は背景プール作成用です。通常のPPTX生成では実行しません。
- 生成後の背景は目視で確認し、不要なものを削除してください。
- 現状のPPTXは各スライドをPNGとして貼り込む方式です。PowerPoint上で本文テキストを直接編集する方式ではありません。
