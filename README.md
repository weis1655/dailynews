# dailynews

每日新闻简报生成脚本（**直接搜索版，不使用 RSS**）：联网搜索最近 24 小时新闻，并按指定主题输出中文简报。

## 功能
- 通过 GDELT 新闻搜索 API 直接检索近 24 小时新闻（非 RSS）。
- 聚焦三大领域：
  - 中国政治
  - 世界战争格局
  - 全球人工智能产业发展
- 按媒体域名做“权威媒体优先”排序（Reuters、AP、BBC、FT、新华社、人民网等优先）。
- 支持 OpenAI 生成高信息密度版本；若未配置 API Key 或调用失败，自动回退本地模板。
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
- 本项目已按你的要求改为“直接搜索”方案，不依赖 RSS 源。
- 若运行环境限制外网访问，脚本会记录告警并输出结构化降级结果，保证自动任务不中断。
