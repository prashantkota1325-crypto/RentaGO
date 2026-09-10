# RentaGO Web - run the FastAPI server.
# Requires: Python 3.12 + `pip install -r requirements.txt`, Oracle reachable.
# Binds 0.0.0.0 so other devices on the network (PCs, mobiles, laptops, tablets)
# can open the app at http://<this-PC's-IP>:8000 (find the IP with: ipconfig).
$ErrorActionPreference = "Stop"

$py = "C:\Users\Prashant Kota\AppData\Local\Programs\Python\Python312\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

& $py -m pip install -r requirements.txt --quiet
& $py -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
