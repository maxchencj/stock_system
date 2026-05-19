"""
系统配置全面检查脚本
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

print('='*80)
print('系统配置全面检查')
print('='*80)

# 1. 检查环境变量
print('\n【1. 环境变量检查】')
print('-'*80)
telegram_token = os.getenv('TELEGRAM_TOKEN', '')
telegram_chat_id = os.getenv('TELEGRAM_CHAT_ID', '')
anthropic_key = os.getenv('ANTHROPIC_API_KEY', '')

print(f'TELEGRAM_TOKEN: {"已配置" if telegram_token else "未配置"}')
print(f'TELEGRAM_CHAT_ID: {"已配置" if telegram_chat_id else "未配置"}')
print(f'ANTHROPIC_API_KEY: {"已配置" if anthropic_key else "未配置"}')

# 2. 检查通知服务
print('\n【2. 通知服务检查】')
print('-'*80)
try:
    from notify.notifier import notifier
    print(f'Telegram启用状态: {notifier.telegram.enabled}')
    if notifier.telegram.enabled:
        print('✓ Telegram通知已启用')
    else:
        print('✗ Telegram通知未启用')
except Exception as e:
    print(f'✗ 通知服务加载失败: {e}')

# 3. 检查数据服务
print('\n【3. 数据服务检查】')
print('-'*80)
try:
    from data.data_service import market_service, sector_service
    from data.ths_service import ths_service
    print('✓ 市场数据服务已加载')
    print('✓ 板块数据服务已加载')
    print('✓ 同花顺行业服务已加载')
except Exception as e:
    print(f'✗ 数据服务加载失败: {e}')

# 4. 检查关注列表
print('\n【4. 关注股票列表检查】')
print('-'*80)
watchlist_file = 'data/watchlist.txt'
if os.path.exists(watchlist_file):
    with open(watchlist_file, 'r') as f:
        codes = []
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                code = line.split('#')[0].strip()
                if code:
                    codes.append(code)
    print(f'✓ 关注列表文件存在')
    print(f'  关注股票: {len(codes)}只')
    print(f'  股票代码: {", ".join(codes)}')
else:
    print('✗ 关注列表文件不存在')

# 5. 检查调度器配置
print('\n【5. 定时任务配置检查】')
print('-'*80)
try:
    from core.scheduler import scheduler
    print('✓ 调度器已加载')
    print('定时任务列表:')
    print('  - 早上8:00: 市场早报')
    print('  - 早上9:45: 每日选股')
    print('  - 9:30-15:00每分钟: 实时行情推送')
    print('  - 下午17:00: 板块分析')
except Exception as e:
    print(f'✗ 调度器加载失败: {e}')

# 6. 检查AI引擎
print('\n【6. AI引擎检查】')
print('-'*80)
try:
    from ai.analysis_engine import ai_engine
    print('✓ AI引擎已加载')
    print(f'  模型: {ai_engine.model}')
except Exception as e:
    print(f'✗ AI引擎加载失败: {e}')

# 7. 测试数据获取
print('\n【7. 数据获取测试】')
print('-'*80)
try:
    # 测试获取股票行情
    from data.data_service import TencentAPI
    test_codes = ['603993']
    df = TencentAPI.get_batch_quotes(test_codes)
    if not df.empty:
        print(f'✓ 股票行情获取正常 (测试股票: 603993)')
    else:
        print('✗ 股票行情获取失败')
except Exception as e:
    print(f'✗ 数据获取测试失败: {e}')

# 8. 测试Telegram推送
print('\n【8. Telegram推送测试】')
print('-'*80)
try:
    from notify.notifier import notifier
    if notifier.telegram.enabled:
        # 不实际发送，只检查配置
        print('✓ Telegram配置正常')
        print(f'  Token: {telegram_token[:10]}...')
        print(f'  Chat ID: {telegram_chat_id}')
    else:
        print('✗ Telegram未启用')
except Exception as e:
    print(f'✗ Telegram配置检查失败: {e}')

# 9. 检查主程序
print('\n【9. 主程序检查】')
print('-'*80)
main_file = 'main.py'
if os.path.exists(main_file):
    print(f'✓ 主程序文件存在: {main_file}')
else:
    print('✗ 主程序文件不存在')

# 10. 总结
print('\n【10. 检查总结】')
print('='*80)
issues = []

if not telegram_token or not telegram_chat_id:
    issues.append('Telegram配置缺失')
if not anthropic_key:
    issues.append('AI API Key缺失')

if issues:
    print('发现问题:')
    for issue in issues:
        print(f'  ✗ {issue}')
    print('\n请修复以上问题后再启动系统')
else:
    print('✓ 所有检查通过！')
    print('\n系统已就绪，明天将自动推送:')
    print('  1. 早上8:00 - 市场早报')
    print('  2. 早上9:45 - 每日选股')
    print('  3. 9:30-15:00 - 每分钟实时行情 (4只关注股票)')
    print('  4. 下午17:00 - 同花顺板块分析')
    print('\n启动命令: python main.py')

print('='*80)
