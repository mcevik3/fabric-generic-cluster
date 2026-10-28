These offline deployment fixtures are rendered copies of the approved C4 baseline
scenarios from the read-only `infrastructure-model` reference:

- `fabric-dpu-fabnet-ipv4-rendered.yaml`: `tests/fixtures/fabric-dpu-fabnet-ipv4.yaml`
- `fabric-fpga-l2bridge-rendered.yaml`: `tests/fixtures/fabric-fpga-l2bridge.yaml`

Source revision: `aeb54aa4b98757f7b7783dfca18588e524ff2215`.
Rendering used its existing `FabricAdapterConfig` from `adapter-configs/fabric.yaml`
and `render_fabric()` with no adapter or schema changes. Tests load the copies here
as `SiteTopology`; they do not import or require the reference repository.

The deployment tests inject an offline provider, keep a separate serialized and
reloaded FIM allocation graph, and prohibit socket connections. No live acceptance
test or resource allocation is performed by this suite.
