"""Normal deployment against an injected provider; all FIM/FABlib work is local."""

from pathlib import Path
import inspect
import socket
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fim.slivers.capacities_labels import ReservationInfo
from fim.user import ExperimentTopology, ServiceType
from fabrictestbed_extensions.fablib.component import Component
from fabrictestbed_extensions.fablib.interface import Interface
from fabrictestbed_extensions.fablib.network_service import NetworkService
from fabrictestbed_extensions.fablib.node import Node
from fabrictestbed_extensions.fablib.slice import Slice

from fabric_generic_cluster import deployment as d
from fabric_generic_cluster import _realization as r
from fabric_generic_cluster.models import (
    FacilityPort, PersistentVolume, load_topology_from_dict, load_topology_from_yaml_file,
)


FIXTURES = Path(__file__).parent / "fixtures"
PROVISION_OPTIONS = dict(wait=True, progress=False, post_boot_config=False, wait_ssh=False)


class OfflineSlice(Slice):
    """Real SDK construction, a separate provider graph, and stale wrapper caches."""

    def __init__(self, manager, name):
        super().__init__(manager, name)
        self.topology = ExperimentTopology()
        self.submissions = []
        self.refreshes = []
        self.provider_state = "StableOK"
        self.on_submit = lambda topology: None
        self.post_boot_config = Mock()
        self.wait_ssh = Mock()
        self.wait_jupyter = Mock()
        self.delete = Mock(side_effect=AssertionError("Must not delete"))

    def submit(self, **kwargs):
        self.submissions.append(kwargs)
        self.slice_id = "offline-slice-id"
        self.provider_topology = ExperimentTopology()
        self.provider_topology.load(graph_string=self.topology.serialize())
        self.provider_slivers = []
        for item in [*self.provider_topology.nodes.values(),
                     *self.provider_topology.facilities.values(),
                     *self.provider_topology.network_services.values()]:
            reservation_id = f"reservation-{item.name}"
            item.reservation_info = ReservationInfo(
                reservation_id=reservation_id, reservation_state="Active"
            )
            self.provider_slivers.append(SimpleNamespace(
                name=item.name, sliver_id=reservation_id, state="Active", notice=""
            ))
        self.on_submit(self.provider_topology)
        if kwargs.get("wait_ssh", True):
            self.wait_ssh()
        if kwargs.get("post_boot_config", True):
            self.post_boot_config()
        return self.slice_id

    def update_slice(self):
        self.refreshes.append("slice")
        self.sm_slice = SimpleNamespace(state=self.provider_state)

    def update_slivers(self):
        self.refreshes.append("slivers")
        self.slivers = self.provider_slivers

    def update_topology(self):
        self.refreshes.append("topology")
        self.topology = self.provider_topology


class OfflineManager:
    def __init__(self):
        self.created = []
        self.prepare = lambda slice: None
        self.get_slices = Mock(return_value=[])

    def new_slice(self, name):
        slice = OfflineSlice(self, name)
        self.created.append(slice)
        self.prepare(slice)
        return slice

    def get_os_images(self):
        return {}

    def get_random_sites(self, **kwargs):
        return ["SRI"]


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    # Any accidental FABRIC or other socket access is a test failure.
    monkeypatch.setattr(socket.socket, "connect", Mock(side_effect=AssertionError("Network forbidden")))
    monkeypatch.setattr(socket, "create_connection", Mock(side_effect=AssertionError("Network forbidden")))


@pytest.fixture
def provider(monkeypatch):
    manager = OfflineManager()
    monkeypatch.setattr(d, "fablib", lambda: manager)
    return manager


@pytest.fixture(params=["fabric-dpu-fabnet-ipv4", "fabric-fpga-l2bridge"])
def approved(request):
    return load_topology_from_yaml_file(FIXTURES / f"{request.param}-rendered.yaml")


def topology(model="NIC_ConnectX_7_100", family="dpu", count=1):
    return load_topology_from_dict({
        "site_topology_nodes": {"nodes": {"node1": {
            "name": "display-name", "hostname": "vm-a", "site": "SRI",
            "capacity": {"cpu": 2, "ram": 4, "disk": 20, "os": "default_rocky_9"},
            "pci": {family: {"key1": {"name": "device1", "model": model,
                "interfaces": {f"iface{i+1}": {
                    "device": f"eth{i+1}", "connection": f"conn{i+1}", "binding": "data"
                } for i in range(count)} if family in ("network", "dpu", "fpga") else {}}}},
        }}},
        "site_topology_networks": {"networks": {"net1": {"name": "data", "type": "L2Bridge"}}},
    })


