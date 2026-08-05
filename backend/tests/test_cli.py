"""Tests for the Cisco IOS command engine.

These are the behavioural contract for Part 6: if a learner follows a CCNA
textbook transcript, it must work here.
"""

from __future__ import annotations

import pytest

from app.models.enums import DeviceKind
from app.schemas.device_config import DeviceConfig, admin_up
from app.services.cli import CliEngine, CliMode, CliSession


class Device:
    """Runs a script of commands against one device, tracking state."""

    def __init__(self, kind: DeviceKind = DeviceKind.ROUTER) -> None:
        self.engine = CliEngine(kind)
        self.session = CliSession()
        self.config = DeviceConfig()

    def run(self, *lines: str) -> str:
        output: list[str] = []
        for line in lines:
            result = self.engine.execute(line, self.session, self.config)
            self.session, self.config = result.session, result.config
            output.append(result.output)
        return "".join(output)

    def configure(self) -> Device:
        """Shortcut into global configuration mode."""
        self.run("enable", "configure terminal")
        return self


@pytest.fixture
def router() -> Device:
    return Device(DeviceKind.ROUTER)


@pytest.fixture
def switch() -> Device:
    return Device(DeviceKind.SWITCH)


class TestModes:
    def test_starts_in_user_exec(self, router: Device) -> None:
        assert router.session.mode is CliMode.USER_EXEC
        assert router.session.prompt() == "Router>"

    def test_enable_enters_privileged_exec(self, router: Device) -> None:
        router.run("enable")
        assert router.session.mode is CliMode.PRIV_EXEC
        assert router.session.prompt().endswith("#")

    def test_configure_terminal_enters_global_config(self, router: Device) -> None:
        router.run("enable", "configure terminal")
        assert router.session.mode is CliMode.GLOBAL_CONFIG
        assert router.session.prompt() == "Router(config)#"

    def test_interface_enters_interface_config(self, router: Device) -> None:
        router.configure().run("interface GigabitEthernet0/0")
        assert router.session.mode is CliMode.INTERFACE_CONFIG
        assert router.session.prompt() == "Router(config-if)#"

    def test_exit_steps_up_one_mode(self, router: Device) -> None:
        router.configure().run("interface g0/0", "exit")
        assert router.session.mode is CliMode.GLOBAL_CONFIG

    def test_end_returns_to_privileged_exec(self, router: Device) -> None:
        router.configure().run("interface g0/0", "end")
        assert router.session.mode is CliMode.PRIV_EXEC

    def test_hostname_changes_the_prompt(self, router: Device) -> None:
        router.configure().run("hostname R1")
        assert router.session.prompt() == "R1(config)#"


class TestAbbreviations:
    """Nobody types commands in full. IOS accepts any unambiguous prefix."""

    def test_conf_t_works(self, router: Device) -> None:
        router.run("en", "conf t")
        assert router.session.mode is CliMode.GLOBAL_CONFIG

    def test_int_with_short_interface_name(self, router: Device) -> None:
        router.configure().run("int g0/0")
        assert router.session.interface == "GigabitEthernet0/0"

    def test_interface_number_may_be_a_separate_token(self, router: Device) -> None:
        router.configure().run("int gi 0/1")
        assert router.session.interface == "GigabitEthernet0/1"

    def test_serial_abbreviation(self, router: Device) -> None:
        router.configure().run("int s0/0/0")
        assert router.session.interface == "Serial0/0/0"

    def test_switch_fastethernet_abbreviation(self, switch: Device) -> None:
        switch.configure().run("int fa0/5")
        assert switch.session.interface == "FastEthernet0/5"

    def test_no_shut_abbreviation(self, router: Device) -> None:
        router.configure().run("int g0/0", "no shut")
        assert router.config.interfaces["GigabitEthernet0/0"].enabled is True

    def test_show_ip_interface_brief_abbreviated(self, router: Device) -> None:
        output = router.run("enable", "sh ip int br")
        assert "GigabitEthernet0/0" in output


