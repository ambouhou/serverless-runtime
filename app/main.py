from api.v1.daas import daas_router
from api.v1.faas import faas_router, CognitFuncExecCollector
from fastapi import FastAPI, Response
import prometheus_client
from prometheus_client.core import GaugeMetricFamily, REGISTRY
from prometheus_client import start_http_server, multiprocess, CollectorRegistry
import os, socket
from ipaddress import ip_address as ipadd, IPv4Address, IPv6Address

import requests
from modules._logger import CognitLogger

# Initialize logger
cognit_logger = CognitLogger()

SR_PORT = 8000
PROM_PORT = 9100

app = FastAPI(title="Serverless Runtime")

@app.get("/")
async def root():
    return "Main routes: \
            POST -> /v1/faas/execute-sync  \
                    /v1/faas/execute-async \
                    /v1/daas/upload \
            GET -> /v1/faas/{faas_uuid}/status"

app.include_router(faas_router, prefix="/v1/faas")
app.include_router(daas_router, prefix="/v1/daas")

def is_prometheus_running() -> bool:
    """
    Check if Prometheus is running by performing a curl to localhost:{PROM_PORT}.
    If the curl fails, check if the port is open on the host.

    Returns:
        bool: True if Prometheus is running, False otherwise.
    """
    # Step 1: Perform a curl to localhost:{PROM_PORT}
    try:
        response = requests.get(f"http://localhost:{PROM_PORT}", timeout=5)
        if response.status_code == 200:
            cognit_logger.info(f"Prometheus is running on localhost:{PROM_PORT}")
            return True
    except requests.exceptions.RequestException as e:
        # Step 2: If curl fails, log a warning
        cognit_logger.warning(f"Prometheus curl failed to localhost:{PROM_PORT}: {e}")

    # Step 2a: Check if the port is open on the host
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(5)
            result = s.connect_ex(("localhost", PROM_PORT))
            if result == 0:
                cognit_logger.warning(f"Port {PROM_PORT} is open on the host, but Prometheus is not responding.")
            else:
                cognit_logger.warning(f"Port {PROM_PORT} is not open on the host.")
    except Exception as e:
        cognit_logger.warning(f"Failed to check if port {PROM_PORT} is open: {e}")

    return False

def get_local_ip() -> str:
    """
    Get the local IP address (IPv4 or IPv6) for 'localhost'.
    Prefers IPv4 if available.
    """
    try:
        # Get all address info for 'localhost'
        addr_info = socket.getaddrinfo(host='localhost', port='80')
        for info in addr_info:
            # Extract the IP address from the address info
            ip = info[4][0]
            # Prefer IPv4 if available
            if ipadd(ip).version == 4:
                return ip
        # If no IPv4 address is found, return the first IPv6 address
        return addr_info[0][4][0]
    except Exception as e:
        cognit_logger.warning(f"Failed to get local IP address: {e}")
        return "127.0.0.1"  # Default to IPv4

# Initialize Prometheus and check if it's running
def initialize_prometheus():
    global r
    cognit_logger.debug("Initializing Prometheus...")
    # Create Prometheus registry
    r = CollectorRegistry()
    # Register COGNIT collector within the registry
    r.register(CognitFuncExecCollector())

    local_ip = get_local_ip()
    # cognit_logger.debug(f"[PROM] local_ip: {local_ip}")
    ip_version = ipadd(local_ip)
    # cognit_logger.debug(f"[PROM] ip_version: {ip_version}")

    # Different Prometheus and COGNIT API server cmds in IPv4 or IPv6
    if type(ip_version) == IPv4Address:
        # Start Prometheus HTTP server on the desired port, for instance 9100
        start_http_server(PROM_PORT, addr="0.0.0.0", registry=r)
    elif type(ip_version) == IPv6Address:
        # Start Prometheus HTTP server on the desired port, for instance 9100
        start_http_server(PROM_PORT, addr='::', registry=r)

    # Check if Prometheus is running
    is_prometheus_running()

# As uvicorn does not execute the code inside `if __name__ == "__main__":`, 
# prometheus initialization must be put outside of the block: 
initialize_prometheus()

# Uvicorn startup (only when running this script directly)
if __name__ == "__main__":
    import uvicorn
    cognit_logger.INFO("Starting Uvicorn server...")
    uvicorn.run(app, host="0.0.0.0", port=SR_PORT)