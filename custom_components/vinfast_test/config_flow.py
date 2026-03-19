import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
import logging

from .const import DOMAIN, CONF_EMAIL, CONF_PASSWORD, CONF_GEMINI_API_KEY
from .model_registry import get_vehicle_profile

_LOGGER = logging.getLogger(__name__)

CONF_GEMINI_MODEL = "gemini_model"

# Danh sách Model AI mới nhất từ Google Gemini (Năm 2026)
GEMINI_MODELS = {
    "gemini-2.5-flash": "Gemini 2.5 Flash (Mặc định - Ổn định & Nhanh)",
    "gemini-2.5-pro": "Gemini 2.5 Pro (Thông minh - Ổn định)",
    "gemini-3-flash-preview": "Gemini 3 Flash Preview (Tốc độ cao thế hệ mới)",
    "gemini-3.1-pro-preview": "Gemini 3.1 Pro Preview (Suy luận phức tạp)",
    "gemini-3.1-flash-lite-preview": "Gemini 3.1 Flash-Lite (Siêu nhẹ, siêu tốc)"
}

def safe_int(val, default):
    try: return int(float(val))
    except (ValueError, TypeError): return default

def safe_float(val, default):
    try: return float(val)
    except (ValueError, TypeError): return default

class VinFastConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_EMAIL].lower())
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=user_input[CONF_EMAIL], data=user_input)

        # Form cài đặt lần đầu
        data_schema = vol.Schema({
            vol.Required(CONF_EMAIL): str,
            vol.Required(CONF_PASSWORD): str,
            vol.Optional(CONF_GEMINI_API_KEY, default=""): str,
            vol.Optional(CONF_GEMINI_MODEL, default="gemini-2.5-flash"): vol.In(GEMINI_MODELS),
        })
        return self.async_show_form(step_id="user", data_schema=data_schema)

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

        domain_data = self.hass.data.get(DOMAIN, {}).get(self._config_entry.entry_id, {})
        api = domain_data.get("api")
        
        # Lấy thông số kỹ thuật xe qua Router
        fallback_ev, fallback_gas = 0.15, 15.0
        if api and hasattr(api, "vehicle_model_display"):
            profile = get_vehicle_profile(api.vehicle_model_display)
            spec = profile.get("spec", {})
            fallback_ev = spec.get("ev_kwh_per_km", 0.15)
            fallback_gas = spec.get("gas_km_per_liter", 15.0)

        opts = self._config_entry.options
        cost_per_kwh = safe_int(opts.get("cost_per_kwh"), 4000)
        gas_price = safe_int(opts.get("gas_price"), 20000)
        ev_kwh_per_km = safe_float(opts.get("ev_kwh_per_km"), fallback_ev)
        gas_km_per_liter = safe_float(opts.get("gas_km_per_liter"), fallback_gas)
        
        current_gemini_key = opts.get(CONF_GEMINI_API_KEY, self._config_entry.data.get(CONF_GEMINI_API_KEY, ""))
        current_gemini_model = opts.get(CONF_GEMINI_MODEL, self._config_entry.data.get(CONF_GEMINI_MODEL, "gemini-2.5-flash"))

        options_schema = vol.Schema({
            vol.Optional(CONF_GEMINI_API_KEY, default=current_gemini_key): str,
            vol.Optional(CONF_GEMINI_MODEL, default=current_gemini_model): vol.In(GEMINI_MODELS),
            vol.Required("cost_per_kwh", default=cost_per_kwh): vol.Coerce(int),
            vol.Required("ev_kwh_per_km", default=ev_kwh_per_km): vol.Coerce(float),
            vol.Required("gas_price", default=gas_price): vol.Coerce(int),
            vol.Required("gas_km_per_liter", default=gas_km_per_liter): vol.Coerce(float),
        })
        
        return self.async_show_form(step_id="init", data_schema=options_schema)