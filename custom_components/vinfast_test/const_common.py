# VIRTUAL SENSORS (Giữ nguyên như cũ)
VIRTUAL_SENSORS = {
    "api_vehicle_status": ("Trạng thái hoạt động", None, "mdi:car-info", None),
    "api_current_address": ("Vị trí xe (Địa chỉ)", None, "mdi:map-marker", None),
    "api_trip_distance": ("Quãng đường chuyến đi (Trip)", "km", "mdi:map-marker-distance", "distance"),
    "api_trip_avg_speed": ("Tốc độ TB chuyến đi", "km/h", "mdi:speedometer-medium", "speed"),
    "api_trip_energy_used": ("Điện năng tiêu thụ Trip", "kWh", "mdi:lightning-bolt", "energy"),
    "api_trip_efficiency": ("Hiệu suất tiêu thụ Trip", "kWh/100km", "mdi:leaf-circle", None),
    "api_static_capacity": ("Dung lượng pin thiết kế", "kWh", "mdi:car-battery", "energy"),
    "api_static_range": ("Quãng đường công bố (Max)", "km", "mdi:map-marker-distance", "distance"),
    "api_soh_calculated": ("Sức khỏe pin (SOH Tính toán)", "%", "mdi:heart-pulse", "battery"),
    "api_est_range_degradation": ("Khả năng chai pin (Tham khảo)", "%", "mdi:battery-alert", None),
    "api_lifetime_efficiency": ("Hiệu suất tiêu thụ (Trung bình xe)", "kWh/100km", "mdi:leaf", None),
    "api_calc_max_range": ("Quãng đường thực tế (Đầy 100% pin)", "km", "mdi:map-marker-path", "distance"),
    "api_best_efficiency_band": ("Dải tốc độ tối ưu nhất", None, "mdi:chart-bell-curve", None),
    "api_last_charge_start_soc": ("% Pin lúc cắm sạc (Lần cuối)", "%", "mdi:battery-arrow-down", "battery"),
    "api_last_charge_end_soc": ("% Pin lúc rút sạc (Lần cuối)", "%", "mdi:battery-arrow-up", "battery"),
    "api_last_charge_duration": ("Thời gian cắm sạc (Lần cuối)", "min", "mdi:timer-sand", "duration"),
    "api_last_charge_energy": ("Điện năng lấy từ lưới (Lần cuối)", "kWh", "mdi:flash", "energy"),
    "api_last_charge_power": ("Công suất sạc trung bình (Lần cuối)", "kW", "mdi:ev-plug-type2", "power"),
    "api_total_charge_cost_est": ("Tổng chi phí sạc quy đổi", "VNĐ", "mdi:cash-fast", "monetary"),
    "api_total_charge_sessions": ("Tổng số lần sạc", "lần", "mdi:battery-charging-100", None),
    "api_public_charge_sessions": ("Số lần sạc tại trạm", "lần", "mdi:ev-station", None),
    "api_home_charge_sessions": ("Số lần sạc tại nhà", "lần", "mdi:home-lightning-bolt-outline", None),
    "api_home_charge_kwh": ("Điện năng sạc tại nhà", "kWh", "mdi:home-battery", "energy"),
    "api_total_energy_charged": ("Tổng điện năng đã sạc", "kWh", "mdi:lightning-bolt", "energy"),
    "api_vehicle_model": ("Tên dòng xe", None, "mdi:car", None),
    "api_vehicle_name": ("Tên định danh xe", None, "mdi:account-car", None),
    "api_outside_temp": ("Nhiệt độ ngoài trời (GPS)", "°C", "mdi:thermometer", "temperature"),
    "api_weather_condition": ("Thời tiết hiện tại", None, "mdi:weather-partly-cloudy", None),
    "api_hvac_load_estimate": ("Ước tính tải Điều hòa", None, "mdi:air-conditioner", None),
    "api_ai_advisor": ("Cố vấn Xe điện AI", None, "mdi:robot-outline", None),
    "api_trip_route": ("Lộ trình GPS", None, "mdi:map-marker-path", None),
    "api_nearby_stations": ("Trạm sạc lân cận", None, "mdi:ev-station", None),
    "api_debug_raw": ("System Debug Raw", None, "mdi:bug", None)
}

