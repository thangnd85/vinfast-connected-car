from .const_common import COMMON_SENSORS, VIRTUAL_SENSORS, REAR_DOORS_WINDOWS

SPEC = {"capacity": 87.7, "range": 471, "ev_kwh_per_km": 0.19, "gas_km_per_liter": 11.1}
SENSORS = COMMON_SENSORS.copy()
SENSORS.update(VIRTUAL_SENSORS)
SENSORS.update(REAR_DOORS_WINDOWS)

# Mã độc quyền kiến trúc VF8
SENSORS.update({
    "34183_00001_00005": ("Pin 12V (Ắc quy)", "%", "mdi:car-battery", "battery"),
    "34220_00001_00001": ("Sức khỏe pin (SOH)", "%", "mdi:heart-pulse", "battery"),
    "34183_00001_00007": ("Nhiệt độ ngoài trời", "°C", "mdi:thermometer", "temperature"),
    "34183_00001_00015": ("Nhiệt độ trong xe", "°C", "mdi:thermometer", "temperature"),
    
    "34180_00001_00010": ("Tên định danh xe (MQTT)", None, "mdi:badge-account", None),
    "34180_00001_00011": ("Phần trăm Pin", "%", "mdi:battery", "battery"),
    "34180_00001_00007": ("Quãng đường dự kiến", "km", "mdi:map-marker-distance", "distance"),
    
    "34183_00000_00001": ("Trạng thái sạc", None, "mdi:ev-station", None),
    "34183_00000_00004": ("Thời gian sạc còn lại", "min", "mdi:timer-outline", "duration"),
    "34183_00000_00012": ("Công suất sạc", "kW", "mdi:flash", "power"),
    "34183_00000_00015": ("Điện áp sạc", "V", "mdi:flash-outline", "voltage"),
    "34183_00000_00016": ("Dòng điện sạc", "A", "mdi:current-ac", "current"),
    "34193_00001_00012": ("Mục tiêu sạc (Target)", "%", "mdi:battery-charging-100", "battery"),
    
    "34187_00000_00000": ("Vị trí cần số", None, "mdi:car-shift-pattern", None),
    "34188_00000_00000": ("Tốc độ hiện tại", "km/h", "mdi:speedometer", "speed"),
    "34199_00000_00000": ("Tổng ODO", "km", "mdi:counter", "distance"),
    "34183_00001_00029": ("Phanh tay điện tử", None, "mdi:car-brake-parking", None),
    
    "34190_00000_00001": ("Áp suất lốp Trước Trái", "bar", "mdi:tire", "pressure"),
    "34190_00001_00001": ("Áp suất lốp Trước Phải", "bar", "mdi:tire", "pressure"),
    "34190_00002_00001": ("Áp suất lốp Sau Trái", "bar", "mdi:tire", "pressure"),
    "34190_00003_00001": ("Áp suất lốp Sau Phải", "bar", "mdi:tire", "pressure"),
})