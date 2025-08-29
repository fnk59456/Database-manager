# ROI 路徑修復總結

## 問題描述

用戶報告了持續的"隨機移動失敗"問題，具體表現為：
- 所有 5 個組件 (`WLPF80030001` 到 `WLPF80030005`) 都失敗
- 錯誤信息為 "找不到組件" (component not found)
- 用戶確認 `WLPF80030004` 的 ORG 和 ROI 數據確實存在於數據庫中

## 根本原因分析

通過代碼分析發現，問題出現在數據庫掃描機制中：

### 1. 數據庫緩存重建問題
- `scan_database()` 每 30 秒被調用，完全重建組件緩存
- 這會清除所有內存中的組件信息，包括文件路徑

### 2. 缺失的 ROI 文件檢查
- `_check_component_files()` 方法負責檢查組件的相關文件並設置路徑
- 該方法檢查了 `org`、`basemap`、`lossmap`、`fpy` 文件
- **但是缺少對 `roi` 文件的檢查**

### 3. 組件緩存不完整
- 即使 ROI 文件在磁盤上存在，組件對象的 `roi_path` 屬性也不會被設置
- 當延遲移動嘗試移動 ROI 文件時，無法找到完整的組件信息

## 修復方案

### 1. 添加 ROI 路徑屬性
在 `dbmplus/app/models/data_models.py` 中：
```python
@dataclass
class ComponentInfo:
    # ... 其他屬性 ...
    roi_path: Optional[str] = None  # 新增
    # ... 其他屬性 ...
```

### 2. 更新 to_dict 方法
```python
def to_dict(self) -> Dict[str, Any]:
    return {
        # ... 其他字段 ...
        "roi_path": self.roi_path,  # 新增
        # ... 其他字段 ...
    }
```

### 3. 添加 ROI 文件檢查
在 `dbmplus/app/models/database_manager.py` 的 `_check_component_files()` 方法中：
```python
def _check_component_files(self, component: ComponentInfo, product_id: str):
    # ... 其他檢查 ...
    
    # 檢查 roi 檔案
    roi_path = self.base_path / product_id / "roi" / lot_id / station / component_id
    if roi_path.exists() and roi_path.is_dir():
        component.roi_path = str(roi_path)
```

## 修復效果

### 修復前
- 組件緩存缺少 ROI 文件路徑信息
- 延遲移動時無法找到完整的組件信息
- 導致 "找不到組件" 錯誤

### 修復後
- 組件緩存包含完整的文件路徑信息（包括 ROI）
- 延遲移動可以正確識別和移動所有文件類型
- 解決了 "找不到組件" 錯誤的根本原因

## 測試驗證

創建了測試腳本 `test_standalone_roi_fix.py` 來驗證修復：
- ✅ ComponentInfo 類現在包含 roi_path 屬性
- ✅ roi_path 可以正確設置和獲取
- ✅ to_dict 方法包含 roi_path 字段
- ✅ update_paths 方法可以更新 roi_path
- ✅ 所有路徑屬性都存在

## 技術細節

### 文件路徑檢查邏輯
```python
# 檢查 roi 檔案
roi_path = self.base_path / product_id / "roi" / lot_id / station / component_id
if roi_path.exists() and roi_path.is_dir():
    component.roi_path = str(roi_path)
```

### 路徑生成邏輯
- 使用 `config.get_path()` 動態生成路徑
- 支持產品、批次、站點、組件的路徑模板
- 自動處理路徑分隔符和格式

## 預期結果

修復後，延遲移動功能應該能夠：
1. 正確識別所有組件的完整文件信息
2. 成功移動 ORG 和 ROI 文件
3. 不再出現 "找不到組件" 錯誤
4. 提高移動成功率，減少隨機失敗

## 注意事項

1. **數據庫掃描頻率**: 每 30 秒的掃描可能會影響性能，建議監控
2. **文件系統一致性**: 確保 ORG 和 ROI 文件在掃描時確實存在
3. **路徑權限**: 確保程序有讀取所有產品目錄的權限
4. **緩存持久化**: 考慮將組件緩存持久化到磁盤，減少重建開銷

## 後續建議

1. **監控移動成功率**: 觀察修復後的移動成功率變化
2. **性能優化**: 如果掃描頻率過高，考慮優化掃描邏輯
3. **錯誤處理增強**: 添加更詳細的錯誤日誌和重試機制
4. **測試覆蓋**: 在測試環境中驗證各種文件組合的移動情況

