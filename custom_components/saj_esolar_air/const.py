"""Constants for the eSolar integration."""
from typing import Final

DOMAIN = "saj_esolar_air"
CONF_MONITORED_SITES = "monitored_sites"
CONF_UPDATE_INTERVAL = 1
ATTRIBUTION = "Data provided by SAJ eSolar"
MANUFACTURER = "SAJ"

CONF_INVERTER_SENSORS: Final = "show_inverter_sensors"
CONF_PV_GRID_DATA: Final = "show_pv_grid_data"

# Misc
P_UNKNOWN = "Unknown"

# Plant Sensor Attributes
PLANT_MODEL = "Solar Plant"
P_NAME = "Plant Name"
P_UID = "Plant UId"
P_ADR = "Plant Address"
P_TYPE = "Plant Type"
P_POWER = "Plant Power"
P_CURRENCY = "Plant Currency"
P_INCOME = "Plant Total Grid Income"
P_CO2 = "Plant Total Co2 Reduction"
P_TREES = "Plant Total Trees Planted"
P_TODAY_E = "Plant Today Energy"
P_TOTAL_E = "Plant Total Energy"
P_CURRENT_POWER = "Plant Current Power"
P_PEAK_POWER = "Plant Peak Power"

# Inverter Sensor Attributes
I_MODEL = "Inverter Model"
I_SN = "Inverter S/N"
I_PC = "Inverter PC"
I_TYPE = "Inverter Type"
I_DB = "Inverter Display Board"
I_CTR = "Inverter Control Board"
I_MOD_SN = "Inverter Module S/N"
I_TODAY_E = "Inverter Today Energy"
I_MONTH_E = "Inverter Month Energy"
I_TOTAL_E = "Inverter Total Energy"
I_STATUS = "Inverter Status"
I_CURRENT_POWER = "Inverter Current Power"

# Plant Status
P_TYPE_GRID = "Grid"
P_TYPE_STORAGE = "Storage"
P_TYPE_BLEND = "Blend"
P_TYPE_AC_COUPLING = "AC Coupling"
P_TYPE_ONGRID = "On-grid"

I_PV_VOL_PV = "Photovoltaics Voltage PV1, PV2, PV3"
I_PV_CURR_PV = "Photovoltaics Current PV1, PV2, PV3"

I_G_VOL_L = "Grid Voltage L1, L2, L3"
I_G_CURR_L = "Grid Current L1, L2, L3"
I_G_FREQ_L = "Grid Frequency L1, L2, L3"

B_DIRECTION = "Battery Direction"
B_PVELEC = "Battery PV Energy"
B_USELEC = "Battergy Use Energy"
B_BUYELEC = "Battery Buy Energy"
B_SELLELEC = "Battery Sell Energy"
B_BUY_RATE = "Battery Buy Rate (%)"
B_SELL_RATE = "Battery Sell Rate (%)"


B_GRID_POWER_W = "Grid Power (W)"
B_GRID_POWER_VA = "Grid Power (VA)"
B_OUT_VOLT = "Battery Output Voltage"
B_OUT_CURR = "Battery Output Current"
B_OUT_POWER_WATT = "Battery Output Power (W)"
B_OUT_POWER_VA = "Battery Output Power (VA)"
B_OUT_FREQ = "Battery Output Frequency"
B_BACKUP_POWER_W = "Backup Power (W)"
B_ON_G_VOLT = "On Grid Voltage"
B_ON_G_FREQ = "On Grid Frequency"
B_ON_G_POWER_W = "On Grid Output Power (W)"

# Inverter status
I_NORMAL = "Normal"
I_ALARM = "Alarm"
I_OFFLINE = "Off-line"
I_STOCK = "Stock"
I_HISTORY = "History"

# Battery
B_DIR_CH = "Charging"
B_DIR_DIS = "Discharging"
B_DIR_STB = "Standby"

B_CAPACITY = "Battery Capacity"
B_CURRENT = "Battery Current"
B_POWER = "Battery Power"

B_GRID_DIRECT = "Grid Direction"
B_IMPORT = "Importing"
B_EXPORT = "Exporting"
G_POWER = "Grid Power"
S_POWER = "Solar Power"
IO_POWER = "Input/Output Power"
IO_DIRECTION = "Output Direction"

PV_POWER = "Photovoltaics Power"
PV_DIRECTION = "Photovoltaics Direction"

B_T_LOAD = "Total Load Power"
B_H_LOAD = "Home Load Power"
B_B_LOAD = "Backup Load Power"

P_LATITUDE = 'Latitude of the plant'
P_LONGITUDE = 'Longitude of the plant'
P_PIC = 'Picture of the plant'
P_DPC = 'Device PC'
P_DEVICE_TYPE = 'Device type'
P_DISPLAY_FW = 'Display firmware'
P_INSTALL_NAME = 'Installer name'
P_FIRST_ONLINE = 'First online datetime'
P_MASTER_MCU_FW = 'Master MCU firmware'
P_MODULE_FW = 'Module firmware'
P_MODULE_PC = 'Module PC'
P_MODULE_SN = 'Module serial number'
P_OWNER_NAME = 'Owner name'
P_OWNER_EMAIL = 'Owner email'
P_NO = 'Plant No.'
P_ID = 'Plant ID'