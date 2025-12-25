# Smart Anti-Theft Sentinel (AIoT)

以 OpenCV + YOLOv8n 為核心的智慧家庭防盜哨兵系統，透過 MQTT 通報入侵並自動存證。

## 功能
- ROI 警戒區：預設矩形 (100,100)-(500,400)，平時綠框，入侵時紅框。
- 入侵判斷：偵測到「人」時，計算人框中心點 `(cx, cy)`；若 `ROI_X1 <= cx <= ROI_X2` 且 `ROI_Y1 <= cy <= ROI_Y2`，視為入侵。
- 警報動作：
  - 螢幕顯示大紅字 `INTRUDER ALERT!`
  - 存證：影像存入 `evidence/`，檔名含時間戳
  - MQTT 通報：Topic `home/security/alert`，payload `{"status":"INTRUSION","timestamp":...,"location":"Living Room"}`
- 冷卻機制：5 秒內不重複發送/存證，避免洗版。
- 監控端：收到 INTRUSION 以紅字與嗶聲提示。

## 專案結構
```
publisher.py      # 邊緣端，攝影機偵測、ROI 入侵判斷、存證與 MQTT 發送
subscriber.py     # 監控端，訂閱 MQTT 並顯示/嗶聲警示
yolov8n.pt        # YOLOv8n 權重（需自行準備或首次自動下載）
evidence/         # 存證影像輸出資料夾（程式自動建立）
requirements.txt  # 依賴清單
```

## 安裝環境
建議使用虛擬環境，並安裝依賴：
```powershell
pip install -r requirements.txt
```

## 執行步驟
1) 啟動監控端（先開方便看訊息）
```powershell
python subscriber.py
```
2) 啟動哨兵端（需攝影機）
```powershell
python publisher.py
```
- 視窗按 `q` 離開。
- 入侵時 `evidence/` 會產生對應圖片，MQTT 發到 `test.mosquitto.org:1883` 的 `home/security/alert`。

## 重要參數 (publisher.py)
- `ROI_X1, ROI_Y1, ROI_X2, ROI_Y2`：警戒區座標，可依場域微調。
- `COOLDOWN_SECONDS`：冷卻時間，避免重複通報/存證。
- `LOCATION_LABEL`：通報內容的場域標籤。
- `CAMERA_INDEX`：攝影機裝置索引。

## 錯誤處理與穩定性
- MQTT 連線/斷線均有 try-except 並嘗試重連。
- 讀取影像失敗會等待再試。
- 存證失敗會提示原因。

## 備註
- 若第一次執行沒有 `yolov8n.pt`，Ultralytics 會自動下載。
- 公開 broker 僅供示範，正式環境請換為自架或有認證的 broker。
- Windows 下嗶聲使用 `winsound`，其他平台使用 `\a`，終端可能不一定響。