# code01

GitHub 高分项目日报：每天北京时间 09:00 自动筛选 GitHub 上近期高 star 的项目，发送到邮箱。

## 工作方式

GitHub Actions 定时触发 `digest.py` → 调用 GitHub 搜索 API 筛项目 → 通过 SMTP 发 HTML 邮件。
不依赖任何本地电脑，关机也能跑。

## 必填的 4 个 Secrets

仓库 → Settings → Secrets and variables → Actions → New repository secret：

| 名称 | 填什么 | 示例 |
| --- | --- | --- |
| `SMTP_HOST` | 邮箱 SMTP 服务器 | `smtp.163.com` |
| `SMTP_USER` | 发信邮箱完整地址 | `xxx@163.com` |
| `SMTP_PASS` | 邮箱授权码（不是登录密码） | 一串字母数字 |
| `MAIL_TO` | 收件地址 | `xxx@163.com` |

授权码获取：

- 163 邮箱：设置 → POP3/SMTP/IMAP → 开启服务 → 获取授权码
- QQ 邮箱：设置 → 账户 → 开启 POP3/IMAP/SMTP 服务 → 生成授权码
- Gmail：开启两步验证 → 生成应用专用密码

## 手动测试

仓库 → Actions → 左侧 `github-high-score-mail` → 右侧 `Run workflow` → 跑完看日志。
日志会打印查询条件、抓到的条数，最后一行是 `发送成功 → 你的邮箱`。

## 调整筛选条件

编辑 `.github/workflows/daily.yml` 的 `env`：

| 变量 | 含义 | 默认 |
| --- | --- | --- |
| `CREATED_DAYS` | 只看最近几天新建 | `7` |
| `MIN_STARS` | star 下限 | `100` |
| `LANGUAGE` | 限定语言，如 `python` | 空（不限） |
| `TOPIC` | 限定话题，如 `llm` | 空（不限） |
| `TOP_N` | 每封最多几条 | `10` |

改发送时间：改 `cron: "0 1 * * *"`，注意这是 **UTC 时间**，北京时间要减 8 小时。

## 费用与限制

- 公开仓库的 Actions 免费额度足够（每月 2000 分钟，这个任务每天约 1 分钟）；
- GitHub 定时任务在高峰期可能延迟几分钟到几十分钟执行，属正常；
- 仓库连续 60 天无提交，GitHub 会自动暂停定时工作流，届时点一下启用即可。

## 常见问题

| 现象 | 原因 |
| --- | --- |
| `缺少环境变量` | Secrets 没配或名字拼错 |
| `Authentication failed` | `SMTP_PASS` 填了登录密码，不是授权码 |
| `Connection refused` | 端口用了 25，改成 465 |
| 收不到邮件 | 先查垃圾箱；确认 `MAIL_TO` 正确 |
