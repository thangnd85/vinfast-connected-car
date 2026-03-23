import logging
from homeassistant.components.button import ButtonEntity
from homeassistant.util import slugify
import asyncio

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

KNOWN_COMMANDS = {
    1: ("Khóa cửa", "mdi:lock", "khoa_cua"),
    2: ("Mở cửa", "mdi:lock-open", "mo_cua"),
    3: ("Bấm còi", "mdi:bullhorn", "bam_coi"),
    4: ("Nháy đèn", "mdi:car-light-high", "nhay_den"),
    5: ("Bật điều hòa", "mdi:fan", "bat_dieu_hoa"),
    6: ("Tắt điều hòa", "mdi:fan-off", "tat_dieu_hoa"),
    7: ("Mở cốp", "mdi:car-back", "mo_cop"),
}

async def async_setup_entry(hass, config_entry, async_add_entities):
    api = hass.data[DOMAIN][config_entry.entry_id]["api"]
    buttons = []

    # 1. TẠO NÚT LOCAL: TÌM TRẠM SẠC
    buttons.append(VinFastLocalAction(api, "Tìm trạm sạc", "mdi:ev-station", "tim_tram_sac", "fetch_nearby_stations"))
    
    # 2. TẠO NÚT NẮN BẢN ĐỒ (MAGIC STAFF)
    buttons.append(VinFastFixMapButton(api))

    # 3. TẠO CÁC NÚT REMOTE COMMAND
    for cmd_id in range(1, 21):
        if cmd_id in KNOWN_COMMANDS:
            name, icon, slug = KNOWN_COMMANDS[cmd_id]
        else:
            name = f"Lệnh Raw (Mã {cmd_id})"
            icon = "mdi:flask-outline"
            slug = f"raw_cmd_{cmd_id}"
            
        buttons.append(VinFastRemoteCommand(api, cmd_id, name, icon, slug))

    async_add_entities(buttons)


class VinFastLocalAction(ButtonEntity):
    def __init__(self, api, name, icon, slug, action_method):
        self.api = api
        self._action_method = action_method
        self._attr_has_entity_name = True
        self._attr_name = name
        self._attr_icon = icon
        
        model_slug = slugify(getattr(api, "vehicle_model_display", "VF")).replace("_", "")
        vin_slug = api.vin.lower() if api.vin else "unknown"
        
        self._attr_unique_id = f"{model_slug}_{vin_slug}_{slug}"
        self.entity_id = f"button.{model_slug}_{vin_slug}_{slug}"

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self.api.vin)},
            "name": f"{getattr(self.api, 'vehicle_model_display', 'VinFast')} {getattr(self.api, 'vehicle_name', '')}".strip(),
            "manufacturer": "VinFast",
            "model": getattr(self.api, "vehicle_model_display", "EV")
        }

    async def async_press(self) -> None:
        if hasattr(self.api, self._action_method):
            method = getattr(self.api, self._action_method)
            await self.hass.async_add_executor_job(method)
            _LOGGER.info(f"VinFast: Đã chạy hàm nội bộ [{self._attr_name}]")


class VinFastFixMapButton(ButtonEntity):
    def __init__(self, api):
        self.api = api
        self._attr_has_entity_name = True
        self._attr_name = "Tối ưu Bản đồ"
        self._attr_icon = "mdi:magic-staff"
        
        model_slug = slugify(getattr(api, "vehicle_model_display", "VF")).replace("_", "")
        vin_slug = api.vin.lower() if api.vin else "unknown"
        
        self._attr_unique_id = f"{model_slug}_{vin_slug}_fix_map"
        self.entity_id = f"button.{model_slug}_{vin_slug}_fix_map"

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self.api.vin)},
            "name": f"{getattr(self.api, 'vehicle_model_display', 'VinFast')} {getattr(self.api, 'vehicle_name', '')}".strip(),
            "manufacturer": "VinFast",
            "model": getattr(self.api, "vehicle_model_display", "EV")
        }

    async def async_press(self) -> None:
        _LOGGER.warning("VinFast: Đã bấm nút Tối ưu Bản đồ. Đang ép chạy lại thuật toán (Force=True)...")
        if hasattr(self.api, "async_fix_all_historical_trips"):
            self.hass.async_create_task(self.api.async_fix_all_historical_trips(force=True))
        else:
            _LOGGER.error("VinFast: Lỗi - Không tìm thấy hàm nắn đường trong api.py")


class VinFastRemoteCommand(ButtonEntity):
    def __init__(self, api, cmd_id, name, icon, slug):
        self.api = api
        self._cmd_id = cmd_id
        self._attr_has_entity_name = True
        self._attr_name = name
        self._attr_icon = icon
        
        model_slug = slugify(getattr(api, "vehicle_model_display", "VF")).replace("_", "")
        vin_slug = api.vin.lower() if api.vin else "unknown"
        
        self._attr_unique_id = f"{model_slug}_{vin_slug}_{slug}"
        self.entity_id = f"button.{model_slug}_{vin_slug}_{slug}"

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self.api.vin)},
            "name": f"{getattr(self.api, 'vehicle_model_display', 'VinFast')} {getattr(self.api, 'vehicle_name', '')}".strip(),
            "manufacturer": "VinFast",
            "model": getattr(self.api, "vehicle_model_display", "EV")
        }

    async def async_press(self) -> None:
        _LOGGER.warning(f"VinFast: Đang gửi lệnh [{self._attr_name}] với mã = {self._cmd_id}...")
        result = await self.hass.async_add_executor_job(self.api.send_remote_command, self._cmd_id)
        if result: _LOGGER.warning(f"VinFast: Lệnh {self._cmd_id} Thành Công!")
        else: _LOGGER.error(f"VinFast: Lệnh {self._cmd_id} Thất Bại.")