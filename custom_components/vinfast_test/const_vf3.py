from .const_common import PLATFORM_A_BASE, VIRTUAL_SENSORS

SPEC = {"capacity": 18.64, "range": 210, "ev_kwh_per_km": 0.09, "gas_km_per_liter": 18.0}
SENSORS = PLATFORM_A_BASE.copy()
SENSORS.update(VIRTUAL_SENSORS)
SENSORS.update({
    "34193_00001_00019": ("Mục tiêu sạc (Target)", "%", "mdi:battery-charging-100", "battery"),
})