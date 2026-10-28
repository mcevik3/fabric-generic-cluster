"""Provider-only checks for the deployment path; no guest or display APIs.

The manifest is built from SiteTopology, then records the selected provider
interfaces exactly once. Refreshed FIM objects, not FABlib wrapper caches, are
used to verify the submitted request.
"""

from collections import Counter

from fabrictestbed_extensions.fablib.component import Component
from fim.graph.abc_property_graph import ABCPropertyGraph
from fim.user.node import Node as FimNode
from fim.user.component import Component as FimComponent
from fim.user.network_service import NetworkService as FimNetworkService


SERVICE_TYPES = {
    "L2Bridge": "L2Bridge", "L2STS": "L2STS", "L2PTP": "L2PTP",
    "IPv4": "FABNetv4", "IPv6": "FABNetv6",
    "IPv4Ext": "FABNetv4Ext", "IPv6Ext": "FABNetv6Ext",
}
FAMILIES = {
    "gpu": {"GPU"}, "dpu": {"SmartNIC"}, "fpga": {"FPGA"},
    "nvme": {"NVME"}, "network": {"SharedNIC", "SmartNIC"},
}


def _model_key(value):
    return str(value).replace("-", "_").replace(" ", "_")


def _identity(obj):
    name, node_id = obj.name, obj.node_id
    if not name or not node_id:
        raise ValueError("Missing provider name or FIM identity")
    return {"name": name, "node_id": node_id}


def _token(identity):
    return identity["name"], identity["node_id"]


def _unique(values, label):
    duplicates = [value for value, count in Counter(values).items() if count > 1]
    if duplicates:
        raise ValueError(f"Duplicate {label}: {duplicates}")
    if any(not value for value in values):
        raise ValueError(f"Empty {label}")


def requested_manifest(topology):
    """Validate requested identities before any slice construction."""
    nodes = list(topology.site_topology_nodes.iter_nodes())
    networks = list(topology.site_topology_networks.iter_networks())
    _unique([node.hostname for node in nodes], "node identity")
    _unique([net.name for net in networks], "NetworkService name")
    manifest = {"nodes": {}, "networks": {}, "facilities": {}}
    for net in networks:
        if net.type not in SERVICE_TYPES:
            raise ValueError(f"Unsupported NetworkService type: {net.name}: {net.type}")
        manifest["networks"][net.name] = {
            "type": net.type, "provider_type": SERVICE_TYPES[net.type],
            "provider_name": net.name, "members": [],
        }
    for node in nodes:
        components = {}
        names = [c.name for family in FAMILIES for c in getattr(node.pci, family).values()]
        names += [v.name for v in node.persistent_storage.volume.values()]
        _unique(names, f"component identity on {node.hostname}")
        for family, allowed in FAMILIES.items():
            for component in getattr(node.pci, family).values():
                model = Component.component_model_map.get(component.model)
                model_name = getattr(model, "name", "")
                if model_name.split("_", 1)[0] not in allowed:
                    raise ValueError(
                        f"Invalid component family/model: {node.hostname}."
                        f"{component.name}: {family}/{component.model}"
                    )
                interfaces = []
                for logical_name, iface in getattr(component, "interfaces", {}).items():
                    if iface.binding and iface.binding not in manifest["networks"]:
                        raise ValueError(f"Unknown binding {iface.binding!r} on "
                                         f"{node.hostname}.{component.name}.{logical_name}")
                    interfaces.append({"name": logical_name, "binding": iface.binding})
                components[component.name] = {
                    "family": family, "model": component.model,
                    "model_key": model_name,
                    "provider_name": f"{node.hostname}-{component.name}",
                    "interfaces": interfaces,
                }
        for volume in node.persistent_storage.volume.values():
            components[volume.name] = {
                "family": "storage", "model": "Storage", "model_key": None,
                "provider_name": volume.name, "interfaces": [],
            }
        manifest["nodes"][node.hostname] = {"components": components}
    if topology.has_facility_ports():
        ports = list(topology.site_topology_facility_ports.facility_ports.values())
        _unique([p.name for p in ports] + [n.hostname for n in nodes], "node/facility identity")
        for port in ports:
            if port.binding not in manifest["networks"]:
                raise ValueError(f"Unknown binding {port.binding!r} on facility {port.name}")
            manifest["facilities"][port.name] = {"binding": port.binding}
    return manifest


