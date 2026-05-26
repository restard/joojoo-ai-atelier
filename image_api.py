#!/usr/bin/env python3
"""
背景ライブラリ生成スクリプト  ―― セットアップ時に1回だけ実行
================================================================
画像生成APIで「型ごとの背景」を量産し、backgrounds/{type}/ に保存する。
生成後、じゅじゅが目視でキュレーションして良いものだけ残す（人間の品質ゲート）。

これは実行時には使わない。実行時は build_deck.py がプールから「選ぶ」だけ。

使い方:
  pip install openai pillow
  export OPENAI_API_KEY="sk-..."
  python image_api.py --type all --count 6
  python image_api.py --type statement --count 9            # 型を指定
  python image_api.py --type cover --count 6 --refs refs/   # 参照画像つき
  python image_api.py --type cover --color terracotta --count 3   # 色を固定

色バリエーション：--color 未指定なら terracotta → cream → deep_green を順に巡回。
  --count は巡回数。3の倍数にすると各色が均等になる。
保存先：backgrounds/{type}/{color}_NN.png（build_deck.py がそのまま読める構造）

参照画像 (--refs) を渡すと images.edit を使い、世界観の再現精度が上がる。
（5/20に検証した「テラコッタ＋構図制約＋参照画像」の式をそのまま実装）
"""
import os, sys, base64, argparse
from io import BytesIO
from PIL import Image

# ====== 顧客ごとに調整する部分（＝「デザインルール」のスタイリング層）======
# この AESTHETIC が顧客の世界観。谷内さん向けの設定。
AESTHETIC = (
    "Vintage travel romance aesthetic. Warm terracotta and brick-red tones "
    "with cream and parchment. Scattered vintage postage stamps, airmail "
    "envelopes, ink postmarks, handwritten old letters, pressed dried flowers. "
    "Soft natural light, subtle analog film grain, nostalgic and elegant."
)

# ====== 色バリエーション（全型共通・--count で順に巡回）======
# 「持ち方」はそのまま：(色名, 色の指示文) のタプル。番号で巡回 or --color で固定。
COLOR_VARIANTS = (
    ("terracotta",
     "COLOR DIRECTION: warm terracotta and brick-red as the dominant surface "
     "tone, with a calm cream/parchment center. Rich and warm — the signature look."),
    ("cream",
     "COLOR DIRECTION: airy cream, ivory and parchment dominant, soft and bright. "
     "Terracotta only as a restrained accent in stamps and paper edges."),
    ("deep_green",
     "COLOR DIRECTION: deep forest green and dark olive as the dominant surface "
     "tone, with a calm cream/parchment center. Rich and moody — a sophisticated look."),
)

# ====== 構図制約（全型共通・5/20に検証済みの式）======
COMPOSITION = (
    "CRITICAL COMPOSITION RULE: the central 60 percent of the image must be a "
    "clean calm cream/parchment area, completely empty — no objects, no text. "
    "It is reserved for text that will be added later. Place ALL decorative "
    "elements (stamps, envelopes, dried flowers, letters) only along the outer "
    "20 percent edges. Horizontal 3:2 framing. "
    "Absolutely NO text, NO letters, NO words, NO numbers anywhere in the image."
)

# ====== 型ごとの構図バリエーション ======
PROMPTS = {
    "cover":       "A single torn-edge cream parchment sheet, centered, lying on a terracotta surface.",
    "list":        "An open vintage letter laid flat, wide blank cream center area.",
    "statement":   "A calm aged cream paper surface, very minimal, lots of empty space.",
    "multi_image": "An open travel scrapbook with blank cream pages.",
    "person":      "A cream parchment sheet with generous empty space in the middle.",
    "cta":         "The blank back of a vintage postcard, empty cream writing area in the center.",
    # 型D(message)は写真背景。風景写真プール or 顧客写真を使うため、ここでは生成しない。
}

SIZE_API = "1536x1024"   # gpt-image-1 の横長サイズ
CROP_169 = (1536, 864)   # 16:9 に中央クロップ


