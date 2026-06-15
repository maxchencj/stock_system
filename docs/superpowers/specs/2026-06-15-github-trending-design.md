# GitHub 科技雷达 · 设计文档

**日期**: 2026-06-15  
**状态**: 已确认，待实现

---

## 一、功能目标

每日自动抓取 GitHub Trending 项目，由 DeepSeek AI 筛选出与**股票投资**或 **AI 科技**相关的优质项目，精选 3-5 个，附中文点评，每天 8:40 推送到专用 Telegram Bot。

---

## 二、架构

### 新增模块

```
stock_system/modules/github_trending/
├── __init__.py
└── trending_engine.py
```

模式与 `knowledge_engine`、`news_engine` 保持一致：单文件引擎，依赖 `ai_engine` 和 `notifier`。

### 数据流

```
第三方 Trending API (gh-trending-api.waite.men)
  → 获取当日 ~25 个项目（name, description, language, stars_today, topics, url）
  → 一次 DeepSeek 调用：批量分析所有项目
      · 判断相关性：股票投资 / AI科技 / 无关
      · 为命中项目输出中文点评（2-3 句）
  → 过滤近 7 天已推送项目（本地 JSON 去重）
  → 取 top 3-5 个
  → 推送到 GitHub Bot（专用 Telegram）
```

---

## 三、关键设计决策

| 项目 | 决策 | 原因 |
|------|------|------|
| Trending API | `https://github-trending-api.waite.men/repositories?language=&since=daily` | 免费公开，JSON 格式，无需 token |
| AI 引擎 | 复用 `ai_engine._call_api()`（DeepSeek） | 系统已有，无需新增依赖 |
| AI 调用次数 | 一次 prompt 处理全部 ~25 个项目 | 省 token，减少延迟 |
| 去重机制 | `data/github_trending_log.json`，记录已推送仓库 full_name，保留 7 天 |防止同一项目反复出现 |
| Telegram Bot | 独立第四个 Bot | 与 A股/美股/模拟盘频道分离，内容更聚焦 |
| 推送时间 | 每天 8:40，不限交易日 | GitHub Trending 与交易日无关 |
| 推送数量 | 3-5 个（AI 根据质量决定，无相关项目时不强推） | 宁缺毋滥 |
| 降级策略 | API 失败 / AI 失败 → 记录日志，跳过当天，不崩溃 | 健壮性 |

---

## 四、数据结构

### 去重日志 `data/github_trending_log.json`

```json
{
  "pushed": [
    {"full_name": "microsoft/graphrag", "date": "2026-06-15"},
    {"full_name": "BerriAI/litellm", "date": "2026-06-14"}
  ]
}
```

保留最近 7 天记录，旧记录自动清除。

---

## 五、DeepSeek Prompt 设计

```
你是一位技术投资研究员，专注于股票量化投资和 AI 科技领域。

以下是今日 GitHub Trending 项目列表（JSON 格式）：
<projects>
[{name, description, language, stars_today, topics, url}, ...]
</projects>

请完成两件事：
1. 判断每个项目是否属于「股票投资/量化交易/金融科技」或「AI/大模型/智能体」领域
2. 对命中的项目用中文写 2-3 句点评，说明它的用途和为什么值得关注

输出 JSON 格式：
{
  "selected": [
    {
      "full_name": "owner/repo",
      "category": "股票投资 | AI科技 | 两者兼有",
      "comment": "中文点评 2-3 句"
    }
  ]
}

只返回相关项目，不相关的直接忽略。如果没有相关项目，返回 {"selected": []}。
```

---

## 六、Telegram 推送格式

```
🔭 GitHub 科技雷达 · 2026-06-15

📦 owner/repo-name
⭐ 1,234 stars today · Python · 量化交易
🏷 AI科技
💬 基于 LLM 的多因子选股框架，支持 A 股数据直接接入。代码结构清晰，适合量化研究入门，也可作为生产环境基础框架扩展...

──────────────────
📦 ...

🔗 查看更多: https://github.com/trending
```

---

## 七、环境变量（`.env` 新增）

```bash
# GitHub 科技雷达 Bot
GITHUB_TELEGRAM_TOKEN=<新Bot token>
GITHUB_TELEGRAM_CHAT_ID=<chat_id>
```

---

## 八、调度器注册（`core/scheduler.py` 新增）

```python
# GitHub Trending 每日精选（每天 8:40）
self.scheduler.add_job(
    self.github_trending_task,
    CronTrigger(hour=8, minute=40),
    id="github_trending_daily",
    name="GitHub科技雷达",
    replace_existing=True
)
```

---

## 九、文件清单

| 文件 | 操作 |
|------|------|
| `modules/github_trending/__init__.py` | 新建 |
| `modules/github_trending/trending_engine.py` | 新建，核心逻辑 |
| `core/scheduler.py` | 新增定时任务 + task 方法 |
| `config/settings.py` | 新增 `GitHubTrendingConfig` |
| `.env.example` | 新增两个环境变量说明 |
| `data/github_trending_log.json` | 运行时自动创建 |
