# -*- coding: utf-8 -*-
"""發布 + 推上 GitHub：跑 publish.py 生靜態站 → git add/commit/push。

用法:
  python deploy.py                 # 發布全部 + 推送
  python deploy.py --series X       # 只重發某連載 + 推送
  python deploy.py --message "..."  # 自訂 commit 訊息
  python deploy.py --no-push        # 只發布不推（本機測試）

story2manga 出稿後會自動呼叫（若 D:\\MangaStudio 是 git repo 且有 origin）。
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def git(*args, check=True, capture=False):
    r = subprocess.run(["git", "-C", str(ROOT)] + list(args),
                       capture_output=capture, text=True, encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        out = (r.stdout or "") + (r.stderr or "")
        raise RuntimeError("git %s 失敗:\n%s" % (" ".join(args), out[:1500]))
    return r


def is_repo():
    return (ROOT / ".git").exists()


def has_origin():
    r = git("remote", check=False, capture=True)
    return "origin" in (r.stdout or "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--series", action="append", default=None)
    ap.add_argument("--message", default=None)
    ap.add_argument("--no-push", action="store_true")
    args = ap.parse_args()

    # 1) 產生靜態站
    pub = [sys.executable, str(HERE / "publish.py")]
    for s in (args.series or []):
        pub += ["--series", s]
    print("[deploy] 產生網站 ...")
    if subprocess.run(pub).returncode != 0:
        print("[deploy] publish 失敗，中止")
        sys.exit(1)

    if not is_repo():
        print("[deploy] 這裡還不是 git repo，略過推送（先執行 setup_git 一次）")
        return

    # 2) commit
    git("add", "-A")
    st = git("status", "--porcelain", capture=True)
    if not (st.stdout or "").strip():
        print("[deploy] 沒有變更，不需推送")
        return
    msg = args.message or ("更新漫畫網站 " + time.strftime("%Y-%m-%d %H:%M"))
    git("commit", "-m", msg)
    print("[deploy] 已提交：%s" % msg)

    if args.no_push:
        print("[deploy] --no-push，只提交本機")
        return

    # 3) push
    if not has_origin():
        print("[deploy] 沒有設定 origin 遠端，略過推送")
        return
    print("[deploy] 推送到 GitHub ...")
    r = git("push", "origin", "HEAD:main", check=False, capture=True)
    if r.returncode != 0:
        out = (r.stdout or "") + (r.stderr or "")
        print("[deploy] 推送失敗（多半是登入問題）：\n" + out[:800])
        print("[deploy] 本機已提交，之後在 D:\\MangaStudio 手動 `git push` 即可補推。")
        sys.exit(1)
    print("[deploy] 完成！網站已更新到 GitHub。")
    print("[deploy] 線上網址：https://patrickhung731.github.io/my-menga/")


if __name__ == "__main__":
    main()