def first_component(topology):
    return next(iter(topology.nodes["vm-a"].components.values()))


def forbid_guest(monkeypatch):
    forbidden = Mock(side_effect=AssertionError("Guest/display operation forbidden"))
    for cls, names in [
        (Node, ["execute", "add_post_boot_execute", "get_ssh_command"]),
        (Interface, ["get_device_name", "ip_addr_add", "get_ip_addr"]),
        (Component, ["configure"]),
        (Slice, ["list_interfaces", "list_nodes", "list_networks", "show"]),
    ]:
        for name in names:
            if hasattr(cls, name):
                monkeypatch.setattr(cls, name, forbidden)
    for name in ("configure_l3_networks", "enable_public_routing"):
        monkeypatch.setattr(d, name, forbidden)
    for module, name in [
        ("network_config", "configure_node_interfaces"),
        ("ssh_setup", "setup_passwordless_ssh"),
        ("selinux_management", "configure_selinux_from_topology"),
        ("ansible_setup", "setup_ansible_environment"),
    ]:
        monkeypatch.setattr(f"fabric_generic_cluster.{module}.{name}", forbidden)
    return forbidden


def test_provision_approved(provider, approved, monkeypatch):
    for node in approved.site_topology_nodes.iter_nodes():
        node.specific.postboot = "echo must-not-run"
    forbidden = forbid_guest(monkeypatch)
    slice = d.deploy_and_configure_slice(approved, "approved", setup_ansible=True, provision_only=True)
    assert slice is provider.created[0]
    assert slice.submissions == [PROVISION_OPTIONS]
    assert slice.refreshes == ["slice", "slivers", "topology"]
    for call in (forbidden, slice.wait_ssh, slice.wait_jupyter, slice.post_boot_config, slice.delete):
        call.assert_not_called()


@pytest.mark.parametrize("family,model,count", [
    ("network", "NIC_Basic", 1),
    ("dpu", "NIC_ConnectX_7_100", 2),
    ("fpga", "FPGA_Xilinx_U280", 2),
])
def test_real_interface_resolution_without_deprecated_accessor(provider, monkeypatch, family, model, count):
    requested = topology(model, family, count)
    slice = provider.new_slice("interface-api")
    node = slice.add_node(name="vm-a", site="SRI")
    component = node.add_component(name="device1", model=model)
    interfaces = component.get_interfaces()
    expected = [{"name": i.get_fim().name, "node_id": i.get_fim().node_id} for i in interfaces]

    # 1.9.5 retains this deprecated alias; 2.0.6 removes it. Keep the real
    # Interface, get_fim(), and FIM objects while reproducing the newer API.
    monkeypatch.delattr(Interface, "get_fim_interface", raising=False)
    assert all(isinstance(i, Interface) and not hasattr(i, "get_fim_interface") for i in interfaces)
    manifest = r.requested_manifest(requested)
    groups = r.resolve_interfaces(slice, manifest, {})

    # Slice.get_node() may rebuild wrappers; the selected FIM identity is stable.
    assert all(isinstance(i, Interface) and not hasattr(i, "get_fim_interface") for i in groups["data"])
    assert [{"name": i.get_fim().name, "node_id": i.get_fim().node_id} for i in groups["data"]] == expected
    assert manifest["networks"]["data"]["members"] == expected
    selected = manifest["nodes"]["vm-a"]["components"]["device1"]["interfaces"]
    assert [i["provider_interface"] for i in selected] == expected
    assert slice.submissions == []


def test_real_facility_interface_resolution_without_deprecated_accessor(provider, monkeypatch):
    requested = topology()
    requested.site_topology_nodes.nodes.clear()
    requested.site_topology_facility_ports.facility_ports["fp1"] = FacilityPort(
        name="external-port", site="SRI", vlan=123, binding="data"
    )
    slice = provider.new_slice("facility-interface-api")
    port = slice.add_facility_port(name="external-port", site="SRI", vlan="123")
    interface = port.get_interfaces()[0]
    expected = {"name": interface.get_fim().name, "node_id": interface.get_fim().node_id}
    monkeypatch.delattr(Interface, "get_fim_interface", raising=False)
    assert isinstance(interface, Interface) and not hasattr(interface, "get_fim_interface")
    manifest = r.requested_manifest(requested)

    groups = r.resolve_interfaces(slice, manifest, {"external-port": port})

    assert groups["data"][0] is interface
    assert manifest["networks"]["data"]["members"] == [expected]
    assert manifest["facilities"]["external-port"]["provider_interface"] == expected
    assert slice.submissions == []


