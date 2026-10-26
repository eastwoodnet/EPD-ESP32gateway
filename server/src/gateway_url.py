import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit


@dataclass(frozen=True)
class GatewayURL:
    origin: str
    trigger_url: str
    scheme: str
    hostname: str
    port: int


def normalize_gateway_url(value: str) -> str:
    return parse_gateway_url(value).origin


def parse_gateway_url(value: str) -> GatewayURL:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("网关地址不能为空或包含首尾空白")
    if any(ord(char) <= 32 or ord(char) == 127 for char in value) or "\\" in value:
        raise ValueError("网关地址包含无效字符")

    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError as exc:
        raise ValueError("网关地址格式无效") from exc

    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        raise ValueError("网关地址仅支持 HTTP(S)")
    if not parts.netloc or parts.hostname is None:
        raise ValueError("网关地址必须包含主机")
    if parts.username is not None or parts.password is not None:
        raise ValueError("网关地址不允许包含用户信息")
    if parts.query or parts.fragment:
        raise ValueError("网关地址不允许包含查询或片段")
    if parts.path not in ("", "/"):
        raise ValueError("网关地址只允许配置源地址")

    hostname = parts.hostname.rstrip(".").lower()
    if not hostname or "%" in hostname:
        raise ValueError("网关主机无效")
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise ValueError("网关地址不允许指向 loopback")

    if port is None:
        port = 443 if scheme == "https" else 80
    if not 1 <= port <= 65535:
        raise ValueError("网关端口无效")

    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address is not None:
        validate_gateway_address(address)

    default_port = 443 if scheme == "https" else 80
    host_for_url = f"[{hostname}]" if address is not None and address.version == 6 else hostname
    netloc = host_for_url if port == default_port else f"{host_for_url}:{port}"
    origin = urlunsplit((scheme, netloc, "", "", ""))
    trigger_url = urlunsplit((scheme, netloc, "/api/trigger", "", ""))
    return GatewayURL(origin=origin, trigger_url=trigger_url, scheme=scheme, hostname=hostname, port=port)


def _ipv4_mapped(address):
    return address.ipv4_mapped if address.version == 6 else None


def validate_gateway_address(address) -> None:
    if isinstance(address, str):
        address = ipaddress.ip_address(address.split("%", 1)[0])
    mapped = _ipv4_mapped(address)
    if mapped is not None:
        address = mapped
    if address.is_loopback or address.is_link_local or address.is_unspecified or address.is_multicast or address.is_reserved:
        raise ValueError("网关地址指向禁止的网络范围")
    if not (address.is_global or address.is_private):
        raise ValueError("网关地址指向禁止的网络范围")


def validate_gateway_addresses(target_addresses, local_addresses=()) -> None:
    targets = {ipaddress.ip_address(address.split("%", 1)[0]) for address in target_addresses}
    locals_ = {ipaddress.ip_address(address.split("%", 1)[0]) for address in local_addresses}
    if not targets:
        raise ValueError("无法解析网关地址")
    for address in targets:
        validate_gateway_address(address)
        mapped = _ipv4_mapped(address)
        candidates = {address}
        if mapped is not None:
            candidates.add(mapped)
        if candidates & locals_:
            raise ValueError("网关地址不允许指向本服务")
