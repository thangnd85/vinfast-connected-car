import os
import json
import time
import logging
import threading
import asyncio
import datetime
from .const import WWW_DIR, REGION_CONFIG
from .api_auth import AuthManager
from .api_mqtt import MQTTManager
from .api_helpers import safe_float
from .map_matching import async_process_route, moving_average_smooth

_LOGGER = logging.getLogger(__name__)

class VinFastAPI:
    def __init__(self, email, password, vin=None, vehicle_name="Xe VinFast", region="VN", lang="vi", options=None, gemini_api_key=""):
        self.email = email
        self.password = password
        self.region = region
        self.lang = lang
        self.gemini_api_key = gemini_api_key.strip() if gemini_api_key else ""
        self.vin = vin
        self.user_id = None
        self.vehicle_name = vehicle_name
        self.vehicle_model_display = "Unknown" 
        self.options = options or {}
        
        cfg = REGION_CONFIG.get(self.region, REGION_CONFIG["VN"])
        self.auth0_domain = cfg["AUTH0_DOMAIN"]
        self.auth0_client_id = cfg["AUTH0_CLIENT_ID"]
        self.api_base = cfg["API_BASE"]
        self.aws_region = cfg["AWS_REGION"]
        self.cognito_pool_id = cfg["COGNITO_POOL_ID"]
        self.iot_endpoint = cfg["IOT_ENDPOINT"]
        
        self.access_token = None
        self._running = False
        self.callbacks = []
        
        ai_state = ("Hệ thống AI đang chờ..." if self.lang == "vi" else "AI is waiting...") if self.gemini_api_key else "DISABLED"
        
        self._last_data = {
            "api_vehicle_status": "Đang kết nối..." if self.lang == "vi" else "Connecting...",
            "api_current_address": "Đang tải..." if self.lang == "vi" else "Loading...",
            "api_trip_route": "[]",
            "api_nearby_stations": "[]",
            "api_trip_distance": 0.0,
            "api_trip_avg_speed": 0.0,
            "api_trip_energy_used": 0.0,
            "api_trip_efficiency": 0.0,
            "api_live_charge_power": 0.0,
            "api_last_charge_start_soc": 0.0, 
            "api_last_charge_end_soc": 0.0,   
            "api_last_lat": None, 
            "api_last_lon": None,
            "api_total_charge_sessions": 0,
            "api_public_charge_sessions": 0, 
            "api_total_energy_charged": 0.0,
            "api_vehicle_name": self.vehicle_name,
            "api_charge_history_list": "[]", 
            "api_home_charge_kwh": 0.0,
            "api_home_charge_sessions": 0,
            "api_ai_advisor": ai_state,
            "api_security_warning": "An toàn" if self.lang == "vi" else "Safe",
            "api_best_efficiency_band": "Chưa đủ dữ liệu" if self.lang == "vi" else "Not enough data",
            "api_est_range_degradation": 0.0,
            "api_debug_raw": "Chờ kết nối MQTT..." if self.lang == "vi" else "Waiting for MQTT..."
        }  
        
        self._is_moving = False
        self._is_charging = False
        self._last_is_charging = False 
        self._last_actual_move_time = time.time()
        self._last_lat_lon = ""
        self._vehicle_offline = False
        self._last_auto_wakeup_time = 0
        
        self._is_trip_active = False
        self._trip_start_odo = 0.0
        self._trip_start_time = time.time()
        self._trip_start_soc = 100.0
        self._trip_start_address = "Unknown"
        self._route_coords = []
        self._last_gps_time = time.time()
        self._trip_accumulated_distance_m = 0.0
        
        self._eff_soc = None
        self._eff_gps_dist = 0.0 
        self._eff_time = None
        self._eff_speeds = []
        self._eff_stats = {}
        
        self._last_ai_anomaly_time = 0
        self._last_ai_weather_time = 0
        
        self._charge_start_time = time.time()
        self._charge_start_soc = 0.0
        self._charge_calc_soc = 0.0
        self._charge_calc_time = time.time()
        self._current_charge_max_power = 0.0 

        self._last_geocoded_grid = None
        self._last_weather_fetch_time = 0 
        self._last_mqtt_msg_time = time.time() 
        self._geocode_lock = threading.Lock()
        
        self._raw_json_dict = {}
        self._changelog_buffer = []

        self.auth = AuthManager(self)
        self.mqtt = MQTTManager(self)

    def add_callback(self, cb):
        if cb not in self.callbacks:
            self.callbacks.append(cb)
            if self._last_data: cb(self._last_data)

    def trigger_callbacks(self):
        if self.callbacks:
            for cb in self.callbacks: cb(self._last_data)

    def stop(self):
        self._running = False
        self.mqtt.stop()

    def login(self): return self.auth.login()
    def get_vehicles(self): return self.auth.get_vehicles()
    def start_mqtt(self): self.mqtt.start()
    def send_remote_command(self, cmd, params=None): return self.auth.send_remote_command(cmd, params)

    def _update_vehicle_name(self, candidate_name):
        if not candidate_name: return
        candidate = str(candidate_name).strip()
        if len(candidate) < 2 or candidate.isnumeric() or candidate.lower() in ["0", "1", "none", "null", "unknown", "vinfast"]: return
        if "profile_email" in candidate.lower(): return
        self._last_data["api_vehicle_name"] = candidate

    def inject_mock_data(self, payload_list):
        class MockMsg:
            def __init__(self, data): self.payload = json.dumps(data).encode('utf-8')
        self.mqtt._on_message(None, None, MockMsg(payload_list))

    def _process_console_command(self, cmd):
        parts = cmd.lower().split()
        if not parts: return
        action = parts[0]
        if action == "cs": self.inject_mock_data([{"deviceKey": "34193_00001_00005", "value": "1"}, {"deviceKey": "34183_00000_00001", "value": "1"}])
        elif action == "rs": self.inject_mock_data([{"deviceKey": "34193_00001_00005", "value": "2"}, {"deviceKey": "34183_00000_00001", "value": "2"}])
        elif action == "soc" and len(parts) > 1: self.inject_mock_data([{"deviceKey": "34183_00001_00009", "value": parts[1]}, {"deviceKey": "34180_00001_00011", "value": parts[1]}])
        elif action == "ai": threading.Thread(target=self.mqtt._run_ai_advisor_wrapper, args=("trip", {"dist": 15.5, "drop": 6.0}), daemon=True).start()

    def _calculate_advanced_stats(self):
        try:
            target_spec = getattr(self, '_vehicle_spec', {"capacity": 0, "range": 0})
            cap = target_spec.get("capacity", 0)
            ran = target_spec.get("range", 0)
            
            if cap > 0:
                self._last_data["api_static_capacity"] = cap
                self._last_data["api_static_range"] = ran
                total_kwh = safe_float(self._last_data.get("api_total_energy_charged", 0))
                odo = safe_float(self._last_data.get("34183_00001_00003", self._last_data.get("34199_00000_00000", 0)))
                calc_max = 0
                if total_kwh > 0 and odo > 0:
                    lifetime_eff = (total_kwh / odo) * 100
                    self._last_data["api_lifetime_efficiency"] = round(lifetime_eff, 2)
                    if lifetime_eff > 0:
                        calc_max = cap / (lifetime_eff / 100)
                        self._last_data["api_calc_max_range"] = round(calc_max, 1)

                if ran > 0 and calc_max > 0:
                    degradation_range = ((ran - calc_max) / ran) * 100.0
                    self._last_data["api_est_range_degradation"] = max(0.0, round(degradation_range, 2))
                
                charge_energy = safe_float(self._last_data.get("api_last_charge_energy", 0))
                start_soc = safe_float(self._last_data.get("api_last_charge_start_soc", 0))
                end_soc = safe_float(self._last_data.get("api_last_charge_end_soc", 0))
                delta_soc = end_soc - start_soc
                
                if charge_energy > 0 and delta_soc >= 10.0:
                    real_capacity = (charge_energy * 0.92) / (delta_soc / 100.0)
                    soh_calc = (real_capacity / cap) * 100.0
                    if 50.0 <= soh_calc <= 110.0: 
                        self._last_data["api_soh_calculated"] = round(min(soh_calc, 100.0), 1)
                else:
                    soh_raw = safe_float(self._last_data.get("34220_00001_00001", 100))
                    self._last_data["api_soh_calculated"] = round(soh_raw, 1)
                    
            batt_pct = safe_float(self._last_data.get("34183_00001_00009", self._last_data.get("34180_00001_00011", 0)))
            calc_max = safe_float(self._last_data.get("api_calc_max_range", 0))
            
            if calc_max > 0:
                self._last_data["api_calc_range_per_percent"] = round(calc_max / 100.0, 2)
                if batt_pct > 0: self._last_data["api_calc_remain_range"] = round(calc_max * (batt_pct / 100.0), 1)
            elif ran > 0:
                self._last_data["api_calc_range_per_percent"] = round(ran / 100.0, 2)
                if batt_pct > 0: self._last_data["api_calc_remain_range"] = round(ran * (batt_pct / 100.0), 1)

            cost_per_kwh = safe_float(self.options.get("cost_per_kwh", 4000))
            gas_price = safe_float(self.options.get("gas_price", 20000))
            gas_km_per_liter = getattr(self, 'gas_km_per_liter', 15.0)

            total_kwh_charged = safe_float(self._last_data.get("api_total_energy_charged", 0))
            self._last_data["api_total_charge_cost_est"] = round(total_kwh_charged * cost_per_kwh)

            odo = safe_float(self._last_data.get("34183_00001_00003", self._last_data.get("34199_00000_00000", 0)))
            if odo > 0 and gas_km_per_liter > 0:
                self._last_data["api_total_gas_cost"] = round((odo / gas_km_per_liter) * gas_price)

        except Exception: pass

    # =================================================================================
    # THUẬT TOÁN NẮN ĐƯỜNG NGẦM (HỖ TRỢ CẢ FILE CHÍNH VÀ FILE ARCHIVE)
    # =================================================================================
    async def async_smooth_trip_background(self, trip_id, raw_route, target_trip_file=None):
        if not raw_route or len(raw_route) < 3: return

        mapbox_token = self.options.get("mapbox_token", "")
        stadia_token = self.options.get("stadia_token", "")

        _LOGGER.warning(f"VinFast: [TRIP {trip_id}] Bắt đầu đẩy {len(raw_route)} tọa độ lên lưới AI Map Matching...")
        smoothed_route = await async_process_route(self.hass, raw_route, mapbox_token, stadia_token)

        # Nếu không truyền file cụ thể, mặc định lưu vào file chính
        trip_file = target_trip_file if target_trip_file else os.path.join(WWW_DIR, f"vinfast_trips_{self.vin.lower()}.json")
        try:
            def update_json_file():
                if not os.path.exists(trip_file): return False
                with open(trip_file, 'r', encoding='utf-8') as f: trips = json.load(f)
                
                updated = False
                for trip in trips:
                    if str(trip.get("id")) == str(trip_id):
                        trip["route"] = smoothed_route
                        trip["is_smoothed"] = True
                        updated = True
                        break
                        
                if updated:
                    with open(trip_file, 'w', encoding='utf-8') as f: json.dump(trips, f, ensure_ascii=False)
                return updated

            _LOGGER.warning(f"VinFast: [TRIP {trip_id}] Đã nắn xong! Đang ghi lại vào {os.path.basename(trip_file)}...")
            updated = await self.hass.async_add_executor_job(update_json_file)
            
            if updated:
                _LOGGER.warning(f"VinFast: [TRIP {trip_id}] -> GHI FILE JSON THÀNH CÔNG!")
                if getattr(self, '_last_data', {}).get("api_trip_route") and "archive" not in trip_file:
                    self._last_data["api_trip_route"] = json.dumps(smoothed_route)
                    self.trigger_callbacks()
            else:
                _LOGGER.error(f"VinFast: [TRIP {trip_id}] Không tìm thấy ID trong file JSON để cập nhật.")
                    
        except Exception as e:
            _LOGGER.error(f"VinFast: Lỗi khi ghi Cache nắn đường: {e}")

    async def async_fix_all_historical_trips(self, force=False):
        """Quét và nắn đường cho cả File Trip Chính và File Archive (Lưu trữ tháng)"""
        vin_str = self.vin.lower()
        now = datetime.datetime.now()
        
        # Tạo danh sách các file cần quét (File chính, file tháng này, file tháng trước)
        prev_month = now.replace(day=1) - datetime.timedelta(days=1)
        files_to_check = [
            os.path.join(WWW_DIR, f"vinfast_trips_{vin_str}.json"),
            os.path.join(WWW_DIR, f"vinfast_trips_archive_{vin_str}_{now.strftime('%Y_%m')}.json"),
            os.path.join(WWW_DIR, f"vinfast_trips_archive_{vin_str}_{prev_month.strftime('%Y_%m')}.json")
        ]

        total_fixed = 0
        for trip_file in files_to_check:
            if not os.path.exists(trip_file): continue

            try:
                def read_trips():
                    with open(trip_file, 'r', encoding='utf-8') as f: return json.load(f)
                
                trips = await self.hass.async_add_executor_job(read_trips)
                pending_trips = []

                for i, trip in enumerate(trips):
                    is_recent = (i < 5)
                    is_archived = "archive" in trip_file
                    
                    # Ưu tiên sửa chuyến chưa smooth. Nếu force=True thì chỉ ép nắn lại 5 chuyến gần nhất của file chính
                    if not trip.get("is_smoothed", False) or (force and is_recent and not is_archived):
                        pending_trips.append(trip)

                if pending_trips:
                    _LOGGER.warning(f"VinFast: Quét thấy {len(pending_trips)} chuyến đi cần nắn thẳng trong file {os.path.basename(trip_file)}")

                for trip in pending_trips:
                    raw_route = trip.get("route", [])
                    if len(raw_route) > 2:
                        await self.async_smooth_trip_background(trip.get("id"), raw_route, target_trip_file=trip_file)
                        total_fixed += 1
                        await asyncio.sleep(2.0) 
                    else:
                        trip["is_smoothed"] = True 
                        def save_trip_ignore():
                            with open(trip_file, 'w', encoding='utf-8') as f: json.dump(trips, f, ensure_ascii=False)
                        await self.hass.async_add_executor_job(save_trip_ignore)
            except Exception as e:
                _LOGGER.error(f"VinFast: Lỗi khi đọc file {os.path.basename(trip_file)}: {e}")
                
        if total_fixed == 0:
            _LOGGER.warning("VinFast: Bản đồ đã được tối ưu toàn bộ. Không có chuyến đi nào cần nắn thêm.")
        else:
            _LOGGER.warning(f"VinFast: HOÀN TẤT NẮN {total_fixed} CHUYẾN ĐI (Bao gồm cả Archive)!")

    def _load_state(self):
        if not self.vin: return
        state_file = os.path.join(WWW_DIR, f"vinfast_state_{self.vin.lower()}.json")
        charge_history_file = os.path.join(WWW_DIR, f"vinfast_charge_history_{self.vin.lower()}.json")
        if os.path.exists(charge_history_file):
            try:
                with open(charge_history_file, 'r', encoding='utf-8') as f:
                    self._last_data["api_charge_history_list"] = json.dumps(json.load(f))
            except: pass
        if os.path.exists(state_file):
            try:
                with open(state_file, 'r', encoding='utf-8') as f:
                    saved_data = json.load(f)
                    if "last_data" in saved_data: self._last_data.update(saved_data["last_data"])
                    if "internal_memory" in saved_data:
                        mem = saved_data["internal_memory"]
                        self._is_trip_active = mem.get("is_trip_active", False)
                        self._trip_start_odo = mem.get("trip_start_odo", 0.0)
                        self._trip_start_time = mem.get("trip_start_time", time.time())
                        self._trip_start_soc = mem.get("trip_start_soc", 100.0)
                        self._trip_accumulated_distance_m = mem.get("trip_accumulated_distance_m", 0.0) 
                        self._eff_soc = mem.get("eff_soc", None)
                        self._eff_gps_dist = mem.get("eff_gps_dist", 0.0)
                        self._eff_time = mem.get("eff_time", None)
                        self._eff_stats = mem.get("eff_stats", {})
                        self._charge_start_soc = mem.get("charge_start_soc", 0.0)
                        self._charge_calc_soc = mem.get("charge_calc_soc", 0.0)
                        self._charge_start_time = mem.get("charge_start_time", time.time())
                        self._charge_calc_time = mem.get("charge_calc_time", time.time())
                        self._is_charging = mem.get("is_charging", False)
                        self._last_is_charging = mem.get("last_is_charging", False)
                        self._current_charge_max_power = mem.get("current_charge_max_power", 0.0)
                        
                        lat_start = self._last_data.get("api_last_lat")
                        lon_start = self._last_data.get("api_last_lon")
                        if lat_start and lon_start: self._last_lat_lon = f"{lat_start},{lon_start}"
            except Exception: pass
        
        vn = str(self._last_data.get("api_vehicle_name", ""))
        if vn.lower() in ["0", "1", "unknown", "none", "", "vinfast"]:
            self._last_data["api_vehicle_name"] = self.vehicle_model_display or "Xe VinFast"
            
        if hasattr(self, 'hass') and self.hass:
            asyncio.run_coroutine_threadsafe(self.async_fix_all_historical_trips(force=False), self.hass.loop)

    def _save_state(self):
        if not self.vin: return
        os.makedirs(WWW_DIR, exist_ok=True)
        state_file = os.path.join(WWW_DIR, f"vinfast_state_{self.vin.lower()}.json")
        changelog_file = os.path.join(WWW_DIR, f"vinfast_changelog_{self.vin.lower()}.json")
        try:
            self._last_data["api_debug_raw_json"] = json.dumps(self._raw_json_dict) if getattr(self, '_raw_json_dict', {}) else "{}"
            data_to_save = {
                "last_data": self._last_data.copy(),
                "internal_memory": {
                    "is_trip_active": getattr(self, '_is_trip_active', False),
                    "trip_start_odo": getattr(self, '_trip_start_odo', 0.0),
                    "trip_start_time": getattr(self, '_trip_start_time', time.time()),
                    "trip_start_soc": getattr(self, '_trip_start_soc', 100.0),
                    "trip_accumulated_distance_m": getattr(self, '_trip_accumulated_distance_m', 0.0), 
                    "eff_soc": getattr(self, '_eff_soc', None),
                    "eff_gps_dist": getattr(self, '_eff_gps_dist', 0.0),
                    "eff_time": getattr(self, '_eff_time', None),
                    "eff_stats": getattr(self, '_eff_stats', {}),
                    "charge_start_soc": getattr(self, '_charge_start_soc', 0.0),
                    "charge_calc_soc": getattr(self, '_charge_calc_soc', 0.0),
                    "charge_start_time": getattr(self, '_charge_start_time', time.time()),
                    "charge_calc_time": getattr(self, '_charge_calc_time', time.time()),
                    "is_charging": getattr(self, '_is_charging', False),
                    "last_is_charging": getattr(self, '_last_is_charging', False),
                    "current_charge_max_power": getattr(self, '_current_charge_max_power', 0.0)
                },
                "unix_time": time.time()
            }
            with open(state_file, 'w', encoding='utf-8') as f: json.dump(data_to_save, f, ensure_ascii=False)
            if hasattr(self, '_changelog_buffer') and len(self._changelog_buffer) > 0:
                old_changelog = []
                if os.path.exists(changelog_file):
                    try:
                        with open(changelog_file, 'r', encoding='utf-8') as cf: old_changelog = json.load(cf)
                    except Exception: pass
                merged_log = (self._changelog_buffer + old_changelog)[:100]
                with open(changelog_file, 'w', encoding='utf-8') as cf: json.dump(merged_log, cf, ensure_ascii=False)
                self._changelog_buffer = []
        except Exception: pass

    def _save_trip_history(self):
        if not self.vin: return
        try:
            import datetime
            os.makedirs(WWW_DIR, exist_ok=True)
            # Việc ghi file archive sẽ do script bên ngoài xử lý, 
            # API chỉ cần ghi vào file chính như bình thường.
            trip_file = os.path.join(WWW_DIR, f"vinfast_trips_{self.vin.lower()}.json")
            trips = []
            if os.path.exists(trip_file):
                try:
                    with open(trip_file, 'r', encoding='utf-8') as f: trips = json.load(f)
                except: pass
            
            dist = float(self._last_data.get("api_trip_distance", 0))
            if dist > 0.05 or len(self._route_coords) > 2: 
                start_dt = datetime.datetime.fromtimestamp(self._trip_start_time)
                end_dt = datetime.datetime.now()
                dur_mins = int((end_dt.timestamp() - self._trip_start_time) / 60)
                start_addr = f"{self._route_coords[0][0]}, {self._route_coords[0][1]}" if self._route_coords else "Unknown"
                end_addr = f"{self._route_coords[-1][0]}, {self._route_coords[-1][1]}" if self._route_coords else "Unknown"
                
                trip_id = int(end_dt.timestamp())
                
                draft_route = moving_average_smooth(self._route_coords, window=3)
                
                new_trip = {
                    "id": trip_id, "date": start_dt.strftime("%d/%m/%Y"), "start_time": start_dt.strftime("%H:%M"),
                    "end_time": end_dt.strftime("%H:%M"), "duration": dur_mins if dur_mins > 0 else 1, "distance": round(dist, 2),
                    "start_address": start_addr, "end_address": end_addr, 
                    "route": draft_route, 
                    "is_smoothed": False 
                }
                trips.insert(0, new_trip) 
                # Giới hạn giữ lại 50 chuyến ở file chính để tránh quá tải
                with open(trip_file, 'w', encoding='utf-8') as f: json.dump(trips[:50], f, ensure_ascii=False)

                if hasattr(self, 'hass') and self.hass:
                    asyncio.run_coroutine_threadsafe(
                        self.async_smooth_trip_background(trip_id, draft_route, target_trip_file=trip_file),
                        self.hass.loop
                    )
        except Exception as e: 
            _LOGGER.error(f"VinFast: Lỗi lưu chuyến đi: {e}")