"""
性能監控工具模塊，提供數據分析和圖表生成功能
"""
import os
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import datetime
from .logger import get_logger

logger = get_logger("performance_utils")

def get_performance_data(days: int = 7, task_type: Optional[str] = None) -> pd.DataFrame:
    """
    讀取性能數據日誌
    
    Args:
        days: 讀取最近多少天的數據
        task_type: 指定任務類型，None表示所有類型
        
    Returns:
        DataFrame: 性能數據
    """
    try:
        log_dir = Path("logs/performance")
        if not log_dir.exists():
            logger.warning("性能日誌目錄不存在")
            return pd.DataFrame()
            
        # 計算日期範圍
        today = datetime.datetime.now()
        date_list = [(today - datetime.timedelta(days=i)).strftime("%Y%m%d") for i in range(days)]
        
        # 讀取所有日期的日誌
        all_data = []
        for date in date_list:
            log_file = log_dir / f"perf_{date}.csv"
            if log_file.exists():
                try:
                    df = pd.read_csv(log_file)
                    all_data.append(df)
                except Exception as e:
                    logger.error(f"讀取性能日誌失敗: {log_file}, 錯誤: {e}")
        
        if not all_data:
            logger.warning("沒有找到性能數據")
            return pd.DataFrame()
            
        # 合併數據
        perf_data = pd.concat(all_data, ignore_index=True)
        
        # 過濾指定任務類型
        if task_type:
            perf_data = perf_data[perf_data["function"].str.contains(task_type)]
            
        return perf_data
    
    except Exception as e:
        logger.error(f"獲取性能數據時發生錯誤: {e}")
        return pd.DataFrame()

def generate_performance_charts(output_dir: str = "reports/performance", days: int = 7) -> bool:
    """
    生成性能監控圖表
    
    Args:
        output_dir: 輸出目錄
        days: 分析最近多少天的數據
        
    Returns:
        bool: 是否成功生成圖表
    """
    try:
        # 確保輸出目錄存在
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # 獲取數據
        df = get_performance_data(days)
        if df.empty:
            logger.warning("沒有可用的性能數據用於生成圖表")
            return False
            
        # 轉換時間戳為datetime
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        
        # 設置matplotlib風格
        plt.style.use("ggplot")
        
        # 圖表1: 各任務類型的執行時間對比
        if "elapsed_time" in df.columns and "function" in df.columns:
            task_time_data = df[df["elapsed_time"].notna()].groupby("function")["elapsed_time"].agg(['mean', 'min', 'max']).reset_index()
            
            plt.figure(figsize=(12, 6))
            bars = plt.bar(task_time_data["function"], task_time_data["mean"], yerr=task_time_data["max"]-task_time_data["min"])
            plt.xlabel("任務類型")
            plt.ylabel("執行時間 (秒)")
            plt.title("各類任務平均執行時間")
            plt.xticks(rotation=45)
            
            # 在柱狀圖上添加數值標籤
            for bar in bars:
                height = bar.get_height()
                plt.text(bar.get_x() + bar.get_width()/2., height + 0.1, f"{height:.2f}s", ha="center")
                
            plt.tight_layout()
            plt.savefig(output_path / "task_execution_time.png")
            plt.close()
            
        # 圖表2: FPY處理與FPY並行處理的效率對比
        fpy_data = df[df["function"].str.contains("fpy")]
        if not fpy_data.empty and "elapsed_time" in fpy_data.columns:
            fpy_comparison = fpy_data.groupby("function")["elapsed_time"].mean().reset_index()
            
            plt.figure(figsize=(10, 5))
            plt.bar(fpy_comparison["function"], fpy_comparison["elapsed_time"])
            plt.xlabel("處理方式")
            plt.ylabel("平均執行時間 (秒)")
            plt.title("FPY處理與並行處理效率對比")
            plt.tight_layout()
            plt.savefig(output_path / "fpy_comparison.png")
            plt.close()
            
        # 圖表3: 任務成功率統計
        if "status" in df.columns:
            status_counts = df.groupby(["function", "status"]).size().unstack(fill_value=0)
            
            # 計算成功率
            if "成功" in status_counts.columns and "錯誤" in status_counts.columns:
                total = status_counts.sum(axis=1)
                success_rate = (status_counts["成功"] / total * 100).fillna(0)
                
                plt.figure(figsize=(10, 5))
                plt.bar(success_rate.index, success_rate)
                plt.xlabel("任務類型")
                plt.ylabel("成功率 (%)")
                plt.title("各類任務成功率")
                plt.ylim(0, 100)
                plt.xticks(rotation=45)
                plt.tight_layout()
                plt.savefig(output_path / "task_success_rate.png")
                plt.close()
        
        # 生成性能報告HTML
        generate_performance_report(df, output_path)
        
        logger.info(f"已生成性能圖表: {output_path}")
        return True
        
    except Exception as e:
        logger.error(f"生成性能圖表時發生錯誤: {e}")
        return False

