import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
import logging
import requests

from .const import (
    DOMAIN, 
    CONF_EMAIL, 
    CONF_PASSWORD, 
    CONF_GEMINI_API_KEY, 
    CONF_REGION, 
    CONF_LANGUAGE,
    CONF_MAPBOX_TOKEN,  # Chú ý: Nhớ thêm 2 biến này vào file const.py nhé
    CONF_STADIA_TOKEN
)

_LOGGER = logging.getLogger(__name__)

CONF_GEMINI_MODEL = "gemini_model"

REGIONS = {"VN": "Việt Nam (VN)", "US": "United States (US)", "EU": "Europe (EU)"}
LANGUAGES = {"vi": "Tiếng Việt (VI)", "en": "English (EN)"}

def safe_int(val, default):
    try: return int(float(val))
    except (ValueError, TypeError): return default

# =====================================================================
# THUẬT TOÁN TỰ ĐỘNG QUÉT DANH SÁCH MODEL MỚI NHẤT TỪ GOOGLE GEMINI
# =====================================================================
def fetch_gemini_models_sync(api_key):
    # Danh sách dự phòng nếu mạng lỗi hoặc người dùng không nhập Key
    default_models = {
        "gemini-2.5-flash": "Gemini 2.5 Flash (Khuyên dùng/Nhanh/Free)",
        "gemini-2.5-pro": "Gemini 2.5 Pro (Cao cấp)",
        "gemini-2.0-flash": "Gemini 2.0 Flash (Nhanh/Free)",
        "gemini-1.5-flash": "Gemini 1.5 Flash",
    }
    
    if not api_key or str(api_key).strip() == "":
        return default_models
        
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
        res = requests.get(url, timeout=10)
        
        if res.status_code == 200:
            data = res.json()
            models = {}
            
            for m in data.get("models", []):
                name = m.get("name", "").replace("models/", "")
                display = m.get("displayName", name)
                methods = m.get("supportedGenerationMethods", [])
                
                # Chỉ lấy các model sinh text (Bỏ qua model nhúng/âm thanh/cũ)
                if "generateContent" in methods and "gemini" in name.lower() and "vision" not in name.lower():
                    # Gắn tag phân loại thông minh
                    if "flash" in name.lower():
                        display = f"{display} (Nhanh/Free)"
                    elif "pro" in name.lower():
                        display = f"{display} (Cao cấp)"
                    
                    models[name] = display
            
            if models:
                # Thuật toán Sắp xếp: Ưu tiên bản 2.5 lên đầu -> Đến dòng Flash -> Các dòng khác
                sorted_models = dict(sorted(models.items(), key=lambda item: (
                    not ("2.5" in item[0]), 
                    not ("flash" in item[0]), 
                    item[0]
                )))
                return sorted_models
                
    except Exception as e:
        _LOGGER.error(f"VinFast: Lỗi khi lấy danh sách Gemini models động: {e}")
        
    return default_models

class VinFastConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self):
        self._setup_data = {}

    async def async_step_user(self, user_input=None):
        # BƯỚC 1: NHẬP TÀI KHOẢN VÀ CÁC API KEY
        if user_input is not None:
            self._setup_data.update(user_input)
            return await self.async_step_model()

        # Bổ sung Mapbox và Stadia vào Form khởi tạo
        data_schema = vol.Schema({
            vol.Required(CONF_EMAIL): str,
            vol.Required(CONF_PASSWORD): str,
            vol.Required(CONF_REGION, default="VN"): vol.In(REGIONS),
            vol.Required(CONF_LANGUAGE, default="vi"): vol.In(LANGUAGES),
            vol.Optional(CONF_GEMINI_API_KEY, default=""): str,
            vol.Optional(CONF_MAPBOX_TOKEN, default=""): str,
            vol.Optional(CONF_STADIA_TOKEN, default=""): str,
        })
        return self.async_show_form(step_id="user", data_schema=data_schema)

    async def async_step_model(self, user_input=None):
        # BƯỚC 2: TỰ ĐỘNG LOAD MODEL VÀ CHỐT LƯU
        if user_input is not None:
            self._setup_data.update(user_input)
            await self.async_set_unique_id(self._setup_data[CONF_EMAIL].lower())
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=self._setup_data[CONF_EMAIL], data=self._setup_data)

        api_key = self._setup_data.get(CONF_GEMINI_API_KEY, "")
        
        # Chạy ngầm hàm lấy API để không làm treo giao diện Home Assistant
        models = await self.hass.async_add_executor_job(fetch_gemini_models_sync, api_key)
        
        data_schema = vol.Schema({
            vol.Required(CONF_GEMINI_MODEL, default=list(models.keys())[0]): vol.In(models),
        })
        return self.async_show_form(step_id="model", data_schema=data_schema)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return VinFastOptionsFlowHandler(config_entry)

class VinFastOptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        self._config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        opts = self._config_entry.options
        data = self._config_entry.data
        
        current_region = opts.get(CONF_REGION, data.get(CONF_REGION, "VN"))
        current_lang = opts.get(CONF_LANGUAGE, data.get(CONF_LANGUAGE, "vi"))
        current_gemini_key = opts.get(CONF_GEMINI_API_KEY, data.get(CONF_GEMINI_API_KEY, ""))
        current_gemini_model = opts.get(CONF_GEMINI_MODEL, data.get(CONF_GEMINI_MODEL, "gemini-2.5-flash"))
        current_mapbox = opts.get(CONF_MAPBOX_TOKEN, data.get(CONF_MAPBOX_TOKEN, ""))
        current_stadia = opts.get(CONF_STADIA_TOKEN, data.get(CONF_STADIA_TOKEN, ""))

        # Cập nhật lại danh sách Model mỗi khi người dùng bấm Cấu hình lại
        available_models = await self.hass.async_add_executor_job(fetch_gemini_models_sync, current_gemini_key)
        if current_gemini_model not in available_models:
            available_models[current_gemini_model] = current_gemini_model

        # Bổ sung Mapbox và Stadia vào Form Cấu hình lại (Configure)
        options_schema = vol.Schema({
            vol.Required(CONF_REGION, default=current_region): vol.In(REGIONS),
            vol.Required(CONF_LANGUAGE, default=current_lang): vol.In(LANGUAGES),
            vol.Optional(CONF_GEMINI_API_KEY, default=current_gemini_key): str,
            vol.Required(CONF_GEMINI_MODEL, default=current_gemini_model): vol.In(available_models),
            vol.Optional(CONF_MAPBOX_TOKEN, default=current_mapbox): str,
            vol.Optional(CONF_STADIA_TOKEN, default=current_stadia): str,
            vol.Required("cost_per_kwh", default=safe_int(opts.get("cost_per_kwh"), 4000)): vol.Coerce(int),
            vol.Required("gas_price", default=safe_int(opts.get("gas_price"), 20000)): vol.Coerce(int),
        })
        
        return self.async_show_form(step_id="init", data_schema=options_schema)