# SENSOR VẬT LÝ DÙNG CHUNG (Cửa, điều hòa, GPS...)
COMMON_SENSORS = {
    "34213_00001_00003": ("Khóa tổng", None, "mdi:lock", None),
    "00006_00001_00000": ("Vĩ độ (Latitude)", "°", "mdi:crosshairs-gps", None),
    "00006_00001_00001": ("Kinh độ (Longitude)", "°", "mdi:crosshairs-gps", None),
    "00006_00001_00002": ("Độ cao (Altitude)", "m", "mdi:elevation-rise", None),
    "00005_00001_00030": ("Phiên bản Phần mềm (FRP)", None, "mdi:update", None),
    "34196_00001_00004": ("Phiên bản T-Box", None, "mdi:cellphone-link", None),
    "34181_00001_00007": ("Biển số / Tên xe phụ", None, "mdi:card-text-outline", None),
    
    # VF3 cũng có 2 cửa trước và cốp sau
    "10351_00002_00050": ("Cửa tài xế", None, "mdi:car-door", None),
    "10351_00001_00050": ("Cửa phụ", None, "mdi:car-door", None),
    "10351_00006_00050": ("Cốp sau", None, "mdi:car-door", None),
    "34215_00002_00002": ("Kính tài xế", None, "mdi:window-open", None),
    "34215_00001_00002": ("Kính phụ", None, "mdi:window-open", None),
    
    # Điều hòa & Nháy đèn
    "34213_00004_00003": ("Trạng thái nháy đèn pha", None, "mdi:car-light-high", None),
    "34184_00001_00004": ("Trạng thái điều hòa", None, "mdi:air-conditioner", None),
    "34184_00001_00011": ("Chế độ lấy gió", None, "mdi:car-windshield-outline", None),
    "34184_00001_00012": ("Hướng gió điều hòa", None, "mdi:fan", None),
    "34184_00001_00009": ("Sấy kính", None, "mdi:car-defrost-front", None),
    "34184_00001_00025": ("Tốc độ quạt gió", "Mức", "mdi:fan-speed-1", None),
    "34184_00001_00041": ("Mức độ làm lạnh", "Mức", "mdi:snowflake", None),
}

# LỚP 3A: NỀN TẢNG A (VF3, VF5, e34, VF6, VF7)
PLATFORM_A_BASE = COMMON_SENSORS.copy()
PLATFORM_A_BASE.update({
    "34183_00001_00010": ("Trạng thái Lái (Ready)", None, "mdi:car-key", None), 
    "34183_00001_00009": ("Phần trăm Pin", "%", "mdi:battery", "battery"),
    "34183_00001_00011": ("Quãng đường dự kiến", "km", "mdi:map-marker-distance", "distance"),
    "34183_00001_00005": ("Pin 12V (Ắc quy)", "%", "mdi:car-battery", "battery"),
    "34220_00001_00001": ("Sức khỏe pin (SOH)", "%", "mdi:heart-pulse", "battery"),
    
    "34193_00001_00031": ("Cắm súng sạc (Plug)", None, "mdi:ev-plug-type2", None),
    "34193_00001_00005": ("Trạng thái dòng sạc", None, "mdi:ev-station", None),
    "34193_00001_00007": ("Thời gian sạc còn lại", "min", "mdi:timer-outline", "duration"),
    
    "34183_00001_00001": ("Vị trí cần số", None, "mdi:car-shift-pattern", None),
    "34183_00001_00002": ("Tốc độ hiện tại", "km/h", "mdi:speedometer", "speed"),
    "34183_00001_00003": ("Tổng ODO", "km", "mdi:counter", "distance"),
    "34183_00001_00007": ("Nhiệt độ ngoài trời", "°C", "mdi:thermometer", "temperature"),
    "34183_00001_00015": ("Nhiệt độ trong xe", "°C", "mdi:thermometer", "temperature"),
    
    "34183_00001_00029": ("Phanh tay", None, "mdi:car-brake-parking", None), # Áp dụng cả phanh cơ/điện tử nếu ECU có đọc
})

# LỚP NÂNG CẤP DÀNH CHO XE 4 CỬA
REAR_DOORS_WINDOWS = {
    "10351_00004_00050": ("Cửa sau tài", None, "mdi:car-door", None),
    "10351_00003_00050": ("Cửa sau phụ", None, "mdi:car-door", None),
    "34215_00004_00002": ("Kính sau tài", None, "mdi:window-open", None),
    "34215_00003_00002": ("Kính sau phụ", None, "mdi:window-open", None),
    "10351_00005_00050": ("Nắp Capo", None, "mdi:car-door", None),
}