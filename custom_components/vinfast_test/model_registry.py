from . import const_vf3, const_vf5, const_vfe34, const_vf6, const_vf7, const_vf8, const_vf9

def get_vehicle_profile(model_name):
    """Router tự động trả về đúng từ điển Sensor và Specs theo tên xe."""
    name = str(model_name).upper().replace(" ", "")
    
    if "VF3" in name:
        return {"sensors": const_vf3.SENSORS, "spec": const_vf3.SPEC}
    elif "VF5" in name:
        return {"sensors": const_vf5.SENSORS, "spec": const_vf5.SPEC}
    elif "E34" in name:
        return {"sensors": const_vfe34.SENSORS, "spec": const_vfe34.SPEC}
    elif "VF6" in name:
        return {"sensors": const_vf6.SENSORS, "spec": const_vf6.SPEC}
    elif "VF7" in name:
        return {"sensors": const_vf7.SENSORS, "spec": const_vf7.SPEC}
    elif "VF8" in name:
        return {"sensors": const_vf8.SENSORS, "spec": const_vf8.SPEC}
    elif "VF9" in name:
        return {"sensors": const_vf9.SENSORS, "spec": const_vf9.SPEC}
    
    # Mặc định an toàn (Fallback cho xe lạ)
    return {"sensors": const_vf5.SENSORS, "spec": const_vf5.SPEC}