class TestInterfaceConfiguration:
    def test_assigns_an_address(self, router: Device) -> None:
        router.configure().run("int g0/0", "ip address 192.168.1.1 255.255.255.0")

        interface = router.config.interfaces["GigabitEthernet0/0"]
        assert interface.ip_address == "192.168.1.1"
        assert interface.subnet_mask == "255.255.255.0"

    def test_router_interfaces_start_administratively_down(self, router: Device) -> None:
        """The single most common reason a correct-looking link does not work."""
        router.configure().run("int g0/0", "ip address 10.0.0.1 255.255.255.0")

        interface = router.config.interfaces["GigabitEthernet0/0"]
        # Never explicitly set, so it resolves to the device's default.
        assert interface.enabled is None
        assert admin_up(interface, "router") is False

    def test_switch_ports_start_up(self, switch: Device) -> None:
        """A Catalyst's ports are live out of the box — routers' are not."""
        switch.configure().run("int fa0/1", "switchport mode access")

        interface = switch.config.interfaces["FastEthernet0/1"]
        assert admin_up(interface, "switch") is True

    def test_no_shutdown_brings_the_interface_up(self, router: Device) -> None:
        router.configure().run("int g0/0", "no shutdown")
        assert router.config.interfaces["GigabitEthernet0/0"].enabled is True

    def test_shutdown_takes_it_down_again(self, router: Device) -> None:
        router.configure().run("int g0/0", "no shutdown", "shutdown")
        assert router.config.interfaces["GigabitEthernet0/0"].enabled is False

    def test_rejects_an_invalid_address(self, router: Device) -> None:
        output = router.configure().run("int g0/0", "ip address 999.1.1.1 255.255.255.0")
        assert "%" in output
        assert router.config.interfaces["GigabitEthernet0/0"].ip_address is None

    def test_rejects_a_non_contiguous_mask(self, router: Device) -> None:
        """255.255.0.255 parses as an address but is not a legal mask."""
        output = router.configure().run("int g0/0", "ip address 10.0.0.1 255.255.0.255")
        assert "contiguous" in output

    def test_rejects_an_overlapping_subnet_on_another_interface(self, router: Device) -> None:
        router.configure().run("int g0/0", "ip address 192.168.1.1 255.255.255.0", "exit")
        output = router.run("int g0/1", "ip address 192.168.1.2 255.255.255.0")

        assert "overlaps" in output
        assert router.config.interfaces["GigabitEthernet0/1"].ip_address is None

    def test_description_is_stored(self, router: Device) -> None:
        router.configure().run("int g0/0", "description Link to core switch")
        assert router.config.interfaces["GigabitEthernet0/0"].description == "Link to core switch"

    def test_ip_address_dhcp(self, router: Device) -> None:
        router.configure().run("int g0/0", "ip address dhcp")
        assert router.config.interfaces["GigabitEthernet0/0"].dhcp is True

    def test_no_ip_address_clears_it(self, router: Device) -> None:
        router.configure().run("int g0/0", "ip address 10.0.0.1 255.255.255.0", "no ip address")
        assert router.config.interfaces["GigabitEthernet0/0"].ip_address is None


class TestSwitching:
    def test_creates_a_vlan_with_a_name(self, switch: Device) -> None:
        switch.configure().run("vlan 10", "name Sales")

        vlan = next(item for item in switch.config.vlans if item.id == 10)
        assert vlan.name == "Sales"

    def test_rejects_an_out_of_range_vlan(self, switch: Device) -> None:
        output = switch.configure().run("vlan 5000")
        assert "1-4094" in output

    def test_assigns_an_access_port(self, switch: Device) -> None:
        switch.configure().run(
            "vlan 10", "exit", "int fa0/1", "switchport mode access", "switchport access vlan 10"
        )

        interface = switch.config.interfaces["FastEthernet0/1"]
        assert interface.switchport_mode == "access"
        assert interface.access_vlan == 10

    def test_configures_a_trunk(self, switch: Device) -> None:
        switch.configure().run(
            "int g0/1",
            "switchport mode trunk",
            "switchport trunk allowed vlan 10,20,30-32",
        )

        interface = switch.config.interfaces["GigabitEthernet0/1"]
        assert interface.switchport_mode == "trunk"
        assert interface.allowed_vlans == [10, 20, 30, 31, 32]


