# slice_deployment.py
"""
Core slice deployment functionality.
Handles FABRIC slice creation and resource provisioning.
"""

import logging
from typing import Optional, List
from datetime import datetime

from fabrictestbed_extensions.fablib.fablib import FablibManager as fablib
from .models import SiteTopology, Node, NIC, DPU, FPGA, GPU, NVMe, PersistentVolume, FacilityPort
from . import _realization

logger = logging.getLogger(__name__)


class SliceDeploymentError(Exception):
    """Deployment failure with optional context for inspecting a partial slice."""

    def __init__(self, *args, phase=None, slice_name=None, slice_id=None,
                 slice=None, diagnostics=None):
        super().__init__(*args)
        self.phase = phase
        self.slice_name = slice_name
        self.slice_id = slice_id
        self.slice = slice
        self.diagnostics = diagnostics if diagnostics is not None else {}


def check_or_generate_unique_slice_name(base_name: str, use_timestamp: bool = False) -> str:
    """
    Ensure the slice name is unique by checking existing slices.
    
    Args:
        base_name: Proposed base name for the slice
        use_timestamp: Whether to append a timestamp for uniqueness
        
    Returns:
        A unique slice name
    """
    fab = fablib()
    try:
        existing_names = [slice.get_name() for slice in fab.get_slices()]
        
        if base_name not in existing_names:
            return base_name
        
        if use_timestamp:
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            return f"{base_name}-{timestamp}"
        
        # Use numeric suffix
        i = 1
        new_name = f"{base_name}-{i}"
        while new_name in existing_names:
            i += 1
            new_name = f"{base_name}-{i}"
        return new_name
        
    except Exception as e:
        logger.error(f"Error checking/generating slice name: {e}")
        return base_name


def add_gpus_to_node(fab_node, node: Node, *, strict: bool = False) -> None:
    """
    Add GPU components to a FABRIC node.
    
    Args:
        fab_node: FABRIC node object
        node: Node model with GPU configuration
    """
    for gpu_id, gpu in node.pci.gpu.items():
        try:
            fab_node.add_component(name=gpu.name, model=gpu.model)
            logger.debug(f"Added GPU {gpu.name} ({gpu.model}) to {node.hostname}")
        except Exception as e:
            if strict:
                raise
            logger.warning(f"Failed to add GPU {gpu.name} to {node.hostname}: {e}")


def add_dpus_to_node(fab_node, node: Node, *, strict: bool = False) -> None:
    """
    Add DPU components to a FABRIC node.
    
    Args:
        fab_node: FABRIC node object
        node: Node model with DPU configuration
    """
    for dpu_id, dpu in node.pci.dpu.items():
        try:
            fab_node.add_component(name=dpu.name, model=dpu.model)
            logger.debug(f"Added DPU {dpu.name} ({dpu.model}) to {node.hostname}")
        except Exception as e:
            if strict:
                raise
            logger.warning(f"Failed to add DPU {dpu.name} to {node.hostname}: {e}")


def add_fpgas_to_node(fab_node, node: Node, *, strict: bool = False) -> None:
    """
    Add FPGA components to a FABRIC node.
    
    Args:
        fab_node: FABRIC node object
        node: Node model with FPGA configuration
    """
    for fpga_id, fpga in node.pci.fpga.items():
        try:
            fab_node.add_component(name=fpga.name, model=fpga.model)
            logger.debug(f"Added FPGA {fpga.name} ({fpga.model}) to {node.hostname}")
        except Exception as e:
            if strict:
                raise
            logger.warning(f"Failed to add FPGA {fpga.name} to {node.hostname}: {e}")


def add_nvmes_to_node(fab_node, node: Node, *, strict: bool = False) -> None:
    """
    Add NVMe components to a FABRIC node.
    
    Args:
        fab_node: FABRIC node object
        node: Node model with NVMe configuration
    """
    for nvme_id, nvme in node.pci.nvme.items():
        try:
            fab_node.add_component(name=nvme.name, model=nvme.model)
            logger.debug(f"Added NVMe {nvme.name} ({nvme.model}) to {node.hostname}")
        except Exception as e:
            if strict:
                raise
            logger.warning(f"Failed to add NVMe {nvme.name} to {node.hostname}: {e}")


def add_nics_to_node(fab_node, node: Node, *, strict: bool = False) -> None:
    """
    Add NIC components to a FABRIC node.
    
    Args:
        fab_node: FABRIC node object
        node: Node model with NIC configuration
    """
    for nic_id, nic in node.pci.network.items():
        try:
            fab_node.add_component(name=nic.name, model=nic.model)
            logger.debug(f"Added NIC {nic.name} ({nic.model}) to {node.hostname}")
        except Exception as e:
            if strict:
                raise
            logger.warning(f"Failed to add NIC {nic.name} to {node.hostname}: {e}")


