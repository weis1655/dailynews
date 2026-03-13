#!/usr/bin/env python3
"""每日新闻简报生成器。

- 抓取多个权威媒体 RSS/Atom
- 筛选近24小时相关新闻
- 聚焦：中国政治 / 世界战争格局 / 全球人工智能产业发展
- 可选调用 OpenAI 生成高密度简报，失败时自动降级本地模板
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import os
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Iterable, List

RSS_SOURCES = {
    "新华社": "https://www.xinhuanet.com/politics/news_politics.xml",
    "人民网": "http://politics.people.com.cn/GB/1024/rss.xml",
    "Reuters World": "https://feeds.reuters.com/reuters/worldNews",
    "AP News": "https://feeds.apnews.com/apf-topnews",
    "BBC World": "http://feeds.bbci.co.uk/news/world/rss.xml",
    "Financial Times": "https://www.ft.com/world?format=rss",
    "MIT Technology Review": "https://www.technologyreview.com/feed/",
    "VentureBeat AI": "https://venturebeat.com/category/ai/feed/",
}

CATEGORY_KEYWORDS = {
    "中国政治": ["中国", "中共中央", "国务院", "人大", "政协", "外交部", "北京", "china", "beijing"],
    "世界战争格局": ["war", "conflict", "military", "missile", "ukraine", "russia", "israel", "gaza", "nato", "ceasefire", "乌克兰", "加沙", "战"],
    "全球人工智能产业发展": ["ai", "artificial intelligence", "大模型", "chip", "nvidia", "openai", "anthropic", "算力", "模型", "llm"],
}

CATEGORY_PRIORITY = {
    "中国政治": 3,
    "世界战争格局": 3,
    "全球人工智能产业发展": 3,
}


def strip_html(text: str) -> str:
    text = unescape(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


@dataclasses.dataclass
class Article:
    source: str
    title: str
    link: str
    summary: str
    published: dt.datetime
    category: str
    score: int

    def as_prompt_dict(self) -> dict:
        return {
            "source": self.source,
            "title": self.title,
            "summary": self.summary,
            "published": self.published.isoformat(),
            "category": self.category,
            "link": self.link,
            "score": self.score,
        }


def http_get(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (dailynews-bot)",
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _find_text(node: ET.Element, paths: list[str]) -> str:
    for p in paths:
        found = node.find(p)
        if found is not None and found.text:
            return found.text.strip()
    return ""


def parse_feed(xml_bytes: bytes) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "content": "http://purl.org/rss/1.0/modules/content/",
        "dc": "http://purl.org/dc/elements/1.1/",
    }

    items: list[dict] = []

    for node in root.findall(".//item"):
        title = _find_text(node, ["title"])
        link = _find_text(node, ["link"])
        summary = _find_text(node, ["description", "content:encoded"]) or ""
        pub = _find_text(node, ["pubDate", "dc:date", "date"])
        items.append({"title": title, "link": link, "summary": summary, "published": pub})

    for node in root.findall(".//atom:entry", ns):
        title = _find_text(node, ["atom:title"])
        summary = _find_text(node, ["atom:summary", "atom:content"])
        pub = _find_text(node, ["atom:published", "atom:updated"])
        link = ""
        link_node = node.find("atom:link", ns)
        if link_node is not None:
            link = (link_node.attrib.get("href") or "").strip()
        items.append({"title": title, "link": link, "summary": summary, "published": pub})

    return items


def parse_datetime(value: str) -> dt.datetime | None:
    if not value:
        return None
    value = value.strip()

    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc)
    except Exception:
        pass

    formats = (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
    )
    for fmt in formats:
        try:
            parsed = dt.datetime.strptime(value, fmt)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=dt.timezone.utc)
            return parsed.astimezone(dt.timezone.utc)
        except ValueError:
            continue
    return None


def classify_and_score(text: str) -> tuple[str | None, int]:
    text_lower = text.lower()
    best_category = None
    best_score = 0
    for category, keywords in CATEGORY_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw.lower() in text_lower)
        if score > best_score:
            best_category = category
            best_score = score
    if not best_category:
        return None, 0
    return best_category, best_score + CATEGORY_PRIORITY.get(best_category, 0)


def fetch_recent_articles(hours: int = 24) -> list[Article]:
    now = dt.datetime.now(dt.timezone.utc)
    earliest = now - dt.timedelta(hours=hours)
    collected: list[Article] = []

    for source, url in RSS_SOURCES.items():
        try:
            raw = http_get(url)
            entries = parse_feed(raw)
        except Exception as exc:
            print(f"[WARN] 抓取失败: {source} -> {exc}")
            continue

        for entry in entries:
            published = parse_datetime(entry.get("published", ""))
            if not published or published < earliest:
                continue

            title = strip_html(entry.get("title", ""))
            summary = strip_html(entry.get("summary", ""))
            link = (entry.get("link") or "").strip()
            if not title:
                continue

            category, score = classify_and_score(f"{title}\n{summary}")
            if not category:
                continue

            collected.append(
                Article(
                    source=source,
                    title=title,
                    link=link,
                    summary=summary,
                    published=published,
                    category=category,
                    score=score,
                )
            )

    dedup: list[Article] = []
    seen = set()
    for a in sorted(collected, key=lambda x: (x.score, x.published), reverse=True):
        key = (a.source, a.title)
        if key in seen:
            continue
        seen.add(key)
        dedup.append(a)
    return dedup


def build_prompt(articles: Iterable[Article]) -> str:
    payload = [a.as_prompt_dict() for a in articles]
    return (
        "你是一位资深国际新闻编辑，请仅根据输入新闻生成中文《每日新闻简报》。\n"
        "硬性要求：\n"
        "1) 不得编造输入中不存在的事实；\n"
        "2) 权威媒体优先，客观、简洁、信息密度高；\n"
        "3) 重点关注：中国政治、世界战争格局、全球人工智能产业发展；\n"
        "4) 输出严格遵循：\n"
        "【每日重点新闻】\n"
        "（选出当天最重要的1-3条新闻，并说明为什么重要）\n"
        "【新闻简报】\n"
        "1. 标题：\n   摘要：3句话概括新闻内容\n   影响：说明为什么值得关注\n"
        "共整理 10条重要新闻。\n\n"
        f"新闻数据(JSON)：\n{json.dumps(payload[:30], ensure_ascii=False)}"
    )


def generate_with_openai(prompt: str, model: str) -> str | None:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    body = json.dumps(
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
        data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
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
            f"   为什么重要：来源为{item.source}，属于{item.category}核心议题，且在近24小时内发布。"
        )

    lines.append("\n【新闻简报】")
    for idx, item in enumerate(chosen, 1):
        details = item.summary or "事件仍在发展中，官方与主流媒体后续信息值得跟踪。"
        lines.append(
            f"{idx}. 标题：{item.title}\n"
            f"   摘要：{item.source}发布该消息。核心信息显示：{details[:110]}。"
            "该事件在过去24小时内受到持续关注。\n"
            f"   影响：该动态与{item.category}相关，可能影响政策、地缘局势或产业预期。"
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
    print(f"[INFO] 定时模式已启动，每天 {at} 生成 -> {output}")
    while True:
        now = dt.datetime.now()
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if now >= target:
            target += dt.timedelta(days=1)
        sleep_seconds = (target - now).total_seconds()
        print(f"[INFO] 下次执行: {target.isoformat()}")
        time.sleep(max(sleep_seconds, 1))
        try:
            run_once(model=model, output=output)
            print("[INFO] 简报生成完成")
        except Exception as exc:
            print(f"[ERROR] 执行失败: {exc}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="每日新闻简报生成器")
    parser.add_argument("--model", default="gpt-4o-mini", help="OpenAI 模型名")
    parser.add_argument("--output", default="daily_news_briefing.md", help="输出文件")
    parser.add_argument("--daily", action="store_true", help="每天指定时间执行")
    parser.add_argument("--time", default="07:20", help="执行时间 HH:MM")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.daily:
        run_daily(model=args.model, output=args.output, at=args.time)
    else:
        print(run_once(model=args.model, output=args.output))


if __name__ == "__main__":
    main()