def crop_to_169(img: Image.Image) -> Image.Image:
    """3:2 で生成された画像を 16:9 に中央クロップ"""
    tw, th = CROP_169
    w, h = img.size
    scale = max(tw / w, th / h)
    img = img.resize((int(w * scale), int(h * scale)))
    w, h = img.size
    left, top = (w - tw) // 2, (h - th) // 2
    return img.crop((left, top, left + tw, top + th))


def load_ref_images(refs_dir):
    """参照画像フォルダから画像を読み込む"""
    if not refs_dir or not os.path.isdir(refs_dir):
        return []
    out = []
    for f in sorted(os.listdir(refs_dir)):
        if f.lower().endswith((".png", ".jpg", ".jpeg")):
            out.append(os.path.join(refs_dir, f))
    return out


def color_variant_for_index(index):
    """1始まりの生成番号から色バリエーションを返す（巡回）"""
    return COLOR_VARIANTS[(index - 1) % len(COLOR_VARIANTS)]


def color_variant_for_name(color_name):
    """色名から色バリエーションを返す"""
    for name, prompt in COLOR_VARIANTS:
        if name == color_name:
            return name, prompt
    valid = ", ".join(name for name, _ in COLOR_VARIANTS)
    raise ValueError(f"未知の色 '{color_name}'。指定可能: {valid}")


def generate_for_type(client, slide_type, count, refs, color=None):
    """1つの型について count 枚の背景を生成して保存。
    色は --color 指定がなければ terracotta→cream→deep_green を巡回する。
    """
    raw = PROMPTS[slide_type]

    print(f"[{slide_type}] {count}枚 生成中...")
    for i in range(1, count + 1):
        if color:
            color_name, color_prompt = color_variant_for_name(color)
        else:
            color_name, color_prompt = color_variant_for_index(i)
        out_dir = os.path.join("backgrounds", color_name)
        os.makedirs(out_dir, exist_ok=True)
        # プロンプトは4要素だけ：型 ＋ 世界観 ＋ 色 ＋ 構図制約
        prompt = f"{raw} {AESTHETIC} {color_prompt} {COMPOSITION}"

        if refs:
            # 参照画像つき：images.edit（世界観の再現精度が高い）
            ref_files = [open(p, "rb") for p in refs]
            try:
                resp = client.images.edit(
                    model="gpt-image-1", image=ref_files,
                    prompt=prompt, size=SIZE_API,
                )
            finally:
                for fh in ref_files:
                    fh.close()
        else:
            # プロンプトのみ：images.generate
            resp = client.images.generate(
                model="gpt-image-1", prompt=prompt, size=SIZE_API, n=1,
            )
        b64 = resp.data[0].b64_json
        img = crop_to_169(Image.open(BytesIO(base64.b64decode(b64))))
        path = os.path.join(out_dir, f"{slide_type}.png")
        n = 2
        while os.path.exists(path):
            path = os.path.join(out_dir, f"{slide_type}_{n:02d}.png")
            n += 1
        img.save(path, quality=95)
        print(f"  saved: {path}  ({color_name})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--type", default="all",
                    help="生成する型。'all' または cover/list/statement/multi_image/person/cta")
    ap.add_argument("--count", type=int, default=6,
                    help="型あたりの生成枚数（3の倍数で各色が均等になる）")
    ap.add_argument("--color", default=None,
                    choices=[name for name, _ in COLOR_VARIANTS],
                    help="生成する色を固定。未指定なら terracotta / cream / deep_green を巡回")
    ap.add_argument("--refs", default=None, help="参照画像フォルダ（任意）")
    args = ap.parse_args()

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        sys.exit("エラー: 環境変数 OPENAI_API_KEY が未設定です")

    try:
        from openai import OpenAI
    except ImportError:
        sys.exit("エラー: pip install openai を実行してください")

    client = OpenAI(api_key=api_key)
    refs = load_ref_images(args.refs)
    if refs:
        print(f"参照画像 {len(refs)}枚を使用: {args.refs}")

    types = list(PROMPTS) if args.type == "all" else [args.type]
    for t in types:
        if t not in PROMPTS:
            print(f"  スキップ: 未知の型 '{t}'")
            continue
        generate_for_type(client, t, args.count, refs, color=args.color)

    print("--- 生成完了。backgrounds/ を目視で確認し、不要なものを削除してください ---")


if __name__ == "__main__":
    main()