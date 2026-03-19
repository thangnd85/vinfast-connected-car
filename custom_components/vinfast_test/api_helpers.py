import requests
import time
import uuid
import logging

_LOGGER = logging.getLogger(__name__)

def safe_float(val, default=0.0):
    try:
        if val is None or str(val).strip() == "": return default
        return float(val)
    except Exception: return default

def get_address_from_osm(lat, lon):
    try:
        res = requests.get(f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}&zoom=18", headers={"User-Agent": f"HA-VinFast-{uuid.uuid4().hex[:6]}"}, timeout=5)
        if res.status_code == 200: 
            addr = res.json().get("display_name")
            if addr and any(c.isalpha() for c in addr): return addr
    except Exception: pass
    return None

def get_weather_data(lat, lon):
    try:
        res = requests.get(f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true", timeout=10)
        if res.status_code == 200:
            data = res.json()
            current = data.get("current_weather", {})
            temp = current.get("temperature")
            wind = current.get("windspeed")
            code = current.get("weathercode", 0)
            
            if temp is not None:
                condition = "Trời quang"
                if code in [1, 2, 3]: condition = "Có mây"
                elif code in [45, 48]: condition = "Sương mù"
                elif code in [51, 53, 55, 61, 63, 65]: condition = "Mưa nhẹ"
                elif code in [80, 81, 82, 95, 96, 99]: condition = "Mưa rào/Giông"

                hvac = "Lý tưởng (Tiết kiệm Pin)"
                if temp > 35: hvac = "Làm mát Tối đa (Tốn Pin)"
                elif temp > 28: hvac = "Làm mát Trung bình"
                elif temp < 15: hvac = "Sưởi ấm Tối đa (Rất tốn Pin)"
                elif temp < 22: hvac = "Sưởi ấm Nhẹ"

                return {"temp": temp, "condition": f"{condition} (Gió {wind}km/h)", "hvac": hvac, "code": code}
    except Exception: pass
    return None

def get_osrm_route(lat1, lon1, lat2, lon2):
    try:
        url = f"http://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}?overview=full&geometries=geojson"
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            data = res.json()
            if data.get("code") == "Ok" and "routes" in data and len(data["routes"]) > 0:
                coords = data["routes"][0]["geometry"]["coordinates"]
                return [[p[1], p[0]] for p in coords]
    except Exception: pass
    return None

def snap_to_road(coords):
    if len(coords) < 3: return coords
    try:
        step = max(1, len(coords) // 90)
        sampled = coords[::step]
        if sampled[-1] != coords[-1]: sampled.append(coords[-1])
        coords_str = ";".join([f"{p[1]},{p[0]}" for p in sampled])
        url = f"http://router.project-osrm.org/match/v1/driving/{coords_str}?geometries=geojson&overview=full&tidy=true"
        
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            data = res.json()
            if data.get("code") == "Ok" and "matchings" in data and len(data["matchings"]) > 0:
                matched_coords = data["matchings"][0]["geometry"]["coordinates"]
                return [[p[1], p[0], 30] for p in matched_coords]
    except Exception: pass
    return coords

def get_ai_advice(api_key, ai_model, mode, data_payload, context_data):
    if not api_key or api_key.strip() == "": return "Vui lòng nhập Google Gemini API Key để AI đánh giá."
    temp = context_data.get("temp", "Không rõ")
    cond = context_data.get("cond", "Không rõ")
    hvac = context_data.get("hvac", "Bình thường")
    expected_km_per_1 = context_data.get("expected_km_per_1", 2.1)

    prompt = ""
    if mode == "weather" and data_payload:
        w_temp = data_payload.get('temp', temp)
        w_cond = data_payload.get('cond', cond)
        prompt = f"CẢNH BÁO THỜI TIẾT CỰC ĐOAN: Nhiệt độ ngoài trời đang là {w_temp} độ C, thời tiết: {w_cond}. Đóng vai chuyên gia AI của xe VinFast, viết MỘT câu tiếng Việt cực kỳ ngắn gọn (dưới 40 từ) khuyên tài xế cách chỉnh điều hòa và lái xe để an toàn và tiết kiệm pin nhất lúc này."
    elif mode == "anomaly" and data_payload:
        dist = round(data_payload.get('dist', 0), 2)
        spd = round(data_payload.get('speed', 0), 1)
        prompt = f"CẢNH BÁO HAO PIN: Xe điện vừa sụt 1% pin nhưng chỉ đi được {dist}km (mức chuẩn lý tưởng của nhà sản xuất công bố là {expected_km_per_1} km/1%). Tốc độ chạy trung bình lúc này: {spd}km/h. Tải điều hòa: {hvac}. Bạn hãy đóng vai Cố vấn AI trên xe, viết MỘT câu tiếng Việt cực kỳ ngắn gọn (dưới 40 từ) nhận xét nguyên nhân gây tốn pin (do tốc độ hay điều hòa) và đưa ra lời khuyên khẩn cấp."
    else:
        dist = data_payload.get('dist', 0) if data_payload else context_data.get("trip_dist", 0.0)
        drop = data_payload.get('drop', 0) if data_payload else 0
        if dist < 0.05: return f"Hệ thống đang đợi... Chuyến đi hiện tại ({dist}km) quá ngắn để phân tích."
        actual_km_per_1 = round(dist / drop, 2) if drop > 0 else dist
        spd = context_data.get("trip_avg_speed", 0)
        prompt = f"Đóng vai kỹ sư phân tích xe điện. Chuyến đi vừa hoàn thành dài {round(dist,2)}km, tiêu hao {round(drop,1)}% pin. Hiệu suất thực tế đạt: {actual_km_per_1} km / 1% pin. (Thông số chuẩn của hãng là {expected_km_per_1} km / 1%). Tốc độ trung bình {spd}km/h. Môi trường: {temp}°C, {cond}. Tải điều hòa: {hvac}. Hãy viết 1 đoạn văn tiếng Việt ngắn gọn (dưới 50 từ), đánh giá xem hiệu suất chuyến đi này là xuất sắc, bình thường hay kém và đưa ra 1 lời khuyên."

    clean_key = api_key.strip()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{ai_model}:generateContent"
    headers = {"Content-Type": "application/json", "x-goog-api-key": clean_key}
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    
    for attempt in range(3):
        try:
            res = requests.post(url, json=payload, headers=headers, timeout=30)
            if res.status_code == 200:
                ai_text = res.json().get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                return ai_text.replace("*", "").strip() if ai_text else "Google AI không phản hồi nội dung."
            elif res.status_code == 403: return "❌ Lỗi 403: API Key bị sai."
            elif res.status_code == 404: return f"❌ Lỗi 404: Model '{ai_model}' không tồn tại."
            elif res.status_code == 400: return "❌ Lỗi 400: Định dạng API Key không hợp lệ."
            elif res.status_code in [503, 429]:
                if attempt < 2: time.sleep(3); continue
                return f"⏳ Google AI đang quá tải (Lỗi {res.status_code})."
            else: return f"❌ Google báo lỗi {res.status_code}"
        except requests.exceptions.RequestException:
            if attempt < 2: time.sleep(3); continue
            return "❌ Lỗi mạng cục bộ: Không thể kết nối tới Google AI."
    return "Lỗi không xác định."