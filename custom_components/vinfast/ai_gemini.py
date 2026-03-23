import requests
import time

def get_ai_advice(api_key, ai_model, mode, data_payload, context_data):
    """Gửi Prompt phân tích lên Google Gemini AI"""
    if not api_key or api_key.strip() == "":
        return "Vui lòng nhập Google Gemini API Key để AI đánh giá."

    temp = context_data.get("temp", "Không rõ")
    cond = context_data.get("cond", "Không rõ")
    hvac = context_data.get("hvac", "Bình thường")
    expected_km_per_1 = context_data.get("expected_km_per_1", 2.1)

    prompt = ""

    if mode == "weather" and data_payload:
        w_temp = data_payload.get('temp', temp)
        w_cond = data_payload.get('cond', cond)
        prompt = (
            f"CẢNH BÁO THỜI TIẾT CỰC ĐOAN: Nhiệt độ ngoài trời đang là {w_temp} độ C, thời tiết: {w_cond}. "
            f"Đóng vai chuyên gia AI của xe VinFast, viết MỘT câu tiếng Việt cực kỳ ngắn gọn (dưới 40 từ) "
            "khuyên tài xế cách chỉnh điều hòa và lái xe để an toàn và tiết kiệm pin nhất lúc này."
        )
    elif mode == "anomaly" and data_payload:
        dist = round(data_payload.get('dist', 0), 2)
        spd = round(data_payload.get('speed', 0), 1)
        prompt = (
            f"CẢNH BÁO HAO PIN: Xe điện vừa sụt 1% pin nhưng chỉ đi được {dist}km "
            f"(mức chuẩn lý tưởng của nhà sản xuất công bố là {expected_km_per_1} km/1%). "
            f"Tốc độ chạy trung bình lúc này: {spd}km/h. Tải điều hòa: {hvac}. "
            "Bạn hãy đóng vai Cố vấn AI trên xe, viết MỘT câu tiếng Việt cực kỳ ngắn gọn (dưới 40 từ) "
            "nhận xét nguyên nhân gây tốn pin (do tốc độ hay điều hòa) và đưa ra lời khuyên khẩn cấp."
        )
    else: # Trip mode
        dist = data_payload.get('dist', 0) if data_payload else context_data.get("trip_dist", 0.0)
        drop = data_payload.get('drop', 0) if data_payload else 0
        
        if dist < 0.05: 
            return f"Hệ thống đang đợi... Chuyến đi hiện tại ({dist}km) quá ngắn để phân tích."

        actual_km_per_1 = round(dist / drop, 2) if drop > 0 else dist
        spd = context_data.get("trip_avg_speed", 0)
        
        prompt = (
            f"Đóng vai kỹ sư phân tích xe điện. Chuyến đi vừa hoàn thành dài {round(dist,2)}km, tiêu hao {round(drop,1)}% pin. "
            f"Hiệu suất thực tế đạt: {actual_km_per_1} km / 1% pin. (Thông số chuẩn của hãng là {expected_km_per_1} km / 1%). "
            f"Tốc độ trung bình {spd}km/h. Môi trường: {temp}°C, {cond}. Tải điều hòa: {hvac}. "
            "Hãy viết 1 đoạn văn tiếng Việt ngắn gọn (dưới 50 từ), đánh giá xem hiệu suất chuyến đi này là xuất sắc, bình thường hay kém "
            "và đưa ra 1 lời khuyên."
        )

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
            elif res.status_code == 403: return "❌ Lỗi 403: API Key bị sai hoặc chưa bật Generative Language API."
            elif res.status_code == 404: return f"❌ Lỗi 404: Model '{ai_model}' không tồn tại hoặc bị khóa."
            elif res.status_code == 400: return "❌ Lỗi 400: Định dạng API Key không hợp lệ."
            elif res.status_code in [503, 429]:
                if attempt < 2: 
                    time.sleep(3)
                    continue
                return f"⏳ Google AI đang quá tải (Lỗi {res.status_code})."
            else:
                return f"❌ Google báo lỗi {res.status_code}"
        except requests.exceptions.RequestException:
            if attempt < 2:
                time.sleep(3)
                continue
            return "❌ Lỗi mạng cục bộ: Không thể kết nối tới Google AI."
            
    return "Lỗi không xác định khi liên hệ AI."