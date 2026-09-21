#!/usr/bin/env python3
"""检测上游集成更新，并把最新代码 vendor 到本仓库。

在 GitHub Actions（.github/workflows/update.yml）里每周自动运行，也可本地手动跑：
    python build.py            # 有更新才改文件
    python build.py --force    # 强制重新拉取全部

流程:
    1. 查询每个上游的当前版本（state_grid 看 main 最新 commit；zr_gas 看最新 release）
    2. 与 versions.json 里记录的对比
    3. 有变化 → 下载 tar.gz → 替换 integrations/<name>/ → 更新 versions.json
    4. 打印变更摘要（workflow 里据此 commit）

longyan_water 是自研集成，source = "self"，不会被自动覆盖。
"""
from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import sys
import tarfile
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
INTEGRATIONS = os.path.join(HERE, "integrations")
VERSIONS = os.path.join(HERE, "versions.json")

UA = {"User-Agent": "ha-integrations-auto"}

# 上游定义：名字 → (仓库, 类型, 包内路径)
UPSTREAMS = {
    "state_grid": {
        "repo": "stevenjoezhang/hass-state-grid",
        "track": "branch",          # 跟 main 分支最新提交
        "ref": "main",
        "inner": "custom_components/state_grid",
    },
    "zr_gas": {
        "repo": "yahooor/zr-gas-ha",
        "track": "release",         # 跟最新 release
        "inner": "custom_components/zr_gas",
    },
}

# 自研集成：只做版本登记，不从外部拉取
SELF = ["longyan_water"]


def http_json(path: str):
    r = urllib.request.Request("https://api.github.com" + path, headers=UA)
    with urllib.request.urlopen(r, timeout=40) as resp:
        return json.load(resp)


def http_bytes(url: str) -> bytes:
    r = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(r, timeout=120) as resp:
        return resp.read()


def upstream_state(name: str, cfg: dict) -> tuple[str, str]:
    """返回 (版本号, 引用标识)"""
    if cfg["track"] == "branch":
        commits = http_json(f"/repos/{cfg['repo']}/commits?per_page=1")
        sha = commits[0]["sha"]
        date = commits[0]["commit"]["committer"]["date"]
        # 版本号仍取 manifest 里的（上游不一定升版本号），用 sha 判定变化
        inner = cfg["inner"]
        content = http_json(f"/repos/{cfg['repo']}/contents/{inner}/manifest.json?ref={cfg['ref']}")
        import base64
        man = json.loads(base64.b64decode(content["content"]))
        return man.get("version", "0"), f"{sha[:8]} ({date[:10]})"
    else:
        rel = http_json(f"/repos/{cfg['repo']}/releases/latest")
        tag = rel["tag_name"]
        content = http_json(f"/repos/{cfg['repo']}/contents/{cfg['inner']}/manifest.json?ref={tag}")
        import base64
        man = json.loads(base64.b64decode(content["content"]))
        return man.get("version", tag.lstrip("v")), tag


def fetch_integration(name: str, cfg: dict, ref: str) -> None:
    """下载上游 tarball，把集成的目录复制到 integrations/<name>/"""
    url = f"https://codeload.github.com/{cfg['repo']}/tar.gz/refs/{'heads' if cfg['track'] == 'branch' else 'tags'}/{ref}"
    print(f"    下载 {url}")
    data = http_bytes(url)
    dest = os.path.join(INTEGRATIONS, name)
    tmp = os.path.join(HERE, f".tmp_{name}")
    if os.path.isdir(tmp):
        shutil.rmtree(tmp)
    os.makedirs(tmp, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
        prefix_parts = None
        for m in tf.getmembers():
            if not m.isfile():
                continue
            parts = m.name.split("/")
            if prefix_parts is None:
                prefix_parts = len(parts) - 1 - len(cfg["inner"].split("/"))
            # 只取 <repo>-<ref>/<inner>/... 下的文件
            inner_parts = cfg["inner"].split("/")
            if len(parts) < 1 + len(inner_parts) + 1:
                continue
            if parts[1:1 + len(inner_parts)] != inner_parts:
                continue
            rel = "/".join(parts[1 + len(inner_parts):])
            if "__pycache__" in rel or rel.endswith((".pyc", ".pyo")):
                continue
            out = os.path.join(tmp, rel)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with open(out, "wb") as fh:
                fh.write(tf.extractfile(m).read())

    if os.path.isdir(dest):
        shutil.rmtree(dest)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.move(tmp, dest)
    n = sum(len(fs) for _b, _d, fs in os.walk(dest))
    print(f"    → integrations/{name}/  {n} 个文件")


def self_version(name: str) -> str:
    p = os.path.join(INTEGRATIONS, name, "manifest.json")
    if not os.path.exists(p):
        return "?"
    return json.load(open(p, encoding="utf-8")).get("version", "?")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    os.makedirs(INTEGRATIONS, exist_ok=True)
    old = {}
    if os.path.exists(VERSIONS):
        old = json.load(open(VERSIONS, encoding="utf-8")).get("integrations", {})

    new = {}
    changed = []

    # 自研集成：登记版本，不动文件
    for name in SELF:
        v = self_version(name)
        new[name] = {"version": v, "source": "self (自研)",
                     "updated_at": old.get(name, {}).get("updated_at",
                                                         time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                                       time.gmtime()))}
        print(f"[{name}] 自研，版本 {v}")

    # 上游集成
    for name, cfg in UPSTREAMS.items():
        ver, ref = upstream_state(name, cfg)
        prev = old.get(name, {})
        same = (prev.get("version") == ver and prev.get("ref") == ref
                and os.path.isdir(os.path.join(INTEGRATIONS, name)))
        print(f"[{name}] 上游版本 {ver} / ref {ref}"
              + ("  → 无变化" if same and not args.force else "  → 需要更新"))
        if same and not args.force:
            new[name] = prev
            continue
        fetch_integration(name, cfg, cfg.get("ref") if cfg["track"] == "branch" else ref)
        new[name] = {
            "version": ver,
            "ref": ref,
            "source": f"{cfg['repo']} ({'main 分支' if cfg['track'] == 'branch' else ref})",
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        if prev.get("version") != ver or prev.get("ref") != ref:
            changed.append(f"{name}: {prev.get('version', '首次')} → {ver} ({ref})")

    data = {"built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "integrations": new}
    with open(VERSIONS, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print("\nversions.json:")
    print(json.dumps(new, ensure_ascii=False, indent=2))
    if changed:
        print("\nCHANGED: " + "; ".join(changed))
    else:
        print("\nNO_CHANGE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
