import os

DOMAIN = "vinfast"
CONF_MAPBOX_TOKEN = "mapbox_token"
CONF_STADIA_TOKEN = "stadia_token"
CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_GEMINI_API_KEY = "gemini_api_key"
CONF_REGION = "region"
CONF_LANGUAGE = "language"

# ==========================================
# CẤU HÌNH ĐA VÙNG (MULTI-REGION)
# ==========================================
REGION_CONFIG = {
    "VN": {
        "AUTH0_DOMAIN": "vin3s.au.auth0.com",
        "AUTH0_CLIENT_ID": "jE5xt50qC7oIh1f32qMzA6hGznIU5mgH",
        "API_BASE": "https://mobile.connected-car.vinfast.vn",
        "AWS_REGION": "ap-southeast-1",
        "COGNITO_POOL_ID": "ap-southeast-1:c6537cdf-92dd-4b1f-99a8-9826f153142a",
        "IOT_ENDPOINT": "prod.iot.connected-car.vinfast.vn"
    },
    "US": {
        "AUTH0_DOMAIN": "vin3s.us.auth0.com", 
        "AUTH0_CLIENT_ID": "jE5xt50qC7oIh1f32qMzA6hGznIU5mgH", 
        "API_BASE": "https://api.us.vinfastauto.com",
        "AWS_REGION": "us-east-1",
        "COGNITO_POOL_ID": "us-east-1:xxxxxx-xxxx-xxxx-xxxx",
        "IOT_ENDPOINT": "prod.iot.us.connected-car.vinfast.vn"
    },
    "EU": {
        "AUTH0_DOMAIN": "vin3s.eu.auth0.com",
        "AUTH0_CLIENT_ID": "jE5xt50qC7oIh1f32qMzA6hGznIU5mgH",
        "API_BASE": "https://api.eu.vinfastauto.com",
        "AWS_REGION": "eu-central-1",
        "COGNITO_POOL_ID": "eu-central-1:xxxxxx-xxxx-xxxx",
        "IOT_ENDPOINT": "prod.iot.eu.connected-car.vinfast.vn"
    }
}

DEVICE_ID = "vfdashboard-community-edition"

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
HA_CONFIG_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))
WWW_DIR = os.path.join(HA_CONFIG_DIR, "www")
MOCK_FILE = os.path.join(WWW_DIR, "mock_console_cmd.txt")

KNOWN_COMMANDS = {
    1: ("Khóa cửa", "mdi:lock", "khoa_cua"),
    2: ("Mở cửa", "mdi:lock-open", "mo_cua"),
    3: ("Bấm còi", "mdi:bullhorn", "bam_coi"),
    4: ("Nháy đèn", "mdi:car-light-high", "nhay_den"),
    5: ("Bật điều hòa", "mdi:fan", "bat_dieu_hoa"),
    6: ("Tắt điều hòa", "mdi:fan-off", "tat_dieu_hoa"),
    7: ("Mở cốp", "mdi:car-back", "mo_cop"),
}