def add_persistent_storage_to_node(fab_node, node: Node, *, strict: bool = False) -> None:
    """
    Add persistent storage volumes to a FABRIC node.
    
    Args:
        fab_node: FABRIC node object
        node: Node model with storage configuration
    """
    for vol_id, volume in node.persistent_storage.volume.items():
        try:
            fab_node.add_storage(name=volume.name)
            logger.debug(f"Added storage {volume.name} ({volume.size}GB) to {node.hostname}")
        except Exception as e:
            if strict:
                raise
            logger.warning(f"Failed to add storage {volume.name} to {node.hostname}: {e}")


def add_postboot_commands_to_node(fab_node, node: Node) -> None:
    """
    Add post-boot commands to a FABRIC node if specified in topology.
    
    Args:
        fab_node: FABRIC node object
        node: Node model with potential postboot commands
    """
    if node.specific.has_postboot_commands():
        try:
            postboot_cmd = node.specific.postboot.strip()
            fab_node.add_post_boot_execute(command=postboot_cmd)
            logger.info(f"Added post-boot command to {node.hostname}")
            logger.debug(f"Post-boot command: {postboot_cmd}")
            print(f"   🔧 Added post-boot commands to {node.hostname}")
        except Exception as e:
            logger.warning(f"Failed to add post-boot command to {node.hostname}: {e}")
            print(f"   ⚠️ Failed to add post-boot command to {node.hostname}: {e}")


def add_facility_ports_to_slice(topology: SiteTopology, slice, *, strict: bool = False) -> dict:
    """
    Add facility ports to the slice.
    
    Args:
        topology: Site topology model
        slice: FABRIC slice object
        
    Returns:
        Dictionary mapping facility port names to FABRIC facility port objects
    """
    facility_port_objects = {}
    
    if not topology.has_facility_ports():
        logger.debug("No facility ports defined in topology")
        return facility_port_objects
    
    logger.info("Adding facility ports to slice")
    print("\n🔌 Adding facility ports...\n")
    
    for fp_id, fp in topology.site_topology_facility_ports.facility_ports.items():
        try:
            logger.info(f"Adding facility port: {fp.name} at {fp.site} (VLAN {fp.vlan})")
            print(f"   🔌 {fp.name} @ {fp.site} - VLAN {fp.vlan} → {fp.binding}")
            
            fab_fp = slice.add_facility_port(
                name=fp.name,
                site=fp.site,
                vlan=str(fp.vlan)
            )
            
            facility_port_objects[fp.name] = fab_fp
            logger.info(f"Successfully added facility port: {fp.name}")
            
        except Exception as e:
            if strict:
                raise
            logger.error(f"Failed to add facility port {fp.name}: {e}")
            print(f"   ❌ Failed to add facility port {fp.name}: {e}")
            continue
    
    return facility_port_objects


