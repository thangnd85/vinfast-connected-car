import json
import time
import datetime
import logging
import uuid
import random
import math
import threading
import paho.mqtt.client as mqtt

from .const import WWW_DIR, MOCK_FILE
from .api_helpers import get_address_from_osm, get_weather_data, get_osrm_route, get_ai_advice, safe_float

_LOGGER = logging.getLogger(__name__)

class MQTTManager:
    def __init__(self, core):
        self.core = core
        self.client = None
        self._needs_mqtt_renew = False 
        self._mqtt_client_id_rand = "".join(random.choice("0123456789qwertyuiop") for _ in range(15))

    def start(self):
        self.core._running = True
        threading.Thread(target=self._api_polling_loop, daemon=True).start()
        threading.Thread(target=self.core.auth.fetch_charging_history, daemon=True).start()

    def stop(self):
        if self.client:
            self.client.loop_stop()
            try: self.client.disconnect()
            except: pass

    def _renew_aws_connection(self):
        try:
            if self.client:
                self.client.loop_stop()
                try: self.client.disconnect()
                except: pass
                self.client = None 
                
            self.client = mqtt.Client(client_id=f"Android_{self.core.vin}_{self._mqtt_client_id_rand}", transport="websockets")
            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            self.client.on_message = self._on_message
            self.client.tls_set()
            
            self.core.auth.login()
            self.core.auth.register_device_trust()
            new_url = self.core.auth.get_aws_mqtt_url()
            if new_url:
                self.client.ws_set_options(path=new_url.split(self.core.iot_endpoint)[1])
                self.client.connect(self.core.iot_endpoint, 443, 30)
                self.client.loop_start()
                self._needs_mqtt_renew = False 
        except Exception as e: pass

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0: 
            client.subscribe(f"/mobile/{self.core.vin}/push", qos=1)
            client.subscribe(f"monitoring/server/{self.core.vin}/push", qos=1)
            client.subscribe(f"/server/{self.core.vin}/remctrl", qos=1)
            self.core._last_mqtt_msg_time = time.time()

    def _on_disconnect(self, client, userdata, rc):
        self._needs_mqtt_renew = True

    def _send_heartbeat(self, state="1"):
        if not self.client or not self.client.is_connected() or not self.core.vin: return
        topic = f"/vehicles/{self.core.vin}/push/connected/heartbeat"
        payload = {"version": "1.2", "timestamp": int(time.time() * 1000), "trans_id": str(uuid.uuid4()), "content": {"34183": { "1": { "54": str(state) } }}}
        try: self.client.publish(topic, json.dumps(payload), qos=1)
        except Exception: pass

    def _api_polling_loop(self):
        time.sleep(5) 
        if not self.core.user_id: self.core.auth.get_vehicles()
        self._renew_aws_connection()
        self.core.auth.register_resources()
        
        last_heartbeat = time.time()
        last_state_save = time.time()
        last_aws_renew = time.time()
        
        while self.core._running:
            try:
                time.sleep(1)
                now = time.time()
                core = self.core

                if now - last_heartbeat >= 60:
                    last_heartbeat = now
                    state = "2" if getattr(core, '_is_moving', False) else "1"
                    self._send_heartbeat(state)

                if now - last_aws_renew >= 3000 or self._needs_mqtt_renew:
                    last_aws_renew = now
                    self._renew_aws_connection()

                time_since_last_msg = now - getattr(core, '_last_mqtt_msg_time', now)
                if getattr(core, '_is_moving', False) and time_since_last_msg > 180:
                    self._needs_mqtt_renew = True
                    core._last_mqtt_msg_time = now 

                if getattr(core, '_is_charging', False):
                    if now - getattr(self, '_last_active_charge_fetch', 0) >= 60:
                        self._last_active_charge_fetch = now
                        has_api_power = core.auth.fetch_active_charging_session()
                        if has_api_power:
                            core._last_api_power_time = now 
                        core.trigger_callbacks()

                if getattr(core, '_vehicle_offline', False):
                    time_since_last_wakeup = now - getattr(core, '_last_auto_wakeup_time', 0)
                    if time_since_last_wakeup > 180:
                        core.auth.register_resources() 

                # =======================================================================
                # ĐÃ TÁCH KHỎI IF IS_MOVING: CẬP NHẬT TRẠM SẠC ĐỊNH KỲ MỖI 15 PHÚT
                # =======================================================================
                if now - getattr(self, '_last_periodic_station_fetch', 0) >= 900:
                    self._last_periodic_station_fetch = now
                    threading.Thread(target=core.auth.fetch_nearby_stations, kwargs={"force": True}, daemon=True).start()

                time_since_move = now - getattr(core, '_last_actual_move_time', now)
                if getattr(core, '_is_trip_active', False) and not getattr(core, '_is_moving', False) and time_since_move >= 300:
                    core._is_trip_active = False 
                    core._save_trip_history()
                    
                    trip_dist = float(core._last_data.get("api_trip_distance", 0))
                    soc_start = getattr(core, '_trip_start_soc', 100.0)
                    soc_end = safe_float(core._last_data.get("34183_00001_00009", core._last_data.get("34180_00001_00011", 50)))
                    soc_drop = soc_start - soc_end
                    
                    std_range = safe_float(core._last_data.get("api_static_range", 210))
                    expected_km_per_1 = (std_range / 100.0) if std_range > 0 else 2.1
                    
                    if trip_dist >= expected_km_per_1: 
                        threading.Thread(target=self._run_ai_advisor_wrapper, args=("trip", {"dist": trip_dist, "drop": soc_drop}), daemon=True).start()
                        
                    core._trip_start_odo = 0.0
                    core._trip_start_time = time.time()
                    core._route_coords = []
                    core._trip_accumulated_distance_m = 0.0 
                    core._save_state() 

                if now - last_state_save >= 60:
                    last_state_save = now
                    core._save_state()
            except Exception: pass

    def _update_location_async(self, lat, lon):
        try:
            core = self.core
            grid_coord = f"{round(float(lat), 3)},{round(float(lon), 3)}"
            curr_addr = core._last_data.get("api_current_address", "")
            
            def fetch_weather():
                now = time.time()
                if now - getattr(core, '_last_weather_fetch_time', 0) < 900: return
                w_data = get_weather_data(lat, lon)
                if w_data:
                    core._last_weather_fetch_time = now
                    core._last_data["api_outside_temp"] = w_data["temp"]
                    core._last_data["api_weather_condition"] = w_data["condition"]
                    core._last_data["api_hvac_load_estimate"] = w_data["hvac"]
                    
                    bad_wmo_codes = [45, 48, 51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 71, 73, 75, 77, 80, 81, 82, 85, 86, 95, 96, 99]
                    is_bad_weather = w_data["code"] in bad_wmo_codes
                    is_extreme_temp = w_data["temp"] >= 35 or w_data["temp"] <= 15
                    cond_lower = str(w_data["condition"]).lower()
                    has_bad_keyword = any(k in cond_lower for k in ["mưa", "bão", "sương mù", "tuyết", "gió", "sấm chớp", "mù"])

                    if now - getattr(core, '_last_ai_weather_time', 0) > 1800 and (is_bad_weather or is_extreme_temp or has_bad_keyword):
                        core._last_ai_weather_time = now
                        threading.Thread(target=self._run_ai_advisor_wrapper, args=("weather", {"temp": w_data["temp"], "cond": w_data["condition"]}), daemon=True).start()
                        
                    core._save_state()
                    core.trigger_callbacks()
                    
            threading.Thread(target=fetch_weather, daemon=True).start()
            
            with core._geocode_lock:
                if getattr(core, '_last_geocoded_grid', None) != grid_coord or "Tọa độ" in curr_addr or "Đang kết nối" in curr_addr or "Loading" in curr_addr:
                    addr = get_address_from_osm(lat, lon)
                    if addr:
                        core._last_data["api_current_address"] = addr
                        core._last_geocoded_grid = grid_coord 
                        threading.Thread(target=core.auth.fetch_nearby_stations, kwargs={"force": False}, daemon=True).start()
                    else:
                        core._last_data["api_current_address"] = f"Lat/Lon: {lat:.5f}, {lon:.5f}"
                    core._save_state()
                    core.trigger_callbacks()
        except Exception: pass

    def _run_ai_advisor_wrapper(self, mode="trip", data_payload=None):
        core = self.core
        try:
            if not getattr(core, 'gemini_api_key', None) or core.gemini_api_key.strip() == "":
                return 
                
            std_range = safe_float(core._last_data.get("api_static_range", 210))
            expected_km_per_1 = round(std_range / 100.0, 2) if std_range > 0 else 2.1
            
            context_data = {
                "temp": core._last_data.get("api_outside_temp", "Unknown"),
                "cond": core._last_data.get("api_weather_condition", "Unknown"),
                "hvac": core._last_data.get("api_hvac_load_estimate", "Normal"),
                "expected_km_per_1": expected_km_per_1,
                "trip_dist": float(core._last_data.get("api_trip_distance", 0.0)),
                "trip_avg_speed": core._last_data.get("api_trip_avg_speed", 0)
            }
            
            ai_model = core.options.get("gemini_model", core.options.get("CONF_GEMINI_MODEL", "gemini-2.5-flash"))
            vi = core.lang == "vi"
            
            if mode == "weather":
                core._last_data["api_ai_advisor"] = f"☁️ Thời tiết khắc nghiệt. Đang gọi AI..." if vi else "☁️ Extreme weather. Asking AI..."
            elif mode == "anomaly":
                core._last_data["api_ai_advisor"] = f"⚠️ Sụt pin nhanh! Đang chờ AI phân tích..." if vi else "⚠️ Fast battery drop! Analyzing..."
            else:
                core._last_data["api_ai_advisor"] = "🔄 Đang gửi dữ liệu cho AI..." if vi else "🔄 Sending trip data to AI..."
                
            core.trigger_callbacks()
            result = get_ai_advice(core.gemini_api_key, ai_model, mode, data_payload, context_data)
            
            core._last_data["api_ai_advisor"] = result
            core._save_state()
            core.trigger_callbacks()
        except Exception: pass

    def _filter_critical_data(self, key, current_val, fallback_val):
        if current_val is None or str(current_val).strip().upper() in ["NONE", "NULL", "UNKNOWN", ""]:
            return fallback_val
        try:
            c_val_float = float(current_val)
            f_val_float = float(fallback_val) if fallback_val is not None else 0.0
            
            no_zero_keys = [
                "34183_00001_00009", "34180_00001_00011", "34183_00001_00011", "34180_00001_00007", 
                "34193_00001_00012", "34193_00001_00014", "34193_00001_00019", "34220_00001_00001", 
                "34183_00001_00005", "00006_00001_00000", "00006_00001_00001"  
            ]
            if key in no_zero_keys and c_val_float <= 0.0001 and f_val_float > 0: return fallback_val

            odo_keys = ["34183_00001_00003", "34199_00000_00000"]
            if key in odo_keys and c_val_float < f_val_float: return fallback_val
        except Exception: pass
        return current_val

    def _on_message(self, client, userdata, msg):
        core = self.core
        current_time = time.time()
        core._last_mqtt_msg_time = current_time 
        
        try:
            payload = json.loads(msg.payload.decode('utf-8'))
            data_dict = {}
            items = []
            if isinstance(payload, list): items = payload
            elif isinstance(payload, dict):
                if "data" in payload and isinstance(payload["data"], list): items = payload["data"]
                elif "content" in payload and isinstance(payload["content"], list): items = payload["content"]
            
            time_str = datetime.datetime.now().strftime("%H:%M:%S")
            
            for item in items:
                if not isinstance(item, dict): continue
                obj, inst, res = str(item.get("objectId", "0")).zfill(5), str(item.get("instanceId", "0")).zfill(5), str(item.get("resourceId", "0")).zfill(5)
                key = item.get("deviceKey") if "deviceKey" in item else f"{obj}_{inst}_{res}"
                val = item.get("value")
                
                if key and val is not None:
                    str_val = str(val).strip()
                    old_val = str(core._last_data.get(key, "N/A"))
                    if old_val != str_val:
                        core._raw_json_dict[key] = str_val
                        core._changelog_buffer.insert(0, {"time": time_str, "code": key, "old_value": old_val, "new_value": str_val})
                
                if key == "56789_00001_00007":
                    if str(val) == "CONNECTION_LOST": core._vehicle_offline = True
                    elif str(val) == "NONE": core._vehicle_offline = False
                
                if key == "34180_00001_00011" and isinstance(val, str) and "profile_email" in val: continue 
                if key and val is not None: data_dict[key] = self._filter_critical_data(key, val, core._last_data.get(key))
            
            if not data_dict: return
            
            t1, t2, t3 = data_dict.get("34193_00001_00012"), data_dict.get("34193_00001_00014"), data_dict.get("34193_00001_00019")
            target_val = t1 if t1 is not None else (t2 if t2 is not None else t3)
            if target_val is not None:
                try:
                    if float(target_val) > 0: core._last_data["api_target_charge_limit"] = float(target_val)
                except: pass

            core._last_data.update(data_dict)
            core._last_data["api_debug_raw"] = f"Nhận: {len(data_dict)} mã ({time_str})"
            
            for k in ["34180_00001_00010", "34183_00001_00010", "34181_00001_00007"]:
                if k in data_dict and isinstance(data_dict[k], str): core._update_vehicle_name(data_dict[k])
                
        except Exception: return

        current_soc = safe_float(core._last_data.get("34183_00001_00009", core._last_data.get("34180_00001_00011", 0)))
        
        try:
            model = getattr(core, "vehicle_model_display", "Unknown").upper()
            if "VF8" in model or "VF9" in model:
                gear = str(core._last_data.get("34187_00000_00000", "1"))
                speed = safe_float(core._last_data.get("34188_00000_00000", 0))
            else: 
                gear = str(core._last_data.get("34183_00001_00001", "1"))
                speed = safe_float(core._last_data.get("34183_00001_00002", 0))

            if speed > 0 or gear in ["2", "4", "D", "R"]:
                core._is_moving = True
                core._last_actual_move_time = current_time
            else:
                core._is_moving = False

            vi = core.lang == "vi"
            base_status = ("Đang di chuyển" if vi else "Moving") if core._is_moving else (("Đang đỗ" if vi else "Parked") if gear == "1" else ("Đang dừng" if vi else "Stopped"))

            if core._is_moving and not getattr(core, '_is_trip_active', False):
                core._trip_start_time = current_time
                core._trip_start_soc = current_soc
                core._is_trip_active = True
                core._last_data["api_trip_distance"] = 0.0
                core._last_data["api_trip_efficiency"] = 0.0
                core._trip_accumulated_distance_m = 0.0 
                core._route_coords = [] 
                
                core._save_state()
        except Exception: pass

        try:
            lat = safe_float(core._last_data.get("00006_00001_00000"))
            lon = safe_float(core._last_data.get("00006_00001_00001"))
            
            if lat > 0 and lon > 0:
                curr_coord = f"{lat},{lon}"
                if curr_coord != getattr(core, '_last_lat_lon', ""): 
                    core._last_lat_lon = curr_coord
                    # BẮT BUỘC LƯU LẠI VỊ TRÍ ĐỂ TRẠM SẠC LUÔN CÓ TỌA ĐỘ NGAY CẢ KHI RESTART
                    core._last_data["api_last_lat"] = lat
                    core._last_data["api_last_lon"] = lon
                    
                    threading.Thread(target=self._update_location_async, args=(lat, lon), daemon=True).start()
                    
                    if getattr(core, '_is_trip_active', False):
                        actual_speed_kmh = float(speed)
                        if not core._route_coords:
                            core._route_coords.append([round(lat, 6), round(lon, 6), int(actual_speed_kmh)])
                            core._last_gps_time = current_time
                        else:
                            last_lat = core._route_coords[-1][0]
                            last_lon = core._route_coords[-1][1]
                            R = 6371000 
                            phi1, phi2 = math.radians(last_lat), math.radians(lat)
                            a = math.sin(math.radians(lat - last_lat)/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(math.radians(lon - last_lon)/2)**2
                            distance_m = R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
                            
                            time_diff = current_time - core._last_gps_time
                            
                            is_valid_point = True
                            if time_diff > 0:
                                implied_speed_kmh = (distance_m / time_diff) * 3.6
                                if implied_speed_kmh > 180.0: 
                                    is_valid_point = False
                                    
                            if actual_speed_kmh == 0 and distance_m > 30.0: 
                                is_valid_point = False

                            if is_valid_point and distance_m > 0:
                                core._trip_accumulated_distance_m += distance_m
                                
                                core._eff_gps_dist = getattr(core, '_eff_gps_dist', 0.0) + distance_m
                                
                                core._route_coords.append([round(lat, 6), round(lon, 6), int(actual_speed_kmh)])
                                core._last_gps_time = current_time
                                
                                if len(core._route_coords) > 2500: core._route_coords.pop(0) 
                                core._last_data["api_trip_route"] = json.dumps(core._route_coords)
                                
            if getattr(core, '_is_trip_active', False):
                final_trip_dist = core._trip_accumulated_distance_m / 1000.0
                core._last_data["api_trip_distance"] = round(final_trip_dist, 2)

                if final_trip_dist > 0:
                    trip_hrs = (current_time - getattr(core, '_trip_start_time', current_time)) / 3600.0
                    if trip_hrs > 0: core._last_data["api_trip_avg_speed"] = round(final_trip_dist / trip_hrs, 1)

                    if getattr(core, '_trip_start_soc', 0) > current_soc:
                        cap = safe_float(core._last_data.get("api_static_capacity", 0))
                        if cap > 0:
                            energy_used = ((core._trip_start_soc - current_soc) / 100.0) * cap
                            core._last_data["api_trip_energy_used"] = round(energy_used, 2)
                            core._last_data["api_trip_efficiency"] = round((energy_used / final_trip_dist) * 100, 2)
                            
                            cost_per_kwh = safe_float(core.options.get("cost_per_kwh", 4000))
                            core._last_data["api_trip_charge_cost"] = round(energy_used * cost_per_kwh)

                    gas_km_per_liter = getattr(core, 'gas_km_per_liter', 15.0)
                    gas_price = safe_float(core.options.get("gas_price", 20000))
                    if gas_km_per_liter > 0:
                        core._last_data["api_trip_gas_cost"] = round((final_trip_dist / gas_km_per_liter) * gas_price)

        except Exception: pass

        if current_soc > 0:
            if getattr(core, '_eff_initial_soc', None) is None or current_soc > core._eff_initial_soc:
                core._eff_initial_soc = current_soc
                core._eff_start_soc = current_soc
                core._eff_gps_dist = 0.0
                core._eff_ignored_first = False
                
            if current_soc < getattr(core, '_eff_start_soc', current_soc):
                if not getattr(core, '_eff_ignored_first', False):
                    if core._eff_initial_soc - current_soc >= 1.0:
                        core._eff_ignored_first = True
                        core._eff_start_soc = current_soc
                        core._eff_gps_dist = 0.0 
                else:
                    drop = core._eff_start_soc - current_soc
                    if drop >= 1.0:
                        dist_km = getattr(core, '_eff_gps_dist', 0.0) / 1000.0
                        if dist_km > 0:
                            eff = dist_km / drop
                            core._last_data["api_calc_range_per_percent"] = round(eff, 2)
                            
                            std_range = safe_float(core._last_data.get("api_static_range", 210))
                            expected_km_per_1 = std_range / 100.0 if std_range > 0 else 2.1
                            
                            if eff < (expected_km_per_1 * 0.70):
                                now = time.time()
                                if now - getattr(core, '_last_ai_anomaly_time', 0) > 900:
                                    core._last_ai_anomaly_time = now
                                    actual_spd = float(speed)
                                    threading.Thread(target=self._run_ai_advisor_wrapper, args=("anomaly", {"dist": dist_km, "drop": drop, "expected": expected_km_per_1, "speed": actual_spd}), daemon=True).start()
                        
                        core._eff_start_soc = current_soc
                        core._eff_gps_dist = 0.0

        try:
            if "VF8" in model or "VF9" in model: c_status = str(core._last_data.get("34183_00000_00001", "0"))
            else: c_status = str(core._last_data.get("34193_00001_00005", "0"))

            is_charging = (c_status == "1")
            is_fully_charged = False 

            if c_status in ["0", "2", "3", "4"] or getattr(core, '_is_moving', False):
                is_charging = False
                is_fully_charged = False

            t_limit = safe_float(core._last_data.get("api_target_charge_limit", 100))
            if t_limit > 0 and current_soc >= t_limit and (is_charging or c_status in ["2", "3"]):
                is_fully_charged = True
                is_charging = False

            core._is_charging = is_charging
            vi = core.lang == "vi"

            if is_charging: core._last_data["api_vehicle_status"] = "Đang sạc" if vi else "Charging"
            elif is_fully_charged: core._last_data["api_vehicle_status"] = "Đã sạc xong" if vi else "Fully Charged"
            else: core._last_data["api_vehicle_status"] = base_status

            if getattr(core, '_is_first_mqtt_message', True):
                core._is_first_mqtt_message = False
                if not is_charging:
                    core._last_is_charging = False

        except Exception as e: pass

        try:
            if core._is_charging and not getattr(core, '_last_is_charging', False):
                core._current_charge_max_power = 0.0
                if current_soc > 0:
                    core._last_data["api_last_charge_start_soc"] = current_soc
                    core._last_data["api_last_charge_end_soc"] = current_soc 
                    core._charge_start_soc = current_soc
                else:
                    core._charge_start_soc = safe_float(core._last_data.get("api_last_charge_start_soc", 0))

                core._charge_calc_soc = core._charge_start_soc
                core._charge_start_time = current_time
                core._charge_calc_time = current_time
                core._last_data["api_live_charge_power"] = 0.0
                core._last_is_charging = True
                
                core._eff_initial_soc = current_soc
                core._eff_start_soc = current_soc
                core._eff_gps_dist = 0.0
                core._eff_ignored_first = False
                
                core._save_state() 
                
            elif core._is_charging and getattr(core, '_last_is_charging', False):
                if current_soc > 0 and current_soc >= core._charge_start_soc:
                    core._last_data["api_last_charge_end_soc"] = current_soc

                if getattr(core, '_charge_calc_soc', 0.0) == 0.0 or current_soc < core._charge_calc_soc:
                    core._charge_calc_soc = current_soc
                    core._charge_calc_time = current_time
                    core._last_data["api_live_charge_power"] = 0.0
                elif current_soc > core._charge_calc_soc and current_soc > 0:
                    delta_soc = current_soc - core._charge_calc_soc
                    delta_time_hrs = (current_time - core._charge_calc_time) / 3600.0
                    cap = safe_float(core._last_data.get("api_static_capacity", 18.64))
                    if cap == 0: cap = 18.64
                    
                    if core._charge_calc_soc > core._charge_start_soc:
                        if delta_time_hrs > 0.002: 
                            power = (delta_soc / 100.0) * cap / delta_time_hrs
                            if 0 < power < 360: 
                                if current_time - getattr(core, '_last_api_power_time', 0) > 120:
                                    core._last_data["api_live_charge_power"] = round(power, 1)
                                core._current_charge_max_power = max(getattr(core, '_current_charge_max_power', 0.0), power)
                                core._last_data["34183_00000_00012"] = round(power, 1)
                    else:
                        if current_time - getattr(core, '_last_api_power_time', 0) > 120:
                            core._last_data["api_live_charge_power"] = 0.0

                    core._charge_calc_soc = current_soc
                    core._charge_calc_time = current_time
                    core._save_state()
                elif current_time - getattr(core, '_charge_calc_time', current_time) > 900:
                    core._last_data["api_live_charge_power"] = 0.0
                    core._last_data["34183_00000_00012"] = 0.0
                    
            elif not core._is_charging and getattr(core, '_last_is_charging', False):
                if current_soc > 0 and current_soc >= getattr(core, '_charge_start_soc', 0):
                    core._last_data["api_last_charge_end_soc"] = current_soc
                else:
                    current_soc = safe_float(core._last_data.get("api_last_charge_end_soc", getattr(core, '_charge_start_soc', 0)))
                    
                delta_soc = current_soc - getattr(core, '_charge_start_soc', 0)
                if getattr(core, '_charge_start_time', 0) > 0:
                    core._last_data["api_last_charge_duration"] = round((current_time - core._charge_start_time) / 60.0, 0)
                
                if delta_soc >= 0.5: 
                    cap = safe_float(core._last_data.get("api_static_capacity", 18.64))
                    if cap == 0: cap = 18.64
                    added_kwh = (delta_soc / 100.0) * cap
                    
                    core._last_data["api_last_charge_energy"] = round(added_kwh / 0.92, 2)
                    core._last_data["api_last_charge_efficiency"] = 92.0
                    
                    is_home_charge = False
                    max_pwr = getattr(core, '_current_charge_max_power', 0.0)
                    try:
                        stations = json.loads(core._last_data.get("api_nearby_stations", "[]"))
                        if not stations or float(stations[0].get("dist", 999)) > 0.5: is_home_charge = True 
                    except: pass
                    
                    if max_pwr > 0 and max_pwr <= 11.0: is_home_charge = True 
                        
                    def verify_and_update_charge():
                        time.sleep(15)
                        prev_pub = int(core._last_data.get("api_public_charge_sessions", 0))
                        prev_history = core._last_data.get("api_charge_history_list", "[]")
                        max_attempts = 6 if max_pwr > 5.0 else 2
                        api_success = False
                        
                        for attempt in range(max_attempts):
                            if attempt > 0: time.sleep(30)
                            core.auth.fetch_charging_history()
                            new_pub = int(core._last_data.get("api_public_charge_sessions", 0))
                            new_history = core._last_data.get("api_charge_history_list", "[]")
                            
                            if new_pub > prev_pub:
                                api_success = True
                                try:
                                    history_list = json.loads(new_history)
                                    if history_list and len(history_list) > 0:
                                        rest_kwh = float(history_list[0].get("kwh", 0.0))
                                        if rest_kwh > 0.0:
                                            eff = (added_kwh / rest_kwh) * 100.0
                                            core._last_data["api_last_charge_energy"] = round(rest_kwh, 2)
                                            core._last_data["api_last_charge_efficiency"] = round(min(eff, 100.0), 1)
                                except Exception: pass
                                break
                            if new_history == prev_history and prev_history != "[]" and is_home_charge and max_pwr <= 11.0:
                                break

                        if not api_success:
                            core._last_data["api_home_charge_sessions"] = int(core._last_data.get("api_home_charge_sessions", 0)) + 1
                            core._last_data["api_home_charge_kwh"] = round(float(core._last_data.get("api_home_charge_kwh", 0.0)) + added_kwh, 2)
                        
                        core._save_state()
                        core.trigger_callbacks()

                    threading.Thread(target=verify_and_update_charge, daemon=True).start()
                
                core._last_is_charging = False
                core._charge_calc_soc = 0.0
                core._charge_calc_time = current_time
                core._last_data["api_live_charge_power"] = 0.0
                core._last_data["34183_00000_00012"] = 0.0
                core._current_charge_max_power = 0.0 
                core._save_state() 

        except Exception: pass

        try:
            open_doors = []
            
            door_map = {
                "10351_00002_00050": "Cửa lái", "10351_00001_00050": "Cửa phụ",
                "10351_00004_00050": "Cửa sau T", "10351_00003_00050": "Cửa sau P",
                "10351_00006_00050": "Cốp", "10351_00005_00050": "Capo"
            }
            for dk, dname in door_map.items():
                if str(core._last_data.get(dk, "0")) == "1": open_doors.append(dname)
                
            window_map = {
                "34215_00002_00002": "Kính lái", "34215_00001_00002": "Kính phụ",
                "34215_00004_00002": "Kính sau T", "34215_00003_00002": "Kính sau P"
            }
            for wk, wname in window_map.items():
                if str(core._last_data.get(wk, "0")) == "2": open_doors.append(wname)
            
            model_name = getattr(core, "vehicle_model_display", "Unknown").upper()
            
            lock_1 = str(core._last_data.get("34213_00001_00003", "1"))
            is_unlocked = (lock_1 == "0")
            
            if "VF5" in model_name or "VF 5" in model_name or "VF6" in model_name or "VF 6" in model_name or "VF7" in model_name or "VF 7" in model_name or "E34" in model_name:
                lock_2 = str(core._last_data.get("34206_00001_00001", "1"))
                if lock_2 == "0":
                    is_unlocked = True
                    
            is_parked = (gear == "1") 
            
            warnings = []
            if open_doors: 
                warnings.append(f"Đang mở {', '.join(open_doors)}")
            if is_parked and is_unlocked: 
                warnings.append("Chưa khóa xe")
            
            if warnings:
                core._last_data["api_security_warning"] = " | ".join(warnings)
            else:
                core._last_data["api_security_warning"] = "An toàn"
        except Exception as e: 
            pass

        core.trigger_callbacks()