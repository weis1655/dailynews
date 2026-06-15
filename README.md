# dailynews

每日新闻简报生成脚本：联网抓取最近 24 小时新闻，并按指定主题生成中文简报。

## 功能
- 优先抓取权威媒体 RSS/Atom（新华社、人民网、Reuters、AP、BBC、FT、MIT Tech Review 等）。
- 自动筛选近 24 小时新闻，并聚焦：
  - 中国政治
  - 世界战争格局
  - 全球人工智能产业发展
- 支持 OpenAI 生成高信息密度版本；若未配置 API Key 或调用失败，自动降级为本地模板输出。
- 支持固定格式输出：
  - `【每日重点新闻】`（1-3 条 + 重要性说明）
  - `【新闻简报】`（最多 10 条，含标题/3句摘要/影响）
- 支持每天 **07:20** 自动执行。

## 环境
- Python 3.10+
- 默认无第三方依赖

## 使用
### 单次执行
```bash
python3 daily_briefing.py --output daily_news_briefing.md
```

### 常驻定时（每天 07:20）
```bash
python3 daily_briefing.py --daily --time 07:20 --output daily_news_briefing.md
```

### 推荐：使用 crontab 每天 07:20 触发
```bash
20 7 * * * cd /workspace/dailynews && /usr/bin/python3 daily_briefing.py --output daily_news_briefing.md >> cron.log 2>&1
```

### 使用 OpenAI（可选）
```bash
export OPENAI_API_KEY="your_key"
# 可选：兼容自定义网关
export OPENAI_BASE_URL="https://api.openai.com/v1"
python3 daily_briefing.py --model gpt-4o-mini --output daily_news_briefing.md
```

## 说明
- 某些运行环境可能对外网 RSS 源有限制（如 403/proxy）。脚本会跳过失败源并继续处理其余源。
- 如果全部源都不可达，仍会输出格式完整的空结果，确保自动化任务不中断。