def create_and_bind_networks(
    topology: SiteTopology, slice, facility_port_objects: dict = None, *,
    strict: bool = False, _manifest=None, _diagnostics=None,
) -> dict:
    """
    Create FABRIC networks and bind node interfaces and facility ports to them.
    Handles NIC, DPU, FPGA interfaces, and facility ports.
    
    Args:
        topology: Site topology model
        slice: FABRIC slice object
        facility_port_objects: Dictionary of facility port objects (optional)
        
    Returns:
        Dictionary mapping network names to FABRIC network objects
    """
    if facility_port_objects is None:
        facility_port_objects = {}
    
    network_objects = {}

    if strict:
        manifest = _manifest if _manifest is not None else _realization.requested_manifest(topology)
        diagnostics = _diagnostics if _diagnostics is not None else {}
        groups = _realization.resolve_interfaces(slice, manifest, facility_port_objects)
        for name, requested in manifest["networks"].items():
            add_network = slice.add_l2network if requested["type"].startswith("L2") else slice.add_l3network
            network_objects[name] = add_network(
                name=name, type=requested["type"], interfaces=groups[name]
            )
            if network_objects[name] is None:
                raise ValueError(f"Provider did not create NetworkService {name}")
            # FABlib's returned name is authoritative for provider normalization.
            provider_name = network_objects[name].get_name()
            if requested["type"].startswith("L2") and provider_name != name:
                raise ValueError(f"Incorrect NetworkService name: requested {name}, got {provider_name}")
            requested["provider_name"] = provider_name
        _realization._unique(
            [n["provider_name"] for n in manifest["networks"].values()],
            "provider NetworkService name",
        )
        _realization.verify(slice, manifest, diagnostics)
        return network_objects

    # Create networks
    for net_id, network in topology.site_topology_networks.networks.items():
        try:
            # Layer 2 networks
            if network.type in ["L2Bridge", "L2PTP", "L2STS"]:
                net = slice.add_l2network(name=network.name, type=network.type)
                logger.info(f"Created L2 network: {network.name} ({network.type})")
            
            # Layer 3 networks (orchestrator-managed)
            elif network.type in ["IPv4", "IPv6", "IPv4Ext", "IPv6Ext"]:
                net = slice.add_l3network(name=network.name, type=network.type)
                logger.info(f"Created L3 network: {network.name} ({network.type})")
            
            else:
                logger.warning(f"Unsupported network type: {network.type}")
                continue
            
            network_objects[network.name] = net
            
        except Exception as e:
            logger.error(f"Failed to create network {network.name}: {e}")
            continue
    
    # Bind facility port interfaces to networks
    if topology.has_facility_ports():
        logger.info("Binding facility port interfaces to networks")
        
        for fp_id, fp in topology.site_topology_facility_ports.facility_ports.items():
            if fp.name not in facility_port_objects:
                logger.warning(f"Facility port {fp.name} not found in facility_port_objects")
                continue
            
            if fp.binding not in network_objects:
                logger.warning(f"Network '{fp.binding}' not found for facility port {fp.name}")
                continue
            
            try:
                fab_fp = facility_port_objects[fp.name]
                fp_interfaces = fab_fp.get_interfaces()
                
                if fp_interfaces:
                    network_objects[fp.binding].add_interface(fp_interfaces[0])
                    logger.info(f"Connected facility port {fp.name} to network {fp.binding}")
                    print(f"   ✅ Connected facility port {fp.name} to {fp.binding}")
                else:
                    logger.warning(f"No interfaces found for facility port {fp.name}")
                    print(f"   ⚠️ No interfaces found for facility port {fp.name}")
                    
            except Exception as e:
                logger.error(f"Failed to bind facility port {fp.name} to network {fp.binding}: {e}")
                print(f"   ❌ Failed to bind facility port {fp.name}: {e}")
    
    # Bind node NIC interfaces to networks
    for node_id, node in topology.site_topology_nodes.nodes.items():
        try:
            fab_node = slice.get_node(name=node.hostname)
        except Exception as e:
            logger.error(f"Could not retrieve node '{node.hostname}': {e}")
            continue
        
        # Process NICs
        for nic_id, nic in node.pci.network.items():
            try:
                fab_nic = fab_node.get_component(name=nic.name)
                iface_list = fab_nic.get_interfaces()
            except Exception as e:
                logger.error(f"Could not retrieve NIC '{nic.name}' on node '{node.hostname}': {e}")
                continue
            
            for i, (iface_name, iface) in enumerate(nic.interfaces.items()):
                if not iface.binding:
                    continue
                
                if iface.binding not in network_objects:
                    logger.warning(f"Network '{iface.binding}' not found in topology")
                    continue
                
                if i < len(iface_list):
                    network_objects[iface.binding].add_interface(iface_list[i])
                    logger.info(f"Connected {node.hostname}.{nic.name}.{iface_name} to {iface.binding}")
                else:
                    logger.warning(f"Interface index out of range: {node.hostname}.{nic.name}.{iface_name}")
        
        # Process DPUs (same logic as NICs)
        for dpu_id, dpu in node.pci.dpu.items():
            try:
                fab_dpu = fab_node.get_component(name=dpu.name)
                iface_list = fab_dpu.get_interfaces()
            except Exception as e:
                logger.error(f"Could not retrieve DPU '{dpu.name}' on node '{node.hostname}': {e}")
                continue
            
            for i, (iface_name, iface) in enumerate(dpu.interfaces.items()):
                if not iface.binding:
                    continue
                
                if iface.binding not in network_objects:
                    logger.warning(f"Network '{iface.binding}' not found in topology")
                    continue
                
                if i < len(iface_list):
                    network_objects[iface.binding].add_interface(iface_list[i])
                    logger.info(f"Connected {node.hostname}.{dpu.name}.{iface_name} to {iface.binding}")
                else:
                    logger.warning(f"Interface index out of range: {node.hostname}.{dpu.name}.{iface_name}")
        
        # Process FPGAs (same logic as NICs and DPUs)
        for fpga_id, fpga in node.pci.fpga.items():
            try:
                fab_fpga = fab_node.get_component(name=fpga.name)
                iface_list = fab_fpga.get_interfaces()
            except Exception as e:
                logger.error(f"Could not retrieve FPGA '{fpga.name}' on node '{node.hostname}': {e}")
                continue
            
            for i, (iface_name, iface) in enumerate(fpga.interfaces.items()):
                if not iface.binding:
                    continue
                
                if iface.binding not in network_objects:
                    logger.warning(f"Network '{iface.binding}' not found in topology")
                    continue
                
                if i < len(iface_list):
                    network_objects[iface.binding].add_interface(iface_list[i])
                    logger.info(f"Connected {node.hostname}.{fpga.name}.{iface_name} to {iface.binding}")
                else:
                    logger.warning(f"Interface index out of range: {node.hostname}.{fpga.name}.{iface_name}")
    
    return network_objects


