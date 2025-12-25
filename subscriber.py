"""
subscriber.py
智慧安防通報系統 - 監控端 (接收端)

功能摘要（智慧家庭防盜哨兵情境）：
1. 訂閱 MQTT Topic home/security/alert，接收邊緣哨兵的入侵警報。
2. 收到 JSON 且 status == "INTRUSION" 時，以紅字顯示緊急提示。
3. 選做：發出嗶聲提醒 (Windows winsound；其他平台用 '\a')，讓監控端迅速注意。


"""

import json
import sys
import time

import paho.mqtt.client as mqtt


# ====== 可調整參數 ======
BROKER_HOST = "test.mosquitto.org"
BROKER_PORT = 1883
MQTT_TOPIC = "home/security/alert"

# ANSI 顏色碼：紅色醒目文字
RED = "\033[91m"
RESET = "\033[0m"


def beep():
	"""發出提示音：Windows 優先使用 winsound，其餘平台用 bell 字元。"""

	try:
		import winsound

		winsound.Beep(1000, 300)  # 1000 Hz, 300ms
	except Exception:
		# 若 winsound 不可用，改用 ASCII Bell 字元；不保證所有終端機都會響
		print("\a", end="")


def create_mqtt_client() -> mqtt.Client:
	"""建立已綁定事件處理的 MQTT Client。"""

	client = mqtt.Client()

	def on_connect(client, userdata, flags, rc):
		# rc == 0 代表成功連線
		if rc == 0:
			print("[MQTT] 已連線，開始訂閱...")
			client.subscribe(MQTT_TOPIC)
		else:
			print(f"[MQTT] 連線失敗，rc={rc}")

	def on_disconnect(client, userdata, rc):
		# 繁體中文註解：非預期斷線時嘗試重連，避免程式直接退出
		if rc != 0:
			print("[MQTT] 非預期斷線，嘗試重連...")
			while True:
				try:
					client.reconnect()
					print("[MQTT] 重連成功")
					break
				except Exception as e:  # noqa: BLE001
					print(f"[MQTT] 重連失敗: {e}，5 秒後再試")
					time.sleep(5)

	def on_message(client, userdata, msg):
		# 繁體中文註解：每次收到訂閱訊息時觸發
		try:
			data = json.loads(msg.payload.decode("utf-8"))
		except Exception as e:  # noqa: BLE001
			print(f"[MQTT] 訊息解析失敗: {e}")
			return

		status = data.get("status", "")
		ts = data.get("timestamp", "未知時間")
		location = data.get("location", "未知位置")

		if status == "INTRUSION":
			# 收到入侵事件，紅色顯示並觸發嗶聲提醒
			print(f"{RED}[緊急] 偵測到入侵者！已觸發錄影蒐證。位置: {location} 時間: {ts}{RESET}")
			beep()
		else:
			print(f"[訊息] 收到非警報訊息: {data}")

	client.on_connect = on_connect
	client.on_disconnect = on_disconnect
	client.on_message = on_message
	return client


def main():
	client = create_mqtt_client()

	try:
		client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
	except Exception as e:  # noqa: BLE001
		print(f"[MQTT] 無法連線至 broker: {e}")
		sys.exit(1)

	# 繁體中文註解：loop_forever 會阻塞主執行緒並自動處理重連/訊息收發
	try:
		print("[System] 監聽中，按 Ctrl+C 可中止")
		client.loop_forever()
	except KeyboardInterrupt:
		print("\n[System] 收到 Ctrl+C，準備離開...")
	finally:
		client.disconnect()
		print("[System] 已關閉 MQTT 連線")


if __name__ == "__main__":
	main()
