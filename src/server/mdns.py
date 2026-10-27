from __future__ import annotations

import socket
import time
from dataclasses import dataclass

from zeroconf import ServiceBrowser, ServiceInfo, Zeroconf, IPVersion

SERVICE_TYPE = "_emusync._tcp.local."


@dataclass
class ServiceEntry:
    name: str
    host: str
    port: int


def _primary_lan_ip() -> str:
    """Return this machine's primary outbound LAN IPv4.

    `socket.gethostbyname(gethostname())` is unreliable: on many Linux distros
    (Steam Deck, Arch, Debian) the hostname maps to 127.0.0.1/127.0.1.1 in
    /etc/hosts, so it advertises a loopback address no other device can reach.
    Opening a UDP socket toward a public IP (no packets are actually sent) lets
    the kernel pick the interface/address it would route through. Falls back to
    loopback only when there is genuinely no route.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        if ip and not ip.startswith("127."):
            return ip
    except OSError:
        pass
    finally:
        s.close()
    return "127.0.0.1"


def advertise(device_name: str, port: int) -> tuple[Zeroconf, ServiceInfo]:
    """Register an mDNS service. Returns (zc, info) — call zc.unregister_service(info) to stop."""
    zc = Zeroconf(ip_version=IPVersion.V4Only)
    hostname = socket.gethostname()
    host_ip = _primary_lan_ip()
    info = ServiceInfo(
        SERVICE_TYPE,
        f"EmuSync-{device_name}.{SERVICE_TYPE}",
        addresses=[socket.inet_aton(host_ip)],
        port=port,
        properties={"device": device_name},
        server=f"{hostname}.local.",
    )
    zc.register_service(info)
    return zc, info


def discover(timeout: float = 5.0) -> list[ServiceEntry]:
    """Scan LAN for EmuSync servers. Blocks for `timeout` seconds."""
    results: list[ServiceEntry] = []
    zc = Zeroconf(ip_version=IPVersion.V4Only)

    class _Listener:
        def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
            info = zc.get_service_info(type_, name)
            if info and info.addresses:
                host = socket.inet_ntoa(info.addresses[0])
                device = info.properties.get(b"device", b"").decode()
                results.append(ServiceEntry(name=device, host=host, port=info.port))

        def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
            pass

        def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
            pass

    ServiceBrowser(zc, SERVICE_TYPE, _Listener())
    time.sleep(timeout)
    zc.close()
    return results