def configure_l3_networks(slice, topology: SiteTopology) -> None:
    """
    Configure L3 (IPv4/IPv6) networks after slice submission.
    
    This function:
    1. Gets available IP addresses from the orchestrator-assigned subnet
    2. Assigns IPs to node interfaces (both NIC and DPU interfaces)
    3. Configures routing between L3 networks for each node
    
    NOTE: For IPv4Ext/IPv6Ext networks, call enable_public_routing() separately
    to enable public internet access.
    
    Args:
        slice: FABRIC slice object (must be already submitted)
        topology: Site topology model
        
    Raises:
        SliceDeploymentError: If L3 network configuration fails
    """
    logger.info("Starting L3 network configuration")
    print("\n🌐 Configuring L3 networks (IPv4/IPv6)...\n")
    
    try:
        fab = fablib()
        
        # Store network information for routing configuration
        network_info = {}  # {network_name: {'subnet': subnet, 'gateway': gateway, 'type': type}}
        node_network_mapping = {}  # {node_hostname: [list of connected network names]}
        
        # Process each network
        for network_model in topology.site_topology_networks.iter_networks():
            # Only process L3 networks (IPv4, IPv4Ext, IPv6, IPv6Ext)
            if network_model.type not in ["IPv4", "IPv4Ext", "IPv6", "IPv6Ext"]:
                continue
            
            network_name = network_model.name
            logger.info(f"Configuring L3 network: {network_name} (type: {network_model.type})")
            print(f"🔧 Configuring network: {network_name} ({network_model.type})")
            
            try:
                # Get the network from the slice
                fabric_network = slice.get_network(name=network_name)
                
                # Get available IPs from orchestrator
                available_ips = fabric_network.get_available_ips()
                logger.info(f"Network {network_name} has {len(available_ips)} available IPs")
                print(f"   📋 Available IPs: {len(available_ips)}")
                
                if not available_ips:
                    logger.warning(f"No available IPs for network {network_name}")
                    print(f"   ⚠️ No available IPs for {network_name}")
                    continue
                
                # Get the subnet for this network
                network_subnet = fabric_network.get_subnet()
                network_gateway = fabric_network.get_gateway()
                logger.debug(f"Network {network_name} subnet: {network_subnet}, gateway: {network_gateway}")
                
                # Store network info for routing configuration
                network_info[network_name] = {
                    'subnet': network_subnet,
                    'gateway': network_gateway,
                    'type': network_model.type
                }
                
                # Get all nodes connected to this network
                connected_nodes = topology.get_nodes_on_network(network_name)
                
                # Configure each node's interface
                for node_model in connected_nodes:
                    try:
                        fab_node = slice.get_node(name=node_model.hostname)
                        fab_iface = fab_node.get_interface(network_name=network_name)
                        
                        # Track which networks each node is connected to
                        if node_model.hostname not in node_network_mapping:
                            node_network_mapping[node_model.hostname] = []
                        node_network_mapping[node_model.hostname].append(network_name)
                        
                        # Pop the first available IP
                        if not available_ips:
                            logger.error(f"Ran out of IPs for network {network_name}")
                            print(f"   ❌ No more IPs available for {node_model.hostname}")
                            break
                        
                        node_ip = available_ips.pop(0)
                        
                        # Assign IP to interface
                        fab_iface.ip_addr_add(addr=node_ip, subnet=network_subnet)
                        logger.info(f"Assigned {node_ip} to {node_model.hostname}")
                        print(f"   ✅ {node_model.hostname}: {node_ip}")
                        
                    except Exception as e:
                        logger.error(f"Failed to configure {node_model.hostname} on {network_name}: {e}")
                        print(f"   ❌ Error configuring {node_model.hostname}: {e}")
                        continue
                
            except Exception as e:
                logger.error(f"Failed to configure network {network_name}: {e}")
                print(f"   ❌ Error configuring network: {e}")
                continue
        
        # Configure inter-network routing for each node
        logger.info("Starting inter-network routing configuration")
        print("\n🔀 Configuring inter-network routing...\n")
        
        for node_hostname, connected_networks in node_network_mapping.items():
            try:
                fab_node = slice.get_node(name=node_hostname)
                
                # Get all L3 networks in topology
                all_l3_networks = [net_name for net_name in network_info.keys()]
                
                # Find networks this node is NOT connected to
                other_networks = [net for net in all_l3_networks if net not in connected_networks]
                
                if not other_networks:
                    logger.debug(f"Node {node_hostname} is connected to all L3 networks, no additional routes needed")
                    print(f"ℹ️  {node_hostname}: Connected to all networks, no routes needed")
                    continue
                
                logger.info(f"Configuring routes on {node_hostname}")
                print(f"🔧 Configuring routes on {node_hostname}:")
                
                routes_added = 0
                
                # For each network this node is NOT connected to, add routes via connected networks
                for target_network in other_networks:
                    target_subnet = network_info[target_network]['subnet']
                    target_type = network_info[target_network]['type']
                    
                    # Determine which gateway to use based on IP version compatibility
                    # IPv4 routes use IPv4 gateways, IPv6 routes use IPv6 gateways
                    is_ipv6_target = target_type in ["IPv6", "IPv6Ext"]
                    
                    # Find a suitable gateway from the networks this node IS connected to
                    gateway_found = False
                    for connected_network in connected_networks:
                        connected_type = network_info[connected_network]['type']
                        is_ipv6_connected = connected_type in ["IPv6", "IPv6Ext"]
                        
                        # Match IPv4 with IPv4, IPv6 with IPv6
                        if is_ipv6_target == is_ipv6_connected:
                            gateway = network_info[connected_network]['gateway']
                            
                            try:
                                fab_node.ip_route_add(subnet=target_subnet, gateway=gateway)
                                logger.info(f"  Added route on {node_hostname}: {target_subnet} via {gateway} ({connected_network})")
                                print(f"   ✅ Route: {target_network} ({target_subnet}) via {connected_network} ({gateway})")
                                routes_added += 1
                                gateway_found = True
                                break  # Only add one route per target network
                            except Exception as e:
                                logger.warning(f"  Failed to add route on {node_hostname} for {target_subnet} via {gateway}: {e}")
                                print(f"   ⚠️  Route failed: {target_network} via {gateway}: {e}")
                    
                    if not gateway_found:
                        logger.warning(f"  No suitable gateway found on {node_hostname} for {target_network} ({target_type})")
                        print(f"   ⚠️  No suitable gateway for {target_network} ({target_type})")
                
                if routes_added > 0:
                    logger.info(f"Added {routes_added} routes on {node_hostname}")
                    print(f"   📊 Total routes added: {routes_added}")
                else:
                    logger.info(f"No routes added on {node_hostname}")
                    print(f"   ℹ️  No routes added")
                    
            except Exception as e:
                logger.error(f"Failed to configure routing on {node_hostname}: {e}")
                print(f"❌ Error configuring routing on {node_hostname}: {e}")
                continue
        
        logger.info("L3 network configuration completed")
        print("\n✅ L3 network configuration completed")
        
        # Check if there are any IPv4Ext/IPv6Ext networks
        ext_networks = [name for name, info in network_info.items() 
                       if info['type'] in ["IPv4Ext", "IPv6Ext"]]
        if ext_networks:
            print("\n💡 Note: You have external networks (IPv4Ext/IPv6Ext):")
            for net_name in ext_networks:
                print(f"   - {net_name}")
            print("\n   To enable public internet routing, call:")
            print("   enable_public_routing(slice, topology)\n")
        
    except Exception as e:
        error_msg = f"Failed to configure L3 networks: {e}"
        logger.error(error_msg)
        print(f"❌ {error_msg}")
        raise SliceDeploymentError(error_msg) from e


