#!/usr/bin/env python3
"""Upload local background images to a Cloudflare R2 bucket.

Required environment variables:
  R2_ACCOUNT_ID or R2_ENDPOINT_URL
  R2_BUCKET
  R2_ACCESS_KEY_ID
  R2_SECRET_ACCESS_KEY
"""
import argparse
import json
import mimetypes
import os
from pathlib import Path


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def iter_background_files(source_dir):
    source = Path(source_dir)
    for path in sorted(source.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        rel_parts = path.relative_to(source).parts
        if any(part.startswith(".") or part.startswith("_") for part in rel_parts):
            continue
        yield path


def build_manifest(source_dir):
    source = Path(source_dir)
    backgrounds = {}
    styles = {}
    style_dirs = {"open_center", "paper_stage", "postcard_cta", "photo_frame"}

    for path in iter_background_files(source):
        rel = path.relative_to(source)
        if len(rel.parts) != 2:
            continue
        folder, filename = rel.parts
        stem = path.stem
        if folder in style_dirs:
            for suffix in ("_normal", "_reverse"):
                if stem.endswith(suffix):
                    color = stem[:-len(suffix)]
                    tone = suffix[1:]
                    styles.setdefault(folder, {}).setdefault(color, {}).setdefault(tone, []).append(rel.as_posix())
                    break
            continue

        slide_type = stem.split("_")[0] if "_" in stem else stem
        backgrounds.setdefault(folder, {}).setdefault(slide_type, []).append(rel.as_posix())

    return {
        "version": 1,
        "backgrounds": backgrounds,
        "styles": styles,
    }


def env(name, required=True, default=None):
    value = os.environ.get(name, default)
    if required and not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def create_client():
    try:
        import boto3
    except ImportError as exc:
        raise SystemExit("boto3 is required. Run: pip install -r requirements.txt") from exc

    endpoint_url = env("R2_ENDPOINT_URL", required=False)
    if not endpoint_url:
        endpoint_url = f"https://{env('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com"

    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=env("R2_ACCESS_KEY_ID"),
        aws_secret_access_key=env("R2_SECRET_ACCESS_KEY"),
        region_name=env("R2_REGION", required=False, default="auto"),
    )


def upload_manifest(client, bucket, dest_prefix, manifest, dry_run=False):
    key = f"{dest_prefix.strip('/')}/manifest.json" if dest_prefix.strip("/") else "manifest.json"
    body = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
    print(f"{'DRY ' if dry_run else ''}upload manifest.json -> s3://{bucket}/{key}")
    if not dry_run:
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=body,
            ContentType="application/json; charset=utf-8",
            CacheControl="no-cache",
        )


def upload_backgrounds(source_dir, dest_prefix, dry_run=False, include_manifest=True):
    files = list(iter_background_files(source_dir))
    if not files:
        raise SystemExit(f"No background image files found in {source_dir}")

    source = Path(source_dir)
    bucket = env("R2_BUCKET", required=not dry_run, default="<R2_BUCKET>")
    client = None if dry_run else create_client()
    uploaded = 0

    if include_manifest:
        upload_manifest(client, bucket, dest_prefix, build_manifest(source), dry_run=dry_run)

    for path in files:
        rel = path.relative_to(source).as_posix()
        key = f"{dest_prefix.strip('/')}/{rel}" if dest_prefix.strip("/") else rel
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        print(f"{'DRY ' if dry_run else ''}upload {path} -> s3://{bucket}/{key}")
        if not dry_run:
            client.upload_file(
                str(path),
                bucket,
                key,
                ExtraArgs={
                    "ContentType": content_type,
                    "CacheControl": "public, max-age=31536000",
                },
            )
        uploaded += 1
    return uploaded


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="backgrounds", help="Local background directory.")
    parser.add_argument("--dest-prefix", default="backgrounds", help="R2 object key prefix.")
    parser.add_argument("--dry-run", action="store_true", help="Print uploads without writing to R2.")
    parser.add_argument("--no-manifest", action="store_true", help="Do not upload manifest.json.")
    args = parser.parse_args()

    count = upload_backgrounds(
        args.source,
        args.dest_prefix,
        dry_run=args.dry_run,
        include_manifest=not args.no_manifest,
    )
    print(f"Done: {count} files {'would be uploaded' if args.dry_run else 'uploaded'}.")


if __name__ == "__main__":
    main()
