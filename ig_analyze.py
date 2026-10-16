#!/usr/bin/env python3
"""IG 追蹤分析器：讀取 Instagram 匯出(JSON)，找出沒回追、退追等。
用法: python3 ig_analyze.py <匯出的zip或資料夾> [輸出資料夾]
全程在本機處理，不連網。"""
import sys, os, json, zipfile, glob, shutil
from datetime import datetime
from html import escape

def fix(s):
    # IG 的 JSON 中文常是 latin-1 誤編碼，嘗試還原
    try:
        return s.encode("latin-1").decode("utf-8")
    except Exception:
        return s

def load_sources(path):
    """回傳 {檔名: 解析後的json}（同名檔案合併成 list）"""
    out = {}
    def add(name, raw):
        base = os.path.basename(name)
        if not base.endswith(".json"):
            return
        try:
            out.setdefault(base, []).append(json.loads(raw))
        except Exception:
            pass
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            for n in z.namelist():
                if "followers_and_following" in n or "follow" in n.lower():
                    add(n, z.read(n))
    else:
        for n in glob.glob(os.path.join(path, "**", "*.json"), recursive=True):
            if "follow" in n.lower():
                with open(n, "rb") as f:
                    add(n, f.read())
    return out

def entries(obj):
    """從各種格式取出 [(username, timestamp, href, displayname)]
    格式 A: string_list_data（followers / following）
    格式 B: label_values（close_friends / pending / recently_unfollowed 等，含顯示名稱）"""
    items = obj
    if isinstance(obj, dict):
        items = next((v for v in obj.values() if isinstance(v, list)), [])
    res = []
    for it in items:
        if "label_values" in it:
            user = dn = ""
            for lv in it["label_values"]:
                lab, val = fix(lv.get("label", "")), fix(lv.get("value", ""))
                if lab == "用戶名稱":
                    user = val.strip()
                elif lab == "名稱":
                    dn = val.strip()
            if user:
                res.append((user, it.get("timestamp", 0), f"https://www.instagram.com/{user}", dn))
            continue
        sld = (it.get("string_list_data") or [{}])[0]
        name = fix(sld.get("value") or it.get("title") or "").strip()
        if not name:
            continue
        res.append((name, sld.get("timestamp", 0), sld.get("href", f"https://www.instagram.com/{name}"), ""))
    return res

def collect(src, prefix):
    data = {}
    for fname, lst in src.items():
        if fname.startswith(prefix):
            for obj in lst:
                for n, ts, href, _ in entries(obj):
                    data[n] = (ts, href)
    return data

def display_names(src):
    """從匯出檔中撈出已知的顯示名稱 {username: name}"""
    out = {}
    for fname, lst in src.items():
        for obj in lst:
            for n, _, _, dn in entries(obj):
                if dn and dn != n:
                    out[n] = dn
    return out

def fmt(ts):
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d") if ts else "-"