def enable_public_routing(slice, topology: SiteTopology, networks: List[str] = None) -> None:
    """
    Enable public internet routing for IPv4Ext/IPv6Ext networks.
    
    This should be called AFTER configure_l3_networks() has completed.
    It enables public routing for external network types, making the assigned
    IPs publicly routable on the internet.
    
    Args:
        slice: FABRIC slice object (must have L3 networks already configured)
        topology: Site topology model
        networks: Optional list of specific network names to enable routing for.
                 If None, enables for all IPv4Ext/IPv6Ext networks.
        
    Raises:
        SliceDeploymentError: If public routing configuration fails
    """
    logger.info("Starting public routing configuration")
    print("\n🌍 Enabling public internet routing...\n")
    
    try:
        fab = fablib()
        needs_resubmit = False
        
        # Process each network
        for network_model in topology.site_topology_networks.iter_networks():
            # Only process external network types
            if network_model.type not in ["IPv4Ext", "IPv6Ext"]:
                continue
            
            # If specific networks requested, check if this is one of them
            if networks is not None and network_model.name not in networks:
                continue
            
            network_name = network_model.name
            logger.info(f"Enabling public routing for: {network_name} (type: {network_model.type})")
            print(f"🔧 Enabling public routing for: {network_name} ({network_model.type})")
            
            try:
                # Get the network from the slice
                fabric_network = slice.get_network(name=network_name)
                
                # Get all nodes connected to this network
                connected_nodes = topology.get_nodes_on_network(network_name)
                
                # Collect IPs that need public routing
                public_ips_to_route = []
                
                for node_model in connected_nodes:
                    try:
                        fab_node = slice.get_node(name=node_model.hostname)
                        fab_iface = fab_node.get_interface(network_name=network_name)
                        
                        # Get the assigned IP
                        node_ip = fab_iface.get_ip_addr()
                        if node_ip:
                            public_ips_to_route.append(str(node_ip))
                            logger.info(f"  Will enable routing for {node_model.hostname}: {node_ip}")
                            print(f"   📍 {node_model.hostname}: {node_ip}")
                        
                    except Exception as e:
                        logger.error(f"Failed to get IP for {node_model.hostname} on {network_name}: {e}")
                        print(f"   ⚠️  Could not get IP for {node_model.hostname}: {e}")
                        continue
                
                # Enable public routing for collected IPs
                if public_ips_to_route:
                    logger.info(f"Enabling public routing for {len(public_ips_to_route)} IPs on {network_name}")
                    print(f"   🌐 Enabling routing for {len(public_ips_to_route)} IPs...")
                    
                    try:
                        if network_model.type == "IPv4Ext":
                            fabric_network.make_ip_publicly_routable(ipv4=public_ips_to_route)
                        elif network_model.type == "IPv6Ext":
                            fabric_network.make_ip_publicly_routable(ipv6=public_ips_to_route)
                        
                        logger.info(f"Public routing enabled for {network_name}")
                        print(f"   ✅ Public routing enabled for {network_name}")
                        needs_resubmit = True
                        
                    except Exception as e:
                        logger.error(f"Failed to enable public routing for {network_name}: {e}")
                        print(f"   ❌ Failed to enable public routing: {e}")
                else:
                    logger.warning(f"No IPs found to enable routing for {network_name}")
                    print(f"   ⚠️  No IPs found for {network_name}")
                
            except Exception as e:
                logger.error(f"Failed to process network {network_name}: {e}")
                print(f"   ❌ Error processing network: {e}")
                continue
        
        # Submit changes if any external networks were configured
        if needs_resubmit:
            logger.info("Submitting slice with public routing configuration...")
            print("\n🚀 Submitting public routing configuration...")
            slice.submit()
            logger.info("Public routing configuration submitted successfully")
            print("✅ Public routing configuration submitted\n")
        else:
            logger.info("No public routing changes to submit")
            print("\nℹ️  No public routing changes were made\n")
        
    except Exception as e:
        error_msg = f"Failed to enable public routing: {e}"
        logger.error(error_msg)
        print(f"❌ {error_msg}")
        raise SliceDeploymentError(error_msg) from e


