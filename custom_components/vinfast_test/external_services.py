import requests
import uuid
import logging

_LOGGER = logging.getLogger(__name__)

def get_address_from_osm(lat, lon):
    """Lấy địa chỉ từ tọa độ (OpenStreetMap)"""
    try:
        res = requests.get(f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}&zoom=18", headers={"User-Agent": f"HA-VinFast-{uuid.uuid4().hex[:6]}"}, timeout=5)
        if res.status_code == 200: 
            addr = res.json().get("display_name")
            if addr and any(c.isalpha() for c in addr): 
                return addr
    except Exception: pass
    return None

def get_weather_data(lat, lon):
    """Lấy thời tiết và tính toán tải điều hòa (Open-Meteo)"""
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

                return {
                    "temp": temp,
                    "condition": f"{condition} (Gió {wind}km/h)",
                    "hvac": hvac,
                    "code": code
                }
    except Exception: pass
    return None

def get_osrm_route(lat1, lon1, lat2, lon2):
    """Tìm đường bám bản đồ giữa 2 tọa độ (Bù lỗ hổng rớt mạng)"""
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
    """Nắn mảng tọa độ khớp với đường giao thông"""
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