def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    src = load_sources(sys.argv[1])
    outdir = sys.argv[2] if len(sys.argv) > 2 else "ig_report"
    os.makedirs(outdir, exist_ok=True)

    followers = collect(src, "followers")
    following = collect(src, "following")
    unfollowed = collect(src, "recently_unfollowed")
    pending = collect(src, "pending_follow_requests")
    if not followers and not following:
        sys.exit("找不到 followers / following 檔案，請確認匯出格式是 JSON。")

    not_back = {n: v for n, v in following.items() if n not in followers}   # 我追他，他沒追我
    fans = {n: v for n, v in followers.items() if n not in following}       # 他追我，我沒追他
    mutual = {n: v for n, v in followers.items() if n in following}

    # 快照與歷史比對（退追者 = 上次有、這次沒有的追蹤者）
    snapdir = os.path.join(outdir, "snapshots")
    os.makedirs(snapdir, exist_ok=True)
    prev_files = sorted(glob.glob(os.path.join(snapdir, "*.json")))
    new_followers, lost_followers, lost_following = [], [], []
    if prev_files:
        prev = json.load(open(prev_files[-1], encoding="utf-8"))
        pf, pg = set(prev["followers"]), set(prev["following"])
        new_followers = sorted(set(followers) - pf)
        lost_followers = sorted(pf - set(followers))
        lost_following = sorted(pg - set(following))
        prev_date = os.path.basename(prev_files[-1])[:-5]
    else:
        prev_date = None
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    json.dump({"followers": list(followers), "following": list(following)},
              open(os.path.join(snapdir, stamp + ".json"), "w", encoding="utf-8"), ensure_ascii=False)

    def table(title, d, desc, sort_by_ts=True):
        rows = sorted(d.items(), key=lambda kv: kv[1][0], reverse=True) if isinstance(d, dict) else d
        body = "".join(
            f'<tr><td><a href="{escape(h)}" target="_blank">@{escape(n)}</a></td><td>{fmt(ts)}</td></tr>'
            for n, (ts, h) in rows)
        return f"<section><h2>{title} ({len(rows)})</h2><p>{desc}</p><table><tr><th>帳號</th><th>日期</th></tr>{body}</table></section>"

    def names_table(title, names, desc):
        body = "".join(f'<tr><td><a href="https://www.instagram.com/{escape(n)}" target="_blank">@{escape(n)}</a></td></tr>' for n in names)
        return f"<section><h2>{title} ({len(names)})</h2><p>{desc}</p><table><tr><th>帳號</th></tr>{body}</table></section>"

    parts = [
        table("我追蹤、但對方沒回追", not_back, "日期 = 你追蹤他的時間"),
        table("對方追蹤我、但我沒回追", fans, "日期 = 他追蹤你的時間"),
        table("互相追蹤", mutual, ""),
    ]
    if unfollowed:
        parts.append(table("你最近取消追蹤的帳號", unfollowed, "來自 IG 官方紀錄"))
    if pending:
        parts.append(table("待處理的追蹤請求", pending, ""))
    if prev_date:
        parts.append(names_table(f"退追你的人（對比 {prev_date}）", lost_followers, "上次是你的追蹤者，現在不是"))
        parts.append(names_table("新追蹤你的人", new_followers, ""))
        parts.append(names_table("你不再追蹤的人", lost_following, ""))
    else:
        parts.append("<section><h2>退追紀錄</h2><p>這是第一次分析，已存下快照。之後用新的匯出檔再跑一次，就會列出退追者與新追蹤者。</p></section>")

    html = f"""<!doctype html><meta charset="utf-8"><title>IG 追蹤分析</title>
<style>body{{font-family:-apple-system,sans-serif;max-width:760px;margin:2em auto;padding:0 1em}}
table{{border-collapse:collapse;width:100%}}td,th{{border-bottom:1px solid #ddd;padding:6px;text-align:left}}
.sum span{{display:inline-block;margin-right:1.5em}}</style>
<h1>IG 追蹤分析</h1>
<p class="sum"><span>追蹤者 <b>{len(followers)}</b></span><span>追蹤中 <b>{len(following)}</b></span>
<span>互相追蹤 <b>{len(mutual)}</b></span></p>{''.join(parts)}"""
    out = os.path.join(outdir, "report.html")
    open(out, "w", encoding="utf-8").write(html)

    print(f"追蹤者 {len(followers)}｜追蹤中 {len(following)}｜互相追蹤 {len(mutual)}")
    print(f"我追蹤但沒回追我：{len(not_back)}")
    print(f"追蹤我但我沒回追：{len(fans)}")
    print(f"你取消追蹤的紀錄：{len(unfollowed)}")
    if prev_date:
        print(f"退追你的人：{len(lost_followers)}｜新追蹤：{len(new_followers)}")
    print(f"報告：{out}")

if __name__ == "__main__":
    main()
