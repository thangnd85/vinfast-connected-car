import math
import json
import os
import asyncio
import aiohttp
import logging
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)

OSRM_SERVERS = [
    "https://routing.openstreetmap.de/routed-car",
    "http://router.project-osrm.org",
]

CACHE_FILE = "vinfast_trips_cache.json"

# ================= TOÁN HỌC & GIẢI MÃ =================

def decode_polyline6(polyline_str):
    precision = 6
    factor = math.pow(10, precision)
    index = 0; lat = 0; lng = 0
    coordinates = []
    length = len(polyline_str)
    
    while index < length:
        shift = 0; result = 0
        while True:
            b = ord(polyline_str[index]) - 63
            index += 1
            result |= (b & 0x1f) << shift
            shift += 5
            if b < 0x20: break
        dlat = ~(result >> 1) if (result & 1) else (result >> 1)
        lat += dlat
        
        shift = 0; result = 0
        while True:
            b = ord(polyline_str[index]) - 63
            index += 1
            result |= (b & 0x1f) << shift
            shift += 5
            if b < 0x20: break
        dlng = ~(result >> 1) if (result & 1) else (result >> 1)
        lng += dlng
        
        coordinates.append([lat / factor, lng / factor])
    return coordinates

def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi, dlambda = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

def calculate_route_length(coords):
    if not coords or len(coords) < 2: return 0
    return sum(haversine_distance(coords[i][0], coords[i][1], coords[i+1][0], coords[i+1][1]) for i in range(len(coords)-1))