def generate_performance_report(df: pd.DataFrame, output_path: Path) -> bool:
    """
    生成性能報告HTML文件
    
    Args:
        df: 性能數據
        output_path: 輸出目錄
        
    Returns:
        bool: 是否成功生成報告
    """
    try:
        # 基本統計信息
        total_tasks = len(df)
        task_types = df["function"].unique()
        
        # 生成HTML
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>性能報告</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                h1, h2 {{ color: #333; }}
                table {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                th {{ background-color: #f2f2f2; }}
                tr:nth-child(even) {{ background-color: #f9f9f9; }}
                .chart {{ margin: 20px 0; max-width: 100%; }}
                .summary {{ background-color: #f0f8ff; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
            </style>
        </head>
        <body>
            <h1>FPY性能報告</h1>
            <div class="summary">
                <h2>摘要</h2>
                <p>總任務數: {total_tasks}</p>
                <p>任務類型: {", ".join(task_types)}</p>
                <p>報告生成時間: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
            </div>
            
            <h2>性能圖表</h2>
            <div class="chart">
                <h3>各類任務平均執行時間</h3>
                <img src="task_execution_time.png" alt="任務執行時間圖" style="max-width:100%;">
            </div>
            
            <div class="chart">
                <h3>FPY處理與並行處理效率對比</h3>
                <img src="fpy_comparison.png" alt="FPY對比圖" style="max-width:100%;">
            </div>
            
            <div class="chart">
                <h3>各類任務成功率</h3>
                <img src="task_success_rate.png" alt="任務成功率圖" style="max-width:100%;">
            </div>
        """
        
        # 添加數據表格
        if not df.empty:
            html_content += """
            <h2>詳細數據</h2>
            <table>
                <tr>
            """
            
            # 表頭
            for col in df.columns:
                html_content += f"<th>{col}</th>"
                
            html_content += "</tr>"
            
            # 數據行 (最多顯示100行)
            for _, row in df.head(100).iterrows():
                html_content += "<tr>"
                for col in df.columns:
                    html_content += f"<td>{row[col]}</td>"
                html_content += "</tr>"
                
            html_content += "</table>"
            
            if len(df) > 100:
                html_content += f"<p>僅顯示前100行，總計{len(df)}行數據</p>"
        
        html_content += """
        </body>
        </html>
        """
        
        # 保存HTML文件
        with open(output_path / "performance_report.html", "w", encoding="utf-8") as f:
            f.write(html_content)
            
        logger.info(f"已生成性能報告: {output_path}/performance_report.html")
        return True
        
    except Exception as e:
        logger.error(f"生成性能報告時發生錯誤: {e}")
        return False

def analyze_fpy_bottlenecks(days: int = 7) -> Dict[str, Any]:
    """
    分析FPY處理的瓶頸
    
    Args:
        days: 分析最近多少天的數據
        
    Returns:
        Dict: 分析結果
    """
    try:
        df = get_performance_data(days)
        if df.empty:
            return {"status": False, "message": "沒有可用的性能數據"}
            
        # 過濾FPY相關任務
        fpy_data = df[df["function"].str.contains("fpy")]
        if fpy_data.empty:
            return {"status": False, "message": "沒有FPY相關的性能數據"}
            
        # 按站點分組計算
        if "station" in fpy_data.columns and "elapsed_time" in fpy_data.columns:
            station_perf = fpy_data.groupby("station")["elapsed_time"].agg(['count', 'mean', 'min', 'max']).reset_index()
            station_perf = station_perf.sort_values('mean', ascending=False)
            
            # 找出耗時最長的站點
            if not station_perf.empty:
                slowest_station = station_perf.iloc[0]["station"]
                fastest_station = station_perf.iloc[-1]["station"]
                
                return {
                    "status": True,
                    "slowest_station": slowest_station,
                    "fastest_station": fastest_station,
                    "station_performance": station_perf.to_dict('records'),
                    "fpy_vs_parallel": fpy_data.groupby("function")["elapsed_time"].mean().to_dict(),
                    "total_fpy_tasks": len(fpy_data)
                }
        
        return {"status": False, "message": "無法計算站點性能數據"}
        
    except Exception as e:
        logger.error(f"分析FPY瓶頸時發生錯誤: {e}")
        return {"status": False, "message": f"分析錯誤: {str(e)}"} 