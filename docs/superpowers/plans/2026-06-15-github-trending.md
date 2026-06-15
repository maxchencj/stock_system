# GitHub 科技雷达 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 每天 8:40 自动抓取 GitHub Trending，用 DeepSeek 筛出股票投资 / AI 科技相关项目 3-5 个，附中文点评推送到专用 Telegram Bot。

**Architecture:** 新建 `modules/github_trending/trending_engine.py` 独立模块，复用 `ai_engine._call()` 做 AI 分析，复用 `TelegramNotifier` 做推送，在 `scheduler.py` 注册 8:40 每日任务。去重日志存 `data/github_trending_log.json`，保留 7 天。

**Tech Stack:** Python requests（抓 Trending API）、DeepSeek via OpenAI SDK（已有）、APScheduler（已有）、Telegram Bot API（已有）

---

## 文件清单

| 文件 | 操作 | 职责 |
|------|------|------|
| `stock_system/modules/github_trending/__init__.py` | 新建 | 空包标识 |
| `stock_system/modules/github_trending/trending_engine.py` | 新建 | 核心逻辑：抓取→AI分析→去重→推送 |
| `stock_system/config/settings.py` | 修改 | 新增 `GitHubTrendingConfig` dataclass + 注册到 `SystemConfig` |
| `stock_system/core/scheduler.py` | 修改 | 新增 `github_trending_task()` 方法 + 注册 8:40 定时任务 |
| `stock_system/.env.example` | 修改 | 新增两个环境变量说明 |

---

## Task 1: 新增配置项

**Files:**
- Modify: `stock_system/config/settings.py`
- Modify: `stock_system/.env.example`

- [ ] **Step 1: 在 `settings.py` 的 `SimTradingConfig` 后面插入新 dataclass**

在 `stock_system/config/settings.py` 的第 146 行（`SimTradingConfig` 结束后）插入：

```python
@dataclass
class GitHubTrendingConfig:
    """GitHub 科技雷达配置"""
    telegram_token: str = os.getenv("GITHUB_TELEGRAM_TOKEN", "")
    telegram_chat_id: str = os.getenv("GITHUB_TELEGRAM_CHAT_ID", "")
    trending_api_url: str = "https://github-trending-api.waite.men/repositories?language=&since=daily"
    max_picks: int = 5
    min_picks: int = 3
    dedup_days: int = 7
```

- [ ] **Step 2: 在 `SystemConfig` dataclass 里注册新配置**

在 `SystemConfig` 的 `sim_trading` 字段后面加一行：

```python
    github_trending: GitHubTrendingConfig = field(default_factory=GitHubTrendingConfig)
```

- [ ] **Step 3: 在 `.env.example` 末尾追加环境变量说明**

在文件末尾追加：

```
# ═══════════════════════════════════════════════════════════
#  GitHub 科技雷达 Bot（可选）
# ═══════════════════════════════════════════════════════════
GITHUB_TELEGRAM_TOKEN=
GITHUB_TELEGRAM_CHAT_ID=
```

- [ ] **Step 4: 验证配置可以正常加载**

```bash
cd stock_system && python -c "from config.settings import config; print(config.github_trending)"
```

期望输出：`GitHubTrendingConfig(telegram_token='', telegram_chat_id='', ...)`

- [ ] **Step 5: Commit**

```bash
git add stock_system/config/settings.py stock_system/.env.example
git commit -m "feat(github-trending): 新增 GitHubTrendingConfig 配置项"
```

---

## Task 2: 创建核心引擎 `trending_engine.py`

**Files:**
- Create: `stock_system/modules/github_trending/__init__.py`
- Create: `stock_system/modules/github_trending/trending_engine.py`

- [ ] **Step 1: 创建空 `__init__.py`**

新建文件 `stock_system/modules/github_trending/__init__.py`，内容为空（0 字节）。

- [ ] **Step 2: 创建 `trending_engine.py`**

新建文件 `stock_system/modules/github_trending/trending_engine.py`，完整内容如下：

```python
"""
GitHub 科技雷达 - 每日精选股票投资 / AI 科技相关开源项目
每天 8:40 推送到专用 Telegram Bot
"""
import json
import time
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
                full_name = item.get("author", "") + "/" + item.get("name", "")
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
```

- [ ] **Step 3: 验证模块可以正常导入**

```bash
cd stock_system && python -c "from modules.github_trending.trending_engine import github_trending_engine; print('OK')"
```

期望输出：`AI 引擎已连接 DeepSeek: ...` 然后 `OK`，无报错。

