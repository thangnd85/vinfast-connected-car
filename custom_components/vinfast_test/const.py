DOMAIN = "vinfast_test"
CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_GEMINI_API_KEY = "gemini_api_key"

AUTH0_DOMAIN = "vin3s.au.auth0.com"
AUTH0_CLIENT_ID = "jE5xt50qC7oIh1f32qMzA6hGznIU5mgH"
API_BASE = "https://mobile.connected-car.vinfast.vn"
AWS_REGION = "ap-southeast-1"
COGNITO_POOL_ID = "ap-southeast-1:c6537cdf-92dd-4b1f-99a8-9826f153142a"
IOT_ENDPOINT = "prod.iot.connected-car.vinfast.vn"
DEVICE_ID = "vfdashboard-community-edition"

KNOWN_COMMANDS = {
    1: ("Khóa cửa", "mdi:lock", "khoa_cua"),
    2: ("Mở cửa", "mdi:lock-open", "mo_cua"),
    3: ("Bấm còi", "mdi:bullhorn", "bam_coi"),
    4: ("Nháy đèn", "mdi:car-light-high", "nhay_den"),
    5: ("Bật điều hòa", "mdi:fan", "bat_dieu_hoa"),
    6: ("Tắt điều hòa", "mdi:fan-off", "tat_dieu_hoa"),
    7: ("Mở cốp", "mdi:car-back", "mo_cop"),
}