#!/usr/bin/env python3
"""Publish a catalogue of finished creatives to Cloudflare R2, so the website can show them with the Mac off.

The ten curated showcase entries (web/scripts/export_showcase.SHOWCASE) come first, in their order and with their
titles; then the catalogue is filled to --limit creatives (default 100) from the studio: every requested kind of the
case is present (text, image-guided, video-guided, controlled edits), newest first, creatives the viewer marked
"ready to ship" preferred, at most three versions each (the first, the latest, and the latest edit).

Files keep the studio-relative layout the site already resolves (<id>/v<n>/ad/ad.mp4 at 720p, posters, boards,
brief.json, level.json, review.json + sheet, inventory.json, uploads/ and sprites/ it needs), plus index.json and
<id>/showcase.json, exactly as the static showcase does, so the web app can read the bucket as a second showcase.

  uv run python scripts/r2_publish.py select [--limit 100]            # print the selection (no files touched)
  uv run python scripts/r2_publish.py export [--limit 100] [--out DIR] # write the files locally (default ~/cbj-work/r2-export)
  uv run python scripts/r2_publish.py upload [--out DIR] [--bucket cbj-creatives] [--prefix ""]
                                                                      # upload DIR to R2; needs R2_ACCOUNT_ID,
                                                                      # R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY in .env
Nothing in the engine, the workflows or the static showcase changes.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "web" / "scripts"))
import export_showcase as X  # noqa: E402  (the static exporter's helpers and curated list)
from cbj import studio  # noqa: E402

STUDIO = REPO / "studio"
SKIP = {"uploads", "levels", "recordings", "sprites"}


def survey() -> list[dict]:
    rows = []
    for d in sorted(STUDIO.iterdir()):
        if not d.is_dir() or d.name.startswith("_") or d.name in SKIP:
            continue
        versions = []
        for p in sorted(d.glob("v*"), key=lambda p: int(p.name[1:]) if p.name[1:].isdigit() else 0):
            vj = p / "version.json"
            if not vj.is_file():
                continue
            try:
                v = json.loads(vj.read_text())
            except Exception:  # noqa: BLE001
                continue
            if not (STUDIO / (v.get("video") or "x")).is_file():
                continue
            overall = None
            rj = p / "review.json"
            if rj.is_file():
                try:
                    overall = json.loads(rj.read_text()).get("overall")
                except Exception:  # noqa: BLE001
                    pass
            versions.append({"n": v["n"], "workflow": v.get("workflow") or "create", "edit": bool(v.get("edit")), "overall": overall,
                             "prompt": v.get("prompt") or "", "summary": (v.get("brief") or {}).get("summary") or ""})
        if versions:
            rows.append({"id": d.name, "versions": versions})
    return rows


def select(limit: int) -> list[tuple[str, list[int], str, str, str]]:
    curated = list(X.SHOWCASE)
    chosen = {c[0] for c in curated}
    out = curated[:]
    rows = [r for r in survey() if r["id"] not in chosen]
    rows.sort(key=lambda r: r["id"], reverse=True)  # newest first (ids start with MMDD-HHMMSS)

    def score(r):
        ship = any(v["overall"] == "ship" for v in r["versions"])
        edits = any(v["edit"] for v in r["versions"])
        return (ship, edits)

    rows.sort(key=score, reverse=True)
    # fill by kind with targets, then anything left
    targets = {"create": 36, "image_guided": 22, "guided": 22}
    picked = []
    for r in rows:
        if len(out) + len(picked) >= limit:
            break
        wf = r["versions"][0]["workflow"]
        if targets.get(wf, 0) > 0:
            targets[wf] -= 1
            picked.append(r)
    for r in rows:
        if len(out) + len(picked) >= limit:
            break
        if r not in picked:
            picked.append(r)
    for r in picked:
        vs = r["versions"]
        ns = [vs[0]["n"]]
        latest_edit = next((v["n"] for v in reversed(vs) if v["edit"]), None)
        if latest_edit and latest_edit not in ns:
            ns.append(latest_edit)
        if vs[-1]["n"] not in ns and len(ns) < 3:
            ns.append(vs[-1]["n"])
        wf = vs[0]["workflow"]
        kind = {"create": "create", "image_guided": "image_guided", "guided": "guided"}.get(wf, "create")
        title = (vs[0]["prompt"].strip().rstrip(".") or r["id"])[:72]
        tag = vs[0]["summary"][:220] or ("Made from a text prompt." if wf == "create" else "Made from a prompt and a reference.")
        if latest_edit:
            tag += f" Edited in v{latest_edit}; the report proves what was kept."
        out.append((r["id"], sorted(set(ns)), title, kind, tag))
    return out


def export(selection, out_dir: Path) -> None:
    X.OUT = out_dir
    X.SHOWCASE = selection
    X.main()


def upload(out_dir: Path, bucket: str, prefix: str) -> None:
    import boto3  # the uploader's only extra dependency

    env = {}
    envf = REPO / ".env"
    if envf.is_file():
        for line in envf.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip().strip('"').strip("'")
    get = lambda k: os.environ.get(k) or env.get(k)  # noqa: E731
    acct, key, secret = get("R2_ACCOUNT_ID"), get("R2_ACCESS_KEY_ID"), get("R2_SECRET_ACCESS_KEY")
    if not (acct and key and secret):
        sys.exit("R2_ACCOUNT_ID, R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY are needed (in the environment or in .env)")
    from botocore.config import Config
    from boto3.s3.transfer import TransferConfig

    # R2 does not accept the newer SDKs' default flexible checksums on PUT (the upload hangs); plain single-part PUTs
    # with timeouts are reliable for files of this size.
    cfg = Config(region_name="auto", connect_timeout=20, read_timeout=120, retries={"max_attempts": 4, "mode": "standard"},
                 request_checksum_calculation="when_required", response_checksum_validation="when_required")
    s3 = boto3.client("s3", endpoint_url=f"https://{acct}.r2.cloudflarestorage.com", aws_access_key_id=key,
                      aws_secret_access_key=secret, config=cfg)
    transfer = TransferConfig(multipart_threshold=256 * 1024 * 1024, use_threads=False)
    names = [b["Name"] for b in s3.list_buckets().get("Buckets", [])]
    if bucket not in names:
        s3.create_bucket(Bucket=bucket)
        print(f"created bucket {bucket}")
    s3.put_bucket_cors(Bucket=bucket, CORSConfiguration={"CORSRules": [{"AllowedOrigins": ["*"], "AllowedMethods": ["GET", "HEAD"],
                                                                        "AllowedHeaders": ["*"], "MaxAgeSeconds": 3600}]})
    # what is already there (skip unchanged sizes)
    have = {}
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        for o in page.get("Contents", []):
            have[o["Key"]] = o["Size"]
    files = [p for p in out_dir.rglob("*") if p.is_file() and p.name != ".DS_Store"]
    # order: index first, then the ten curated creatives, then the assets, then the rest (the uplink may be slow)
    curated = [c[0] for c in X.SHOWCASE]
    def rank(p: Path):
        rel = p.relative_to(out_dir).as_posix(); top = rel.split("/")[0]
        if rel == "index.json": return (0, rel)
        if top in curated: return (1, curated.index(top), rel)
        if top in ("assets", "sprites", "uploads"): return (2, rel)
        return (3, rel)
    files.sort(key=rank)
    todo = []
    for p in files:
        k = prefix + p.relative_to(out_dir).as_posix()
        if have.get(k) != p.stat().st_size or p.name in ("index.json", "showcase.json"):
            todo.append((p, k))
    print(f"{len(files)} files, {len(todo)} to upload ({sum(p.stat().st_size for p, _ in todo) / 1e6:.1f} MB)", flush=True)
    t0 = time.time()

    def put(item):
        p, k = item
        ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        cache = "no-cache" if p.name in ("index.json", "showcase.json") else "public, max-age=31536000, immutable"
        s3.upload_file(str(p), bucket, k, ExtraArgs={"ContentType": ctype, "CacheControl": cache}, Config=transfer)
        return k

    with ThreadPoolExecutor(4) as ex:
        for i, k in enumerate(ex.map(put, todo), 1):
            if i % 50 == 0 or i == len(todo):
                print(f"  {i}/{len(todo)} {k}", flush=True)
    print(f"uploaded in {time.time() - t0:.0f} s; bucket {bucket} now holds {len(have) + len(todo)} keys (approx.)")
    print("Public URL: enable it in the Cloudflare dashboard (R2 > the bucket > Settings > Public access: r2.dev subdomain "
          "or a custom domain); the site needs that base URL as NEXT_PUBLIC_CATALOGUE_URL.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("select", "export", "upload"))
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--out", default=str(Path.home() / "cbj-work" / "r2-export"))
    ap.add_argument("--bucket", default="cbj-creatives")
    ap.add_argument("--prefix", default="")
    a = ap.parse_args()
    if a.cmd == "select":
        sel = select(a.limit)
        kinds = {}
        for cid, ns, title, kind, _ in sel:
            kinds[kind] = kinds.get(kind, 0) + 1
            print(f"{kind:13} {cid:45} v{','.join(map(str, ns)):8} {title[:60]}")
        print(f"\n{len(sel)} creatives, {sum(len(s[1]) for s in sel)} versions; by kind: {kinds}; with edits: "
              f"{sum(1 for s in sel if len(s[1]) > 1)}")
    elif a.cmd == "export":
        export(select(a.limit), Path(a.out))
    else:
        upload(Path(a.out), a.bucket, a.prefix)


if __name__ == "__main__":
    main()
