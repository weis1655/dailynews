#!/usr/bin/env python3
"""生成每日新闻简报。"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
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

KEYWORDS = {
    "中国政治": ["中国", "中共中央", "国务院", "人大", "政协", "外交部", "北京", "politics", "china"],
    "世界战争格局": ["war", "conflict", "military", "missile", "乌克兰", "俄", "以色列", "加沙", "北约", "停火", "战"],
    "全球人工智能产业发展": ["ai", "artificial intelligence", "大模型", "chip", "nvidia", "openai", "anthropic", "算力", "模型"],
}


@dataclasses.dataclass
class Article:
    source: str
    title: str
    link: str
    summary: str
    published: dt.datetime
    category: str

    def as_prompt_dict(self) -> dict:
        return dataclasses.asdict(self) | {"published": self.published.isoformat()}


def http_get(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "dailynews-bot/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def parse_rss(xml_bytes: bytes) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    items = []

    for tag in ("item", "{http://www.w3.org/2005/Atom}entry"):
        for node in root.iter(tag):
            title = (node.findtext("title") or "").strip()
            link = (node.findtext("link") or "").strip()
            summary = (node.findtext("description") or node.findtext("summary") or "").strip()
            pub = (
                node.findtext("pubDate")
                or node.findtext("published")
                or node.findtext("updated")
                or ""
            ).strip()

            if not link:
                link_node = node.find("link")
                if link_node is not None and isinstance(link_node.attrib, dict):
                    link = link_node.attrib.get("href", "").strip()

            items.append({"title": title, "link": link, "summary": summary, "published": pub})
    return items


def parse_datetime(value: str) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc)
    except Exception:
        pass

    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            parsed = dt.datetime.strptime(value, fmt)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=dt.timezone.utc)
            return parsed.astimezone(dt.timezone.utc)
        except ValueError:
            continue
    return None


def classify(text: str) -> str | None:
    text_lower = text.lower()
    for category, words in KEYWORDS.items():
        if any(w.lower() in text_lower for w in words):
            return category
    return None


def fetch_recent_articles(hours: int = 24) -> List[Article]:
    now = dt.datetime.now(dt.timezone.utc)
    earliest = now - dt.timedelta(hours=hours)
    collected: List[Article] = []

    for source, url in RSS_SOURCES.items():
        try:
            raw = http_get(url)
            entries = parse_rss(raw)
        except Exception as exc:
            print(f"[WARN] 抓取失败: {source} -> {exc}")
            continue

        for entry in entries:
            published = parse_datetime(entry["published"])
            if not published or published < earliest:
                continue
            title, summary, link = entry["title"], entry["summary"], entry["link"]
            category = classify(f"{title}\n{summary}")
            if not category or not title:
                continue
            collected.append(Article(source, title, link, summary, published, category))

    seen, deduped = set(), []
    for a in sorted(collected, key=lambda x: x.published, reverse=True):
        key = (a.source, a.title)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(a)
    return deduped


def build_prompt(articles: Iterable[Article]) -> str:
    payload = [a.as_prompt_dict() for a in articles]
    return (
        "你是一位资深国际新闻编辑，请基于给定新闻列表输出中文《每日新闻简报》。\n"
        "要求：权威媒体优先、客观简洁、信息密度高；\n"
        "重点：中国政治、世界战争格局、全球人工智能产业发展。\n"
        "输出格式：\n"
        "【每日重点新闻】\n"
        "（选出当天最重要的1-3条新闻，并说明为什么重要）\n"
        "【新闻简报】\n"
        "1. 标题：\n   摘要：3句话概括新闻内容\n   影响：说明为什么值得关注\n"
        "共整理 10条重要新闻。\n\n"
        f"新闻数据(JSON):\n{json.dumps(payload, ensure_ascii=False)}"
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


def local_fallback(articles: List[Article], total: int = 10) -> str:
    if not articles:
        return "【每日重点新闻】\n暂无可用新闻数据。\n\n【新闻简报】\n共整理 0条重要新闻。"

    chosen, highlights = articles[:total], articles[:3]
    lines = ["【每日重点新闻】"]
    for i, a in enumerate(highlights, 1):
        lines.append(f"{i}. {a.title}（{a.category}）\n   为什么重要：来自{a.source}，直接关联{a.category}，且属于近24小时动态。")

    lines.append("\n【新闻简报】")
    for i, a in enumerate(chosen, 1):
        brief = (a.summary or "事件仍在快速发展，更多细节待官方披露。").replace("\n", " ")
        lines.append(
            f"{i}. 标题：{a.title}\n"
            f"   摘要：该新闻由{a.source}发布。核心信息是：{brief[:90]}。"
            "该事件在近24小时内引发持续关注。\n"
            f"   影响：与{a.category}高度相关，可能影响政策走向、地缘安全或产业预期。"
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
        sleep_s = (target - now).total_seconds()
        print(f"[INFO] 下次执行: {target.isoformat()}")
        time.sleep(sleep_s)
        try:
            run_once(model=model, output=output)
            print("[INFO] 简报生成完成")
        except Exception as exc:
            print(f"[ERROR] 执行失败: {exc}")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="每日新闻简报生成器")
    p.add_argument("--model", default="gpt-4o-mini")
    p.add_argument("--output", default="daily_news_briefing.md")
    p.add_argument("--daily", action="store_true", help="每天指定时间执行")
    p.add_argument("--time", default="07:20", help="HH:MM")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    if args.daily:
        run_daily(model=args.model, output=args.output, at=args.time)
    else:
        print(run_once(model=args.model, output=args.output))


if __name__ == "__main__":
    main()
