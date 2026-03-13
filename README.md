# dailynews

每日新闻简报生成脚本：联网抓取最近24小时新闻，并按指定主题生成中文简报。

## 功能
- 权威媒体 RSS 抓取（中国政治、世界战争格局、全球 AI 产业）。
- 优先调用 OpenAI 生成高信息密度简报；无 API Key 时自动使用本地模板。
- 默认输出格式：
  - 【每日重点新闻】（1-3条 + 重要性说明）
  - 【新闻简报】（10条，含标题/3句摘要/影响）
- 支持每天早上 **07:20** 自动执行。

## 安装
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 使用
### 单次执行
```bash
python3 daily_briefing.py --output daily_news_briefing.md
```

### 每天 07:20 执行（脚本常驻）
```bash
python3 daily_briefing.py --daily --time 07:20 --output daily_news_briefing.md
```

### 使用 OpenAI（可选）
```bash
export OPENAI_API_KEY="your_key"
# 可选自定义兼容端点
export OPENAI_BASE_URL="https://api.openai.com/v1"
python3 daily_briefing.py --model gpt-4o-mini
```

## 用 crontab 每天 07:20 执行（推荐）
```bash
20 7 * * * cd /workspace/dailynews && /usr/bin/python3 daily_briefing.py --output daily_news_briefing.md >> cron.log 2>&1
```

> 如果未配置 OPENAI_API_KEY，程序会自动输出基于抓取内容的本地简报模板。
