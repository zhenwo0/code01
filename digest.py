"""GitHub 高分项目日报（GitHub Actions 云端版）

筛选 GitHub 上 star 超过阈值的项目，跳过历史上已经发送过的仓库，
把新项目通过 SMTP 发到邮箱。

已发送记录保存在同目录 state.json，由工作流提交回仓库。
"""

import datetime
import html
import json
import os
import smtplib
import ssl
import sys
import time
import urllib.parse
import urllib.request
from email.header import Header
from email.mime.text import MIMEText

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(BASE_DIR, "state.json")

MAX_RESULTS = 1000      # GitHub 搜索接口最多返回 1000 条
PAGE_SIZE = 100


def env(name, default=""):
    return (os.environ.get(name) or default).strip()


def build_query():
    stars = int(env("MIN_STARS", "10000"))
    days = int(env("CREATED_DAYS", "0"))
    language = env("LANGUAGE")
    topic = env("TOPIC")

    parts = [f"stars:>{stars}"]
    if days > 0:
        since = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
        parts.append(f"created:>{since}")
    if language:
        parts.append(f"language:{language}")
    if topic:
        parts.append(f"topic:{topic}")
    return " ".join(parts), days, stars


def github_headers():
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "gh-digest-actions",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = env("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def fetch_page(query, page, retries=3):
    url = "https://api.github.com/search/repositories?" + urllib.parse.urlencode(
        {"q": query, "sort": "stars", "order": "desc",
         "per_page": str(PAGE_SIZE), "page": str(page)}
    )
    last_error = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=github_headers())
            with urllib.request.urlopen(req, timeout=40) as resp:
                return json.loads(resp.read().decode("utf-8")).get("items", [])
        except Exception as e:
            last_error = e
            print(f"  第 {page} 页读取失败（第 {attempt + 1} 次）：{type(e).__name__}")
            time.sleep(2 * (attempt + 1))
    raise last_error


def fetch_unseen(query, sent, want):
    """按 star 降序翻页，边取边筛，凑够 want 个未发送过的就停。"""
    unseen = []
    scanned = 0
    seen_names = set()

    for page in range(1, MAX_RESULTS // PAGE_SIZE + 1):
        if len(unseen) >= want:
            break
        batch = fetch_page(query, page)
        scanned += len(batch)
        for it in batch:
            name = it["full_name"]
            if name in seen_names:
                continue
            seen_names.add(name)
            if name not in sent:
                unseen.append(it)
        if len(batch) < PAGE_SIZE:
            break

    return unseen, scanned


def load_state():
    if not os.path.exists(STATE_PATH):
        return {"sent": []}
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            state = json.load(f)
        if not isinstance(state.get("sent"), list):
            state["sent"] = []
        return state
    except Exception:
        return {"sent": []}


def save_state(sent):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {"sent": sorted(sent), "updated": datetime.datetime.now().isoformat(timespec="seconds")},
            f, ensure_ascii=False, indent=2,
        )


def render(items, days, stars, skipped, restarted):
    if not items:
        return f"<h3>star &gt; {stars} 的新项目</h3><p>本轮没有未发送过的新项目。</p>"

    rows = []
    for it in items:
        desc = html.escape((it.get("description") or "").strip())
        lang = html.escape(it.get("language") or "-")
        rows.append(
            f"<li style='margin-bottom:12px'>"
            f"<a href=\"{it['html_url']}\" style='font-size:15px'>{html.escape(it['full_name'])}</a>"
            f" &nbsp;⭐ {it['stargazers_count']} &nbsp;{lang}"
            f"<br><span style='color:#666'>{desc}</span></li>"
        )

    note = ""
    if skipped:
        note += f"<p style='color:#999'>已跳过 {skipped} 个之前发送过的项目。</p>"
    if restarted:
        note += "<p style='color:#999'>候选池已轮完一轮，本轮重新开始记录。</p>"

    return (
        f"<h3>star &gt; {stars} 的新项目 Top {len(items)}</h3>"
        f"<ol>{''.join(rows)}</ol>"
        f"{note}"
        f"<p style='color:#999;font-size:12px'>按 star 总数降序，已发送过的项目不再重复</p>"
    )


def send_mail(host, port, user, password, to, subject, body_html):
    msg = MIMEText(body_html, "html", "utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = user
    msg["To"] = to

    context = ssl.create_default_context()
    if int(port) == 465:
        with smtplib.SMTP_SSL(host, int(port), timeout=30, context=context) as s:
            s.login(user, password)
            s.sendmail(user, [to], msg.as_string())
    else:
        with smtplib.SMTP(host, int(port), timeout=30) as s:
            s.starttls(context=context)
            s.login(user, password)
            s.sendmail(user, [to], msg.as_string())


def main():
    dry_run = env("DRY_RUN", "0") == "1"
    host = env("SMTP_HOST", "smtp.qq.com")
    port = env("SMTP_PORT", "465")
    user = env("SMTP_USER")
    password = env("SMTP_PASS")
    to = env("MAIL_TO") or user
    top_n = int(env("TOP_N", "10"))
    prefix = env("SUBJECT_PREFIX", "GitHub 高分项目日报")

    missing = [k for k, v in (("SMTP_HOST", host), ("SMTP_USER", user),
                              ("SMTP_PASS", password), ("MAIL_TO", to)) if not v]
    if missing and not dry_run:
        print("缺少环境变量：" + "、".join(missing))
        return 1

    query, days, stars = build_query()
    print(f"查询条件：{query}")

    state = load_state()
    sent = set(state["sent"])
    print(f"历史已发送：{len(sent)} 个")

    try:
        unseen, scanned = fetch_unseen(query, sent, top_n)
    except Exception as e:
        print(f"抓取 GitHub 失败：{type(e).__name__}: {e}")
        return 2

    skipped = scanned - len(unseen)
    print(f"扫描 {scanned} 个，其中未发送过 {len(unseen)} 个")

    restarted = False
    if not unseen and scanned:
        restarted = True
        sent = set()
        print("候选池已轮完一轮，重新开始记录")
        try:
            unseen, scanned = fetch_unseen(query, sent, top_n)
        except Exception as e:
            print(f"抓取 GitHub 失败：{type(e).__name__}: {e}")
            return 2
        skipped = 0

    picks = unseen[:top_n]
    if not picks:
        print("没有可发送的新项目，本轮不发信")
        return 0

    for it in picks:
        print(f"  {it['full_name']} star={it['stargazers_count']} lang={it['language']}")

    if dry_run:
        print("DRY_RUN=1，只抓取不发信，不更新记录")
        return 0

    body = render(picks, days, stars, skipped, restarted)
    subject = f"{prefix} {datetime.date.today().isoformat()}"

    try:
        send_mail(host, port, user, password, to, subject, body)
    except Exception as e:
        print(f"发送邮件失败：{type(e).__name__}: {e}")
        return 3

    sent.update(it["full_name"] for it in picks)
    save_state(sent)
    print(f"发送成功 → {to}，已记录 {len(picks)} 个新项目，累计 {len(sent)} 个")
    return 0


if __name__ == "__main__":
    sys.exit(main())