- [ ] **Step 4: Commit**

```bash
git add stock_system/modules/github_trending/
git commit -m "feat(github-trending): 新增 GitHubTrendingEngine 核心模块"
```

---

## Task 3: 注册定时任务到调度器

**Files:**
- Modify: `stock_system/core/scheduler.py`

- [ ] **Step 1: 在 `scheduler.py` 顶部 import 区域添加引用**

找到文件开头的 import 区域，在现有业务模块 import 后（`from modules.stock_picker...` 等之后）加入：

```python
from modules.github_trending.trending_engine import github_trending_engine
```

- [ ] **Step 2: 在 `start()` 方法的定时任务注册区域添加新任务**

在 `# ── Phase 4：复盘 & 持仓` 区域之后（`daily_review` 注册代码之后）插入：

```python
        # GitHub 科技雷达（每天 8:40）
        self.scheduler.add_job(
            self.github_trending_task,
            CronTrigger(hour=8, minute=40),
            id="github_trending_daily",
            name="GitHub科技雷达",
            replace_existing=True
        )
```

- [ ] **Step 3: 在任务函数区域添加 `github_trending_task` 方法**

在 `daily_review_task` 方法定义之后添加：

```python
    def github_trending_task(self):
        """GitHub 科技雷达任务"""
        logger.info("执行定时任务: GitHub 科技雷达")
        try:
            github_trending_engine.run()
        except Exception as e:
            logger.error(f"GitHub 科技雷达任务失败: {e}", exc_info=True)
```

- [ ] **Step 4: 验证调度器可以正常启动并列出新任务**

```bash
cd stock_system && python -c "
from core.scheduler import TaskScheduler
s = TaskScheduler()
s.start()
jobs = [j.name for j in s.scheduler.get_jobs()]
print(jobs)
s.stop()
" 2>&1 | grep -E "GitHub|Error|error"
```

期望输出中包含：`GitHub科技雷达`

- [ ] **Step 5: Commit**

```bash
git add stock_system/core/scheduler.py
git commit -m "feat(github-trending): 注册 8:40 每日定时任务到调度器"
```

---

## Task 4: 手动触发冒烟测试

**Files:** 无新文件，验证整体链路

- [ ] **Step 1: 确认 `.env` 中填写了 Bot 配置（或跳过 Bot 仅验证日志）**

如果还没有 Bot token，引擎会打印消息到日志而非推送，仍可验证 AI 分析链路。

```bash
grep "GITHUB_TELEGRAM" stock_system/.env || echo "（未配置，将只打印日志）"
```

- [ ] **Step 2: 手动执行一次引擎**

```bash
cd stock_system && python -c "
from modules.github_trending.trending_engine import github_trending_engine
github_trending_engine.run()
"
```

期望日志输出顺序：
1. `GitHub Trending 抓取成功，共 XX 个项目`
2. `去重后剩余 XX 个项目待分析`
3. `GitHub 科技雷达推送完成，共 X 个项目` 或 `AI 未筛出相关项目，今日不推送`

如果 API 调用成功但 Bot 未配置，应看到消息内容打印在日志里而非报错。

- [ ] **Step 3: 验证去重日志已生成**

```bash
cat stock_system/../data/github_trending_log.json 2>/dev/null || cat data/github_trending_log.json
```

期望输出：包含 `pushed` 数组，有今日日期的记录。

- [ ] **Step 4: 再次手动触发，验证去重生效**

```bash
cd stock_system && python -c "
from modules.github_trending.trending_engine import github_trending_engine
github_trending_engine.run()
"
```

期望日志：`去重后剩余 0 个项目待分析`（或数量大幅减少），说明去重正常。

- [ ] **Step 5: Commit**

```bash
git add data/github_trending_log.json 2>/dev/null; git status
git commit -m "feat(github-trending): 完成冒烟测试，链路验证通过" --allow-empty
```

---

## 补充说明

### Bot 配置方式

如需使用独立 Bot，在 `.env` 中填写：

```
GITHUB_TELEGRAM_TOKEN=<BotFather 给的 token>
GITHUB_TELEGRAM_CHAT_ID=<目标 chat 的 ID>
```

不填则引擎仍会运行 AI 分析，只是结果打印到日志而非 Telegram。

### Trending API 备选

若 `github-trending-api.waite.men` 不可用，可替换 `trending_api_url` 为：
- `https://trendings.herokuapp.com/repo?l=&s=daily`
- `https://api.gtrend.app/repositories`

只需修改 `config.github_trending.trending_api_url` 即可，无需改引擎代码。
