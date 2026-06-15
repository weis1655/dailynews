# dailynews

每日新闻简报生成脚本（直接搜索版，不使用 RSS）：联网搜索最近 24 小时新闻，并按指定主题输出中文简报。

## 功能
- 通过 GDELT 新闻搜索 API 直接检索近 24 小时新闻（非 RSS）。
- 聚焦三大领域：
  - 中国政治
  - 世界战争格局
  - 全球人工智能产业发展
- 按媒体域名做“权威媒体优先”排序（Reuters、AP、BBC、FT、新华社、人民网等优先）。
- 支持 OpenAI / SCNet 模型生成；失败自动回退本地模板。
- 支持每天 **07:20** 自动执行。

## 环境
- Python 3.10+
- 默认无第三方依赖

## 使用
### 单次执行
```bash
python3 daily_briefing.py --output daily_news_briefing.md
```

### 指定模型服务商
```bash
# 自动尝试（默认）：先 OpenAI，再 SCNet
python3 daily_briefing.py --provider auto --model gpt-4o-mini

# 仅 OpenAI
python3 daily_briefing.py --provider openai --model gpt-4o-mini

# 仅 SCNet
python3 daily_briefing.py --provider scnet --model <scnet_model_name>
```

### 常驻定时（每天 07:20）
```bash
python3 daily_briefing.py --daily --time 07:20 --output daily_news_briefing.md
```

### 推荐：使用 crontab 每天 07:20 触发
```bash
20 7 * * * cd /workspace/dailynews && /usr/bin/python3 daily_briefing.py --output daily_news_briefing.md >> cron.log 2>&1
```

## 模型配置
### OpenAI
```bash
export OPENAI_API_KEY="your_key"
export OPENAI_BASE_URL="https://api.openai.com/v1"  # 可选
```

### SCNet（方式一：OpenAI SDK）
根据你的说明：
- `base_url: https://api.scnet.cn/api/llm`
- `api_key: your_api_key`
- `model: 平台提供的模型名称`
- OpenAI SDK 会自动补 `/v1`，所以 base_url **不要包含 `/v1`**。

本脚本不是直接使用 OpenAI SDK，但兼容这一约定：
```bash
export SCNET_API_KEY="your_api_key"
export SCNET_BASE_URL_SDK="https://api.scnet.cn/api/llm"
python3 daily_briefing.py --provider scnet --model <scnet_model_name>
```

### SCNet（方式二：直接 HTTP 调用）
根据你的说明：
- `base_url: https://api.scnet.cn/api/llm/v1`
- 完整请求：`POST https://api.scnet.cn/api/llm/v1/chat/completions`

本脚本默认即按该方式调用：
```bash
export SCNET_API_KEY="your_api_key"
# 可选：若你有代理网关，可覆盖默认地址
export SCNET_BASE_URL_HTTP="https://api.scnet.cn/api/llm/v1"
python3 daily_briefing.py --provider scnet --model <scnet_model_name>
```

## 说明
- 已按你的要求改为“直接搜索”方案，不依赖 RSS 源。
- 若运行环境限制外网访问，脚本会记录告警并输出结构化降级结果，保证自动任务不中断。
