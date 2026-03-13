#!/usr/bin/env python3
"""每日新闻简报生成器（搜索版，非 RSS）。

核心能力：
- 通过 GDELT Doc API 直接搜索近 24 小时新闻（非 RSS）。
- 聚焦：中国政治、世界战争格局、全球人工智能产业发展。
- 优先权威媒体域名，按相关性和时效性排序。
- 可选调用 OpenAI 生成高信息密度中文简报；失败时回退本地模板。
- 支持每天 07:20 自动执行。
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import os
import time
import urllib.parse
import urllib.request
from typing import Iterable

GDELT_ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"

FOCUS_QUERIES = {
    "中国政治": '("China" OR 中国 OR 中共中央 OR 国务院 OR 全国人大 OR 全国政协 OR 外交部) AND (policy OR 政策 OR 政治)',
    "世界战争格局": '((war OR conflict OR ceasefire OR military OR missile OR invasion) OR (乌克兰 OR 俄乌 OR 加沙 OR 以色列 OR 北约))',
    "全球人工智能产业发展": '((AI OR "artificial intelligence" OR 大模型 OR 生成式AI OR chip OR NVIDIA OR OpenAI OR Anthropic) AND (industry OR investment OR 监管 OR 发布))',
}

AUTHORITATIVE_DOMAINS = {
    "xinhuanet.com": 8,
    "people.com.cn": 8,
    "news.cn": 8,
    "reuters.com": 8,
    "apnews.com": 7,
    "bbc.com": 7,
    "ft.com": 7,
    "wsj.com": 7,
    "nytimes.com": 7,
    "economist.com": 6,
    "technologyreview.com": 6,
    "bloomberg.com": 7,
}


@dataclasses.dataclass
class Article:
    category: str
    title: str
    url: str
    domain: str
    seendate: dt.datetime
    language: str
    sourcecountry: str
    score: float

    def as_prompt_dict(self) -> dict:
        return {
            "category": self.category,
            "title": self.title,
            "url": self.url,
            "domain": self.domain,
            "published": self.seendate.isoformat(),
            "language": self.language,
            "sourcecountry": self.sourcecountry,
            "score": round(self.score, 2),
        }


def http_get_json(url: str, params: dict[str, str], timeout: int = 25) -> dict:
    query = urllib.parse.urlencode(params)
    full_url = f"{url}?{query}"
    req = urllib.request.Request(
        full_url,
        headers={
            "User-Agent": "Mozilla/5.0 (dailynews-search-bot)",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def parse_seendate(value: str) -> dt.datetime | None:
    if not value:
        return None
    for fmt in ("%Y%m%dT%H%M%SZ", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            parsed = dt.datetime.strptime(value, fmt).replace(tzinfo=dt.timezone.utc)
            return parsed
        except ValueError:
            continue
    return None


def extract_domain(url: str) -> str:
    try:
        return urllib.parse.urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""


def source_weight(domain: str) -> int:
    if not domain:
        return 0
    for d, w in AUTHORITATIVE_DOMAINS.items():
        if domain == d or domain.endswith(f".{d}"):
            return w
    return 1


def relevance_boost(title: str, category: str) -> int:
    t = title.lower()
    if category == "中国政治":
        kws = ["china", "beijing", "ccp", "国务院", "中共中央", "外交部", "全国人大"]
    elif category == "世界战争格局":
        kws = ["war", "conflict", "ceasefire", "ukraine", "gaza", "israel", "nato", "missile", "乌克兰", "加沙"]
    else:
        kws = ["ai", "artificial intelligence", "model", "chip", "nvidia", "openai", "anthropic", "大模型", "算力"]
    return sum(1 for kw in kws if kw.lower() in t)


def search_category_news(category: str, query: str, hours: int = 24, maxrecords: int = 80) -> list[Article]:
    params = {
        "query": query,
        "mode": "ArtList",
        "format": "json",
        "sort": "HybridRel",
        "maxrecords": str(maxrecords),
        "timespan": f"{hours}h",
    }
    data = http_get_json(GDELT_ENDPOINT, params)
    now = dt.datetime.now(dt.timezone.utc)
    earliest = now - dt.timedelta(hours=hours)

    out: list[Article] = []
    for raw in data.get("articles", []):
        title = (raw.get("title") or "").strip()
        url = (raw.get("url") or "").strip()
        if not title or not url:
            continue

        seen = parse_seendate((raw.get("seendate") or "").strip())
        if not seen or seen < earliest:
            continue

        domain = extract_domain(url)
        rel = relevance_boost(title, category)
        src = source_weight(domain)
        age_h = max((now - seen).total_seconds() / 3600.0, 0.0)
        recency = max(0.0, 6.0 - min(age_h, 6.0))
        score = rel * 2.0 + src + recency

        out.append(
            Article(
                category=category,
                title=title,
                url=url,
                domain=domain,
                seendate=seen,
                language=(raw.get("language") or "").strip(),
                sourcecountry=(raw.get("sourcecountry") or "").strip(),
                score=score,
            )
        )
    return out


def fetch_recent_articles(hours: int = 24) -> list[Article]:
    combined: list[Article] = []
    for category, query in FOCUS_QUERIES.items():
        try:
            combined.extend(search_category_news(category=category, query=query, hours=hours))
        except Exception as exc:
            print(f"[WARN] 搜索失败: {category} -> {exc}")

    deduped: list[Article] = []
    seen = set()
    for item in sorted(combined, key=lambda x: (x.score, x.seendate), reverse=True):
        key = (item.domain, item.title.lower())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def build_prompt(articles: Iterable[Article]) -> str:
    payload = [a.as_prompt_dict() for a in articles]
    return (
        "你是一位资深国际新闻编辑，请基于给定新闻数据输出中文《每日新闻简报》。\n"
        "必须遵守：\n"
        "1) 只能使用输入事实，不得编造；\n"
        "2) 保持客观、简洁、信息密度高；\n"
        "3) 权威媒体优先；\n"
        "4) 聚焦：中国政治、世界战争格局、全球人工智能产业发展；\n"
        "5) 输出格式严格为：\n"
        "【每日重点新闻】\n"
        "（选出当天最重要的1-3条新闻，并说明为什么重要）\n"
        "【新闻简报】\n"
        "1. 标题：\n   摘要：3句话概括新闻内容\n   影响：说明为什么值得关注\n"
        "共整理 10条重要新闻。\n\n"
        f"新闻数据(JSON)：\n{json.dumps(payload[:40], ensure_ascii=False)}"
    )


def generate_with_openai(prompt: str, model: str) -> str | None:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    req_body = json.dumps(
        {
            "model": model,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": "你是严格遵守格式的中文新闻编辑。"},
                {"role": "user", "content": prompt},
            ],
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=req_body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        print(f"[WARN] OpenAI 生成失败，切换本地模板：{exc}")
        return None


def local_fallback(articles: list[Article], total: int = 10) -> str:
    if not articles:
        return "【每日重点新闻】\n暂无可用新闻数据。\n\n【新闻简报】\n共整理 0条重要新闻。"

    chosen = articles[:total]
    highlights = chosen[:3]

    lines = ["【每日重点新闻】"]
    for idx, item in enumerate(highlights, 1):
        lines.append(
            f"{idx}. {item.title}（{item.category}）\n"
            f"   为什么重要：来源域名 {item.domain}，属于{item.category}核心议题，且在近24小时内出现。"
        )

    lines.append("\n【新闻简报】")
    for idx, item in enumerate(chosen, 1):
        lines.append(
            f"{idx}. 标题：{item.title}\n"
            f"   摘要：该消息来自 {item.domain}，时间为 {item.seendate.isoformat()}。"
            f"内容归类为“{item.category}”，并在搜索排序中位于前列。"
            "该事件在近24小时内受到媒体持续关注。\n"
            f"   影响：可能对{item.category}相关的政策走向、国际局势或产业预期产生影响。"
        )

    lines.append(f"共整理 {len(chosen)}条重要新闻。")
    return "\n".join(lines)


def run_once(model: str, output: str) -> str:
    articles = fetch_recent_articles(hours=24)
    prompt = build_prompt(articles)
    report = generate_with_openai(prompt, model=model) or local_fallback(articles)
    with open(output, "w", encoding="utf-8") as f:
        f.write(report)
    return report


def run_daily(model: str, output: str, at: str = "07:20") -> None:
    hour, minute = map(int, at.split(":"))
    print(f"[INFO] 定时模式已启动：每天 {at} 生成 -> {output}")
    while True:
        now = dt.datetime.now()
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if now >= target:
            target += dt.timedelta(days=1)
        wait_seconds = max((target - now).total_seconds(), 1)
        print(f"[INFO] 下次执行时间：{target.isoformat()}")
        time.sleep(wait_seconds)
        try:
            run_once(model=model, output=output)
            print("[INFO] 简报生成完成")
        except Exception as exc:
            print(f"[ERROR] 定时执行失败：{exc}")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="每日新闻简报生成器（搜索版）")
    p.add_argument("--model", default="gpt-4o-mini", help="OpenAI 模型名")
    p.add_argument("--output", default="daily_news_briefing.md", help="输出文件路径")
    p.add_argument("--daily", action="store_true", help="每天指定时间执行")
    p.add_argument("--time", default="07:20", help="执行时间，格式 HH:MM")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    if args.daily:
        run_daily(model=args.model, output=args.output, at=args.time)
    else:
        print(run_once(model=args.model, output=args.output))


if __name__ == "__main__":
    main()