class TestRouting:
    def test_adds_a_static_route(self, router: Device) -> None:
        router.configure().run("ip route 10.0.0.0 255.0.0.0 192.168.1.254")

        route = router.config.static_routes[0]
        assert route.network == "10.0.0.0"
        assert route.next_hop == "192.168.1.254"

    def test_adds_a_default_route(self, router: Device) -> None:
        router.configure().run("ip route 0.0.0.0 0.0.0.0 203.0.113.1")
        assert router.config.static_routes[0].network == "0.0.0.0"

    def test_no_ip_route_removes_it(self, router: Device) -> None:
        router.configure().run(
            "ip route 10.0.0.0 255.0.0.0 192.168.1.254",
            "no ip route 10.0.0.0 255.0.0.0 192.168.1.254",
        )
        assert router.config.static_routes == []

    def test_configures_ospf(self, router: Device) -> None:
        router.configure().run(
            "router ospf 1",
            "router-id 1.1.1.1",
            "network 192.168.1.0 0.0.0.255 area 0",
        )

        assert router.config.ospf is not None
        assert router.config.ospf.process_id == 1
        assert router.config.ospf.router_id == "1.1.1.1"
        assert router.config.ospf.networks[0].area == 0

    def test_ospf_network_requires_a_wildcard_and_area(self, router: Device) -> None:
        output = router.configure().run("router ospf 1", "network 192.168.1.0")
        assert "Incomplete" in output

    def test_configures_eigrp(self, router: Device) -> None:
        router.configure().run("router eigrp 100", "network 10.0.0.0", "no auto-summary")

        assert router.config.eigrp is not None
        assert router.config.eigrp.as_number == 100
        assert router.config.eigrp.auto_summary is False

    def test_configures_rip(self, router: Device) -> None:
        router.configure().run("router rip", "version 2", "network 192.168.1.0")

        assert router.config.rip is not None
        assert router.config.rip.version == 2


class TestServicesAndPolicy:
    def test_configures_a_dhcp_pool(self, router: Device) -> None:
        router.configure().run(
            "ip dhcp pool LAN",
            "network 192.168.1.0 255.255.255.0",
            "default-router 192.168.1.1",
            "dns-server 8.8.8.8",
        )

        pool = router.config.dhcp_pools[0]
        assert pool.name == "LAN"
        assert pool.gateway == "192.168.1.1"
        assert pool.dns_servers == ["8.8.8.8"]

    def test_configures_a_standard_acl(self, router: Device) -> None:
        router.configure().run("access-list 10 permit 192.168.1.0 0.0.0.255")

        acl = router.config.acls[0]
        assert acl.kind == "standard"
        assert acl.entries[0].action == "permit"

    def test_an_extended_acl_is_recognised_by_its_number(self, router: Device) -> None:
        router.configure().run("access-list 100 permit tcp any any eq 80")

        acl = router.config.acls[0]
        assert acl.kind == "extended"
        assert acl.entries[0].protocol == "tcp"
        assert acl.entries[0].destination_port == 80

    def test_applies_an_acl_to_an_interface(self, router: Device) -> None:
        router.configure().run("access-list 10 permit any", "int g0/0", "ip access-group 10 in")
        assert router.config.interfaces["GigabitEthernet0/0"].acl_in == "10"

    def test_configures_nat_overload(self, router: Device) -> None:
        router.configure().run(
            "int g0/0",
            "ip nat inside",
            "exit",
            "int g0/1",
            "ip nat outside",
            "exit",
            "ip nat inside source list 1 interface GigabitEthernet0/1 overload",
        )

        assert router.config.interfaces["GigabitEthernet0/0"].nat_side == "inside"
        assert router.config.interfaces["GigabitEthernet0/1"].nat_side == "outside"
        assert router.config.nat_rules[0].kind == "overload"

    def test_sets_the_default_gateway(self, switch: Device) -> None:
        switch.configure().run("ip default-gateway 192.168.1.1")
        assert switch.config.default_gateway == "192.168.1.1"


