"""
Web Dashboard - FastAPI + ECharts
K线图表 + 板块分析 + 交易信号 + 回测
"""
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn
from datetime import datetime
from typing import Optional

from config.settings import config
from modules.stock_picker.picker import stock_picker
from modules.monitor.monitor import monitor
from modules.sector.analyzer import sector_analyzer
from data.data_service import market_service, sector_service
from utils.logger import logger


app = FastAPI(title="股票智能分析系统", version="1.0.0")

# 静态文件和模板
# app.mount("/static", StaticFiles(directory="web/static"), name="static")
templates = Jinja2Templates(directory="web/templates")


# ═══════════════════════════════════════════════════════════
#  API 接口
# ═══════════════════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """首页"""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/health")
async def health_check():
    """健康检查"""
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "monitor_running": monitor.running
    }


@app.get("/api/market/realtime")
async def get_market_realtime(codes: Optional[str] = None):
    """获取实时行情"""
    try:
        code_list = codes.split(",") if codes else None
        df = market_service.get_realtime_quotes(code_list)
        return JSONResponse(content={
            "success": True,
            "data": df.to_dict("records") if not df.empty else []
        })
    except Exception as e:
        logger.error(f"获取实时行情失败: {e}")
        return JSONResponse(content={"success": False, "error": str(e)}, status_code=500)


@app.get("/api/stock/history/{code}")
async def get_stock_history(code: str, days: int = 90):
    """获取历史K线"""
    try:
        df = market_service.get_history(code)
        if not df.empty:
            df = df.tail(days)
        return JSONResponse(content={
            "success": True,
            "data": df.to_dict("records") if not df.empty else []
        })
    except Exception as e:
        logger.error(f"获取{code}历史数据失败: {e}")
        return JSONResponse(content={"success": False, "error": str(e)}, status_code=500)


@app.get("/api/picker/scan")
async def run_stock_scan():
    """执行选股扫描"""
    try:
        result = stock_picker.run_daily_scan()
        return JSONResponse(content={"success": True, "data": result})
    except Exception as e:
        logger.error(f"选股扫描失败: {e}")
        return JSONResponse(content={"success": False, "error": str(e)}, status_code=500)


@app.get("/api/sector/analysis")
async def run_sector_analysis():
    """执行板块分析"""
    try:
        result = sector_analyzer.run_daily_analysis()
        return JSONResponse(content={"success": True, "data": result})
    except Exception as e:
        logger.error(f"板块分析失败: {e}")
        return JSONResponse(content={"success": False, "error": str(e)}, status_code=500)


@app.get("/api/sector/stocks/{sector_name}")
async def get_sector_stocks(sector_name: str):
    """获取板块成分股"""
    try:
        stocks = sector_analyzer.get_sector_stocks(sector_name)
        return JSONResponse(content={"success": True, "data": stocks})
    except Exception as e:
        logger.error(f"获取板块成分股失败: {e}")
        return JSONResponse(content={"success": False, "error": str(e)}, status_code=500)


@app.get("/api/monitor/watchlist")
async def get_watchlist():
    """获取自选股列表"""
    try:
        codes = monitor.get_watchlist()
        return JSONResponse(content={"success": True, "data": codes})
    except Exception as e:
        return JSONResponse(content={"success": False, "error": str(e)}, status_code=500)


@app.post("/api/monitor/watchlist/add/{code}")
async def add_to_watchlist(code: str):
    """添加自选股"""
    try:
        success = monitor.add_stock(code)
        return JSONResponse(content={"success": success})
    except Exception as e:
        return JSONResponse(content={"success": False, "error": str(e)}, status_code=500)


@app.delete("/api/monitor/watchlist/remove/{code}")
async def remove_from_watchlist(code: str):
    """移除自选股"""
    try:
        monitor.remove_stock(code)
        return JSONResponse(content={"success": True})
    except Exception as e:
        return JSONResponse(content={"success": False, "error": str(e)}, status_code=500)


@app.post("/api/monitor/start")
async def start_monitor():
    """启动监控"""
    try:
        monitor.start()
        return JSONResponse(content={"success": True, "message": "监控已启动"})
    except Exception as e:
        return JSONResponse(content={"success": False, "error": str(e)}, status_code=500)


@app.post("/api/monitor/stop")
async def stop_monitor():
    """停止监控"""
    try:
        monitor.stop()
        return JSONResponse(content={"success": True, "message": "监控已停止"})
    except Exception as e:
        return JSONResponse(content={"success": False, "error": str(e)}, status_code=500)


# ═══════════════════════════════════════════════════════════
#  启动服务
# ═══════════════════════════════════════════════════════════

def start_web_server():
    """启动Web服务"""
    logger.info(f"启动Web服务: http://{config.web.host}:{config.web.port}")
    uvicorn.run(
        app,
        host=config.web.host,
        port=config.web.port,
        log_level="info"
    )


if __name__ == "__main__":
    start_web_server()