def deploy_topology_to_fabric(
    topology: SiteTopology,
    slice_name: str,
    use_timestamp: bool = False,
    *,
    provision_only: bool = False,
    strict: bool = False,
) -> Optional[object]:
    """
    Create and submit a FABRIC slice from the provided topology.
    
    This function creates the slice infrastructure:
    1. Create nodes with components (NICs, DPUs, GPUs, FPGAs, NVMe)
    2. Apply worker constraints if specified
    3. Add post-boot commands if specified
    4. Add facility ports if defined
    5. Create and bind networks (including facility port connections)
    6. Submit slice
    
    After this, you should call:
    - configure_l3_networks(slice, topology) - for L3 network IP assignment and routing
    - enable_public_routing(slice, topology) - OPTIONAL: for IPv4Ext/IPv6Ext public access
    - configure_node_interfaces(slice, topology) - for persistent network config
    
    Args:
        topology: Site topology model
        slice_name: Proposed name for the slice
        use_timestamp: If True, ensure uniqueness by timestamping
        provision_only: Skip all guest work and SSH waiting; implies strict.
        strict: Verify requested topology before and after provider submission.
        
    Returns:
        The created and submitted FABRIC slice.
        
    Raises:
        SliceDeploymentError: If deployment fails
    """
    strict = strict or provision_only
    slice = None
    unique_slice_name = slice_name
    phase = "preflight"
    diagnostics = {}
    try:
        if strict:
            diagnostics["requested_topology"] = topology.model_dump()
            manifest = _realization.requested_manifest(topology)
            diagnostics["expected"] = manifest
        unique_slice_name = check_or_generate_unique_slice_name(slice_name, use_timestamp)
        phase = "construction"
        fab = fablib()
        slice = fab.new_slice(name=unique_slice_name)
        logger.info(f"Creating slice: {unique_slice_name}")
        print(f"\n🛠️ Creating slice: {unique_slice_name}\n")
        
        # Add nodes
        for node_id, node in topology.site_topology_nodes.nodes.items():
            logger.info(f"Adding node: {node.hostname}")
            
            # Prepare add_node arguments
            add_node_kwargs = {
                'name': node.hostname,
                'cores': node.capacity.cpu,
                'ram': node.capacity.ram,
                'disk': node.capacity.disk,
                'image': node.capacity.os
            }

            if node.site:
                add_node_kwargs['site'] = node.site
            
            
            # Add worker constraint if specified
            if node.has_worker_constraint():
                add_node_kwargs['host'] = node.worker
                logger.info(f"Node {node.hostname} constrained to worker: {node.worker}")
                print(f"   📍 Placing {node.hostname} on worker: {node.worker}")
            
            # Create the node
            fab_node = slice.add_node(**add_node_kwargs)
            
            # Add components
            add_gpus_to_node(fab_node, node, strict=strict)
            add_dpus_to_node(fab_node, node, strict=strict)
            add_fpgas_to_node(fab_node, node, strict=strict)
            add_nvmes_to_node(fab_node, node, strict=strict)
            add_nics_to_node(fab_node, node, strict=strict)
            add_persistent_storage_to_node(fab_node, node, strict=strict)
            
            # Add post-boot commands if specified
            if not provision_only:
                add_postboot_commands_to_node(fab_node, node)
        
        # Add facility ports if defined
        facility_port_objects = add_facility_ports_to_slice(topology, slice, strict=strict)
        
        # Create and bind networks (handles NICs, DPUs, FPGAs, and facility ports)
        phase = "pre_submission_verification" if strict else "construction"
        create_and_bind_networks(
            topology, slice, facility_port_objects, strict=strict,
            _manifest=manifest if strict else None, _diagnostics=diagnostics,
        )
        
        # Submit slice
        logger.info("Submitting slice to FABRIC...")
        print("\n🚀 Submitting slice...")
        phase = "submission"
        if provision_only:
            slice.submit(wait=True, progress=False, post_boot_config=False, wait_ssh=False)
        else:
            slice.submit()
        if strict:
            phase = "provider_refresh"
            _realization.refresh_provider(slice)
            phase = "post_submission_verification"
            _realization.verify(slice, manifest, diagnostics, allocated=True)
        if provision_only:
            print(f"✅ Slice '{unique_slice_name}' provisioned and topology verified")
            return slice
        
        # At the end, update the print statement:
        logger.info(f"Slice '{unique_slice_name}' submitted successfully")
        print(f"✅ Slice '{unique_slice_name}' created successfully")
        print(f"\n💡 Next steps:")
        print(f"   1. Call configure_l3_networks(slice, topology) for L3 IP assignment")
        print(f"   2. [Optional] Call enable_public_routing(slice, topology) for IPv4Ext/IPv6Ext")
        print(f"   3. Call configure_node_interfaces(slice, topology) for persistent config")
    
        return slice       

    except Exception as e:
        error_msg = f"Failed to deploy slice: {e}"
        logger.critical(error_msg)
        print(f"❌ {error_msg}")
        raise SliceDeploymentError(
            error_msg, phase=phase, slice_name=unique_slice_name,
            **_realization.failure_context(slice, diagnostics),
        ) from e


