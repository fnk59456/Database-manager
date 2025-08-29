# 重試機制說明文檔

## 概述

重試機制是為了解決文件移動過程中因文件系統延遲、傳輸延遲等問題導致的隨機失敗。當移動失敗時，系統會自動將失敗的組件添加到重試隊列，並在設定的時間間隔後重新嘗試移動。

## 配置說明

### 1. settings.json 配置

在 `settings.json` 的 `auto_move` 部分添加以下配置：

```json
{
    "auto_move": {
        "enabled": true,
        "target_product": "i-Pixel",
        "immediate": {
            "enabled": true,
            "file_types": ["csv", "map"],
            "delay_minutes": 1
        },
        "delayed": {
            "enabled": true,
            "file_types": ["org", "roi"],
            "schedule": {
                "time": "10:39",
                "days": ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
            }
        },
        "retry_mechanism": {
            "enabled": true,
            "max_retry_count": 3,
            "retry_intervals_minutes": [5, 10, 15],
            "retry_on_partial_failure": true,
            "description": "移動失敗重試機制設定"
        }
    }
}
```

### 2. 配置參數說明

| 參數 | 類型 | 預設值 | 說明 |
|------|------|--------|------|
| `enabled` | boolean | true | 是否啟用重試機制 |
| `max_retry_count` | integer | 3 | 最大重試次數 |
| `retry_intervals_minutes` | array | [5, 10, 15] | 重試間隔時間（分鐘） |
| `retry_on_partial_failure` | boolean | true | 是否在部分失敗時重試 |

### 3. 重試間隔邏輯

- **第 1 次重試**：失敗後 5 分鐘
- **第 2 次重試**：失敗後 10 分鐘  
- **第 3 次重試**：失敗後 15 分鐘
- **超過最大次數**：不再重試

## 工作原理

### 1. 失敗檢測

當文件移動失敗時，系統會：

1. 記錄失敗原因和失敗的文件類型
2. 分析成功和失敗的文件
3. 將失敗的組件添加到重試隊列

### 2. 重試觸發

重試機制在以下時機觸發：

1. **延遲移動處理完成後**：檢查重試隊列
2. **發現準備重試的任務**：重新加入延遲移動隊列
3. **自動調度**：按照設定的時間間隔執行

### 3. 重試邏輯

```python
# 重試條件檢查
if retry_manager.is_retry_enabled():
    # 所有失敗都添加到重試隊列，包括 "找不到組件" 錯誤
    # 因為這可能是暫時性的檔案系統延遲或資料庫掃描時機問題
    retry_manager.add_retry_task(...)
```

## 使用場景

### 1. 文件系統延遲

**問題**：ORG 文件傳輸完成，但 ROI 還在生成中
**解決**：重試機制會等待 ROI 生成完成後重新嘗試移動

### 2. 網絡傳輸延遲

**問題**：大文件傳輸完成，但文件系統緩存還沒同步
**解決**：重試間隔給文件系統足夠時間同步

### 3. 部分成功情況

**問題**：ORG 移動成功，ROI 移動失敗
**解決**：重試時只移動失敗的 ROI 文件

## 監控和調試

### 1. 重試統計

```python
# 獲取重試統計信息
stats = retry_manager.get_retry_stats()
print(f"總重試任務數: {stats['total_retry_tasks']}")
print(f"準備重試的任務數: {stats['ready_for_retry']}")
```

### 2. 任務詳情

```python
# 查看具體任務信息
for task in stats['task_details']:
    print(f"組件: {task['component_id']}")
    print(f"嘗試次數: {task['attempt_count']}")
    print(f"下次重試時間: {task['next_retry_time']}")
    print(f"失敗原因: {task['failure_reason']}")
```

### 3. 日誌輸出

重試機制會輸出詳細的日誌信息：

```
🔄 重試隊列處理:
  準備重試的任務數: 2
  🔄 重試組件 WLPF80030001 (第 1 次嘗試)
  🔄 重試組件 WLPF80030002 (第 2 次嘗試)
  ✅ 已將 2 個重試任務重新加入延遲移動隊列
```

## 最佳實踐

### 1. 重試間隔設置

- **HDD 環境**：建議使用較長的間隔（5-15分鐘）
- **SSD 環境**：可以使用較短的間隔（2-8分鐘）
- **網絡環境**：根據網絡穩定性調整間隔

### 2. 最大重試次數

- **生產環境**：建議 3-5 次
- **測試環境**：可以使用較少次數（1-2次）
- **考慮因素**：文件大小、系統性能、業務需求

### 3. 監控建議

- 定期檢查重試統計信息
- 監控重試成功率
- 分析失敗原因，優化重試策略

## 故障排除

### 1. 重試機制不工作

**檢查項目**：
- 配置中的 `enabled` 是否為 `true`
- 重試間隔是否設置正確
- 日誌中是否有重試相關信息

### 2. 重試次數異常

**檢查項目**：
- `max_retry_count` 設置是否合理
- 失敗原因是否適合重試
- 組件是否已達到最大重試次數

### 3. 重試時間不準確

**檢查項目**：
- 系統時間是否準確
- 重試間隔配置是否正確
- 時區設置是否正確

## 測試

使用提供的測試腳本驗證重試機制：

```bash
cd dbmplus
python scripts/test_retry_mechanism.py
```

測試腳本會驗證：
- 配置載入
- 任務添加和更新
- 重試邏輯
- 任務管理功能

## 總結

重試機制通過智能的失敗檢測和自動重試，有效解決了文件移動過程中的隨機失敗問題。通過合理的配置和監控，可以大大提高文件移動的成功率，減少人工干預的需求。
