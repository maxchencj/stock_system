"""
GitHub 科技雷达 - 每日精选股票投资 / AI 科技相关开源项目
每天 8:40 推送到专用 Telegram Bot
"""
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict

import requests

from ai.analysis_engine import ai_engine
from config.settings import config
from notify.notifier import TelegramNotifier
from utils.logger import logger

_LOG_FILE = Path(__file__).parent.parent.parent / "data" / "github_trending_log.json"

_SYSTEM_PROMPT = """你是一位技术投资研究员，专注于股票量化投资和 AI 科技领域。"""

_USER_PROMPT_TMPL = """以下是今日 GitHub Trending 项目列表（JSON 格式）：
<projects>
{projects_json}
</projects>

请完成两件事：
1. 判断每个项目是否属于「股票投资/量化交易/金融科技」或「AI/大模型/智能体/机器学习」领域
2. 对命中的项目用中文写 2-3 句点评，说明它的用途和为什么值得关注

输出 JSON 格式（只输出 JSON，不要其他内容）：
{{
  "selected": [
    {{
      "full_name": "owner/repo",
      "category": "股票投资 | AI科技 | 两者兼有",
      "comment": "中文点评 2-3 句"
    }}
  ]
}}

只返回相关项目，不相关的直接忽略。如果没有相关项目，返回 {{"selected": []}}。"""


class _DedupeLog:
    """管理已推送记录，7 天内不重复推送同一仓库"""

    def __init__(self):
        self._data = self._load()

    def _load(self) -> Dict:
        if _LOG_FILE.exists():
            try:
                with open(_LOG_FILE) as f:
                    return json.load(f)
            except Exception:
                pass
        return {"pushed": []}

    def _save(self):
        _LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_LOG_FILE, "w") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def _cleanup(self):
        cutoff = (datetime.now() - timedelta(days=config.github_trending.dedup_days)).strftime("%Y-%m-%d")
        self._data["pushed"] = [
            r for r in self._data["pushed"] if r["date"] >= cutoff
        ]

    def already_pushed(self, full_name: str) -> bool:
        return any(r["full_name"] == full_name for r in self._data["pushed"])

    def mark_pushed(self, full_names: List[str]):
        today = datetime.now().strftime("%Y-%m-%d")
        self._cleanup()
        for name in full_names:
            if not self.already_pushed(name):
                self._data["pushed"].append({"full_name": name, "date": today})
        self._save()


class GitHubTrendingEngine:
    """GitHub 科技雷达引擎"""

    def __init__(self):
        self._bot = TelegramNotifier(
            token=config.github_trending.telegram_token,
            chat_id=config.github_trending.telegram_chat_id,
        )
        self._log = _DedupeLog()

    def _fetch_trending(self) -> List[Dict]:
        """从第三方 API 抓取今日 Trending 项目"""
        try:
            resp = requests.get(
                config.github_trending.trending_api_url,
                timeout=15,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            resp.raise_for_status()
            data = resp.json()
            projects = []
            for item in data:
                author = item.get("author", "")
                name = item.get("name", "")
                if not author or not name:
                    continue
                full_name = author + "/" + name
                projects.append({
                    "full_name": full_name,
                    "description": item.get("description", ""),
                    "language": item.get("language", ""),
                    "stars_today": item.get("currentPeriodStars", 0),
                    "topics": item.get("builtBy", []),
                    "url": item.get("url", f"https://github.com/{full_name}"),
                })
            logger.info(f"GitHub Trending 抓取成功，共 {len(projects)} 个项目")
            return projects
        except Exception as e:
            logger.error(f"GitHub Trending 抓取失败: {e}")
            return []

    def _ai_select(self, projects: List[Dict]) -> List[Dict]:
        """调用 DeepSeek 筛选相关项目并生成点评"""
        if not projects:
            return []

        slim = [
            {
                "full_name": p["full_name"],
                "description": p["description"],
                "language": p["language"],
                "stars_today": p["stars_today"],
                "url": p["url"],
            }
            for p in projects
        ]
        projects_json = json.dumps(slim, ensure_ascii=False, indent=2)
        user_prompt = _USER_PROMPT_TMPL.format(projects_json=projects_json)

        raw = ai_engine._call(_SYSTEM_PROMPT, user_prompt, max_tokens=2000, as_json=True)
        if not raw:
            return []
        try:
            result = json.loads(raw)
            return result.get("selected", [])
        except Exception as e:
            logger.error(f"解析 AI 结果失败: {e} | raw={raw[:200]}")
            return []

    def _build_message(self, selected: List[Dict], projects_by_name: Dict[str, Dict]) -> str:
        today = datetime.now().strftime("%Y-%m-%d")
        lines = [f"🔭 GitHub 科技雷达 · {today}\n"]
        for item in selected:
            meta = projects_by_name.get(item["full_name"], {})
            stars = meta.get("stars_today", 0)
            lang = meta.get("language", "") or "未知"
            url = meta.get("url", f"https://github.com/{item['full_name']}")
            category = item.get("category", "")
            comment = item.get("comment", "")
            lines.append(
                f"📦 {item['full_name']}\n"
                f"⭐ {stars:,} stars today · {lang}\n"
                f"🏷 {category}\n"
                f"💬 {comment}\n"
                f"🔗 {url}\n"
                f"──────────────────"
            )
        lines.append("\n查看更多: https://github.com/trending")
        return "\n".join(lines)

    def run(self):
        """执行每日 GitHub 科技雷达推送"""
        logger.info("GitHub 科技雷达任务开始")

        projects = self._fetch_trending()
        if not projects:
            logger.warning("Trending 数据为空，跳过今日推送")
            return

        # 过滤已推送
        new_projects = [p for p in projects if not self._log.already_pushed(p["full_name"])]
        logger.info(f"去重后剩余 {len(new_projects)} 个项目待分析")

        selected = self._ai_select(new_projects)
        if not selected:
            logger.info("AI 未筛出相关项目，今日不推送")
            return

        # 限制数量
        selected = selected[:config.github_trending.max_picks]

        projects_by_name = {p["full_name"]: p for p in projects}
        message = self._build_message(selected, projects_by_name)

        if not self._bot.enabled:
            logger.warning("GitHub Bot 未配置，仅打印消息:\n" + message)
        else:
            self._bot.send(message)

        self._log.mark_pushed([item["full_name"] for item in selected])
        logger.info(f"GitHub 科技雷达推送完成，共 {len(selected)} 个项目")


github_trending_engine = GitHubTrendingEngine()