def get_bearing(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlon = lon2 - lon1
    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    initial_bearing = math.atan2(x, y)
    return (math.degrees(initial_bearing) + 360) % 360

def project_point_onto_line(pt, line_start, line_end):
    x0, y0 = pt[1], pt[0]
    x1, y1 = line_start[1], line_start[0]
    x2, y2 = line_end[1], line_end[0]
    dx = x2 - x1
    dy = y2 - y1
    if dx == 0 and dy == 0:
        return line_start[0], line_start[1], 0.0
    t = ((x0 - x1) * dx + (y0 - y1) * dy) / (dx * dx + dy * dy)
    px = x1 + t * dx
    py = y1 + t * dy
    return py, px, t

def get_projected_pt(pt, pt_a, pt_b, allow_extend_start=False, allow_extend_end=False):
    py, px, t = project_point_onto_line(pt, pt_a, pt_b)
    if t < 0.0 and not allow_extend_start:
        t = 0.0
        py, px = pt_a[0], pt_a[1]
    elif t > 1.0 and not allow_extend_end:
        t = 1.0
        py, px = pt_b[0], pt_b[1]
    d = haversine_distance(pt[0], pt[1], py, px)
    return [py, px], t, d

# Hàm giữ nguyên nhưng không gọi tự động để tránh cắt sai
def trim_route_to_projections(offset_route, coords):
    if len(offset_route) < 2 or len(coords) < 2: return offset_route
    raw_start = coords[0]
    min_d_start = float('inf')
    best_proj_start = None
    best_idx_start = 0
    search_limit_start = max(1, min(15, len(offset_route) // 2))
    
    for i in range(search_limit_start):
        pt_a = offset_route[i]
        pt_b = offset_route[i+1]
        is_first = (i == 0)
        proj_pt, t, d = get_projected_pt(raw_start, pt_a, pt_b, allow_extend_start=is_first, allow_extend_end=False)
        if d < min_d_start:
            min_d_start = d
            best_proj_start = proj_pt
            best_idx_start = i
            
    raw_end = coords[-1]
    min_d_end = float('inf')
    best_proj_end = None
    best_idx_end = len(offset_route) - 2
    start_search = max(0, len(offset_route) - search_limit_start - 1)
    
    for i in range(len(offset_route) - 2, start_search - 1, -1):
        pt_a = offset_route[i]
        pt_b = offset_route[i+1]
        is_last = (i == len(offset_route) - 2)
        proj_pt, t, d = get_projected_pt(raw_end, pt_a, pt_b, allow_extend_start=False, allow_extend_end=is_last)
        if d < min_d_end:
            min_d_end = d
            best_proj_end = proj_pt
            best_idx_end = i

    final_route = []
    if best_proj_start:
        final_route.append([best_proj_start[0], best_proj_start[1], offset_route[best_idx_start][2] if len(offset_route[best_idx_start])>2 else 0])
    
    start_loop = best_idx_start + 1
    end_loop = best_idx_end
    if start_loop <= end_loop:
        for i in range(start_loop, end_loop + 1):
            final_route.append(offset_route[i])
            
    if best_proj_end:
        final_route.append([best_proj_end[0], best_proj_end[1], offset_route[best_idx_end][2] if len(offset_route[best_idx_end])>2 else 0])
    
    return final_route

def light_cleanup(coords, min_dist=0.1):
    """Chỉ loại bỏ những điểm hoàn toàn trùng lặp để tránh lỗi toán học chia cho 0"""
    if len(coords) < 2: return coords
    cleaned = [coords[0]]
    for i in range(1, len(coords)):
        if haversine_distance(cleaned[-1][0], cleaned[-1][1], coords[i][0], coords[i][1]) >= min_dist:
            cleaned.append(coords[i])
    if haversine_distance(cleaned[-1][0], cleaned[-1][1], coords[-1][0], coords[-1][1]) > 0.05:
        cleaned.append(coords[-1])
    return cleaned

def offset_route_right(coords, offset_meters=1.5):
    """Dạt lề phải 1.5m để đi đúng làn đường"""
    if not coords or len(coords) < 2: return coords
    shifted = []
    n = len(coords)
    for i in range(n):
        lat, lon = coords[i][0], coords[i][1]
        speed = coords[i][2] if len(coords[i]) > 2 else 0

        if i == 0: dx, dy = coords[i+1][1] - lon, coords[i+1][0] - lat
        elif i == n - 1: dx, dy = lon - coords[i-1][1], lat - coords[i-1][0]
        else: dx, dy = coords[i+1][1] - coords[i-1][1], coords[i+1][0] - coords[i-1][0]

        if dx == 0 and dy == 0:
            shifted.append([round(lat, 6), round(lon, 6), round(speed, 1)])
            continue
        
        right_angle = math.atan2(dy, dx) - (math.pi / 2.0)
        lat_offset = (offset_meters / 111320.0) * math.sin(right_angle)
        lon_offset = (offset_meters / (111320.0 * math.cos(math.radians(lat)))) * math.cos(right_angle)
        shifted.append([round(lat + lat_offset, 6), round(lon + lon_offset, 6), round(speed, 1)])
    return shifted

def assign_speeds(smooth_coords, original_coords):
    res = []
    for sp in smooth_coords:
        min_d = float('inf')
        closest_speed = 0
        for op in original_coords:
            d = (op[0] - sp[0])**2 + (op[1] - sp[1])**2
            if d < min_d:
                min_d, closest_speed = d, (op[2] if len(op) > 2 else 0)
        res.append([sp[0], sp[1], closest_speed])
    return res

def moving_average_smooth(coords, window=3):
    if len(coords) < window: return coords
    smoothed = []
    half = window // 2
    for i in range(len(coords)):
        start = max(0, i - half)
        end = min(len(coords), i + half + 1)
        subset = coords[start:end]
        avg_lat = sum(p[0] for p in subset) / len(subset)
        avg_lon = sum(p[1] for p in subset) / len(subset)
        speed = coords[i][2] if len(coords[i]) > 2 else 0
        smoothed.append([avg_lat, avg_lon, speed])
    return smoothed

def kinematic_filter(raw_coords):
    """Lọc bỏ các điểm nhảy tọa độ quá xa (Glitch) do lỗi thiết bị GPS"""
    if not raw_coords or len(raw_coords) < 2: return raw_coords
    cleaned = [raw_coords[0]]
    for i in range(1, len(raw_coords)):
        prev = cleaned[-1]
        curr = raw_coords[i]
        dist = haversine_distance(prev[0], prev[1], curr[0], curr[1])
        t_prev = prev[3] if len(prev) > 3 else 0
        t_curr = curr[3] if len(curr) > 3 else 0
        dt = max(1, t_curr - t_prev) if t_curr > 0 and t_prev > 0 else 2
        v_kmh = max(curr[2] if len(curr) > 2 else 0, prev[2] if len(prev) > 2 else 0)
        v_ms = v_kmh / 3.6
        max_phys_dist = (v_ms * dt) + 150.0 # Khoảng sai số rộng rãi để không mất điểm
        if dist > max_phys_dist and dist > 300.0:
            continue
        cleaned.append(curr)
    return cleaned

# ================= CƠ CHẾ THÁC NƯỚC BẤT ĐỒNG BỘ =================

async def fetch_map_matching_api_async(session, chunk, chunk_bearings, chunk_timestamps, mapbox_token, stadia_token):
    coord_str = ";".join([f"{p[1]:.5f},{p[0]:.5f}" for p in chunk])
    radiuses = ";".join(["40"] * len(chunk)) 
    bearings_str = ";".join(chunk_bearings)
    timestamps_str = ";".join(map(str, chunk_timestamps))
    
    if mapbox_token and str(mapbox_token).strip() != "":
        url = f"https://api.mapbox.com/matching/v5/mapbox/driving/{coord_str}?geometries=geojson&radiuses={radiuses}&bearings={bearings_str}&timestamps={timestamps_str}&tidy=true&overview=full&access_token={mapbox_token.strip()}"
        try:
            async with session.get(url, timeout=5) as res:
                if res.status == 200:
                    data = await res.json()
                    if data.get("code") == "Ok":
                        if len(data["matchings"]) > 1: return None, "Mapbox Broken Route"
                        matched = [[p[1], p[0]] for p in data["matchings"][0]["geometry"]["coordinates"]]
                        return matched, "Mapbox"
        except Exception: pass

    if stadia_token and str(stadia_token).strip() != "":
        url = f"https://api.stadiamaps.com/valhalla/trace_route?api_key={stadia_token.strip()}"
        shape_payload = []
        for i, p in enumerate(chunk):
            heading, tol = map(int, chunk_bearings[i].split(","))
            shape_payload.append({
                "lat": p[0], "lon": p[1], 
                "heading": heading, "heading_tolerance": tol, "time": chunk_timestamps[i]
            })
        payload = {"shape": shape_payload, "costing": "auto", "shape_match": "map_snap"}
        try:
            async with session.post(url, json=payload, timeout=8) as res:
                if res.status == 200:
                    data = await res.json()
                    if "trip" in data and "legs" in data["trip"]:
                        coords = []
                        for leg in data["trip"]["legs"]: coords.extend(decode_polyline6(leg["shape"]))
                        return coords, "Stadia"
        except Exception: pass

    headers = {"User-Agent": "HA-VinFast-Hybrid/21.0"}
    for server in OSRM_SERVERS:
        url = f"{server}/match/v1/driving/{coord_str}?overview=full&geometries=geojson&radiuses={radiuses}&bearings={bearings_str}&timestamps={timestamps_str}&tidy=true"
        try:
            async with session.get(url, headers=headers, timeout=5) as res:
                if res.status == 200:
                    data = await res.json()
                    if data.get("code") == "Ok":
                        if len(data["matchings"]) > 1: return None, "OSRM Broken Route"
                        matched = [[p[1], p[0]] for p in data["matchings"][0]["geometry"]["coordinates"]]
                        return matched, f"OSRM"
                elif res.status == 429: await asyncio.sleep(1.0) 
        except Exception: pass

    return None, "Error"

async def recursive_hybrid_match_async(session, chunk, chunk_bearings, chunk_timestamps, mapbox_token, stadia_token, depth=0):
    if len(chunk) < 2 or calculate_route_length(chunk) < 40.0 or depth > 4 or len(chunk) <= 3: 
        return chunk 
        
    matched_coords, engine = await fetch_map_matching_api_async(session, chunk, chunk_bearings, chunk_timestamps, mapbox_token, stadia_token)
    
    if isinstance(matched_coords, list):
        raw_dist = calculate_route_length(chunk)
        api_dist = calculate_route_length(matched_coords)
        
        # Ngăn chặn việc API tự ý kéo dài lộ trình vô lý (nhảy làn cao tốc, đi lòng vòng)
        if raw_dist > 0 and api_dist > raw_dist * 1.50: 
            _LOGGER.warning(f"      [-] {engine} đi vòng ({api_dist:.1f}m > {raw_dist:.1f}m). CẮT ĐÔI...")
            return await split_and_recurse_async(session, chunk, chunk_bearings, chunk_timestamps, mapbox_token, stadia_token, depth)
            
        _LOGGER.warning(f"      [+] Khớp {engine} HOÀN HẢO! (Dài API: {api_dist:.1f}m)")
        return matched_coords
    else:
        _LOGGER.warning(f"      [!] API ({engine}) từ chối đoạn nhiễu. CẮT ĐÔI...")
        return await split_and_recurse_async(session, chunk, chunk_bearings, chunk_timestamps, mapbox_token, stadia_token, depth)

async def split_and_recurse_async(session, chunk, chunk_bearings, chunk_timestamps, mapbox_token, stadia_token, depth):
    mid = len(chunk) // 2
    left = await recursive_hybrid_match_async(session, chunk[:mid+1], chunk_bearings[:mid+1], chunk_timestamps[:mid+1], mapbox_token, stadia_token, depth + 1)
    right = await recursive_hybrid_match_async(session, chunk[mid:], chunk_bearings[mid:], chunk_timestamps[mid:], mapbox_token, stadia_token, depth + 1)
    if len(left) > 0 and len(right) > 0: return left[:-1] + right
    return left + right

async def async_process_route(hass, raw_coords, mapbox_token, stadia_token):
    if not raw_coords or len(raw_coords) < 5: return raw_coords
    
    _LOGGER.warning(f"[1] TỌA ĐỘ GỐC: {len(raw_coords)} điểm. Chiều dài: {calculate_route_length(raw_coords):.1f}m")
    session = async_get_clientsession(hass)

    # BƯỚC 1: LÀM SẠCH LỖI VÀ NHIỄU (Bảo toàn 100% chuyến đi kể cả tắc đường)
    cleaned_raw = kinematic_filter(raw_coords)
    cleaned_raw = light_cleanup(cleaned_raw, min_dist=0.1)
    if len(cleaned_raw) < 2: return raw_coords
    
    global_bearings = []
    global_timestamps = []
    current_time = 1600000000 
    
    for i in range(len(cleaned_raw)):
        if i < len(cleaned_raw) - 1: b = get_bearing(cleaned_raw[i][0], cleaned_raw[i][1], cleaned_raw[i+1][0], cleaned_raw[i+1][1])
        elif i > 0: b = get_bearing(cleaned_raw[i-1][0], cleaned_raw[i-1][1], cleaned_raw[i][0], cleaned_raw[i][1])
        else: b = 0
        
        global_bearings.append(f"{int(b)},120")
        
        if i == 0: global_timestamps.append(current_time)
        else:
            d = haversine_distance(cleaned_raw[i-1][0], cleaned_raw[i-1][1], cleaned_raw[i][0], cleaned_raw[i][1])
            spd = cleaned_raw[i-1][2] if len(cleaned_raw[i-1]) > 2 else 30.0
            dt = max(1, int(d / (max(10.0, spd) / 3.6)))
            current_time += dt
            global_timestamps.append(current_time)

    final_matched_route = []
    is_mapbox = bool(mapbox_token and str(mapbox_token).strip() != "")
    CHUNK_SIZE = 80 if is_mapbox else 40 
    OVERLAP = 2 
    
    for i in range(0, len(cleaned_raw), CHUNK_SIZE - OVERLAP):
        chunk = cleaned_raw[i:i+CHUNK_SIZE]
        chunk_b = global_bearings[i:i+CHUNK_SIZE]
        chunk_t = global_timestamps[i:i+CHUNK_SIZE]
        if len(chunk) < 2: continue
        
        _LOGGER.warning(f"--- Đang xử lý Chặng: {i} đến {i+len(chunk)} ---")
        matched_chunk = await recursive_hybrid_match_async(session, chunk, chunk_b, chunk_t, mapbox_token, stadia_token)

        if i > 0 and len(final_matched_route) > 0 and len(matched_chunk) > 0:
            final_matched_route.extend(matched_chunk[1:])
        else:
            final_matched_route.extend(matched_chunk)
            
        await asyncio.sleep(0.1 if is_mapbox else 0.5) 
        
    _LOGGER.warning(f"[3] BẢN ĐỒ TRẢ VỀ: {len(final_matched_route)} điểm.")

    # BƯỚC 4: GÁN TỐC ĐỘ VÀ TỊNH TIẾN LUÔN SÁT LỀ PHẢI
    route_with_speed = assign_speeds(final_matched_route, cleaned_raw)
    offset_route = offset_route_right(route_with_speed, offset_meters=1.5)

    # BƯỚC 5: KHÓA CHẶT ĐIỂM ĐẦU VÀ CUỐI VỚI RAW GPS (Bắt buộc điểm nối trip phải chuẩn xác)
    if len(offset_route) >= 2 and len(raw_coords) >= 2:
        offset_route[0][0] = raw_coords[0][0]
        offset_route[0][1] = raw_coords[0][1]
        
        offset_route[-1][0] = raw_coords[-1][0]
        offset_route[-1][1] = raw_coords[-1][1]

    # TRẢ VỀ TOÀN BỘ LỘ TRÌNH, KHÔNG DÙNG TRIM NỮA THEO YÊU CẦU
    return offset_route

# ================= QUẢN LÝ LƯU TRỮ CHUYẾN ĐI (JSON CACHE) =================

def load_cache(hass):
    path = hass.config.path("www", CACHE_FILE)
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f: return json.load(f)
        except Exception: return {}
    return {}

def save_cache(hass, cache_data):
    path = hass.config.path("www", CACHE_FILE)
    try:
        with open(path, 'w', encoding='utf-8') as f: json.dump(cache_data, f, ensure_ascii=False)
    except Exception: pass

async def async_get_or_process_trip(hass, trip_id, raw_coords, config_entry):
    if not raw_coords or len(raw_coords) < 5:
        return raw_coords

    mapbox_token = config_entry.options.get("mapbox_token", config_entry.data.get("mapbox_token", ""))
    stadia_token = config_entry.options.get("stadia_token", config_entry.data.get("stadia_token", ""))

    cache_data = await hass.async_add_executor_job(load_cache, hass)
    
    if str(trip_id) in cache_data:
        _LOGGER.debug(f"VinFast: Đã tìm thấy tuyến đường {trip_id} trong Cache.")
        return cache_data[str(trip_id)]
        
    _LOGGER.info(f"VinFast: Đang nắn lại tuyến đường {trip_id} bằng công nghệ Hybrid Map Matching...")
    processed_route = await async_process_route(hass, raw_coords, mapbox_token, stadia_token)
    
    cache_data[str(trip_id)] = processed_route
    await hass.async_add_executor_job(save_cache, hass, cache_data)
    
    return processed_route