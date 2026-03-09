# 股票分析系统 - 进程守护配置指南

## 方案一：使用 crontab（推荐）

### 1. 授权 Terminal 使用 crontab
在 macOS 上，需要先授权：
1. 打开"系统偏好设置" > "安全性与隐私" > "完全磁盘访问权限"
2. 点击左下角的锁图标解锁
3. 添加"终端"或你使用的终端应用
4. 重启终端

### 2. 安装 crontab 任务
```bash
cd /Users/maxchen/Desktop/claudeForStock/stock_system
crontab crontab_config.txt
```

### 3. 验证安装
```bash
crontab -l
```

应该看到：
```
*/5 * * * * cd /Users/maxchen/Desktop/claudeForStock/stock_system && ./watchdog.sh
0 4 * * * cd /Users/maxchen/Desktop/claudeForStock/stock_system && ./restart.sh >> logs/restart.log 2>&1
```

### 4. 说明
- 每5分钟检查一次系统是否运行，如果停止则自动启动
- 每天凌晨4点自动重启系统（清理内存）

---

## 方案二：手动管理（简单但需要手动）

### 启动系统
```bash
cd /Users/maxchen/Desktop/claudeForStock/stock_system
./restart.sh
```

### 检查系统状态
```bash
ps aux | grep "python3.*main.py" | grep -v grep
```

### 查看日志
```bash
tail -f logs/system_run.log
```

### 停止系统
```bash
pkill -f "python3.*main.py"
```

---

## 方案三：使用 launchd（macOS 原生，最稳定）

我可以帮你创建 launchd 配置文件，这是 macOS 推荐的方式。

---

## 当前状态

✅ 守护脚本已创建: `watchdog.sh`
✅ 重启脚本已创建: `restart.sh`
✅ Crontab配置已准备: `crontab_config.txt`

## 下一步

请选择一个方案：
1. 如果你想用 crontab，请按照"方案一"的步骤操作
2. 如果你想用 launchd（更稳定），告诉我，我帮你配置
3. 如果你想手动管理，使用"方案二"的命令

## 测试守护脚本

可以手动运行测试：
```bash
cd /Users/maxchen/Desktop/claudeForStock/stock_system
./watchdog.sh
cat logs/watchdog.log
```
