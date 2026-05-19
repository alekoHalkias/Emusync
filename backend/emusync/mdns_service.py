import socket
import threading
import time
from dataclasses import dataclass
from typing import List

from zeroconf import ServiceBrowser, ServiceInfo, Zeroconf

SERVICE_TYPE = "_emusync._tcp.local."


@dataclass
class ServiceResult:
    name: str
    host: str
    port: int


def advertise(device_name: str, port: int, stop_event: threading.Event):
    zc = Zeroconf()
    try:
        local_ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        local_ip = "127.0.0.1"

    info = ServiceInfo(
        SERVICE_TYPE,
        f"EmuSync-{device_name}.{SERVICE_TYPE}",
        addresses=[socket.inet_aton(local_ip)],
        port=port,
        properties={"device": device_name},
        server=f"{socket.gethostname()}.local.",
    )
    zc.register_service(info)
    stop_event.wait()
    zc.unregister_service(info)
    zc.close()


def discover(timeout: float = 5.0) -> List[ServiceResult]:
    results: List[ServiceResult] = []
    zc = Zeroconf()

    class Listener:
        def add_service(self, zc, type_, name):
            info = zc.get_service_info(type_, name)
            if info and info.addresses:
                host = socket.inet_ntoa(info.addresses[0])
                label = name.replace(f".{SERVICE_TYPE}", "").replace("EmuSync-", "")
                results.append(ServiceResult(name=label, host=host, port=info.port))

        def remove_service(self, zc, type_, name):
            pass

        def update_service(self, zc, type_, name):
            pass

    ServiceBrowser(zc, SERVICE_TYPE, Listener())
    time.sleep(timeout)
    zc.close()
    return results
