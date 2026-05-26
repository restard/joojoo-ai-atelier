# genDeck

顧客ごとの世界観を反映した背景プールを作り、その背景を使ってスライド画像とPPTXを生成するパイプラインです。

実行時に画像生成APIは呼びません。背景はセットアップ時に `image_api.py` で作り置きし、デッキ生成時は `build_deck.py` が背景プールから選びます。

## 構成

| ファイル | 役割 |
| --- | --- |
| `image_api.py` | OpenAI Images APIで背景プールを生成する |
| `slide_render.py` | 背景画像とコンテンツから各スライド画像を描画する |
| `build_deck.py` | deck JSONを読み、スライド画像を生成してPPTXにまとめる |
| `specs/` | デッキ内容のJSON仕様・サンプル/実データ |
| `docs/` | 事業計画、仕様書、ロードマップ、棚卸し |
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