def deploy_and_configure_slice(
    topology: SiteTopology,
    slice_name: str,
    configure_selinux: bool = True,
    setup_ansible: bool = False,
    use_timestamp: bool = False,
    *,
    provision_only: bool = False,
    strict: bool = False,
) -> Optional[object]:
    """
    Complete slice deployment and configuration workflow.
    
    This performs:
    1. Deploy slice infrastructure
    2. Configure L3 networks and routing
    3. Configure persistent network interfaces
    4. Setup passwordless SSH
    5. Configure SELinux (if specified in topology)
    6. Setup Ansible environment (if requested)
    
    Args:
        topology: Site topology model
        slice_name: Name for the slice
        configure_selinux: If True, applies SELinux settings from topology
        setup_ansible: If True, sets up Ansible environment
        use_timestamp: If True, adds timestamp to slice name
        provision_only: Return after verified provisioning; implies strict.
        strict: Verify topology, retaining the normal guest workflow.
        
    Returns:
        FABRIC slice object, or None on legacy (non-strict) failure.

    Raises:
        SliceDeploymentError: On strict/provision-only deployment failure.
    """
    # Import here to avoid circular imports
    from .network_config import configure_node_interfaces
    from .ssh_setup import setup_passwordless_ssh
    from .selinux_management import configure_selinux_from_topology
    from .ansible_setup import setup_ansible_environment

    slice = None
    deployed_name = slice_name
    try:
        # Step 1: Deploy slice
        print("="*70)
        print("STEP 1: Deploying FABRIC Slice")
        print("="*70)
        slice = deploy_topology_to_fabric(
            topology, slice_name, use_timestamp,
            provision_only=provision_only, strict=strict,
        )
        if not slice:
            if strict or provision_only:
                raise SliceDeploymentError("Deployment returned no verified slice")
            return None
        if provision_only:
            return slice
        if strict:
            deployed_name = slice.get_name()
        
        # Step 2: Configure L3 networks
        print("\n" + "="*70)
        print("STEP 2: Configuring L3 Networks")
        print("="*70)
        configure_l3_networks(slice, topology)
        
        # Step 3: Configure persistent network interfaces
        print("\n" + "="*70)
        print("STEP 3: Configuring Network Interfaces")
        print("="*70)
        configure_node_interfaces(slice, topology)
        
        # Step 4: Setup SSH
        print("\n" + "="*70)
        print("STEP 4: Setting up Passwordless SSH")
        print("="*70)
        setup_passwordless_ssh(slice)
        
        # Step 5: Configure SELinux
        if configure_selinux:
            print("\n" + "="*70)
            print("STEP 5: Configuring SELinux")
            print("="*70)
            configure_selinux_from_topology(slice, topology, persistent=True)
        
        # Step 6: Setup Ansible
        if setup_ansible:
            print("\n" + "="*70)
            print("STEP 6: Setting up Ansible Environment")
            print("="*70)
            setup_ansible_environment(slice, topology)
        
        print("\n" + "="*70)
        print("✅ DEPLOYMENT COMPLETE")
        print("="*70)
        print(f"\nSlice '{slice.get_name()}' is ready!")
        
        return slice
        
    except Exception as e:
        if strict or provision_only:
            if isinstance(e, SliceDeploymentError) and slice is None:
                raise
            raise SliceDeploymentError(
                f"Slice configuration failed: {e}", phase="guest_configuration",
                slice_name=deployed_name,
                **_realization.failure_context(slice, {}),
            ) from e
        logger.error(f"Deployment failed: {e}")
        print(f"\n❌ Deployment failed: {e}")
        import traceback
        traceback.print_exc()
        return None


