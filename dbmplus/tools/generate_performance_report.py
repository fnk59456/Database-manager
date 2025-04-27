#!/usr/bin/env python
"""
性能報告生成工具
用法: python generate_performance_report.py [--days 7] [--output reports/performance]
"""
import os
import sys
import argparse
from pathlib import Path
import datetime

# 確保可以導入應用程序模塊
script_dir = Path(__file__).resolve().parent
app_dir = script_dir.parent
sys.path.insert(0, str(app_dir))

from app.utils.performance_utils import generate_performance_charts, analyze_fpy_bottlenecks
from app.utils.logger import get_logger

logger = get_logger("perf_report")

def parse_args():
    """解析命令行參數"""
    parser = argparse.ArgumentParser(description="生成FPY性能報告")
    parser.add_argument("--days", type=int, default=7, help="分析最近幾天的數據 (默認: 7)")
    parser.add_argument("--output", type=str, default="reports/performance", help="報告輸出目錄 (默認: reports/performance)")
    return parser.parse_args()

def main():
    """主函數"""
    args = parse_args()
    
    logger.info(f"開始生成性能報告 (分析 {args.days} 天數據)")
    
    # 生成圖表和報告
    result = generate_performance_charts(args.output, args.days)
    
    if result:
        logger.info(f"性能報告生成成功，保存在: {args.output}")
        
        # 分析FPY瓶頸
        bottlenecks = analyze_fpy_bottlenecks(args.days)
        if bottlenecks["status"]:
            logger.info(f"FPY瓶頸分析:")
            logger.info(f"- 處理最慢站點: {bottlenecks['slowest_station']}")
            logger.info(f"- 處理最快站點: {bottlenecks['fastest_station']}")
            
            if "fpy_vs_parallel" in bottlenecks:
                for func, time in bottlenecks["fpy_vs_parallel"].items():
                    logger.info(f"- {func}: {time:.2f}秒")
        else:
            logger.warning(f"FPY瓶頸分析失敗: {bottlenecks['message']}")
    else:
        logger.error("性能報告生成失敗")
        
    return 0 if result else 1

if __name__ == "__main__":
    sys.exit(main()) 