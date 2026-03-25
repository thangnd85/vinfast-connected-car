import logging
import json
from homeassistant.components.sensor import SensorEntity
from homeassistant.core import callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.util import slugify

from .const import DOMAIN
from .const_common import VIRTUAL_SENSORS

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_entities):
    api = hass.data[DOMAIN][config_entry.entry_id]["api"]
    sensors = []
    
    active_dict = VIRTUAL_SENSORS.copy()
    if hasattr(api, '_active_sensors'):
        active_dict.update(api._active_sensors)

    for device_key, (name, unit, icon, device_class) in active_dict.items():
        sensors.append(VinFastSensor(api, device_key, name, unit, icon, device_class))
        
    async_add_entities(sensors)

class VinFastSensor(SensorEntity):
    def __init__(self, api, device_key, name, unit, icon, device_class):
        self.api = api
        self._device_key = device_key
        self._attr_name = name
        self._attr_native_unit_of_measurement = unit
        self._attr_icon = icon
        self._attr_device_class = device_class

        model_slug = slugify(getattr(api, "vehicle_model_display", "VF")).replace("_", "")
        vin_slug = api.vin.lower() if api.vin else "unknown"
        
        self._attr_unique_id = f"{model_slug}_{vin_slug}_{device_key}"
        self.entity_id = f"sensor.{model_slug}_{vin_slug}_{slugify(name)}"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.api.vin)},
            name=f"{getattr(self.api, 'vehicle_model_display', 'VinFast')} {getattr(self.api, 'vehicle_name', '')}".strip(),
            manufacturer="VinFast",
            model=getattr(self.api, "vehicle_model_display", "EV"),
            sw_version=self.api._last_data.get("00005_00001_00030", "Unknown")
        )

    async def async_added_to_hass(self):
        def handle_update(data):
            try: self.hass.loop.call_soon_threadsafe(self._process_update, data)
            except Exception: pass
        self.api.add_callback(handle_update)
        handle_update(self.api._last_data)

    @callback
    def _process_update(self, data):
        if self._device_key in data:
            val = data[self._device_key]
            val_clean = str(int(float(val))) if isinstance(val, (int, float)) else str(val).strip().upper()
            vi = getattr(self.api, "lang", "vi") == "vi"

            if self._device_key in ["34183_00001_00001", "34187_00000_00000"]:
                if val_clean == "1": self._attr_native_value = "P (Đỗ)" if vi else "P (Park)"
                elif val_clean == "2": self._attr_native_value = "R (Lùi)" if vi else "R (Reverse)"
                elif val_clean == "3": self._attr_native_value = "N (Mo)" if vi else "N (Neutral)"
                elif val_clean == "4": self._attr_native_value = "D (Đi)" if vi else "D (Drive)"
                else: self._attr_native_value = val

            elif self._device_key == "34183_00001_00029":
                if val_clean == "0": self._attr_native_value = "Nhả phanh tay" if vi else "Released"
                elif val_clean == "1": self._attr_native_value = "Kéo phanh tay" if vi else "Engaged"
                else: self._attr_native_value = val
                
            elif self._device_key == "34183_00001_00010":
                if val_clean == "2": self._attr_native_value = "Chưa sẵn sàng" if vi else "Not Ready"
                elif val_clean == "3": self._attr_native_value = "Sẵn sàng chạy (Ready)" if vi else "Ready to Drive"
                else: self._attr_native_value = val

            elif self._device_key == "34193_00001_00031":
                if val_clean == "1": self._attr_native_value = "Đã cắm súng sạc" if vi else "Plugged In"
                elif val_clean == "0": self._attr_native_value = "Chưa cắm súng sạc" if vi else "Unplugged"
                else: self._attr_native_value = val

            elif self._device_key in ["34193_00001_00005", "34183_00000_00001"]:
                if val_clean == "1": self._attr_native_value = "Đang sạc" if vi else "Charging"
                elif val_clean == "2": self._attr_native_value = "Sạc xong (Đầy)" if vi else "Fully Charged"
                elif val_clean in ["0", "3", "4"]: self._attr_native_value = "Không Sạc" if vi else "Not Charging"
                else: self._attr_native_value = val

            # --- SỬA LẠI NHÓM KHÓA CỬA CHO VF6 ---
            elif self._device_key in ["34213_00001_00003", "34206_00001_00001"]:
                if val_clean == "1": self._attr_native_value = "Đã Khóa" if vi else "Locked"
                elif val_clean == "0": self._attr_native_value = "Mở Khóa" if vi else "Unlocked"
                else: self._attr_native_value = val

            elif self._device_key == "34234_00001_00003":
                if val_clean in ["1", "2"]: self._attr_native_value = "Đã Bật An Ninh" if vi else "Armed"
                elif val_clean == "0": self._attr_native_value = "Đã Tắt An Ninh" if vi else "Disarmed"
                else: self._attr_native_value = val

            # --- XÓA 34206 KHỎI ĐÂY (VÌ NÓ ĐÃ THÀNH KHÓA CỬA TRÊN VF6) ---
            elif self._device_key in ["34205_00001_00001", "34207_00001_00001", "34186_00005_00004"]:
                if val_clean == "1": self._attr_native_value = "Đang Bật" if vi else "On"
                elif val_clean == "0": self._attr_native_value = "Đã Tắt" if vi else "Off"
                else: self._attr_native_value = val

            elif self._device_key.startswith("10351_"):
                if val_clean == "0": self._attr_native_value = "Đóng kín" if vi else "Closed"
                elif val_clean == "1": self._attr_native_value = "Đang mở" if vi else "Open"
                else: self._attr_native_value = val

            elif self._device_key.startswith("34215_"):
                if val_clean == "1": self._attr_native_value = "Đóng kín" if vi else "Closed"
                elif val_clean == "2": self._attr_native_value = "Đang mở" if vi else "Open"
                elif val_clean == "0": self._attr_native_value = "Đóng kín" if vi else "Closed"
                else: self._attr_native_value = val

            elif self._device_key == "34184_00001_00004":
                if val_clean == "0": self._attr_native_value = "Tắt" if vi else "Off"
                elif val_clean == "1": self._attr_native_value = "Bật" if vi else "On"
                else: self._attr_native_value = val

            elif self._device_key == "34184_00001_00011":
                if val_clean == "0": self._attr_native_value = "Lấy gió ngoài" if vi else "Fresh Air"
                elif val_clean == "1": self._attr_native_value = "Lấy gió trong" if vi else "Recirculation"
                else: self._attr_native_value = val

            elif self._device_key == "34184_00001_00012":
                if val_clean == "1": self._attr_native_value = "Gió mặt" if vi else "Face"
                elif val_clean == "2": self._attr_native_value = "Gió mặt & chân" if vi else "Face & Floor"
                elif val_clean == "3": self._attr_native_value = "Gió chân" if vi else "Floor"
                elif val_clean == "4": self._attr_native_value = "Gió kính & chân" if vi else "Defrost & Floor"
                elif val_clean == "0": self._attr_native_value = "Gió mặt (Auto)" if vi else "Face (Auto)"
                else: self._attr_native_value = val

            elif self._device_key == "34184_00001_00009":
                if val_clean == "0": self._attr_native_value = "Tắt sấy" if vi else "Defrost Off"
                elif val_clean == "1": self._attr_native_value = "Bật sấy kính lái" if vi else "Defrost On"
                else: self._attr_native_value = val

            # --- THÊM XỬ LÝ CHO ĐÈN PHA ---
            elif self._device_key in ["34213_00004_00003", "56789_00001_00005"]:
                if val_clean == "0": self._attr_native_value = "Tắt" if vi else "Off"
                elif val_clean == "1": self._attr_native_value = "Bật" if vi else "On"
                else: self._attr_native_value = val

            elif self._device_key in ["34184_00001_00025", "34184_00001_00041"]:
                self._attr_native_value = val_clean

            elif self._device_key in ["00006_00001_00000", "00006_00001_00001"]:
                try:
                    num_val = float(val)
                    if num_val == 0.0: self._attr_native_value = "Đang tìm GPS..." if vi else "Searching GPS..."
                    else: self._attr_native_value = round(num_val, 6)
                except (ValueError, TypeError):
                    self._attr_native_value = "Không có tín hiệu" if vi else "No Signal"

            elif self._device_key == "api_trip_route":
                self._attr_native_value = "Dữ liệu Map" if vi else "Map Data"
                self._attr_extra_state_attributes = {"route_json": val if isinstance(val, str) else json.dumps(val)}
                
            elif self._device_key == "api_nearby_stations":
                self._attr_native_value = "Danh sách Trạm" if vi else "Station List"
                self._attr_extra_state_attributes = {"stations": val if isinstance(val, str) else json.dumps(val)}
                
            elif self._device_key == "api_public_charge_sessions":
                self._attr_native_value = val
                history_str = self.api._last_data.get("api_charge_history_list", "[]")
                try:
                    history_data = json.loads(history_str) if isinstance(history_str, str) else history_str
                    formatted_history = []
                    for item in history_data:
                        date = item.get("date", "")
                        address = item.get("address", "")[:35]
                        kwh = item.get("kwh", 0)
                        dur = item.get("duration", 0)
                        formatted_history.append(f"{date} | {kwh} kWh ({dur} {'phút' if vi else 'mins'}) | {address}")
                    self._attr_extra_state_attributes = {("Lịch sử chi tiết" if vi else "Detailed History"): formatted_history if formatted_history else (["Chưa có dữ liệu"] if vi else ["No data"])}
                except Exception:
                    self._attr_extra_state_attributes = {"Lỗi" if vi else "Error": "Không thể parse dữ liệu sạc" if vi else "Parse error"}

            elif self._device_key == "api_home_charge_sessions":
                self._attr_native_value = val
                home_kwh = self.api._last_data.get("api_home_charge_kwh", 0.0)
                self._attr_extra_state_attributes = {("Tổng điện năng (kWh)" if vi else "Total Energy (kWh)"): round(home_kwh, 2)}

            elif self._device_key == "api_best_efficiency_band":
                attrs = {}
                stats = getattr(self.api, '_eff_stats', {})
                for k, v in stats.items():
                    if v["drops"] > 0:
                        attrs[f"Dải {k} km/h" if vi else f"Band {k} km/h"] = f"{round(v['dist'] / v['drops'], 2)} km/1%"
                self._attr_extra_state_attributes = attrs if attrs else {("Trạng thái" if vi else "Status"): ("Chưa đủ dữ liệu sụt pin" if vi else "Not enough data")}
                self._attr_native_value = val

            elif self._device_key == "api_ai_advisor":
                val_str = str(val) if val else ("Chờ AI phân tích..." if vi else "Waiting for AI...")
                self._attr_extra_state_attributes = {"full_text": val_str}
                self._attr_native_value = val_str[:250] + "..." if len(val_str) > 250 else val_str

            elif self._device_key == "api_total_charge_sessions":
                try:
                    pub = int(float(self.api._last_data.get("api_public_charge_sessions", 0)))
                    home = int(float(self.api._last_data.get("api_home_charge_sessions", 0)))
                    self._attr_native_value = pub + home
                    self._attr_extra_state_attributes = {
                        "Sạc tại trạm": pub,
                        "Sạc tại nhà": home
                    }
                except Exception:
                    self._attr_native_value = val

            elif self._device_key == "api_debug_raw":
                try:
                    raw_dict = getattr(self.api, '_raw_json_dict', {})
                    if raw_dict:
                        self._attr_extra_state_attributes = raw_dict.copy()
                    else:
                        self._attr_extra_state_attributes = {"Trạng thái": "Chờ bản tin MQTT..."}
                    val_str = str(val) if val else "Đang hoạt động"
                    self._attr_native_value = val_str[:250] + "..." if len(val_str) > 250 else val_str
                except Exception: pass
                
            else:
                if isinstance(val, float):
                    self._attr_native_value = round(val, 2)
                else:
                    val_str = str(val)
                    self._attr_native_value = val_str[:250] + "..." if len(val_str) > 250 else val_str

            self.async_write_ha_state()