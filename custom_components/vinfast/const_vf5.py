from .const_common import PLATFORM_A_BASE, VIRTUAL_SENSORS, REAR_DOORS_WINDOWS

SPEC = {"capacity": 37.23, "range": 326, "ev_kwh_per_km": 0.12, "gas_km_per_liter": 16.5}
SENSORS = PLATFORM_A_BASE.copy()
SENSORS.update(VIRTUAL_SENSORS)
SENSORS.update(REAR_DOORS_WINDOWS)
SENSORS.update({
    "34193_00001_00014": ("Mục tiêu sạc (Target)", "%", "mdi:battery-charging-100", "battery"),
})