def resolve_interfaces(slice, manifest, facility_ports):
    """Keep existing insertion-order ifaceN selection, scoped to each allocation."""
    groups = {name: [] for name in manifest["networks"]}
    selected = []

    def bind(iface, request):
        identity = _identity(iface.get_fim_interface())
        request["provider_interface"] = identity
        selected.append(_token(identity))
        if request["binding"]:
            net = request["binding"]
            groups[net].append(iface)
            manifest["networks"][net]["members"].append(identity)

    for hostname, node in manifest["nodes"].items():
        fab_node = slice.get_node(name=hostname)
        if fab_node is None:
            raise ValueError(f"Missing provider node: {hostname}")
        for name, component in node["components"].items():
            fab_component = fab_node.get_component(name=name)
            if fab_component is None:
                raise ValueError(f"Missing provider component: {hostname}.{name}")
            if fab_component.get_name() != component["provider_name"]:
                raise ValueError(f"Wrong component identity: {hostname}.{name}")
            component["provider_identity"] = _identity(fab_component.get_fim_component())
            interfaces = list(fab_component.get_interfaces())
            if len(interfaces) < len(component["interfaces"]):
                raise ValueError(f"Missing provider interfaces: {hostname}.{name}: "
                                 f"requested {len(component['interfaces'])}, got {len(interfaces)}")
            for iface, request in zip(interfaces, component["interfaces"]):
                bind(iface, request)
    for name, port in manifest["facilities"].items():
        interfaces = list(facility_ports[name].get_interfaces())
        if not interfaces:
            raise ValueError(f"Missing provider interfaces: facility {name}")
        bind(interfaces[0], port)
    _unique(selected, "selected interface identity (incompatible or duplicate bindings)")
    return groups


def _reservation(obj):
    info = obj.reservation_info
    return {
        "reservation_id": getattr(info, "reservation_id", None),
        "state": str(getattr(info, "reservation_state", None)),
        "notice": getattr(info, "error_message", None),
    }


def provider_snapshot(slice):
    """Read raw FIM membership, including service ports FABlib cannot resolve."""
    topology = slice.get_fim_topology()
    graph = topology.graph_model

    def objects(ids, cls):
        # Name-keyed FIM dictionaries can hide duplicate graph allocations.
        # Enumerate graph IDs before constructing read-only FIM views.
        for node_id in ids:
            _, properties = graph.get_node_properties(node_id=node_id)
            yield cls(name=properties[ABCPropertyGraph.PROP_NAME],
                      node_id=node_id, topo=topology)

    result = {"nodes": [], "networks": []}
    for node in objects(graph.get_all_network_nodes(), FimNode):
        item = {**_identity(node), **_reservation(node), "components": []}
        for component in objects(
            graph.get_all_network_node_components(parent_node_id=node.node_id), FimComponent
        ):
            item["components"].append({
                **_identity(component), "type": str(component.type),
                "model": str(component.model),
                "interfaces": [_identity(i) for i in component.interface_list],
            })
        # Facilities have interfaces directly on the node.
        item["interfaces"] = [_identity(i) for i in node.interface_list]
        result["nodes"].append(item)
    for network in objects(graph.get_all_network_service_nodes(), FimNetworkService):
        item = {**_identity(network), **_reservation(network),
                "type": str(network.type), "members": []}
        for interface in network.interface_list:
            item["members"].append({
                "service_interface": _identity(interface),
                "peers": [_identity(peer) for peer in (interface.get_peers() or [])],
            })
        result["networks"].append(item)
    return result


