"""
publisher.py
智慧家庭防盜哨兵系統 - 邊緣端 (AI 哨兵)

功能摘要（防竊/ROI 入侵偵測情境）：
1. 使用 OpenCV + YOLOv8n 偵測人員。
2. 在畫面中央定義「警戒區 (ROI)」，以綠框標示；若有人「中心點」進入 ROI，框線轉紅並觸發警報。
3. 觸發時：存證拍照 (evidence/)，並透過 MQTT 發送 INTRUSION 通報。
4. 冷卻 5 秒避免重複存檔與洗版。

環境需求：
- pip install ultralytics opencv-python paho-mqtt
- 需有攝影機裝置，並能連線到公開 broker test.mosquitto.org
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2
import paho.mqtt.client as mqtt
from ultralytics import YOLO


# ====== 可調整參數 ======
BROKER_HOST = "test.mosquitto.org"
BROKER_PORT = 1883
MQTT_TOPIC = "home/security/alert"
CONF_THRESHOLD = 0.5            # YOLO 信心度門檻
COOLDOWN_SECONDS = 5            # 冷卻時間（秒）避免洗版
MODEL_PATH = "yolov8n.pt"      # 輕量化模型，適合邊緣裝置
CAMERA_INDEX = 0                # 攝影機裝置編號
ROI_X1, ROI_Y1 = 100, 100       # 警戒區左上角座標
ROI_X2, ROI_Y2 = 500, 400       # 警戒區右下角座標
LOCATION_LABEL = "Living Room"  # 場域標記，會放入 MQTT payload
EVIDENCE_DIR = Path("evidence")  # 存證資料夾


def create_mqtt_client() -> mqtt.Client:
	"""建立並回傳已設定事件處理的 MQTT Client。"""

	client = mqtt.Client()

	def on_connect(client, userdata, flags, rc):
		# 繁體中文註解：當連上 broker 時會觸發此事件，rc==0 代表成功
		if rc == 0:
			print("[MQTT] 已連線到 broker")
		else:
			print(f"[MQTT] 連線失敗，rc={rc}")

	def on_disconnect(client, userdata, rc):
		# 繁體中文註解：當非預期斷線時 rc 會是非 0，這裡簡單提示並嘗試重連
		if rc != 0:
			print("[MQTT] 非預期斷線，嘗試重連...")
			try:
				client.reconnect()
			except Exception as e:  # noqa: BLE001 - demo 中直接打印
				print(f"[MQTT] 重連失敗: {e}")

	client.on_connect = on_connect
	client.on_disconnect = on_disconnect
	return client


def publish_alert(client: mqtt.Client, last_sent_ts: Optional[float]) -> float:
	"""
	發送入侵警報到 MQTT，並回傳此次送出時間戳。
	參數 last_sent_ts: 上一次送出的 Unix time，None 代表尚未送過。
	"""

	payload = {
		"status": "INTRUSION",
		"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
		"location": LOCATION_LABEL,
	}

	try:
		client.publish(MQTT_TOPIC, json.dumps(payload))
		print(f"[ALERT] 已發送入侵 MQTT 訊息: {payload}")
		return time.time()
	except Exception as e:  # noqa: BLE001 - demo 中直接打印
		print(f"[MQTT] 發送失敗: {e}")
		return last_sent_ts if last_sent_ts is not None else 0.0


def point_in_rect(cx: float, cy: float, x1: int, y1: int, x2: int, y2: int) -> bool:
	"""
	判斷點 (cx, cy) 是否在矩形 (x1, y1)-(x2, y2) 內（含邊界）。
	數學邏輯：若 x1 <= cx <= x2 且 y1 <= cy <= y2 則點落在矩形內。
	"""

	return (x1 <= cx <= x2) and (y1 <= cy <= y2)


def main():
	# 確保 evidence 資料夾存在，用來存放蒐證影像
	EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

	# 載入 YOLOv8 模型
	print("[YOLO] 載入模型中...首次執行可能需等待下載")
	model = YOLO(MODEL_PATH)

	# 啟動 MQTT 連線
	client = create_mqtt_client()
	try:
		client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
		client.loop_start()  # 背景執行接收/重連
	except Exception as e:  # noqa: BLE001
		print(f"[MQTT] 連線 broker 失敗: {e}")
		return

	# 開啟攝影機
	cap = cv2.VideoCapture(CAMERA_INDEX)
	if not cap.isOpened():
		print("[Camera] 無法開啟攝影機")
		return

	last_sent = None  # 上次發送/存證時間

	try:
		while True:
			ret, frame = cap.read()
			if not ret:
				print("[Camera] 無法讀取影像幀，稍後重試")
				time.sleep(0.5)
				continue

			# 預設 ROI 顏色為綠色，偵測到入侵時會改成紅色
			roi_color = (0, 255, 0)
			intrusion = False

			# YOLO 推論
			results = model(frame, verbose=False)

			for result in results:
				for box in result.boxes:
					cls_id = int(box.cls[0])
					conf = float(box.conf[0])
					label = model.names.get(cls_id, "unknown")

					if label != "person" or conf < CONF_THRESHOLD:
						continue

					# 取得邊界框與中心點
					x1, y1, x2, y2 = map(int, box.xyxy[0])
					cx = (x1 + x2) / 2
					cy = (y1 + y2) / 2

					# 繪出人員框與信心度
					cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
					cv2.putText(
						frame,
						f"Person {conf:.2f}",
						(x1, y1 - 10),
						cv2.FONT_HERSHEY_SIMPLEX,
						0.7,
						(0, 0, 255),
						2,
					)

					# 判斷「中心點是否落在 ROI」的數學邏輯：
					# 若 ROI_X1 <= cx <= ROI_X2 且 ROI_Y1 <= cy <= ROI_Y2，代表此人中心進入警戒區。
					if point_in_rect(cx, cy, ROI_X1, ROI_Y1, ROI_X2, ROI_Y2):
						intrusion = True
						roi_color = (0, 0, 255)  # 警戒區框改紅色

			# 繪製 ROI 框與標籤
			cv2.rectangle(frame, (ROI_X1, ROI_Y1), (ROI_X2, ROI_Y2), roi_color, 2)
			cv2.putText(
				frame,
				"Restricted Area",
				(ROI_X1, ROI_Y1 - 10),
				cv2.FONT_HERSHEY_SIMPLEX,
				0.7,
				roi_color,
				2,
			)

			now = time.time()
			if intrusion:
				# 顯示大字警告
				cv2.putText(
					frame,
					"INTRUDER ALERT!",
					(80, 80),
					cv2.FONT_HERSHEY_SIMPLEX,
					1.5,
					(0, 0, 255),
					3,
				)

				# 冷卻判斷：只有超過 COOLDOWN_SECONDS 才重新存證/發送
				if (last_sent is None) or (now - last_sent >= COOLDOWN_SECONDS):
					# 存證：檔名含時間戳
					ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
					filename = EVIDENCE_DIR / f"intruder_{ts_str}.jpg"
					try:
						cv2.imwrite(str(filename), frame)
						print(f"[EVIDENCE] 已存檔: {filename}")
					except Exception as e:  # noqa: BLE001
						print(f"[EVIDENCE] 存檔失敗: {e}")

					last_sent = publish_alert(client, last_sent)

			# 顯示影像，按 q 結束
			cv2.imshow("Smart Anti-Theft Sentinel", frame)
			if cv2.waitKey(1) & 0xFF == ord("q"):
				print("[System] 收到 q 指令，準備離開...")
				break

	except KeyboardInterrupt:
		print("[System] 偵測到 Ctrl+C，安全結束程式")
	except Exception as e:  # noqa: BLE001
		print(f"[System] 運行時發生錯誤: {e}")
	finally:
		cap.release()
		cv2.destroyAllWindows()
		client.loop_stop()
		client.disconnect()
		print("[System] 已關閉攝影機與 MQTT 連線")


if __name__ == "__main__":
	main()