class TestShowCommands:
    def test_running_config_reflects_what_was_typed(self, router: Device) -> None:
        router.configure().run(
            "hostname R1", "int g0/0", "ip address 192.168.1.1 255.255.255.0", "no shutdown", "end"
        )
        output = router.run("show running-config")

        assert "hostname R1" in output
        assert " ip address 192.168.1.1 255.255.255.0" in output
        # An enabled interface has no `shutdown` line — its absence is what
        # "up" looks like in a running config.
        assert "interface GigabitEthernet0/0\n ip address" in output

    def test_running_config_lists_unconfigured_interfaces_too(self, router: Device) -> None:
        output = router.run("enable", "show run")
        assert "interface GigabitEthernet0/1" in output
        assert "shutdown" in output

    def test_running_config_omits_the_console_port(self, router: Device) -> None:
        """Console is configured under `line con 0`, not as an interface."""
        output = router.run("enable", "show run")
        assert "interface Console" not in output

    def test_interface_brief_shows_addresses_and_state(self, router: Device) -> None:
        router.configure().run(
            "int g0/0", "ip address 10.0.0.1 255.255.255.0", "no shutdown", "end"
        )
        output = router.run("show ip interface brief")

        assert "10.0.0.1" in output
        assert "administratively down" in output  # the other interfaces

    def test_ip_route_shows_connected_and_static(self, router: Device) -> None:
        router.configure().run(
            "int g0/0",
            "ip address 192.168.1.1 255.255.255.0",
            "no shutdown",
            "exit",
            "ip route 0.0.0.0 0.0.0.0 192.168.1.254",
            "end",
        )
        output = router.run("show ip route")

        assert "C    192.168.1.0/24 is directly connected" in output
        assert "Gateway of last resort is 192.168.1.254" in output

    def test_vlan_brief_lists_ports(self, switch: Device) -> None:
        switch.configure().run(
            "vlan 10",
            "name Sales",
            "exit",
            "int fa0/1",
            "switchport mode access",
            "switchport access vlan 10",
            "end",
        )
        output = switch.run("show vlan brief")

        assert "Sales" in output
        assert "Fa0/1" in output

    def test_show_version_names_the_model(self, router: Device) -> None:
        output = router.run("enable", "show version")
        assert "ISR 2911" in output

    def test_startup_config_is_absent_until_saved(self, router: Device) -> None:
        assert "not present" in router.run("enable", "show startup-config")

        router.run("copy running-config startup-config")
        assert "not present" not in router.run("show startup-config")


class TestErrorHandling:
    def test_unknown_command_reports_invalid_input(self, router: Device) -> None:
        output = router.run("enable", "flibbertigibbet")

        assert "% Invalid input detected at '^' marker." in output
        assert "^" in output

    def test_incomplete_command_says_so(self, router: Device) -> None:
        output = router.configure().run("interface")
        assert "% Incomplete command." in output

    def test_an_unknown_interface_is_rejected(self, router: Device) -> None:
        output = router.configure().run("interface GigabitEthernet9/9")
        assert "% Invalid input" in output

    def test_configuration_commands_are_rejected_in_exec_mode(self, router: Device) -> None:
        """`hostname` is a global-config command; EXEC must not accept it."""
        output = router.run("enable", "hostname R1")

        assert "% Invalid input" in output
        assert router.config.hostname == ""

    def test_a_device_without_a_cli_says_so(self) -> None:
        pc = Device(DeviceKind.PC)
        assert "does not have a command-line interface" in pc.run("enable")


class TestFormAndCliAgree:
    """The point of building Parts 5 and 6 together."""

    def test_cli_output_reflects_configuration_set_directly(self) -> None:
        # Stand in for the configuration form by setting the model directly.
        from app.schemas.device_config import InterfaceConfig

        device = Device(DeviceKind.ROUTER)
        device.config = DeviceConfig(
            hostname="FormSet",
            interfaces={
                "GigabitEthernet0/0": InterfaceConfig(
                    ip_address="172.16.0.1", subnet_mask="255.255.0.0", enabled=True
                )
            },
        )

        output = device.run("enable", "show running-config")
        assert "hostname FormSet" in output
        assert " ip address 172.16.0.1 255.255.0.0" in output

    def test_cli_changes_are_visible_in_the_same_model(self) -> None:
        device = Device(DeviceKind.ROUTER)
        device.configure().run("int g0/0", "ip address 172.16.0.1 255.255.0.0", "no shutdown")

        # Exactly what a configuration form would read back.
        interface = device.config.interfaces["GigabitEthernet0/0"]
        assert interface.ip_address == "172.16.0.1"
        assert interface.enabled is True
