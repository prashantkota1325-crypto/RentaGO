import subprocess
import sys
import time
import urllib.request

print("=" * 60)
print("RentaGO - Server Start + Login Test")
print("=" * 60)

# Step 1: Start the server
print("\n[1] Starting server...")
proc = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"],
    cwd="C:\\Users\\Prashant Kota\\OneDrive\\Documents\\Default Project\\RentaGO_Prototype_NewWeb",
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE
)

# Wait until the application itself responds, not just until the port opens.
ready = False
for i in range(15):
    time.sleep(1)
    if proc.poll() is not None:
        print("ERROR: Server failed to start")
        break
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000/auth/login", timeout=3) as response:
            ready = response.status == 200
    except Exception:
        continue
    if ready:
        break

if not ready:
    print("ERROR: Server process started but the application did not become ready")
    sys.exit(1)
print("[OK] Server is ready on port 8000")

print("\n[2] Login endpoint is ready.")
print("Email OTP is required after password verification for non-Driver users.")

print("\n" + "=" * 60)
print("Done. Server is running in background.")
print("Open browser to: http://<this-PC-LAN-IP>:8000/auth/login")
print("=" * 60)
