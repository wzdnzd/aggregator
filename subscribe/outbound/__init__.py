# -*- coding: utf-8 -*-

from outbound.anytls import AnyTLSVerifier
from outbound.base import proxy_exists, register, verify
from outbound.builtin import DirectVerifier, DnsVerifier, RejectVerifier, RematchVerifier
from outbound.common import QuotedStr, endpoint_key, quoted_scalar
from outbound.hysteria import Hysteria2Verifier, HysteriaVerifier
from outbound.http import HttpVerifier, Socks5Verifier
from outbound.mieru import MieruVerifier
from outbound.overlay import EasyTierVerifier, TailscaleVerifier, ZeroTierVerifier
from outbound.quic import ShadowQuicVerifier, TuicVerifier
from outbound.shadowsocks import ShadowsocksRVerifier, ShadowsocksVerifier
from outbound.snell import SnellVerifier
from outbound.ssh import SshVerifier
from outbound.sudoku import SudokuVerifier
from outbound.trojan import TrojanVerifier
from outbound.tunnel import GostRelayVerifier, TrustTunnelVerifier
from outbound.vless import VlessVerifier
from outbound.vmess import VmessVerifier
from outbound.vpn import MasqueVerifier, OpenVPNVerifier, WireGuardVerifier

register(
    ShadowsocksVerifier(),
    ShadowsocksRVerifier(),
    SnellVerifier(),
    VmessVerifier(),
    VlessVerifier(),
    TrojanVerifier(),
    HttpVerifier(),
    Socks5Verifier(),
    AnyTLSVerifier(),
    HysteriaVerifier(),
    Hysteria2Verifier(),
    TuicVerifier(),
    ShadowQuicVerifier(),
    SshVerifier(),
    MieruVerifier(),
    SudokuVerifier(),
    TrustTunnelVerifier(),
    GostRelayVerifier(),
    WireGuardVerifier(),
    OpenVPNVerifier(),
    MasqueVerifier(),
    EasyTierVerifier(),
    TailscaleVerifier(),
    ZeroTierVerifier(),
    DirectVerifier(),
    DnsVerifier(),
    RejectVerifier(),
    RematchVerifier(),
)

__all__ = ["QuotedStr", "endpoint_key", "proxy_exists", "quoted_scalar", "verify"]