def get_slice(slice_name: str) -> Optional[object]:
    """
    Retrieve an existing FABRIC slice by name.
    
    Args:
        slice_name: Name of the slice to retrieve
        
    Returns:
        FABRIC slice object, or None if not found
    """
    try:
        fab = fablib()
        logger.info(f"Retrieving slice: {slice_name}")
        print(f"\n🚀 Getting slice object for: '{slice_name}'")
        
        slice = fab.get_slice(name=slice_name)
        print(f"✅ Slice retrieved successfully")
        return slice
        
    except Exception as e:
        logger.error(f"Failed to retrieve slice '{slice_name}': {e}")
        print(f"❌ Exception: {e}")
        return None


def delete_slice(slice_name: str) -> bool:
    """
    Delete a FABRIC slice.
    
    Args:
        slice_name: Name of the slice to delete
        
    Returns:
        True if deletion successful, False otherwise
    """
    try:
        fab = fablib()
        slice = fab.get_slice(name=slice_name)
        
        logger.info(f"Deleting slice: {slice_name}")
        print(f"\n🚀 Deleting slice '{slice_name}'")
        
        slice.delete()
        logger.info(f"Slice '{slice_name}' deleted successfully")
        print(f"✅ Slice '{slice_name}' deleted")
        return True
        
    except Exception as e:
        logger.error(f"Failed to delete slice '{slice_name}': {e}")
        print(f"❌ Slice deletion failed: {e}")
        return False


def check_slices() -> None:
    """Display all existing slices."""
    try:
        fab = fablib()
        print(f"\n🚀 Checking existing slices...")
        
        slices = list(fab.get_slices())
        if not slices:
            print("No slices found")
            return
        
        for slice in slices:
            print(f"✅ {slice}")
            
    except Exception as e:
        logger.error(f"Failed to check slices: {e}")
        print(f"❌ Exception: {e}")


def show_config() -> None:
    """Display current Fablib configuration."""
    try:
        fab = fablib()
        print(f"\n🚀 Fablib Configuration:")
        fab.show_config()
        print(f"✅ Configuration displayed")
        
    except Exception as e:
        logger.error(f"Failed to show config: {e}")
        print(f"❌ Exception: {e}")
