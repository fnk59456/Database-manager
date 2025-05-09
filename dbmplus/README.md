# Database Manager Plus (DBM+)

改進版的半導體製造資料庫管理系統，用於追蹤和分析製造過程中的檢測數據。

## 功能特點

- **模組化設計**: 使用MVC架構，便於擴展和維護
- **多線程處理**: 使用背景線程處理大型數據集，避免UI凍結
- **任務管理**: 提供完整的任務管理，支援取消和進度顯示
- **統一配置**: 使用集中的配置管理
- **完善的記錄**: 詳細的日誌記錄，幫助診斷問題
- **資料快取**: 使用快取機制提高性能
- **直觀的UI**: 改進的用戶界面和反饋機制
- **數據備份**: 提供數據備份功能

## 安裝指南

### 系統要求

- Python 3.8+
- Windows 10 或更高版本

### 安裝步驟

1. 克隆或下載本倉庫：
   ```
   git clone https://github.com/your-username/dbmplus.git
   cd dbmplus
   ```

2. 創建並啟用虛擬環境（推薦）：
   ```
   python -m venv venv
   # Windows
   venv\Scripts\activate
   # Linux/Mac
   source venv/bin/activate
   ```

3. 安裝依賴：
   ```
   pip install -r requirements.txt
   ```

4. 配置設定：
   - 檢查 `config/settings.json`，確保資料庫路徑正確設置

5. 運行應用程式：
   ```
   python main.py
   ```

## 使用指南

### 主界面

應用程式主界面分為三個主要部分：

1. **產品資料表**：顯示所有產品和批次信息
2. **元件詳情**：顯示選中批次/站點的元件列表
3. **操作面板**：提供各種處理功能

### 基本操作

1. **瀏覽數據**
   - 點擊產品資料表中的項目以查看詳細信息
   - 點擊產品、批次或站點可查看對應元件

2. **數據處理**
   - 選擇產品、批次和站點後，使用底部按鈕進行處理
   - 生成 Basemap: 為選中站點生成基本缺陷地圖
   - 生成 Lossmap: 比較相鄰站點生成損失地圖
   - 生成 FPY: 計算並顯示優率數據

3. **刷新數據**
   - 使用"重新掃描資料"按鈕刷新數據庫視圖

## 自定義配置

主要配置文件位於 `config/settings.json`，可以修改以下設置：

- **資料庫路徑**: 修改 `database.base_path` 指向資料庫所在位置
- **處理邏輯**: 調整 `processing` 部分修改站點順序和處理邏輯
- **UI設置**: 在 `ui` 部分調整界面設置
- **日誌設置**: 在 `logging` 部分調整日誌行為

## 故障排除

常見問題:

1. **無法啟動應用程式**
   - 確認已安裝所有依賴
   - 檢查日誌文件 (`logs/app.log`) 查看詳細錯誤信息

2. **找不到數據**
   - 確認 `settings.json` 中的資料庫路徑設置正確
   - 使用"重新掃描資料"按鈕刷新資料庫視圖

3. **處理失敗**
   - 檢查日誌文件查看詳細錯誤信息
   - 確認選擇的站點有有效的數據
   - 對於 Lossmap，確保不是選擇第一站

## 開發人員文檔

詳細的設計文檔和API參考請查看 `docs/` 目錄。 