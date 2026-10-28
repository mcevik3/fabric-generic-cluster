# fabric-generic-cluster

A comprehensive, type-safe Python framework for managing FABRIC testbed slices with support for complex network topologies, DPU interfaces, multi-OS configurations, and various hardware components.

[![PyPI version](https://badge.fury.io/py/fabric-generic-cluster.svg)](https://badge.fury.io/py/fabric-generic-cluster)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![Pydantic V2](https://img.shields.io/badge/pydantic-v2-orange.svg)](https://docs.pydantic.dev/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## 🌟 Features

### Core Capabilities
- ✅ **Type-Safe Data Models** - Pydantic-based topology definitions with automatic validation
- ✅ **DPU Interface Support** - Full support for DPU network interfaces alongside traditional NICs
- ✅ **Multi-OS Support** - Automatic detection and configuration for Rocky Linux, Ubuntu, and Debian
- ✅ **Hardware Components** - Full support for GPUs, FPGAs, DPUs, NVMe, and custom NICs
- ✅ **Network Management** - L2/L3 network configuration with IPv4/IPv6 support
- ✅ **SSH Automation** - Passwordless SSH setup across all nodes
- ✅ **Visualization** - Multiple output formats (text, ASCII, graphs, tables)
- ✅ **Easy Installation** - Available on PyPI via `pip install`
- ✅ **Modular Design** - Separated concerns for better maintainability

### Hardware Support
- **GPUs** - NVIDIA RTX series, Tesla T4, A30, A40
- **FPGAs** - Xilinx Alveo U280, U50, U250
- **DPUs** - ConnectX-7 100G/400G Data Processing Units with network interfaces
- **NVMe** - Intel P4510, P4610 NVMe storage
- **NICs** - Basic, ConnectX-5, ConnectX-6, SharedNICs, SmartNICs
- **Persistent Storage** - Volume management

## 📋 Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [Package Structure](#package-structure)
- [Usage Examples](#usage-examples)
- [API Reference](#api-reference)
- [Command-Line Tools](#command-line-tools)
- [Development](#development)
- [Documentation](#documentation)
- [Contributing](#contributing)

## 🚀 Installation

### From PyPI (Recommended)

```bash
pip install fabric-generic-cluster
```

### From Source

```bash
git clone https://github.com/mcevik0/fabric-generic-cluster.git
cd fabric-generic-cluster
pip install -e .
```

### Prerequisites

- Python 3.9 or higher
- Access to FABRIC testbed
- `fabrictestbed-extensions>=1.9.0` (installed automatically)

### Verify Installation

```python
import fabric_generic_cluster
print(fabric_generic_cluster.__version__)
```

## 🎯 Quick Start

### Option 1: Python Script

```python
from fabric_generic_cluster import (
    load_topology_from_yaml_file,
    deploy_topology_to_fabric,
    configure_l3_networks,
    configure_node_interfaces,
    setup_passwordless_ssh,
)

# Load topology
topology = load_topology_from_yaml_file("topology.yaml")

# Deploy to FABRIC
slice = deploy_topology_to_fabric(topology, "my-cluster")

# Configure networks (if using L3 networks)
configure_l3_networks(slice, topology)

# Configure interfaces
configure_node_interfaces(slice, topology)

# Setup SSH
setup_passwordless_ssh(slice)

print("✅ Cluster deployed and configured!")
```

### Option 2: Using the Example Script

```bash
# Clone the repository for examples
git clone https://github.com/mcevik0/fabric-generic-cluster.git
cd fabric-generic-cluster

# Run the complete deployment example
python examples/complete-deployment-example.py \
    --yaml path/to/topology.yaml \
    --slice-name my-test-slice
```

### Option 3: Jupyter Notebooks

For interactive workflows, check out the [fabric-generic-cluster-notebooks](https://github.com/mcevik0/fabric-generic-cluster-notebooks) repository:

```bash
git clone https://github.com/mcevik0/fabric-generic-cluster-notebooks.git
cd fabric-generic-cluster-notebooks
jupyter notebook
```

## 📦 Package Structure

```
fabric-generic-cluster/
├── fabric_generic_cluster/          # Main package
│   ├── __init__.py                  # Package exports
│   ├── models.py                    # Pydantic models for topology
│   ├── deployment.py                # Slice deployment functions
│   ├── network_config.py            # Network configuration
│   ├── ssh_setup.py                 # SSH management
│   ├── topology_viewer.py           # Visualization tools
│   ├── builder_compat.py            # Backward compatibility
│   └── tools/                       # Command-line tools
│       ├── __init__.py
│       └── topology_summary.py      # Topology summary generator
│
├── examples/                        # Usage examples
│   └── complete-deployment-example.py
│
├── tests/                          # Test suite
│   ├── test-dpu-support.py
│   └── test-fpga-support.py
│
├── pyproject.toml                  # Package metadata
├── setup.py                        # Setup configuration
├── MANIFEST.in                     # Package data
├── LICENSE                         # MIT License
└── README.md                       # This file
```

## 📚 Usage Examples

### Example 1: Load and Explore Topology

```python
from fabric_generic_cluster import (
    load_topology_from_yaml_file,
    print_topology_summary,
    draw_topology_graph,
)

# Load topology
topology = load_topology_from_yaml_file("topology.yaml")

# Print summary
print_topology_summary(topology)

# Create visualization
draw_topology_graph(topology, show_ip=True, save_path="topology.png")
```

### Example 2: Deploy Multi-Site Cluster

```python
from fabric_generic_cluster import (
    load_topology_from_yaml_file,
    deploy_topology_to_fabric,
    configure_node_interfaces,
    verify_node_interfaces,
)

# Load topology with nodes at multiple sites
topology = load_topology_from_yaml_file("multi-site-topology.yaml")

# Deploy
slice = deploy_topology_to_fabric(topology, "multi-site-cluster")

# Configure all nodes
configure_node_interfaces(slice, topology)

# Verify configuration
verify_node_interfaces(slice, topology)
```

### Example 3: Access Type-Safe Data

```python
from fabric_generic_cluster import load_topology_from_yaml_file

topology = load_topology_from_yaml_file("topology.yaml")

# Get specific node
node = topology.get_node_by_hostname("node-1")

print(f"Node: {node.hostname}")
print(f"Site: {node.site}")
print(f"CPU: {node.capacity.cpu} cores")
print(f"RAM: {node.capacity.ram} GB")

# Check hardware components
if node.pci.dpu:
    print(f"DPUs: {len(node.pci.dpu)}")
    for dpu_name, dpu in node.pci.dpu.items():
        print(f"  - {dpu_name}: {dpu.model}")
        print(f"    Interfaces: {len(dpu.interfaces)}")

if node.pci.fpga:
    print(f"FPGAs: {len(node.pci.fpga)}")
    for fpga_name, fpga in node.pci.fpga.items():
        print(f"  - {fpga_name}: {fpga.model}")

# Get all interfaces (NIC + DPU)
all_interfaces = node.get_all_interfaces()
print(f"\nTotal interfaces: {len(all_interfaces)}")

for device_name, iface_name, iface in all_interfaces:
    device_type = "DPU" if device_name.startswith("dpu") else "NIC"
    print(f"{device_type} {device_name}.{iface_name}: {iface.binding}")
```

### Example 4: Test Network Connectivity

```python
from fabric_generic_cluster import (
    get_slice,
    load_topology_from_yaml_file,
    ping_network_from_node,
    verify_ssh_access,
)

# Get existing slice
slice = get_slice("my-cluster")
topology = load_topology_from_yaml_file("topology.yaml")

# Test ping connectivity
ping_results = ping_network_from_node(
    slice, 
    topology, 
    source_hostname="node-1", 
    network_name="network1",
    count=3
)

if all(ping_results.values()):
    print("✅ All ping tests passed!")

# Test SSH access
ssh_results = verify_ssh_access(
    slice,
    topology,
    source_hostname="node-1",
    network_name="network1"
)

if all(ssh_results.values()):
    print("✅ All SSH connections successful!")
```

### Example 5: Using Module-Style Imports

For compatibility with existing code:

```python
from fabric_generic_cluster import deployment as sd
from fabric_generic_cluster import network_config as snc
from fabric_generic_cluster import ssh_setup as ssh
from fabric_generic_cluster import load_topology_from_yaml_file

# Load topology
topology = load_topology_from_yaml_file("topology.yaml")

# Deploy
slice = sd.deploy_topology_to_fabric(topology, "my-slice")

# Configure
snc.configure_node_interfaces(slice, topology)
ssh.setup_passwordless_ssh(slice)
```

## 🔧 API Reference

### Models and Loaders

```python
from fabric_generic_cluster import (
    SiteTopology,              # Main topology model
    Node,                      # Node model
    Network,                   # Network model
    load_topology_from_yaml_file,   # Load from YAML file
    load_topology_from_dict,        # Load from dictionary
)
```

### Deployment Functions

```python
from fabric_generic_cluster import (
    deploy_topology_to_fabric,   # Deploy slice to FABRIC
    configure_l3_networks,        # Configure L3 networks
    get_slice,                    # Get existing slice
    delete_slice,                 # Delete slice
    check_slices,                 # List all slices
)

# Usage
slice = deploy_topology_to_fabric(topology, "slice-name")
configure_l3_networks(slice, topology)
```

Both deployment entry points accept optional keyword-only mode flags:

```python
deploy_topology_to_fabric(
    topology, slice_name, use_timestamp=False,
    *, provision_only=False, strict=False,
)
deploy_and_configure_slice(
    topology, slice_name, configure_selinux=True,
    setup_ansible=False, use_timestamp=False,
    *, provision_only=False, strict=False,
)
```

Existing positional arguments and defaults are unchanged.

| Mode | Topology verification | Guest behavior |
| --- | --- | --- |
| Default | Existing best-effort construction | Existing FABlib post-boot/SSH behavior; the all-in-one wrapper also configures guests |
| `strict=True` | Required before and after submission | Existing guest workflow remains enabled |
| `provision_only=True` | Required; implies `strict=True` | No guest commands, interface discovery, IP/routes, persistent networking, public routing, post-boot command registration, DPU configuration, FPGA programming, or SSH waiting |

For example, provision an adapter-rendered topology for provider inspection:

```python
from fabric_generic_cluster import load_topology_from_yaml_file
from fabric_generic_cluster.deployment import (
    deploy_and_configure_slice, SliceDeploymentError,
)

topology = load_topology_from_yaml_file("rendered-topology.yaml")
try:
    slice = deploy_and_configure_slice(
        topology, "hardware-check", provision_only=True,
    )
except SliceDeploymentError as error:
    print(error.phase, error.slice_name, error.slice_id)
    diagnostics = error.diagnostics
    partial_slice = error.slice  # Retained for inspection/recovery, if created.
    raise
```

Provisioning-only calls `slice.submit(wait=True, progress=False,
post_boot_config=False, wait_ssh=False)`. Authentication and provider resource-state
waiting remain enabled. `progress=False` also avoids FABlib's Jupyter display/wait
branch. The all-in-one wrapper returns immediately after verified provisioning;
it does not run its network, SSH, SELinux, or Ansible steps. Guest-dependent
listing/display methods are not used in this mode.

**Strict verification contract.** The parsed `SiteTopology` supplies node
hostnames, component family/name/model, requested interface counts, service
names/types, and bindings. Effective names must be unique in their scope.
Two same-model devices with different names are separate allocations. Every
requested interface must resolve within its component, and every nonempty binding
must name a requested service. Duplicate or incompatible interface assignments
fail. Services are constructed with all resolved interfaces, then their actual
types and exact membership are checked before submission. Errors that the legacy
construction helpers log and skip become failures in strict mode.

Interface selection retains the existing positional behavior: interface entries
in dictionary order select provider interfaces in their initial enumeration order.
The selected FIM names and IDs are retained across submission and refresh; refreshed
list positions are never used to select replacements. Unbound second ports and
unused provider interfaces are allowed. This does not define physical p1/p2
selectors or imply that `iface1` means physical port 1.

After submission, strict mode explicitly refreshes the slice, slivers, and topology
using `update_slice()`, `update_slivers()`, and `update_topology()`. This avoids
`Slice.update()` suppressing refresh errors. A successful slice state
(`StableOK` or `ModifyOK`), active reservations for required nodes/facilities and
services, and matching active sliver evidence are required. `isStable()` alone is
insufficient: it also accepts failed states. Components are verified under their
parent node reservation; independent component sliver IDs are not required.

Verification reads the refreshed FIM graph by resource ID, including entries that
name-keyed dictionaries could collapse. It checks component identities/models,
selected interfaces, requested services, and exact service membership by following
raw service-port peers. Unresolved members cannot disappear through FABlib wrapper
filtering. IPv4/IPv6 and FABNetv4/FABNetv6 type representations are normalized,
including Ext variants; the service name returned during L3 construction is retained.
Before submission and after refresh, standalone provider NetworkService names must
match those expected provider names. Additional services are rejected. Internal
services owned by nodes/components (such as NIC OVS services) are excluded from
this set comparison by raw graph ownership, not by type or name prefix. Raw
duplicate-service checks still include these internal services.
Missing, stale, ambiguous, failed, or mismatched evidence raises an error.

This is a provider topology/allocation check. It does not establish guest driver
readiness, firmware state, dataplane connectivity, guest IP configuration, or
application readiness. Successful provisioning leaves that work for a later phase.
Strict mode with full configuration retains the existing guest helpers and their
error-handling behavior; it does not add a guest health-verification contract.

**Failure and recovery.** `SliceDeploymentError` remains compatible with ordinary
exception construction and adds optional `phase`, `slice_name`, `slice_id`, `slice`,
and `diagnostics` attributes. Diagnostics contain expected resources, actual raw
provider resources, binding/type mismatches, reservation states/notices, and a
serialized FIM topology where available. Collection errors are recorded without
replacing the original exception, which remains in `__cause__`. No failed slice is
automatically deleted. Inspect the retained slice or retrieve it by its recorded ID
with FABlib before deciding whether to repair or explicitly delete it. A refresh
failure means verification is incomplete; it does not prove allocation failed.
Both strict/provision-only entry points propagate failures. The all-in-one wrapper
retains its legacy `None` return on failures when both flags are false.

**SDK context and limits.** Offline tests use installed FABlib
(`fabrictestbed-extensions`) **1.9.5**, FIM **1.9.0**, and Python **3.13.2**.
They exercise the normal entry point with fake providers and real local FIM/FABlib
construction, including rendered DPU IPv4 and U280 L2Bridge fixtures. Complete-list
construction preserved **L2Bridge, L2STS, and L2PTP** in this installation. Incremental
L2 attachments can cause FABlib to recalculate service types. Complete-list
construction is not assumed to preserve L2PTP on every SDK version: if the installed
provider changes a requested type, strict mode fails with requested/actual types.
There is no model substitution or SDK patch. Tests make no live FABRIC calls and do
not constitute new live acceptance results.

Notebook integration is deferred to C4.2b. Guest DPU discovery fixes, guest network
changes, FPGA programming, physical port selection, multiple FABNet services per VM,
and new scheduling behavior are outside this change. Strict mode accepts component
models mapped by the installed SDK in the supported NIC/DPU/GPU/FPGA/NVMe families;
it does not expand the adapter or schema.

### Network Configuration

```python
from fabric_generic_cluster import (
    configure_node_interfaces,    # Configure all interfaces
    verify_node_interfaces,       # Verify configuration
    ping_network_from_node,       # Test connectivity
    update_hosts_file_on_nodes,   # Update /etc/hosts
)

# Usage
configure_node_interfaces(slice, topology)
verify_node_interfaces(slice, topology)
```

### SSH Setup

```python
from fabric_generic_cluster import (
    setup_passwordless_ssh,       # Complete SSH setup
    verify_ssh_access,            # Verify SSH connectivity
)

# Usage
setup_passwordless_ssh(slice)
results = verify_ssh_access(slice, topology, "node-1", "network1")
```

### Visualization

```python
from fabric_generic_cluster import (
    print_topology_summary,       # Detailed summary
    print_compact_summary,        # Brief summary
    draw_topology_graph,          # Visual graph
)

# Usage
print_topology_summary(topology)
draw_topology_graph(topology, show_ip=True, save_path="topology.png")
```

## 🛠️ Command-Line Tools

### Topology Summary Generator

The package includes a command-line tool for generating topology summaries:

```bash
# Generate summary for a YAML file
fabric-topology-summary input.yaml --output output.yaml

# Just print summary without modifying file
fabric-topology-summary input.yaml --dry-run

# Include ASCII diagram
fabric-topology-summary input.yaml --ascii --output output.yaml
```

This tool is automatically installed when you install the package.

## 💻 Development

### Setting Up Development Environment

```bash
# Clone repository
git clone https://github.com/mcevik0/fabric-generic-cluster.git
cd fabric-generic-cluster

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install in editable mode with dev dependencies
pip install -e ".[dev]"
```

### Running Tests

```bash
# Run test suite
pytest tests/

# Run specific test
python tests/test-dpu-support.py
python tests/test-fpga-support.py
```

### Package Version

The `[project].version` field in `pyproject.toml` is the version source of truth.
`fabric_generic_cluster.__version__` reads the installed distribution metadata
and falls back to `"0+unknown"` in an uninstalled source checkout when metadata
is unavailable. After changing the project version for a release, editable
installs may need their metadata refreshed by reinstalling with
`pip install -e ".[dev]"`.

### Building the Package

```bash
# Install build tools
pip install build twine

# Build distribution
python -m build

# Check package
twine check dist/*

# Test upload to TestPyPI
twine upload --repository testpypi dist/*

# Upload to PyPI
twine upload dist/*
```

### Code Style

```bash
# Format code
black fabric_generic_cluster/

# Check style
flake8 fabric_generic_cluster/
```

## 📖 Documentation

### Comprehensive Guides

- **Getting Started**: See [Quick Start](#quick-start) above
- **Jupyter Notebooks**: [fabric-generic-cluster-notebooks](https://github.com/mcevik0/fabric-generic-cluster-notebooks)
- **YAML Format**: Detailed topology format documentation in notebooks repository
- **API Reference**: See [API Reference](#api-reference) above

### Example Topologies

Example YAML topology files are available in the [notebooks repository](https://github.com/mcevik0/fabric-generic-cluster-notebooks/tree/main/model):

- Basic 2-node cluster
- Multi-site deployment
- Storage cluster with NVMe
- DPU/SmartNIC configurations
- FPGA-enabled topologies
- OpenStack deployment variants

### YAML Topology Format

```yaml
site_topology:
  nodes:
    node-1:
      hostname: node-1
      site: SITE1
      capacity:
        cpu: 8
        ram: 32
        disk: 100
        os: default_rocky_9
      nics:
        nic1:
          interfaces:
            iface1:
              binding: network1
              ipv4_address: 10.0.1.1
              ipv4_netmask: 255.255.255.0
      pci:
        dpu:
          dpu1:
            model: NIC_ConnectX_7_100
            interfaces:
              iface1:
                binding: network1
                ipv4_address: 10.0.1.10

  networks:
    network1:
      name: network1
      type: L2Bridge
      subnet: 10.0.1.0/24
```

## 🤝 Contributing

Contributions are welcome! Here's how you can help:

1. **Report bugs**: Open an issue on GitHub
2. **Suggest features**: Open an issue with your idea
3. **Submit PRs**: Fork, make changes, and submit a pull request

### Contribution Guidelines

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Development Workflow

1. Update code in `fabric_generic_cluster/`
2. Add tests in `tests/`
3. Update documentation
4. Run tests: `pytest tests/`
5. Build package: `python -m build`
6. Test locally: `pip install dist/*.whl`

## 📊 Performance

- **Validation Speed**: ~10ms for typical topology (3-10 nodes)
- **Deployment Time**: Depends on FABRIC (typically 5-10 minutes)
- **Network Config**: ~30 seconds per node
- **SSH Setup**: ~1-2 minutes for 3-node cluster

## 🗺️ Roadmap

- [x] Type-safe Pydantic models
- [x] DPU interface support
- [x] Multi-distro support (Rocky/Ubuntu/Debian)
- [x] L2/L3 network configuration
- [x] Automated SSH setup
- [x] PyPI package distribution
- [ ] Web-based topology editor
- [ ] Ansible playbook integration
- [ ] Monitoring and metrics collection
- [ ] REST API endpoint

## 🐛 Troubleshooting

### Import Issues

**Problem**: `ModuleNotFoundError: No module named 'fabric_generic_cluster'`

**Solution**: 
```bash
pip install fabric-generic-cluster
```

### YAML File Not Found

**Problem**: `FileNotFoundError` when loading topology

**Solution**: Use absolute paths or ensure YAML file is in current directory:
```python
from pathlib import Path

yaml_file = Path("path/to/topology.yaml")
topology = load_topology_from_yaml_file(str(yaml_file))
```

### DPU Interfaces Not Detected

**Problem**: DPU interfaces not showing up

**Solution**: Verify DPU configuration in YAML:
```python
node = topology.get_node_by_hostname("node-1")
print(f"DPUs: {node.pci.dpu}")

# Check all interfaces
all_ifaces = node.get_all_interfaces()
print(f"Total interfaces: {len(all_ifaces)}")
```

### Network Configuration Fails

**Problem**: Interface configuration errors

**Solution**: 
1. Check L3 networks are configured first: `configure_l3_networks(slice, topology)`
2. Ensure nodes are active: `slice.wait()`
3. Verify OS detection: Check logs for supported distro

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Built for the [FABRIC Testbed](https://fabric-testbed.net/)
- Uses [Pydantic](https://docs.pydantic.dev/) for data validation
- Network visualization with [NetworkX](https://networkx.org/) and [Matplotlib](https://matplotlib.org/)

## 📞 Support

- 📧 **Issues**: [GitHub Issues](https://github.com/mcevik0/fabric-generic-cluster/issues)
- 📚 **Documentation**: [fabric-generic-cluster-notebooks](https://github.com/mcevik0/fabric-generic-cluster-notebooks)
- 💬 **FABRIC Slack**: [FABRIC Workspace](https://fabric-testbed.slack.com)
- 🌐 **FABRIC Help**: [FABRIC Learn](https://learn.fabric-testbed.net/)

## 📦 Related Repositories

- **Jupyter Notebooks**: [fabric-generic-cluster-notebooks](https://github.com/mcevik0/fabric-generic-cluster-notebooks) - Example notebooks and topology files
- **PyPI Package**: [fabric-generic-cluster](https://pypi.org/project/fabric-generic-cluster/) - Install via pip

## 🔗 Links

- **GitHub**: https://github.com/mcevik0/fabric-generic-cluster
- **PyPI**: https://pypi.org/project/fabric-generic-cluster/
- **Documentation**: https://github.com/mcevik0/fabric-generic-cluster-notebooks
- **FABRIC Testbed**: https://fabric-testbed.net/

---

**Made with ❤️ for the FABRIC Community**

**Author**: Mert Cevik ([@mcevik0](https://github.com/mcevik0))
