"""
推送今天的板块分析报告
"""
import os
from dotenv import load_dotenv
load_dotenv()

from modules.sector.analyzer import sector_analyzer
from notify.notifier import notifier

print('正在生成板块分析报告...')
result = sector_analyzer.run_daily_analysis()
report = sector_analyzer.format_daily_report(result)

print(f'报告长度: {len(report)} 字符')
print('正在推送到Telegram...')

notifier.send_sector_report(report)
print('✅ 推送完成，请查看Telegram')
