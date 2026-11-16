"""GitHub 高分项目日报（GitHub Actions 云端版）

从环境变量读取邮箱配置，筛选 GitHub 近期高 star 项目并发送邮件。
"""

import datetime
import html
import json
import os
import smtplib
import ssl
import sys
import urllib.parse
import urllib.request
from email.header import Header
from email.mime.text import MIMEText


def env(name, default=""):
    return (os.environ.get(name) or default).strip()


def build_query():
    days = int(env("CREATED_DAYS", "7"))
    stars = int(env("MIN_STARS", "100"))
    language = env("LANGUAGE")
    topic = env("TOPIC")

    since = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    parts = [f"created:>{since}", f"stars:>{stars}"]
    if language:
        parts.append(f"language:{language}")
    if topic:
        parts.append(f"topic:{topic}")
    return " ".join(parts), days, stars


def fetch_repos(query, top_n):
    url = "https://api.github.com/search/repositories?" + urllib.parse.urlencode(
        {"q": query, "sort": "stars", "order": "desc", "per_page": str(max(1, min(100, top_n)))}
    )
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "gh-digest-actions",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = env("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data.get("items", [])


def render(items, days, stars):
    if not items:
        return f"<h3>近 {days} 天新建、star &gt; {stars} 的项目</h3><p>本轮没有符合条件的项目。</p>"

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

    return (
        f"<h3>近 {days} 天新建、star &gt; {stars} 的项目 Top {len(items)}</h3>"
        f"<ol>{''.join(rows)}</ol>"
        f"<p style='color:#999;font-size:12px'>由 GitHub Actions 自动生成</p>"
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
    host = env("SMTP_HOST", "smtp.163.com")
    port = env("SMTP_PORT", "465")
    user = env("SMTP_USER")
    password = env("SMTP_PASS")
    to = env("MAIL_TO") or user
    top_n = int(env("TOP_N", "10"))
    prefix = env("SUBJECT_PREFIX", "GitHub 高分项目日报")

    missing = [k for k, v in (("SMTP_HOST", host), ("SMTP_USER", user),
                              ("SMTP_PASS", password), ("MAIL_TO", to)) if not v]
    if missing:
        print("缺少环境变量：" + "、".join(missing))
        return 1

    query, days, stars = build_query()
    print(f"查询条件：{query}")

    try:
        items = fetch_repos(query, top_n)
    except Exception as e:
        print(f"抓取 GitHub 失败：{type(e).__name__}: {e}")
        return 2

    print(f"抓到 {len(items)} 条")
    for it in items:
        print(f"  {it['full_name']} star={it['stargazers_count']} lang={it['language']}")

    body = render(items, days, stars)
    subject = f"{prefix} {datetime.date.today().isoformat()}"

    try:
        send_mail(host, port, user, password, to, subject, body)
    except Exception as e:
        print(f"发送邮件失败：{type(e).__name__}: {e}")
        return 3

    print(f"发送成功 → {to}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