@pytest.mark.parametrize("strict", [False, True])
def test_default_and_strict_keep_guest_behavior(provider, monkeypatch, strict):
    calls = []
    for module, name in [
        (d, "configure_l3_networks"),
        ("fabric_generic_cluster.network_config", "configure_node_interfaces"),
        ("fabric_generic_cluster.ssh_setup", "setup_passwordless_ssh"),
        ("fabric_generic_cluster.selinux_management", "configure_selinux_from_topology"),
        ("fabric_generic_cluster.ansible_setup", "setup_ansible_environment"),
    ]:
        recorder = lambda *args, _name=name, **kwargs: calls.append(_name)
        if isinstance(module, str):
            monkeypatch.setattr(f"{module}.{name}", recorder)
        else:
            monkeypatch.setattr(module, name, recorder)
    model = topology()
    model.site_topology_nodes.nodes["node1"].specific.postboot = "echo registered"
    postboot = Mock()
    monkeypatch.setattr(Node, "add_post_boot_execute", postboot)
    slice = d.deploy_and_configure_slice(model, "default", True, True, False, strict=strict)
    assert slice.submissions == [{}]
    assert calls == ["configure_l3_networks", "configure_node_interfaces", "setup_passwordless_ssh",
                     "configure_selinux_from_topology", "setup_ansible_environment"]
    postboot.assert_called_once_with(command="echo registered")
    slice.wait_ssh.assert_called_once()
    slice.post_boot_config.assert_called_once()
    assert bool(slice.refreshes) is strict


