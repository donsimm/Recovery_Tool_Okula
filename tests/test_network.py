import ipaddress
import unittest

from okula_recovery import network

IP_ADDR = """\
2: enp2s0    inet 192.168.1.20/24 brd 192.168.1.255 scope global dynamic enp2s0\\       valid_lft 86000sec
3: wlan0    inet 10.0.0.5/16 brd 10.0.255.255 scope global wlan0\\       valid_lft forever
"""

IP_NEIGH = """\
192.168.1.1 dev enp2s0 lladdr aa:bb:cc:dd:ee:01 REACHABLE
192.168.1.30 dev enp2s0 lladdr aa:bb:cc:dd:ee:1e STALE
192.168.1.40 dev enp2s0 FAILED
fe80::1 dev enp2s0 lladdr aa:bb:cc:dd:ee:01 router STALE
"""


class ParseTest(unittest.TestCase):
    def test_ip_addr(self):
        ifaces = network.parse_ip_addr(IP_ADDR)
        self.assertEqual(ifaces, [ipaddress.IPv4Interface("192.168.1.20/24"),
                                  ipaddress.IPv4Interface("10.0.0.5/16")])

    def test_ip_neigh(self):
        self.assertEqual(network.parse_ip_neigh(IP_NEIGH), {
            "192.168.1.1": "aa:bb:cc:dd:ee:01",
            "192.168.1.30": "aa:bb:cc:dd:ee:1e",
        })


class ScanTest(unittest.TestCase):
    def test_scan_uses_ping_and_skips_own_ip(self):
        orig = (network.ping, network.resolve_name, network.neighbours, network.local_interfaces)
        network.ping = lambda ip, timeout=1: ip in ("192.168.1.1", "192.168.1.2")
        network.resolve_name = lambda ip: "router" if ip == "192.168.1.1" else ""
        network.neighbours = lambda: {"192.168.1.1": "aa:bb:cc:dd:ee:01"}
        network.local_interfaces = lambda: [ipaddress.IPv4Interface("192.168.1.2/29")]
        try:
            seen = []
            result = network.scan(ipaddress.IPv4Network("192.168.1.0/29"),
                                  progress=lambda d, t: seen.append((d, t)))
        finally:
            network.ping, network.resolve_name, network.neighbours, network.local_interfaces = orig
        self.assertEqual([(m.ip, m.name, m.mac) for m in result],
                         [("192.168.1.1", "router", "aa:bb:cc:dd:ee:01")])
        self.assertEqual(seen[-1], (5, 5))


if __name__ == "__main__":
    unittest.main()
