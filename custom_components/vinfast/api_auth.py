import requests
import time
import datetime
import hashlib
import hmac
import base64
import urllib.parse
import threading
import logging
import json
import os

from .const import DEVICE_ID, WWW_DIR
from .model_registry import get_vehicle_profile
from .api_helpers import safe_float

_LOGGER = logging.getLogger(__name__)

class AuthManager:
    def __init__(self, core):
        self.core = core

    def _get_base_headers(self, vin_override=None):
        request_vin = vin_override or self.core.vin
        headers = {
            "Authorization": f"Bearer {self.core.access_token}", 
            "x-service-name": "CAPP",
            "x-app-version": "2.17.5", 
            "x-device-platform": "android", 
            "x-device-identifier": DEVICE_ID,
            "Content-Type": "application/json"
        }
        if request_vin and request_vin != "none": headers["x-vin-code"] = request_vin
        if self.core.user_id: headers["x-player-identifier"] = self.core.user_id
        return headers

    def _safe_request(self, method, url, max_retries=3, delay=5, **kwargs):
        for attempt in range(max_retries):
            try:
                if method.upper() == "POST": return requests.post(url, **kwargs)
                elif method.upper() == "PUT": return requests.put(url, **kwargs)
                else: return requests.get(url, **kwargs)
            except Exception as e:
                if attempt < max_retries - 1: time.sleep(delay)
        return None

    def login(self):
        url = f"https://{self.core.auth0_domain}/oauth/token"
        res = self._safe_request("POST", url, json={
            "client_id": self.core.auth0_client_id, "grant_type": "password",
            "username": self.core.email, "password": self.core.password,
            "scope": "openid profile email offline_access", "audience": self.core.api_base
        }, timeout=15) 
        if res and res.status_code == 200:
            self.core.access_token = res.json()["access_token"]
            return self.core.access_token
        return None

    def get_vehicles(self):
        url = f"{self.core.api_base}/ccarusermgnt/api/v1/user-vehicle"
        res = self._safe_request("GET", url, headers=self._get_base_headers(vin_override="none"), timeout=15)
        if res and res.status_code == 200:
            vehicles = res.json().get("data", [])
            if vehicles:
                v = vehicles[0]
                self.core.user_id = str(v.get("userId", ""))
                if not self.core.vin: self.core.vin = v.get("vinCode", "")
                self.core._load_state()

                self.core.vehicle_model_display = v.get("marketingName") or v.get("dmsVehicleModel") or "VF"
                self.core._last_data["api_vehicle_model"] = self.core.vehicle_model_display
                
                plate = v.get("licensePlate")
                custom_name = v.get("customizedVehicleName")
                
                if plate and len(str(plate)) > 3 and str(plate).lower() != "vinfast":
                    self.core.vehicle_name = plate
                    self.core._last_data["api_vehicle_name"] = plate
                    self.core._last_data["34181_00001_00007"] = plate
                elif custom_name and len(str(custom_name)) > 1 and not str(custom_name).isnumeric() and str(custom_name).lower() != "vinfast":
                    self.core.vehicle_name = custom_name
                    self.core._last_data["api_vehicle_name"] = custom_name
                else:
                    self.core._last_data["api_vehicle_name"] = self.core.vehicle_model_display
                
                profile = get_vehicle_profile(self.core.vehicle_model_display)
                self.core._active_sensors = profile["sensors"]
                self.core._vehicle_spec = profile["spec"]
                self.core.ev_kwh_per_km = safe_float(self.core.options.get("ev_kwh_per_km", self.core._vehicle_spec.get("ev_kwh_per_km", 0.15)))
                self.core.gas_km_per_liter = safe_float(self.core.options.get("gas_km_per_liter", self.core._vehicle_spec.get("gas_km_per_liter", 15.0)))
                
                self.core._calculate_advanced_stats()
                lat_start = self.core._last_data.get("api_last_lat")
                lon_start = self.core._last_data.get("api_last_lon")
                if lat_start and lon_start:
                    threading.Thread(target=self.core.mqtt._update_location_async, args=(lat_start, lon_start), daemon=True).start()
            return vehicles
        return []

    def _generate_x_hash(self, method, api_path, vin, timestamp_ms, secret_key="Vinfast@2025"):
        path = api_path.split("?")[0]
        if not path.startswith("/"): path = "/" + path
        parts = [method, path, vin, secret_key, str(timestamp_ms)] if vin else [method, path, secret_key, str(timestamp_ms)]
        return base64.b64encode(hmac.new(secret_key.encode('utf-8'), "_".join(parts).lower().encode('utf-8'), hashlib.sha256).digest()).decode('utf-8')

    def _generate_x_hash_2(self, platform, vin_code, identifier, path, method, timestamp_ms, hash2_key="ConnectedCar@6521"):
        norm_path = path.split("?")[0].strip("/").replace("/", "_")
        parts = [platform, vin_code, identifier, norm_path, method, str(timestamp_ms)] if vin_code else [platform, identifier, norm_path, method, str(timestamp_ms)]
        return base64.b64encode(hmac.new(hash2_key.encode('utf-8'), "_".join(parts).lower().encode('utf-8'), hashlib.sha256).digest()).decode('utf-8')

    def _post_api(self, path, payload, max_retries=1, vin_override=None):
        for attempt in range(max_retries + 1):
            ts = int(time.time() * 1000)
            request_vin = vin_override or self.core.vin
            headers = self._get_base_headers(request_vin)
            headers.update({
                "X-HASH": self._generate_x_hash("POST", path, request_vin, ts),
                "X-HASH-2": self._generate_x_hash_2("android", request_vin, DEVICE_ID, path, "POST", ts),
                "X-TIMESTAMP": str(ts)
            })
            try:
                res = requests.post(f"{self.core.api_base}/{path}", headers=headers, json=payload, timeout=15)
                # CHÌA KHÓA: Nếu API trả về 401 hoặc 403 (Hết hạn Token), tự động Login lấy Token mới và gọi lại
                if res.status_code in [401, 403]:
                    _LOGGER.warning(f"VinFast: Token hết hạn (Lỗi {res.status_code}), đang xin cấp lại Token...")
                    self.login() 
                    continue
                return res
            except Exception as e:
                _LOGGER.error(f"VinFast: Lỗi kết nối API POST - {e}")
                time.sleep(2)
        return None

    def register_device_trust(self):
        try:
            ts = int(time.time() * 1000)
            headers = self._get_base_headers()
            headers.update({"X-HASH": self._generate_x_hash("PUT", "ccarusermgnt/api/v1/device-trust/fcm-token", self.core.vin, ts), "X-HASH-2": self._generate_x_hash_2("android", self.core.vin, DEVICE_ID, "ccarusermgnt/api/v1/device-trust/fcm-token", "PUT", ts), "X-TIMESTAMP": str(ts)})
            self._safe_request("PUT", f"{self.core.api_base}/ccarusermgnt/api/v1/device-trust/fcm-token", headers=headers, json={"fcmToken": f"ha_bypass_token_{int(time.time())}", "devicePlatform": "android"}, timeout=10, max_retries=2, delay=2)
        except Exception: pass

    def register_resources(self):
        try:
            self._post_api("ccarusermgnt/api/v1/user-vehicle/set-primary-vehicle", {"vinCode": self.core.vin})
            self._post_api("ccaraccessmgmt/api/v1/remote/app/wakeup", {})
            
            active_dict = getattr(self.core, '_active_sensors', {})
            reqs = [{"objectId": str(int(k.split("_")[0])), "instanceId": str(int(k.split("_")[1])), "resourceId": str(int(k.split("_")[2]))} for k in active_dict.keys() if "_" in k and not k.startswith("api_")]
            
            extra_resources = [
                ("34180", "00001", "00010"), ("34181", "00001", "00010"), ("34183", "00001", "00010"),
                ("34193", "00001", "00012"), ("34193", "00001", "00014"), ("34193", "00001", "00019")
            ]
            for obj, inst, res in extra_resources:
                item = {"objectId": obj, "instanceId": inst, "resourceId": res}
                if item not in reqs: reqs.append(item)
                
            self._post_api("ccaraccessmgmt/api/v1/telemetry/app/ping", reqs)
            self._post_api(f"ccaraccessmgmt/api/v1/telemetry/{self.core.vin}/list_resource", reqs)
            self.core._last_auto_wakeup_time = time.time()
        except Exception: pass

    def send_remote_command(self, command_type, params=None):
        payload = {"commandType": command_type, "vinCode": self.core.vin, "params": params or {}}
        res = self._post_api("ccaraccessmgmt/api/v2/remote/app/command", payload)
        if res and res.status_code == 200:
            threading.Thread(target=self.register_resources, daemon=True).start()
            return True
        return False

    def _sign(self, key, msg):
        return hmac.new(key, msg.encode('utf-8'), hashlib.sha256).digest()

    def _get_signature_key(self, key, date_stamp, regionName, serviceName):
        kDate = self._sign(('AWS4' + key).encode('utf-8'), date_stamp)
        kRegion = self._sign(kDate, regionName)
        kService = self._sign(kRegion, serviceName)
        kSigning = self._sign(kService, 'aws4_request')
        return kSigning

    def get_aws_mqtt_url(self):
        try:
            url_id = f"https://cognito-identity.{self.core.aws_region}.amazonaws.com/"
            res_id = self._safe_request("POST", url_id, headers={"Content-Type": "application/x-amz-json-1.1", "X-Amz-Target": "AWSCognitoIdentityService.GetId"}, json={"IdentityPoolId": self.core.cognito_pool_id, "Logins": {self.core.auth0_domain: self.core.access_token}}, timeout=15)
            if not res_id or res_id.status_code != 200: return None
            identity_id = res_id.json()["IdentityId"]
            
            res_cred = self._safe_request("POST", url_id, headers={"Content-Type": "application/x-amz-json-1.1", "X-Amz-Target": "AWSCognitoIdentityService.GetCredentialsForIdentity"}, json={"IdentityId": identity_id, "Logins": {self.core.auth0_domain: self.core.access_token}}, timeout=15)
            if not res_cred or res_cred.status_code != 200: return None
            creds = res_cred.json()["Credentials"]
            
            self._safe_request("POST", f"{self.core.api_base}/ccarusermgnt/api/v1/user-vehicle/attach-policy", headers={"Authorization": f"Bearer {self.core.access_token}", "Content-Type": "application/json", "x-service-name": "CAPP"}, json={"target": identity_id}, timeout=15)
            
            t = datetime.datetime.now(datetime.timezone.utc)
            amz_date = t.strftime('%Y%m%dT%H%M%SZ')
            datestamp = t.strftime('%Y%m%d')
            credential_scope = f"{datestamp}/{self.core.aws_region}/iotdevicegateway/aws4_request"
            query_params = f"X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential={urllib.parse.quote(creds['AccessKeyId'] + '/' + credential_scope, safe='')}&X-Amz-Date={amz_date}&X-Amz-Expires=86400&X-Amz-SignedHeaders=host"
            canonical_request = f"GET\n/mqtt\n{query_params}\nhost:{self.core.iot_endpoint}\n\nhost\n" + hashlib.sha256("".encode('utf-8')).hexdigest()
            
            string_to_sign = f"AWS4-HMAC-SHA256\n{amz_date}\n{credential_scope}\n" + hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()
            signing_key = self._get_signature_key(creds['SecretKey'], datestamp, self.core.aws_region, 'iotdevicegateway')
            signature = hmac.new(signing_key, string_to_sign.encode('utf-8'), hashlib.sha256).hexdigest()
            
            return f"wss://{self.core.iot_endpoint}/mqtt?{query_params}&X-Amz-Signature={signature}&X-Amz-Security-Token={urllib.parse.quote(creds['SessionToken'], safe='')}"
        except Exception: return None

    def fetch_active_charging_session(self):
        try:
            if not self.core.vin or not self.core.access_token: return False
            api_path = "ccarcharging/api/v1/charging-sessions/active"
            ts = int(time.time() * 1000)
            headers = self._get_base_headers()
            headers.update({
                "X-HASH": self._generate_x_hash("GET", api_path, self.core.vin, ts), 
                "X-HASH-2": self._generate_x_hash_2("android", self.core.vin, DEVICE_ID, api_path, "GET", ts), 
                "X-TIMESTAMP": str(ts)
            })
            res = requests.get(f"{self.core.api_base}/{api_path}", headers=headers, timeout=10)
            if res and res.status_code == 401:
                self.login()
                headers["Authorization"] = f"Bearer {self.core.access_token}"
                res = requests.get(f"{self.core.api_base}/{api_path}", headers=headers, timeout=10)
                
            if res and res.status_code == 200:
                data = res.json().get("data")
                if data:
                    power = safe_float(data.get("chargingPower", 0))
                    target = safe_float(data.get("targetBatteryLevel", 0))
                    if target > 0: self.core._last_data["api_target_charge_limit"] = target
                    if power > 0:
                        self.core._last_data["api_live_charge_power"] = power
                        self.core._current_charge_max_power = max(getattr(self.core, '_current_charge_max_power', 0.0), power)
                        return True
        except Exception: pass
        return False

    def fetch_nearby_stations(self, force=True):
        try:
            now = time.time()
            if not force and now - getattr(self.core, '_last_station_fetch_time', 0) < 60:
                return

            # XỬ LÝ LỖI KHỞI ĐỘNG KHI XE ĐANG NGỦ (Không có MQTT): Lấy vị trí từ bộ nhớ đệm
            lat_str = getattr(self.core, '_last_lat_lon', "").split(',')[0] if getattr(self.core, '_last_lat_lon', "") else self.core._last_data.get("api_last_lat")
            lon_str = getattr(self.core, '_last_lat_lon', "").split(',')[1] if getattr(self.core, '_last_lat_lon', "") else self.core._last_data.get("api_last_lon")
            
            if not lat_str or not lon_str: 
                _LOGGER.warning("VinFast: Chưa xác định được tọa độ, không thể tìm trạm sạc.")
                return
            
            remain_range = safe_float(self.core._last_data.get("api_calc_remain_range", self.core._last_data.get("34180_00001_00007", 50)))
            search_radius = int(min(max(remain_range * 1000, 10000), 100000))
            
            payload = {
                "latitude": float(lat_str), 
                "longitude": float(lon_str), 
                "radius": search_radius, 
                "excludeFavorite": False, "stationType": [], "status": [], "brandIds": []
            }
            
            # SỬ DỤNG _POST_API CHỐNG LỖI TOKEN
            res = self._post_api("ccarcharging/api/v1/stations/search?page=0&size=50", payload)
            
            if res and res.status_code == 200:
                self.core._last_station_fetch_time = now
                data = res.json().get("data", [])
                if isinstance(data, dict) and "content" in data: data = data.get("content", [])
                stations = []
                for st in data:
                    st_lat = safe_float(st.get("latitude"))
                    st_lng = safe_float(st.get("longitude"))
                    if not st_lat or not st_lng: continue
                    dist = round(safe_float(st.get("distance", 0))/1000, 1)
                    
                    if dist > (search_radius / 1000) + 2.0: continue 
                    
                    max_power, avail, total = 0, 0, 0
                    for evse in st.get("evsePowers", []):
                        avail += int(evse.get("numberOfAvailableEvse", 0))
                        total += int(evse.get("totalEvse", 0))
                        power_kw = int(evse.get("type", 0)) / 1000 if int(evse.get("type", 0)) >= 1000 else int(evse.get("type", 0))
                        if power_kw > max_power: max_power = int(power_kw)
                    stations.append({"id": st.get("locationId", ""), "name": st.get("stationName", "Trạm sạc VinFast").strip(), "lat": st_lat, "lng": st_lng, "power": max_power, "avail": avail, "total": total, "dist": dist})
                
                stations = sorted(stations, key=lambda x: x["dist"])
                self.core._last_data["api_nearby_stations"] = json.dumps(stations)
                _LOGGER.warning(f"VinFast: Đã tải thành công {len(stations)} trạm sạc lân cận (Bán kính {search_radius/1000}km)")
                self.core.trigger_callbacks()
        except Exception as e: 
            _LOGGER.error(f"VinFast: Lỗi tải trạm sạc - {e}")

    def fetch_charging_history(self):
        max_retries = 5 
        attempt = 0
        while self.core._running and attempt < max_retries:
            attempt += 1
            try:
                if not self.core.vin or not self.core.access_token: 
                    time.sleep(5)
                    continue
                    
                api_path = "ccarcharging/api/v1/charging-sessions/search"
                ts = int(time.time() * 1000)
                payload = {"orderStatus": [3, 5, 7], "startTime": 1704067200000, "endTime": ts}
                
                all_sessions = []
                page = 0
                size = 50
                success_fetch = False
                
                while page < 50: 
                    # SỬ DỤNG _POST_API CHỐNG LỖI TOKEN
                    res = self._post_api(f"{api_path}?page={page}&size={size}", payload)
                    if res and res.status_code == 200:
                        data = res.json().get("data", {})
                        content = data.get("content", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
                        all_sessions.extend(content)
                        if len(content) < size:
                            success_fetch = True
                            break 
                        page += 1
                        time.sleep(0.5) 
                    else: break 
                        
                if success_fetch:
                    valid_sessions = sorted([s for s in all_sessions if safe_float(s.get("totalKWCharged", 0)) > 0], key=lambda x: safe_float(x.get("pluggedTime", 0)), reverse=True)
                    actual_public_sessions = len(valid_sessions)
                    prev_public_count = int(self.core._last_data.get("api_public_charge_sessions", 0))
                    
                    if actual_public_sessions >= prev_public_count or prev_public_count == 0:
                        detailed_history = []
                        for s in valid_sessions[:10]:
                            addr = s.get("chargingStationAddress", "Trạm sạc VinFast")
                            kwh = safe_float(s.get("totalKWCharged", 0))
                            p_time = safe_float(s.get("pluggedTime", 0))
                            u_time = safe_float(s.get("unpluggedTime", 0))
                            dur = round((u_time - p_time) / 60000) if u_time > p_time else 0
                            date_str = datetime.datetime.fromtimestamp(p_time/1000).strftime('%d/%m/%Y %H:%M') if p_time > 0 else ""
                            detailed_history.append({"date": date_str, "address": addr, "kwh": kwh, "duration": dur})
                        
                        self.core._last_data["api_charge_history_list"] = json.dumps(detailed_history)
                        self.core._last_data["api_public_charge_sessions"] = actual_public_sessions
                        home_sessions = int(self.core._last_data.get("api_home_charge_sessions", 0))
                        self.core._last_data["api_total_charge_sessions"] = actual_public_sessions + home_sessions
                        
                        public_energy = sum(safe_float(s.get("totalKWCharged", 0)) for s in valid_sessions)
                        self.core._last_data["api_public_charge_energy"] = round(public_energy, 2)
                        home_kwh = safe_float(self.core._last_data.get("api_home_charge_kwh", 0.0))
                        self.core._last_data["api_total_energy_charged"] = round(public_energy + home_kwh, 2)

                        if valid_sessions:
                            last_s = valid_sessions[0]
                            s_start = safe_float(last_s.get("startBatteryLevel", 0))
                            s_end = safe_float(last_s.get("endBatteryLevel", 0))
                            s_kwh = safe_float(last_s.get("totalKWCharged", 0))
                            spec_cap = getattr(self.core, '_vehicle_spec', {}).get("capacity", 0)
                            if (s_end - s_start) > 0 and s_kwh > 0 and spec_cap > 0:
                                theo_kwh = ((s_end - s_start) / 100.0) * spec_cap
                                eff = (theo_kwh / s_kwh) * 100.0
                                self.core._last_data["api_last_charge_efficiency"] = round(min(eff, 100.0), 1)
                                self.core._last_data["api_last_charge_energy"] = round(s_kwh, 2)

                        self.core._calculate_advanced_stats()
                        self.core._save_state()
                        
                        history_file = os.path.join(WWW_DIR, f"vinfast_charge_history_{self.core.vin.lower()}.json")
                        try:
                            with open(history_file, 'w', encoding='utf-8') as f: json.dump(detailed_history, f, ensure_ascii=False)
                        except Exception: pass

                        self.core.trigger_callbacks()
                        break 
                    else:
                        time.sleep(10)
                        continue
                else:
                    time.sleep(10)
                    continue
            except Exception as e:
                time.sleep(10)