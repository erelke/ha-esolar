"""ESolar Cloud Platform Basic Test"""
import requests
import json
import sys
from esolar import get_esolar_data

USER = "NAME"
PASSWORD = "PASSWORD"
OUTPUT_FILE = "output.txt"

f=open(OUTPUT_FILE, "w")
try:
    print("Obtaining plant information")
    plant_info = get_esolar_data(REGION, USER, PASSWORD)
    
    print(f"\nProducing the output into {OUTPUT_FILE}")
    f.write(json.dumps(plant_info))

    f.close()
    
except requests.exceptions.HTTPError as errh:
    sys.exit(errh)
except requests.exceptions.ConnectionError as errc:
    sys.exit(errc)
except requests.exceptions.Timeout as errt:
    sys.exit(errt)
except requests.exceptions.RequestException as errr:
    sys.exit(errr)
except ValueError as errv:
    sys.exit(errv)