def verify(slice, manifest, diagnostics, *, allocated=False):
    """Verify one raw snapshot, failing closed on absent or ambiguous evidence."""
    actual = provider_snapshot(slice)
    diagnostics["actual"] = actual
    errors = []
    diagnostics["mismatches"] = errors

    def one(items, name, kind):
        matches = [item for item in items if item["name"] == name]
        if len(matches) != 1:
            errors.append(f"Expected one {kind} {name!r}; found {len(matches)}")
            return None
        return matches[0]

    def unique(items, kind):
        for field in ("name", "node_id"):
            duplicates = [v for v, count in Counter(i[field] for i in items).items() if count > 1]
            if duplicates:
                errors.append(f"Duplicate {kind} {field}: {duplicates}")

    slivers = []
    if allocated:
        diagnostics["slice_state"] = slice.get_state()
        if diagnostics["slice_state"] not in ("StableOK", "ModifyOK"):
            errors.append(f"Unsuccessful slice state: {diagnostics['slice_state']}")
        slivers = [{"name": s.name, "reservation_id": s.sliver_id,
                    "state": str(s.state), "notice": getattr(s, "notice", None)}
                   for s in slice.get_slivers()]
        diagnostics["slivers"] = slivers
        ids = [s["reservation_id"] for s in slivers]
        if len(set(ids)) != len(ids):
            errors.append("Duplicate provider sliver identities")

    def active(item, kind):
        if not allocated:
            return
        reservation = item["reservation_id"]
        if item["state"] != "Active" or not reservation:
            errors.append(f"{kind} {item['name']}: expected Active reservation; "
                          f"got {item['state']} ({reservation})")
        evidence = [s for s in slivers if s["reservation_id"] == reservation]
        if (len(evidence) != 1 or evidence[0]["state"] != "Active"
                or evidence[0]["name"] != item["name"]):
            errors.append(f"{kind} {item['name']}: missing successful allocation evidence")

    unique(actual["nodes"], "node")
    unique(actual["networks"], "NetworkService")
    # FIM also lists internal services owned by nodes/components (e.g. NIC OVS
    # services). Exclude these by graph ownership, never by type or name prefix.
    graph = slice.get_fim_topology().graph_model
    internal_services = set()
    for node in actual["nodes"]:
        for owner in [node, *node["components"]]:
            internal_services.update(
                graph.get_all_network_node_or_component_nss(parent_node_id=owner["node_id"])
            )
    expected_services = {network["provider_name"] for network in manifest["networks"].values()}
    provider_services = {
        network["name"] for network in actual["networks"]
        if network["node_id"] not in internal_services
    }
    extra_services = provider_services - expected_services
    if extra_services:
        errors.append(f"Unexpected NetworkService allocations: {sorted(extra_services)}")
    expected_nodes = set(manifest["nodes"]) | set(manifest["facilities"])
    extra_nodes = {node["name"] for node in actual["nodes"]} - expected_nodes
    if extra_nodes:
        errors.append(f"Unexpected node allocations: {sorted(extra_nodes)}")
    component_ids = [c["node_id"] for n in actual["nodes"] for c in n["components"]]
    if len(set(component_ids)) != len(component_ids):
        errors.append("Duplicate component allocation identity across nodes")
    for hostname, expected in manifest["nodes"].items():
        node = one(actual["nodes"], hostname, "node")
        if node is None:
            continue
        active(node, "Node")
        unique(node["components"], f"component on {hostname}")
        expected_names = {c["provider_name"] for c in expected["components"].values()}
        extras = {c["name"] for c in node["components"]} - expected_names
        if extras:
            errors.append(f"Unexpected component allocations on {hostname}: {sorted(extras)}")
        for component in expected["components"].values():
            found = one(node["components"], component["provider_name"], "component")
            if found is None:
                continue
            if any(found[k] != v for k, v in component["provider_identity"].items()):
                errors.append(f"Changed component identity: {found['name']}")
            key = _model_key(f"{found['type']}_{found['model']}")
            if (component["model_key"] is not None and key != component["model_key"]) or (
                component["family"] == "storage" and found["type"] != "Storage"
            ):
                errors.append(f"Wrong component model: {found['name']}: requested "
                              f"{component['model']}, actual {found['type']}/{found['model']}")
            unique(found["interfaces"], f"interface on {found['name']}")
            for interface in component["interfaces"]:
                selected = interface["provider_interface"]
                if sum(i == selected for i in found["interfaces"]) != 1:
                    errors.append(f"Missing selected interface on {found['name']}: {selected}")
    for name, port in manifest["facilities"].items():
        node = one(actual["nodes"], name, "facility")
        if node is not None:
            active(node, "Facility")
            if port["provider_interface"] not in node["interfaces"]:
                errors.append(f"Missing selected facility interface: {name}")
    for name, network in manifest["networks"].items():
        found = one(actual["networks"], network["provider_name"], "NetworkService")
        if found is None:
            continue
        active(found, "NetworkService")
        if SERVICE_TYPES.get(found["type"], found["type"]) != network["provider_type"]:
            errors.append(f"Incorrect service type for {name}: requested {network['type']}, "
                          f"actual {found['type']}; installed provider did not preserve requested type")
        members = []
        for member in found["members"]:
            if len(member["peers"]) != 1:
                errors.append(f"Unresolved service member in {name}: {member}")
            members.extend(_token(peer) for peer in member["peers"])
        expected_members = Counter(_token(i) for i in network["members"])
        actual_members = Counter(members)
        if actual_members != expected_members:
            errors.append(f"Membership mismatch for {name}: missing "
                          f"{list((expected_members - actual_members).elements())}; extra "
                          f"{list((actual_members - expected_members).elements())}")
    if errors:
        raise ValueError("Topology verification failed: " + "; ".join(errors))


def refresh_provider(slice):
    """Unlike Slice.update(), these calls propagate provider refresh errors."""
    if not slice.get_slice_id():
        raise ValueError("Missing slice ID after submission")
    slice.update_slice()
    if slice.get_state() is None:
        raise ValueError("Missing refreshed slice state")
    slice.update_slivers()
    before = slice.get_fim_topology()
    slice.update_topology()
    refreshed = slice.get_fim_topology()
    if refreshed is None:
        raise ValueError("Missing refreshed provider topology")
    if refreshed is before:
        raise ValueError("Provider topology refresh did not replace the cached request")


def failure_context(slice, diagnostics):
    """Best-effort diagnostics must never replace the deployment exception."""
    context = {"slice": slice, "diagnostics": diagnostics}
    if slice is None:
        return context
    probes = {
        "slice_id": lambda: slice.get_slice_id(),
        "slice_state": lambda: slice.get_state(),
        "actual_at_failure": lambda: provider_snapshot(slice),
        "serialized_topology": lambda: slice.get_fim_topology().serialize(),
        "provider_notice": lambda: getattr(getattr(slice, "sm_slice", None), "notice", None),
        "slivers_at_failure": lambda: [
            {"name": s.name, "reservation_id": s.sliver_id,
             "state": str(s.state), "notice": getattr(s, "notice", None)}
            for s in getattr(slice, "slivers", [])
        ],
    }
    for key, probe in probes.items():
        try:
            value = probe()
            if key == "slice_id":
                context[key] = value
            else:
                diagnostics[key] = value
        except Exception as error:
            diagnostics.setdefault("collection_errors", {})[key] = str(error)
    return context
