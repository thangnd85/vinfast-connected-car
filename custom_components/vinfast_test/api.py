import os
import json
import time
import logging
from .const import WWW_DIR
from .api_auth import AuthManager
from .api_mqtt import MQTTManager
from .api_helpers import snap_to_road

_LOGGER = logging.getLogger(__name__)

class VinFastAPI:
    def __init__(self, email, password, vin=None, vehicle_name="Xe VinFast", options=None, gemini_api_key=""):
        # Single Source of Truth
        self.email = email
        self.password = password
        self.gemini_api_key = gemini_api_key
        self.vin = vin
        self.user_id = None
        self.vehicle_name = vehicle_name
        self.vehicle_model_display = "Unknown" 
        self.options = options or {}
        
        self.access_token = None
        self._running = False
        self.callbacks = []
        
        self._last_data = {
            "api_vehicle_status": "Đang kết nối...",
            "api_current_address": "Đang tải...",
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
            "api_ai_advisor": "Hệ thống AI đang chờ phân tích...",
            "api_best_efficiency_band": "Chưa đủ dữ liệu",
            "api_est_range_degradation": 0.0,
            "api_debug_raw": "Chờ kết nối MQTT..." 
        }  
        
        # Biến tính toán dùng chung
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
        self._trip_start_address = "Không xác định"
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
        self._geocode_lock = __import__('threading').Lock()
        
        self._raw_json_dict = {}
        self._changelog_buffer = []

        # Khởi tạo các Module Nan Hoa (Spokes)
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
        if len(candidate) < 2 or candidate.isnumeric() or candidate in ["0", "1"]: return
        if candidate.lower() in ["none", "null", "unknown", "xevinfast"] or "profile_email" in candidate.lower(): return
        self._last_data["api_vehicle_name"] = candidate

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
                    if "last_data" in saved_data:
                        self._last_data.update(saved_data["last_data"])
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
                        
                        lat_start = self._last_data.get("api_last_lat")
                        lon_start = self._last_data.get("api_last_lon")
                        if lat_start and lon_start:
                            self._last_lat_lon = f"{lat_start},{lon_start}"
            except Exception: pass

    def _save_state(self):
        if not self.vin: return
        os.makedirs(WWW_DIR, exist_ok=True)
        state_file = os.path.join(WWW_DIR, f"vinfast_state_{self.vin.lower()}.json")
        changelog_file = os.path.join(WWW_DIR, f"vinfast_changelog_{self.vin.lower()}.json")
        try:
            if hasattr(self, '_raw_json_dict') and len(self._raw_json_dict) > 0:
                self._last_data["api_debug_raw_json"] = json.dumps(self._raw_json_dict)
            else:
                self._last_data["api_debug_raw_json"] = "{}"
                
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
                    "charge_calc_time": getattr(self, '_charge_calc_time', time.time())
                },
                "unix_time": time.time()
            }
            with open(state_file, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, ensure_ascii=False)
                
            if hasattr(self, '_changelog_buffer') and len(self._changelog_buffer) > 0:
                old_changelog = []
                if os.path.exists(changelog_file):
                    try:
                        with open(changelog_file, 'r', encoding='utf-8') as cf:
                            old_changelog = json.load(cf)
                    except Exception: pass
                
                merged_log = self._changelog_buffer + old_changelog
                merged_log = merged_log[:100]
                
                with open(changelog_file, 'w', encoding='utf-8') as cf:
                    json.dump(merged_log, cf, ensure_ascii=False)
                self._changelog_buffer = []
                
        except Exception: pass

    def _save_trip_history(self):
        if not self.vin: return
        try:
            import datetime
            os.makedirs(WWW_DIR, exist_ok=True)
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

                snapped_route = snap_to_road(self._route_coords)

                new_trip = {
                    "id": int(end_dt.timestamp()),
                    "date": start_dt.strftime("%d/%m/%Y"),
                    "start_time": start_dt.strftime("%H:%M"),
                    "end_time": end_dt.strftime("%H:%M"),
                    "duration": dur_mins if dur_mins > 0 else 1,
                    "distance": round(dist, 2),
                    "start_address": start_addr,
                    "end_address": end_addr,
                    "route": snapped_route 
                }
                
                trips.insert(0, new_trip) 
                trips = trips[:50] 
                with open(trip_file, 'w', encoding='utf-8') as f:
                    json.dump(trips, f, ensure_ascii=False)
                    
                month_str = end_dt.strftime("%Y_%m")
                archive_file = os.path.join(WWW_DIR, f"vinfast_trips_archive_{self.vin.lower()}_{month_str}.json")
                archives = []
                if os.path.exists(archive_file):
                    try:
                        with open(archive_file, 'r', encoding='utf-8') as f: archives = json.load(f)
                    except: pass
                archives.insert(0, new_trip)
                with open(archive_file, 'w', encoding='utf-8') as f:
                    json.dump(archives, f, ensure_ascii=False)
                    
        except Exception: pass