@pytest.mark.parametrize("family,model,count", [
    ("network", "NIC_Basic", 1), ("network", "NIC_ConnectX_5", 2),
    ("network", "NIC_ConnectX_6", 1), ("dpu", "NIC_ConnectX_7_100", 1),
    ("dpu", "NIC_ConnectX_7_400", 2), ("fpga", "FPGA_Xilinx_U280", 1),
    ("fpga", "FPGA_Xilinx_SN1022", 2), ("gpu", "GPU_TeslaT4", 0),
    ("gpu", "GPU_RTX6000", 0), ("gpu", "GPU_A30", 0), ("gpu", "GPU_A40", 0),
    ("nvme", "NVME_P4510", 0),
])
def test_pci_regressions(provider, family, model, count):
    slice = d.deploy_topology_to_fabric(topology(model, family, count), "pci", provision_only=True)
    assert len(slice.topology.nodes["vm-a"].components) == 1


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("family,model", [("dpu", "NIC_ConnectX_7_100"), ("fpga", "FPGA_Xilinx_U280")])
def test_distinct_allocations_interleaved_bindings_and_refresh(provider, monkeypatch, reverse, family, model):
    requested = topology(model, family, 2)
    devices = getattr(requested.site_topology_nodes.nodes["node1"].pci, family)
    devices["key2"] = devices["key1"].model_copy(deep=True)
    devices["key2"].name = "device2"
    networks = requested.site_topology_networks.networks
    networks["net2"] = networks["net1"].model_copy(update={"name": "other"})
    devices["key1"].interfaces["iface2"].binding = "other"
    devices["key2"].interfaces["iface1"].binding = "other"
    original = Component.get_interfaces
    selected = {}

    def enumerated(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        if isinstance(result, list):
            result = sorted(result, key=lambda i: i.get_name(), reverse=reverse)
            if self.get_slice().slice_id:
                result.reverse()
            else:
                selected[self.get_name()] = [r._identity(i.get_fim()) for i in result]
        return result

    monkeypatch.setattr(Component, "get_interfaces", enumerated)
    slice = d.deploy_topology_to_fabric(requested, "two", provision_only=True)
    actual = r.provider_snapshot(slice)
    data = next(n for n in actual["networks"] if n["name"] == "data")
    assert {r._token(m["peers"][0]) for m in data["members"]} == {
        r._token(selected["vm-a-device1"][0]), r._token(selected["vm-a-device2"][1]),
    }
    assert len(actual["nodes"][0]["components"]) == 2


@pytest.mark.parametrize("mutation,match", [
    ("duplicate_node", "Duplicate node identity"),
    ("duplicate_component", "Duplicate component identity"),
    ("duplicate_network", "Duplicate NetworkService name"),
    ("unknown_binding", "Unknown binding"),
    ("wrong_family", "Invalid component family/model"),
])
def test_preflight_failure(provider, mutation, match):
    model = topology()
    nodes = model.site_topology_nodes.nodes
    device = nodes["node1"].pci.dpu["key1"]
    if mutation == "duplicate_node":
        nodes["node2"] = nodes["node1"].model_copy(deep=True)
    elif mutation == "duplicate_component":
        nodes["node1"].pci.dpu["key2"] = device.model_copy(deep=True)
    elif mutation == "duplicate_network":
        model.site_topology_networks.networks["net2"] = model.site_topology_networks.networks["net1"]
    elif mutation == "unknown_binding":
        device.interfaces["iface1"].binding = "absent"
    else:
        device.model = "GPU_A40"
    with pytest.raises(d.SliceDeploymentError, match=match) as caught:
        d.deploy_topology_to_fabric(model, "bad", strict=True)
    assert caught.value.phase == "preflight"
    assert caught.value.diagnostics["requested_topology"]
    assert not provider.created


@pytest.mark.parametrize("strict", [False, True])
def test_component_creation_failure(provider, monkeypatch, strict):
    cause = RuntimeError("component creation failed")
    monkeypatch.setattr(Node, "add_component", Mock(side_effect=cause))
    if strict:
        with pytest.raises(d.SliceDeploymentError) as caught:
            d.deploy_topology_to_fabric(topology(), "broken", strict=True)
        assert caught.value.__cause__ is cause
        assert caught.value.slice is provider.created[0]
        assert caught.value.phase == "construction"
        assert caught.value.diagnostics["expected"]["nodes"]
        assert provider.created[0].submissions == []
    else:
        assert d.deploy_topology_to_fabric(topology(), "legacy") is provider.created[0]
        assert provider.created[0].submissions == [{}]
    provider.created[0].delete.assert_not_called()


@pytest.mark.parametrize("fault", ["missing", "duplicate", "wrong_identity"])
def test_interface_resolution_failures(provider, monkeypatch, fault):
    original = Component.get_interfaces

    def broken(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        if isinstance(result, list):
            if fault == "missing":
                return result[:1]
            if fault == "duplicate":
                return [result[0], result[0]]
        return result

    monkeypatch.setattr(Component, "get_interfaces", broken)
    if fault == "wrong_identity":
        monkeypatch.setattr(Node, "get_component", lambda self, **kw: SimpleNamespace(get_name=lambda: "wrong"))
    with pytest.raises(d.SliceDeploymentError):
        d.deploy_topology_to_fabric(topology(count=2), "bad", strict=True)
    assert not provider.created[0].submissions
    assert "data" not in provider.created[0].topology.network_services


def mutate_provider(topology, fault):
    network = topology.network_services["data"]
    component = first_component(topology)
    if fault == "wrong_model":
        component.set_property("model", "ConnectX-6")
    elif fault == "missing_component":
        topology.nodes["vm-a"].remove_component(name=component.name)
    elif fault == "extra_component":
        topology.nodes["vm-a"].add_component(name="vm-a-duplicate", model_type=Component.component_model_map["NIC_ConnectX_7_100"])
    elif fault == "missing_service":
        topology.remove_network_service(name="data")
    elif fault == "wrong_type":
        network.set_property("type", ServiceType.L2STS)
    elif fault == "missing_member":
        network.disconnect_interface(network.interface_list[0].get_peers()[0])
    elif fault == "extra_member":
        bound = network.interface_list[0].get_peers()[0].node_id
        extra = next(i for i in component.interface_list if i.node_id != bound)
        network.connect_interface(extra)
    elif fault == "swapped_member":
        selected = network.interface_list[0].get_peers()[0]
        other = next(i for i in component.interface_list if i.node_id != selected.node_id)
        network.disconnect_interface(selected)
        network.connect_interface(other)
    elif fault == "failed_node":
        node = topology.nodes["vm-a"]
        node.reservation_info = ReservationInfo(reservation_id="reservation-vm-a", reservation_state="Failed", error_message="allocation rejected")
    elif fault == "missing_reservation":
        topology.nodes["vm-a"].reservation_info = None
    elif fault == "unresolved_member":
        network.add_interface(name="unresolved-service-port")
    elif fault == "extra_node":
        topology.add_node(name="vm-a-duplicate", site="SRI")


@pytest.mark.parametrize("fault,match", [
    ("wrong_model", "Wrong component model"), ("missing_component", "Expected one component"),
    ("extra_component", "Unexpected component allocations"), ("missing_service", "Expected one NetworkService"),
    ("wrong_type", "Incorrect service type"), ("missing_member", "Membership mismatch"),
    ("extra_member", "Membership mismatch"), ("swapped_member", "Membership mismatch"),
    ("failed_node", "expected Active"), ("missing_reservation", "expected Active"),
    ("unresolved_member", "Unresolved service member"),
    ("extra_node", "Unexpected node allocations"),
])
def test_post_submission_failures(provider, fault, match):
    provider.prepare = lambda slice: setattr(slice, "on_submit", lambda t: mutate_provider(t, fault))
    with pytest.raises(d.SliceDeploymentError, match=match) as caught:
        d.deploy_and_configure_slice(topology(), "failed", provision_only=True)
    error = caught.value
    assert error.phase == "post_submission_verification"
    assert error.slice_id == "offline-slice-id"
    assert error.slice_name == "failed"
    assert error.slice is provider.created[0]
    assert error.diagnostics["expected"]["networks"]["data"]["members"]
    assert error.diagnostics["actual"]["nodes"]
    assert error.diagnostics["serialized_topology"]
    assert error.diagnostics["mismatches"]
    assert isinstance(error.__cause__, ValueError)
    error.slice.delete.assert_not_called()


@pytest.mark.parametrize("fault", ["wrong_model", "missing_service", "wrong_type", "missing_member", "extra_member"])
def test_pre_submission_rejects_silent_incomplete_construction(provider, monkeypatch, fault):
    original = Slice.add_l2network

    def broken(self, **kwargs):
        result = original(self, **kwargs)
        mutate_provider(self.topology, fault)
        return result

    monkeypatch.setattr(Slice, "add_l2network", broken)
    with pytest.raises(d.SliceDeploymentError) as caught:
        d.deploy_topology_to_fabric(topology(), "failed", strict=True)
    assert caught.value.phase == "pre_submission_verification"
    assert provider.created[0].submissions == []


@pytest.mark.parametrize("when", ["construction", "refresh"])
@pytest.mark.parametrize("service_type", [ServiceType.L2Bridge, ServiceType.FABNetv4, ServiceType.OVS])
def test_unexpected_raw_network_service(provider, monkeypatch, when, service_type):
    def add_extra(t):
        # Even an internal-looking type is unexpected without graph ownership.
        t.add_network_service(name="unexpected-service", nstype=service_type)

    if when == "refresh":
        provider.prepare = lambda slice: setattr(slice, "on_submit", add_extra)
    else:
        original = Slice.add_l2network
        def add(self, **kwargs):
            result = original(self, **kwargs)
            add_extra(self.topology)
            return result
        monkeypatch.setattr(Slice, "add_l2network", add)

    with pytest.raises(d.SliceDeploymentError, match="Unexpected NetworkService.*unexpected-service") as caught:
        d.deploy_topology_to_fabric(topology(), "extra-service", provision_only=True)
    expected_phase = "pre_submission_verification" if when == "construction" else "post_submission_verification"
    assert caught.value.phase == expected_phase
    assert bool(provider.created[0].submissions) is (when == "refresh")
    assert any("unexpected-service" in message for message in caught.value.diagnostics["mismatches"])
    provider.created[0].delete.assert_not_called()


def test_non_strict_still_accepts_additional_network_service(provider, monkeypatch):
    original = Slice.add_l2network
    def add(self, **kwargs):
        result = original(self, **kwargs)
        self.topology.add_network_service(name="extra-service", nstype=ServiceType.L2Bridge)
        return result
    monkeypatch.setattr(Slice, "add_l2network", add)
    slice = d.deploy_topology_to_fabric(topology(), "legacy")
    assert slice.submissions == [{}]
    assert slice.refreshes == []
    assert "extra-service" in slice.topology.network_services


@pytest.mark.parametrize("when", ["construction", "refresh"])
@pytest.mark.parametrize("kind", ["component", "node", "network"])
def test_duplicate_identities_hidden_by_name_dictionaries(provider, monkeypatch, when, kind):
    def duplicate(t):
        if kind == "component":
            original = first_component(t)
            clone = t.nodes["vm-a"].add_component(
                name="duplicate-temp", model_type=Component.component_model_map["NIC_ConnectX_7_100"]
            )
        elif kind == "node":
            original = t.nodes["vm-a"]
            clone = t.add_node(name="duplicate-temp", site="SRI")
        else:
            original = t.network_services["data"]
            clone = t.add_network_service(name="duplicate-temp", nstype=ServiceType.L2Bridge)
        # Simulate malformed provider evidence; FIM name dictionaries collapse it.
        t.graph_model.update_node_properties(node_id=clone.node_id, props={"Name": original.name})

    if when == "refresh":
        provider.prepare = lambda slice: setattr(slice, "on_submit", duplicate)
    else:
        original = Slice.add_l2network
        def add(self, **kwargs):
            result = original(self, **kwargs)
            duplicate(self.topology)
            return result
        monkeypatch.setattr(Slice, "add_l2network", add)
    match = "Duplicate NetworkService name" if kind == "network" else "Duplicate"
    with pytest.raises(d.SliceDeploymentError, match=match) as caught:
        d.deploy_topology_to_fabric(topology(), "duplicates", strict=True)
    if kind == "network":
        # Set comparison must not collapse duplicates before the raw-ID check.
        assert sum(n["name"] == "data" for n in caught.value.diagnostics["actual"]["networks"]) == 2
    assert bool(provider.created[0].submissions) is (when == "refresh")


def test_raw_membership_detects_members_hidden_by_wrappers(provider, monkeypatch):
    monkeypatch.setattr(NetworkService, "get_interfaces", lambda self: [])
    provider.prepare = lambda slice: setattr(slice, "on_submit", lambda t: mutate_provider(t, "extra_member"))
    with pytest.raises(d.SliceDeploymentError, match="Membership mismatch"):
        d.deploy_topology_to_fabric(topology(), "raw", provision_only=True)


@pytest.mark.parametrize("strict", [False, True])
def test_silent_attachment_noop(provider, monkeypatch, strict):
    from fim.user.network_service import NetworkService as FimService
    monkeypatch.setattr(FimService, "connect_interface", lambda self, interface: None)
    if strict:
        with pytest.raises(d.SliceDeploymentError, match="Membership mismatch"):
            d.deploy_topology_to_fabric(topology(), "noop", strict=True)
        assert not provider.created[0].submissions
    else:
        assert d.deploy_topology_to_fabric(topology(), "legacy") is provider.created[0]


def test_persistent_storage_and_facility_regression(provider):
    requested = topology()
    requested.site_topology_nodes.nodes["node1"].persistent_storage.volume["vol1"] = PersistentVolume(
        name="existing-volume", size=100
    )
    requested.site_topology_facility_ports.facility_ports["fp1"] = FacilityPort(
        name="external-port", site="SRI", vlan=123, binding="data"
    )
    slice = d.deploy_topology_to_fabric(requested, "facility", provision_only=True)
    assert "existing-volume" in slice.topology.nodes["vm-a"].components
    assert len(slice.topology.network_services["data"].interface_list) == 2


@pytest.mark.parametrize("helper", ["add_storage", "add_facility_port", "add_l2network", "add_l3network"])
def test_construction_errors_propagate_in_strict(provider, monkeypatch, helper):
    requested = topology()
    cls = Slice
    if helper == "add_storage":
        cls = Node
        requested.site_topology_nodes.nodes["node1"].persistent_storage.volume["vol1"] = PersistentVolume(name="volume", size=10)
    elif helper == "add_facility_port":
        requested.site_topology_facility_ports.facility_ports["fp1"] = FacilityPort(name="facility", site="SRI", vlan=1, binding="data")
    elif helper == "add_l3network":
        requested.site_topology_networks.networks["net1"].type = "IPv4"
    cause = RuntimeError(f"{helper} failed")
    monkeypatch.setattr(cls, helper, Mock(side_effect=cause))
    with pytest.raises(d.SliceDeploymentError) as caught:
        d.deploy_topology_to_fabric(requested, "bad", strict=True)
    assert caught.value.__cause__ is cause
    assert not provider.created[0].submissions


@pytest.mark.parametrize("unbound", [False, True])
def test_unused_provider_interfaces_are_allowed(provider, unbound):
    requested = topology(count=2 if unbound else 1)
    if unbound:
        requested.site_topology_nodes.nodes["node1"].pci.dpu["key1"].interfaces["iface2"].binding = ""
    slice = d.deploy_topology_to_fabric(requested, "unused", provision_only=True)
    assert len(slice.topology.network_services["data"].interface_list) == 1


@pytest.mark.parametrize("error_type", [RuntimeError, d.SliceDeploymentError])
def test_guest_failure_has_context_and_strict_wrapper_cannot_return_none(provider, monkeypatch, error_type):
    cause = error_type("guest configuration failed")
    monkeypatch.setattr(d, "configure_l3_networks", Mock(side_effect=cause))
    with pytest.raises(d.SliceDeploymentError) as caught:
        d.deploy_and_configure_slice(topology(), "guest", strict=True)
    assert caught.value.__cause__ is cause
    assert caught.value.phase == "guest_configuration"
    assert caught.value.slice is provider.created[0]
    monkeypatch.setattr(d, "deploy_topology_to_fabric", Mock(return_value=None))
    with pytest.raises(d.SliceDeploymentError, match="no verified slice"):
        d.deploy_and_configure_slice(topology(), "none", strict=True)


@pytest.mark.parametrize("method", ["update_slice", "update_slivers", "update_topology"])
def test_refresh_failure_is_not_swallowed(provider, method):
    cause = RuntimeError(f"{method} failed")
    provider.prepare = lambda slice: setattr(slice, method, Mock(side_effect=cause))
    with pytest.raises(d.SliceDeploymentError) as caught:
        d.deploy_topology_to_fabric(topology(), "failed", provision_only=True)
    assert caught.value.__cause__ is cause
    assert caught.value.phase == "provider_refresh"
    assert caught.value.slice_id == "offline-slice-id"


@pytest.mark.parametrize("cls,method,match", [
    (Slice, "get_node", "Missing provider node"),
    (Node, "get_component", "Missing provider component"),
    (Slice, "add_l2network", "Provider did not create NetworkService"),
])
def test_missing_provider_objects_fail_clearly(provider, monkeypatch, cls, method, match):
    monkeypatch.setattr(cls, method, Mock(return_value=None))
    with pytest.raises(d.SliceDeploymentError, match=match):
        d.deploy_topology_to_fabric(topology(), "missing", strict=True)
    assert not provider.created[0].submissions


@pytest.mark.parametrize("fault", ["stable_error", "failed_sliver", "wrong_sliver_name", "no_slivers", "no_refresh", "no_topology"])
def test_missing_or_failed_allocation_evidence(provider, fault):
    def prepare(slice):
        if fault == "stable_error":
            slice.provider_state = "StableError"
        elif fault == "no_refresh":
            slice.update_topology = Mock()
        elif fault == "no_topology":
            slice.update_topology = lambda: setattr(slice, "topology", None)
        else:
            def after(topology):
                if fault == "no_slivers":
                    slice.provider_slivers = []
                elif fault == "wrong_sliver_name":
                    slice.provider_slivers[0].name = "different-allocation"
                else:
                    slice.provider_slivers[0].state = "Failed"
            slice.on_submit = after
    provider.prepare = prepare
    with pytest.raises(d.SliceDeploymentError):
        d.deploy_topology_to_fabric(topology(), "failed", strict=True)


def test_diagnostic_failure_keeps_original_cause(provider, monkeypatch):
    cause = RuntimeError("original submit error")
    def prepare(slice):
        def submit(**kwargs):
            slice.slice_id = "recover-me"
            slice.get_fim_topology = Mock(side_effect=RuntimeError("diagnostic error"))
            raise cause
        slice.submit = submit
    provider.prepare = prepare
    with pytest.raises(d.SliceDeploymentError) as caught:
        d.deploy_topology_to_fabric(topology(), "recover", provision_only=True)
    assert caught.value.__cause__ is cause
    assert caught.value.slice_id == "recover-me"
    assert caught.value.diagnostics["collection_errors"]["serialized_topology"] == "diagnostic error"


def test_legacy_wrapper_returns_none_but_strict_propagates(provider, monkeypatch):
    cause = d.SliceDeploymentError("failed", phase="submission")
    monkeypatch.setattr(d, "deploy_topology_to_fabric", Mock(side_effect=cause))
    assert d.deploy_and_configure_slice(topology(), "legacy") is None
    for kwargs in ({"strict": True}, {"provision_only": True}):
        with pytest.raises(d.SliceDeploymentError) as caught:
            d.deploy_and_configure_slice(topology(), "strict", **kwargs)
        assert caught.value is cause


def test_keyword_only_compatibility():
    for function in (d.deploy_topology_to_fabric, d.deploy_and_configure_slice):
        signature = inspect.signature(function)
        for name in ("strict", "provision_only"):
            assert signature.parameters[name].kind == inspect.Parameter.KEYWORD_ONLY
            assert signature.parameters[name].default is False
    assert str(d.SliceDeploymentError("legacy")) == "legacy"


@pytest.mark.parametrize("type", ["L2Bridge", "L2STS", "L2PTP"])
def test_installed_fablib_complete_list_service_types(provider, type):
    model = topology("NIC_ConnectX_6", "network")
    nodes = model.site_topology_nodes.nodes
    nodes["node2"] = nodes["node1"].model_copy(deep=True)
    nodes["node2"].hostname = "vm-b"
    if type != "L2Bridge":
        nodes["node2"].site = "TACC"
    model.site_topology_networks.networks["net1"].type = type
    slice = d.deploy_topology_to_fabric(model, "l2", provision_only=True)
    assert str(slice.topology.network_services["data"].type) == type


def test_l2ptp_type_mutation_fails_clearly(provider, monkeypatch):
    model = topology("NIC_ConnectX_6", "network")
    nodes = model.site_topology_nodes.nodes
    nodes["node2"] = nodes["node1"].model_copy(deep=True)
    nodes["node2"].hostname = "vm-b"
    nodes["node2"].site = "TACC"
    model.site_topology_networks.networks["net1"].type = "L2PTP"
    original = Slice.add_l2network
    def mutating_provider(self, **kwargs):
        network = original(self, **kwargs)
        network.get_fim().set_property("type", ServiceType.L2STS)
        return network
    monkeypatch.setattr(Slice, "add_l2network", mutating_provider)
    with pytest.raises(d.SliceDeploymentError, match="requested L2PTP, actual L2STS") as caught:
        d.deploy_topology_to_fabric(model, "ptp", provision_only=True)
    assert caught.value.phase == "pre_submission_verification"
    assert not provider.created[0].submissions


def test_incremental_l2_type_recalculation_is_observable(provider):
    slice = provider.new_slice("incremental")
    nodes = [slice.add_node(name=name, site=site) for name, site in [("vm-a", "SRI"), ("vm-b", "TACC")]]
    interfaces = [node.add_component(name="nic", model="NIC_ConnectX_6").get_interfaces()[0] for node in nodes]
    network = slice.add_l2network(name="wan", type="L2PTP")
    for interface in interfaces:
        network.add_interface(interface)
    assert str(network.get_type()) == "L2STS"


@pytest.mark.parametrize("type", ["IPv4", "IPv6", "IPv4Ext", "IPv6Ext"])
@pytest.mark.parametrize("extra", [False, True])
def test_fabnet_representations_and_provider_names(provider, monkeypatch, type, extra):
    model = topology()
    model.site_topology_networks.networks["net1"].type = type
    original = Slice.add_l3network
    def normalized(self, **kwargs):
        kwargs["name"] += "-provider"
        result = original(self, **kwargs)
        if extra:
            # The requested logical name is not an alias for an extra service.
            self.topology.add_network_service(name="data", nstype=ServiceType.FABNetv4)
        return result
    monkeypatch.setattr(Slice, "add_l3network", normalized)
    if extra:
        with pytest.raises(d.SliceDeploymentError, match="Unexpected NetworkService allocations: \\['data'\\]"):
            d.deploy_topology_to_fabric(model, "l3-extra", provision_only=True)
        assert not provider.created[0].submissions
        return
    slice = d.deploy_topology_to_fabric(model, "l3", provision_only=True)
    assert str(slice.topology.network_services["data-provider"].type) == r.SERVICE_TYPES[type]
    assert slice.refreshes == ["slice", "slivers", "topology"]
    # Real FIM component-internal services remain legitimate in both snapshots.
    assert any(str(network.type) == "OVS" for network in slice.topology.network_services.values())


@pytest.mark.parametrize("jupyter", [False, True])
def test_real_sdk_submit_skips_jupyter_and_guest_paths(provider, monkeypatch, jupyter):
    """Exercise the installed Slice.submit, with only its external boundary faked."""
    from fabrictestbed.slice_manager import Status
    from fabrictestbed_extensions.fablib.slice import FABRICSSHKey
    monkeypatch.setattr(FABRICSSHKey, "get_key_length", Mock(return_value=2048))
    create = Mock(return_value=(Status.OK, [SimpleNamespace(slice_id="offline-slice-id")]))
    provider.get_manager = lambda: SimpleNamespace(create=create)
    provider.is_jupyter_notebook = lambda: jupyter
    original_submit = OfflineSlice.submit

    def prepare(slice):
        # The offline submission creates provider evidence; real submit then
        # exercises the exact SDK wait/SSH/post-boot/Jupyter branching.
        def submit(**kwargs):
            original_submit(slice, **kwargs)
            return Slice.submit(slice, **kwargs)
        slice.submit = submit
        slice._is_modify = lambda: False
        slice.get_slice_public_key = Mock(return_value="offline-public-key")
        slice.update = Mock()
        slice.wait = Mock()
        slice.is_advanced_allocation = lambda: False
    provider.prepare = prepare
    forbidden = forbid_guest(monkeypatch)
    slice = d.deploy_topology_to_fabric(topology(), "sdk", provision_only=True)
    create.assert_called_once()
    slice.get_slice_public_key.assert_called_once()
    slice.wait.assert_called_once()
    for operation in (forbidden, slice.wait_ssh, slice.wait_jupyter, slice.post_boot_config):
        operation.assert_not_called()
