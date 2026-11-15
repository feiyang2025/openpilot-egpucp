# 相机标定统一（CameraCalibSet）P0–P2 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把前视双路相机内参/外参收敛到 `CameraCalibSet.cams[CamId]` 单一数据源：P0 建对象+序列化+唯一写入者，P1 全部消费端切到 helper，P2 camcalibd 上线并收紧帧对窗口。

**Architecture:** 新增 `common/transformations/camera_calib.py` 提供数据模型与派生矩阵，capnp `LiveCalibrationData` 追加 @13/@14/@15（Python 侧导入即生效，C++ 需 scons 重建）；`calibrationd` 是唯一写入者，把新老字段同一次 `to_bytes()` 落进 `Params["CalibrationParams"]`；`cameraCalibCandidate` 挂 fork-safe 槽（`custom.capnp` 的 `CustomReserved4`）；`camcalibd` 由 `intrinsic_calibd.py` 迁移，发布候选 + `cameraSyncState`。

**Tech Stack:** Python 3（capnp 动态解析, no codegen for python）、C++（scons 重建 cereal/params_pyx/services.h）、numpy。

**Spec:** `/data/openpilot/docs/camera_auto_calibration_design_20261112.md`（§4 数据结构 / §5 读写路径 / §7 消费侧 / §9 灰度 / §12 改动清单 / §16 时间同步 / §18 审计清单）。本计划从该 spec 论证，执行者需同时阅读两者。

## Global Constraints

- **只写一个持久化 key**：`Params["CalibrationParams"]`（`{PERSISTENT, BYTES}`）。不得新增 `CameraCalibSet`/`CamCalibRoad`/`CamCalibWide` key（spec §4.4、§8）。
- **新字段与旧字段必须同一次 `get_msg(True).to_bytes()` 写出**，禁止两处赋值（spec §18.4）。
- **`wide_warp_physical` 不进入消息**：它是消费策略，构造 `CameraCalibSet` 时从 `Params["CalibWideWarpPhysical"]` 注入，默认 False（spec §4.3，已修文档）。
- **capnp 只追加不改编号**：`LiveCalibrationData` 仅加 `@13/@14/@15`；`CameraCalibCandidate` 用 `custom.capnp` 的 `CustomReserved4 @0x80ae746ee2596b11`（改名不换 ID，spec/cereal README）。
- **`calibrationd.all_checks` 必须显式列 `['cameraOdometry','carState']`**，`cameraCalibCandidate`/新订阅不进有效性聚合（spec §5.1 A2）。
- **`MAX_CAMERA_SKEW_NS` 从 20ms 收到 15ms**；判据只针对 `|Δts − deltaRef|` 残差（spec §16.2/§16.4，C1）。
- **服务登记先行**：`cameraCalibCandidate`、`cameraSyncState` 必须进 `services.py` 并重建 `services.h`（spec A5）。
- 平台键 `("pc","imx390")`；`DEVICE_CAMERAS[("pc","imx390")]` 的 fcam=1920×1080 f≈2637.0、dcam/ecam=fisheye 1920×1080 f≈564.6（`camera.py:56-57`，`intrinsic_calibd.py:281` 的 2637.0/564.6 即此处）。
- **`CameraCalib` 与 `CameraCalibSet` 是可变 dataclass**（`CalibIdentity` 保持 frozen）：calibrationd 是单写者，`update_status` 就地更新 rpy/height/seq，冻结对象会逼每周期重建整棵树。可变性由单写者约定保证（R1）。

## Review Focus

没有任务测试覆盖、但使用者必踩的输入类/失败模式：

1. **旧 rlog / 旧 `CalibrationParams` 字节**（无 `cams[]` 字段）——`from_live_calibration` 必须静默降级为"工厂内参 + 旧字段组合"，不得抛异常、不得写盘；对应 Task 3 的 `test_legacy_bytes_without_cams_falls_back`。
2. **`sensor` 键缺失**（`DEVICE_CAMERAS.get` 返回 None，如旧的 `("unknown","ar0231")` 组合）——回退到 `DEVICE_CAMERAS[("unknown","ar0231")]` 并继续，不是 KeyError；对应 Task 3 `test_factory_set_unknown_sensor_falls_back`。
3. **DCAM 只有内参**——`camera_from_calib/warp_matrix(DCAM)` 必须抛 `ValueError`（不是返回单位阵），UI 走 `K(DCAM)` 自建；对应 Task 1 `test_dcam_projection_raises`。
4. **`CalibWideWarpPhysical=0` 时 wide warp 与旧 modeld 逐位一致**——gate 只换旋转、内参仍取 `K(WIDE)`；对应 Task 1 `test_wide_warp_legacy_matches_old_modeld`。
5. **相机帧对超过 15ms 绝对窗口**——`receive_camera_pair` 返回 None 而不是接受过期对；对应 Task 7 更新后的 `test_outside_skew_limit_requires_a_fresh_frame`（15ms+1ns）。
6. **`calibrationd` 启动时还没有 `roadCameraState`**——先发 legacy-only 消息，`cams=[]` 合法；`all_checks` 不因缺失而把 `valid` 判 false；对应 Task 5 `test_get_msg_no_calib_set_emits_legacy_only`。
7. **同段数据 wide warp 看两种语义不能混**——A/B/迁移测试必须显式指定 gate 状态再断言；对应 Task 3 迁移测试的两个 gate 分支。

---

## Task 1: `camera_calib.py` 数据模型与派生矩阵

**Files:**
- Create: `openpilot/common/transformations/camera_calib.py`
- Test: `openpilot/common/transformations/tests/test_camera_calib.py`

**Interfaces:**
- Consumes: `openpilot.common.transformations.camera.view_frame_from_device_frame`、`openpilot.common.transformations.orientation.rot_from_euler`、`openpilot.common.transformations.model.{calib_from_medmodel, calib_from_sbigmodel, get_warp_matrix}`（仅测试对照用）。
- Produces（后续任务依赖）:

```python
class Cam(IntEnum): ROAD=0; WIDE=1; LEFT=2; RIGHT=3; REAR=4; DCAM=5
class CalibSource(IntEnum): FACTORY=0; PRIOR=1; AUTO=2; MANUAL=3

@dataclass                      # 可变（R1）：calibrationd 单写者就地更新
class CameraCalib:
  uid: str
  width: int
  height: int
  fx: float
  fy: float
  cx: float
  cy: float
  dist: np.ndarray            # (5,)
  rpy: np.ndarray | None      # (3,) cam_from_body；None=无外参(DCAM)
  mount_height: float | None
  extrinsic_valid: bool       # DCAM=False
  valid: bool
  source: CalibSource
  blocks: int
  rms_reproj: float
  spread: np.ndarray          # (3,)
  updated_at_ns: int

@dataclass(frozen=True)
class CalibIdentity:
  device_type: str
  sensor: str
  sizes: dict[int, tuple[int, int]]   # Cam.id -> (w,h)

@dataclass                      # 可变（R1）
class CameraCalibSet:
  schema_version: int
  seq: int
  identity: CalibIdentity
  height: float                      # 兼容字段 = cams[ROAD].mount_height
  body_from_calib: np.ndarray        # (3,)
  cams: dict[Cam, CameraCalib]       # 按 Cam 索引（capnp 用 id 字段）
  wide_warp_physical: bool = False

  def K(self, cam: Cam) -> np.ndarray                      # [[fx,0,cx],[0,fy,cy],[0,0,1]]
  def camera_from_body(self, cam: Cam) -> np.ndarray       # V @ rot(rpy)；extrinsic_valid=False 抛 ValueError
  def camera_from_calib(self, cam: Cam) -> np.ndarray      # camera_from_body(cam) @ rot(body_from_calib)
  def device_from_calib(self) -> np.ndarray                # rot(body_from_calib)
  def calib_from_device(self) -> np.ndarray                # rot(body_from_calib).T
  def warp_matrix(self, cam: Cam, bigmodel_frame: bool = False) -> np.ndarray  # gate 见下
  def project_calib_points(self, cam: Cam, pts_calib: np.ndarray) -> np.ndarray  # UI/诊断
```

`warp_matrix` 精确语义（spec §4.3 已修）：

```python
calib_from_model = calib_from_sbigmodel if bigmodel_frame else calib_from_medmodel
rpy_cam = self.cams[Cam.ROAD].rpy if (cam == Cam.WIDE and not self.wide_warp_physical) else self.cams[cam].rpy
camera_from_body = view_frame_from_device_frame @ rot_from_euler(rpy_cam)
return (self.K(cam) @ camera_from_body @ rot_from_euler(self.body_from_calib) @ calib_from_model).astype(np.float32)
```

`project_calib_points`: `pts_view = camera_from_calib(cam) @ pts_calib`，再 `K(cam)` 齐次投影（UI 唯一投影入口）。

- [ ] **Step 1: 写失败测试** `openpilot/common/transformations/tests/test_camera_calib.py`

```python
import numpy as np
import pytest
from openpilot.common.transformations.camera import view_frame_from_device_frame
from openpilot.common.transformations.orientation import rot_from_euler
from openpilot.common.transformations.model import get_warp_matrix
from openpilot.common.transformations.camera_calib import Cam, CalibSource, CameraCalib, CameraCalibSet, CalibIdentity

def _calib(rpy=(0., 0., 0.), wide=False, extrinsic=True):
  cams = {
    Cam.ROAD: CameraCalib("road:x", 1920, 1080, 2637.0, 2637.0, 960., 540., np.zeros(5),
                          np.array(rpy, dtype=float), 1.22, extrinsic, True, CalibSource.AUTO, 10, 0.5, np.zeros(3), 0),
    Cam.WIDE: CameraCalib("wide:x", 1920, 1080, 564.6, 564.6, 960., 540., np.zeros(5),
                          np.array((0., 0., 0.03) if wide else (0., 0., 0.), dtype=float), None,
                          extrinsic, True, CalibSource.AUTO, 10, 0.5, np.zeros(3), 0),
  }
  return CameraCalibSet(1, 0, CalibIdentity("pc", "imx390", {}), 1.22,
                        np.array((0., 0.05, 0.01)), cams)

def test_K_geometry():
  s = _calib()
  K = s.K(Cam.ROAD)
  assert K[0, 0] == 2637.0 and K[1, 1] == 2637.0 and K[0, 2] == 960. and K[1, 2] == 540.

def test_camera_from_calib_road_matches_legacy_formula():
  s = _calib()
  expected = view_frame_from_device_frame @ rot_from_euler([0., 0.05, 0.01])
  assert np.allclose(s.camera_from_calib(Cam.ROAD), expected)

def test_wide_warp_legacy_matches_old_modeld():
  # gate off: wide warp 旋转用 cams[ROAD].rpy（此处为 0），内参用 K(WIDE)
  s = _calib(wide=True)
  legacy_intr = np.array([[564.6, 0, 960.], [0, 564.6, 540.], [0, 0, 1.]])
  expected = get_warp_matrix(np.array([0., 0.05, 0.01]), legacy_intr, False)
  assert np.allclose(s.warp_matrix(Cam.WIDE, False), expected)

def test_wide_warp_physical_uses_wide_rotation():
  import dataclasses
  s = _calib(wide=True)
  s2 = dataclasses.replace(s, wide_warp_physical=True)   # rpy(0,0,0.03)
  legacy = get_warp_matrix(np.array([0., 0.05, 0.01]), np.array([[564.6,0,960.],[0,564.6,540.],[0,0,1.]]), False)
  assert not np.allclose(s2.warp_matrix(Cam.WIDE, False), legacy)

def test_dcam_projection_raises():
  cams = {Cam.DCAM: CameraCalib("dcam:x", 1920, 1080, 564.6, 564.6, 960., 540., np.zeros(5),
                                None, None, False, True, CalibSource.PRIOR, 0, 0., np.zeros(3), 0)}
  s = CameraCalibSet(1, 0, CalibIdentity("pc", "imx390", {}), 1.22, np.zeros(3), cams)
  with pytest.raises(ValueError):
    s.camera_from_calib(Cam.DCAM)
  with pytest.raises(ValueError):
    s.warp_matrix(Cam.DCAM)

def test_device_from_calib_inverse():
  s = _calib()
  R = s.device_from_calib()
  assert np.allclose(R @ s.calib_from_device(), np.eye(3))
```

- [ ] **Step 2: 运行确认失败**

Run: `cd /data/openpilot && python -m pytest openpilot/common/transformations/tests/test_camera_calib.py -q`
Expected: FAIL / import error（模块不存在）

- [ ] **Step 3: 实现** `openpilot/common/transformations/camera_calib.py`

按 Interfaces 实现全部类型与方法；`camera_from_body`/`warp_matrix`/`camera_from_calib` 对 `extrinsic_valid=False` 抛 `ValueError`；`CameraCalib` 与 `CameraCalibSet` 用可变 `@dataclass`（**不设** `frozen=True`，R1），`CalibIdentity` 保持 frozen。

- [ ] **Step 4: 运行确认通过**

Run: `cd /data/openpilot && python -m pytest openpilot/common/transformations/tests/test_camera_calib.py -q`
Expected: PASS（6 tests）

- [ ] **Step 5: 提交**

```bash
git add openpilot/common/transformations/camera_calib.py openpilot/common/transformations/tests/test_camera_calib.py
git commit -m "feat(camera-calib): CameraCalibSet 数据模型与派生矩阵 (P0)"
```

---

## Task 2: capnp 结构与服务登记（P0 依赖）

**Files:**
- Modify: `openpilot/cereal/log.capnp`（`LiveCalibrationData` 段落，约 779-808 行；Event union `customReserved4 @111`、`customReserved5 @112` 改名，见 R18）
- Modify: `openpilot/cereal/custom.capnp`（`CustomReserved4` → `CameraCalibCandidate`，约 278-280 行；`CustomReserved5` → `CameraSyncState`，见 R18）
- Modify: `openpilot/cereal/services.py`
- Test: `openpilot/cereal/messaging/tests/test_services.py`（**追加到已有文件**，R13；python 侧 capnp 导入即生效，无需 codegen）

**Interfaces:**
- Produces: `LiveCalibrationData` 新字段 `calibSchemaVersion @13 :UInt16; calibSeq @14 :UInt32; cams @15 :List(CameraCalib);`；顶层 `struct CameraCalib`（字段见 spec §4.4）；`Custom.CameraCalibCandidate`（替换 `CustomReserved4`，ID 不变 `@0x80ae746ee2596b11`）；Event union `customReserved4 @111` 字段名改为 `cameraCalibCandidate @111`。
- `CameraCalibCandidate` 字段（spec §5.1 候选内容）：

```capnp
struct CameraCalibCandidate {
  generation @0 :UInt32;
  cam @1 :List(CamEntry);
  struct CamEntry {
    id @0 :UInt8;
    intrinsics @1 :List(Float32);   # [fx,fy,cx,cy]
    rpy @2 :List(Float32);          # cam_from_body 候选
    blocks @3 :Int32;
    rmsReproj @4 :Float32;
    mode @5 :Text;
    std @6 :Float32;
    span @7 :Float32;
  }
}
```

- `CameraCalib` struct（spec §4.4 原样）：

```capnp
struct CameraCalib {
  id @0 :UInt8;  uid @1 :Text;  width @2 :UInt16;  height @3 :UInt16;
  intrinsics @4 :List(Float32);  distortion @5 :List(Float32);
  rpy @6 :List(Float32);  valid @7 :Bool;  source @8 :Source;
  blocks @9 :Int32;  rmsReproj @10 :Float32;  spread @11 :List(Float32);
  updatedAtNs @12 :UInt64;  mountHeight @13 :Float32;  extrinsicValid @14 :Bool;
  enum Source { factory @0; prior @1; auto @2; manual @3; }
}
```

- **R18 补漏（cameraSyncState schema）：** `cameraSyncState` 服务在 Task 2 登记，但原计划没有任务定义它的消息结构（Task 8 只发布）。
  补在本任务：`custom.capnp` 的 `CustomReserved5 @0xa5cd762cd951a455` 改名为 `CameraSyncState`（ID 不变），
  `log.capnp` Event union `customReserved5 @112` 改名 `cameraSyncState @112`（编号不变）。字段按 spec §16.4 第 5 条 13 项：

```capnp
struct CameraSyncState @0xa5cd762cd951a455 {   # 原 CustomReserved5，ID 不变
  cam @0 :UInt8;
  deltaNs @1 :Int64;
  deltaP50Ns @2 :Int64;
  deltaP99Ns @3 :Int64;
  jitterNs @4 :Int64;              # 残差 MAD，不是 Δ 的标准差
  skewPpm @5 :Float32;
  missingFrames @6 :UInt32;
  streamEpoch @7 :UInt64;
  synced @8 :Bool;
  timebase @9 :Timebase;
  timestampSource @10 :TimestampSource;
  quantizationNs @11 :UInt32;
  alignedResidualNs @12 :Int64;
  enum Timebase { systemClock @0; fsin @1; hwTs @2; }
  enum TimestampSource { kernelRecv @0; driver @1; vipc @2; }
}
```

- `services.py` 追加（保持字典内已有桶的结构）：

```python
"cameraCalibCandidate": (True, 5., 1),
"cameraSyncState": (True, 10., 1),
```

- [ ] **Step 1: 追加失败测试** 到已有的 `openpilot/cereal/messaging/tests/test_services.py`（R13：该文件已存在并承担服务注册表不变量校验，新建 `cereal/tests/` 会造出重复的第二份）

```python
import openpilot.cereal.messaging as messaging
from openpilot.cereal.services import SERVICE_LIST

def test_new_live_calibration_fields_exist():
  msg = messaging.new_message('liveCalibration')
  lc = msg.liveCalibration
  lc.calibSchemaVersion = 1
  lc.calibSeq = 7
  # R3: pycapnp 结构体列表用 init() 建，没有 .add()
  lc.init('cams', 2)
  assert lc.cams[0] is not None  # schema 层面存在即通过

def test_camera_calib_candidate_struct():
  msg = messaging.new_message('cameraCalibCandidate')
  cand = msg.cameraCalibCandidate
  cand.init('cam', 1)
  e = cand.cam[0]
  e.id = 0; e.intrinsics = [2637., 2637., 960., 540.]
  e.blocks = 12; e.mode = "joint_lsq"; e.std = 0.8; e.span = 0.02

def test_services_registered():
  assert "cameraCalibCandidate" in SERVICE_LIST
  assert "cameraSyncState" in SERVICE_LIST
```

- [ ] **Step 2: 运行确认失败**

Run: `cd /data/openpilot && python -m pytest openpilot/cereal/messaging/tests/test_services.py -q`
Expected: FAIL（`liveCalibration.calibSchemaVersion` AttributeError / `SERVICE_LIST` 缺 key / `cameraCalibCandidate` 消息不存在）

- [ ] **Step 3: 修改三个 schema 文件**，字段与结构按 Interfaces 精确落地；`customReserved4` 的 Event union 字段名改 `cameraCalibCandidate`（ID 与 struct ID 不变）。

- [ ] **Step 4: 运行确认通过**

Run: `cd /data/openpilot && python -m pytest openpilot/cereal/messaging/tests/test_services.py -q`
Expected: PASS（3 tests）

- [ ] **Step 5: 重建 C++ 产物并验证**

Run: `cd /data/openpilot && scons -j$(nproc) cereal services 2>&1 | tail -5`
Expected: 成功（生成 `openpilot/cereal/gen/cpp/log.capnp.{h,c++}` 与 `openpilot/cereal/services.h` 更新）

- [ ] **Step 6: 提交**

```bash
git add openpilot/cereal/log.capnp openpilot/cereal/custom.capnp openpilot/cereal/services.py openpilot/cereal/services.h openpilot/cereal/gen/cpp openpilot/cereal/messaging/tests/test_services.py
git commit -m "feat(camera-calib): capnp CameraCalib/LiveCalibrationData@13-15 + CameraCalibCandidate + 服务登记 (P0)"
```

---

## Task 3: `camera_calib.py` 工厂构造 / 序列化 / 迁移 / to_json

**Files:**
- Modify: `openpilot/common/transformations/camera_calib.py`
- Modify: `openpilot/common/transformations/tests/test_camera_calib.py`

**Interfaces:**
- Consumes: Task 1 类型 + `DEVICE_CAMERAS`（`camera.py`，仅此处允许直读）、Task 2 capnp 字段。
- Produces:

```python
def build_factory_set(device_type: str, sensor: str,
                      sizes: dict[int, tuple[int, int]] | None = None) -> CameraCalibSet
def from_legacy_values(rpy, height, wide_from_device_euler, device_type, sensor,
                       sizes=None, seq=0) -> CameraCalibSet      # spec §5.3 组合
def from_live_calibration(msg, *, device_type: str = "", sensor: str = "") -> CameraCalibSet
def write_live_calibration(lc_builder, s: CameraCalibSet) -> None
def to_json(s: CameraCalibSet) -> dict
```

语义要点（spec §5.3 / §4.4 / 已修文档）：
- `from_live_calibration`：`msg.liveCalibration.cams` 非空 → 直接反序列化（忽略 device_type/sensor）；为空 → `from_legacy_values` 降级（需要 device_type/sensor；cams 用工厂表，`source=FACTORY`，不写盘）。
- `from_legacy_values`：`road.rpy=[0,0,0]`、`wide.rpy=wide_from_device_euler`、`road.K/wide.K = DEVICE_CAMERAS[...].fcam/ecam.intrinsics`、`dcam.PRIOR` 无外参、`height=legacy.height`；`sizes` 为 None 时 `sizes={ROAD:(fcam.w,fcam.h), WIDE:(ecam.w,ecam.h), DCAM:(dcam.w,dcam.h)}`。
- 工厂表缺 `(device_type,sensor)` 键时回退 `DEVICE_CAMERAS[("unknown","ar0231")]`（Review Focus #2）。
- **工厂集相机裁剪与 ROAD 高度（R23）**：配置为 `_NoneCameraConfig`（或 width/height ≤ 0）的相机不进 `cams`
  （与 `DeviceCameraConfig.all_cams` 约定一致；当前只有 `("neo","unknown")` 的 WIDE 命中）；工厂 ROAD
  `mount_height = 1.22`（镜像 `calibrationd.HEIGHT_INIT` 先验；spec §4.2 规定 ROAD 有值、其余为 None），
  `set.height` 同值，保持 `height == cams[ROAD].mount_height` 镜像不变量；`from_legacy_values` 在 WIDE 缺失时跳过 wide.rpy。
- `write_live_calibration`：填 `calibSchemaVersion=1`、`calibSeq=s.seq`、`cams` 列表（每项带 `id`，`rpy` 空即写空 list，`mountHeight` NaN 表示无）；是 cams 内容的**唯一**填充点。
- `to_json`：`{seq, schemaVersion, height, bodyFromCalib:[3], cams:[{id,width,height,fx,fy,cx,cy,dist:5,rpy|None,mountHeight|None,extrinsicValid,valid,source,blocks,rmsReproj,spread:3}]}`（spec §4.4 网关）。

- [ ] **Step 1: 追加失败测试**

```python
def test_factory_set_matches_device_cameras():
  from openpilot.common.transformations.camera import DEVICE_CAMERAS
  s = build_factory_set("pc", "imx390")
  dc = DEVICE_CAMERAS[("pc", "imx390")]
  assert np.allclose(s.K(Cam.ROAD), dc.fcam.intrinsics)
  assert np.allclose(s.K(Cam.WIDE), dc.ecam.intrinsics)
  assert np.allclose(s.K(Cam.DCAM), dc.dcam.intrinsics)
  assert s.cams[Cam.DCAM].extrinsic_valid is False and s.cams[Cam.DCAM].source == CalibSource.PRIOR
  assert Cam.LEFT not in s.cams

def test_factory_set_unknown_sensor_falls_back():
  s = build_factory_set("tici", "something_new")
  assert s.cams[Cam.ROAD].width > 0   # 不抛 KeyError

def test_legacy_composition_matches_doc():
  rpy = np.array([0., 0.05, 0.01]); height = np.array([1.22])
  wide = np.array([0., 0., 0.03])
  s = from_legacy_values(rpy, height, wide, "pc", "imx390")
  assert np.allclose(s.body_from_calib, rpy)
  assert np.allclose(s.cams[Cam.ROAD].rpy, np.zeros(3))
  assert np.allclose(s.cams[Cam.WIDE].rpy, wide)
  assert s.height == 1.22 and s.cams[Cam.WIDE].mount_height is None

def test_live_calibration_roundtrip_preserves_values():
  s0 = from_legacy_values(np.array([0., 0.05, 0.01]), np.array([1.22]),
                          np.array([0., 0., 0.03]), "pc", "imx390")
  msg = messaging.new_message('liveCalibration')
  write_live_calibration(msg.liveCalibration, s0)
  s1 = from_live_calibration(msg)
  assert s1.schema_version == 1 and s1.seq == s0.seq
  for cam in (Cam.ROAD, Cam.WIDE, Cam.DCAM):
    a, b = s0.cams[cam], s1.cams[cam]
    assert (a.fx, a.fy, a.cx, a.cy) == (b.fx, b.fy, b.cx, b.cy)
    assert np.allclose(a.rpy if a.rpy is not None else [], b.rpy if b.rpy is not None else [])
    assert a.valid == b.valid and a.source == b.source

def test_legacy_bytes_without_cams_falls_back():
  # 构造一个只有旧字段的 liveCalibration 消息
  msg = messaging.new_message('liveCalibration')
  msg.liveCalibration.rpyCalib = [0., 0.05, 0.01]
  msg.liveCalibration.height = [1.22]
  msg.liveCalibration.wideFromDeviceEuler = [0., 0., 0.03]
  s = from_live_calibration(msg, device_type="pc", sensor="imx390")
  assert s.cams[Cam.ROAD].source == CalibSource.FACTORY  # 降级，非 AUTO

def test_to_json_shape():
  s = from_legacy_values(np.zeros(3), np.array([1.22]), np.zeros(3), "pc", "imx390")
  j = to_json(s)
  assert set(j) == {"seq", "schemaVersion", "height", "bodyFromCalib", "cams"}
  assert {c["id"] for c in j["cams"]} == {0, 1, 5}
```

- [ ] **Step 2: 运行确认失败**（新测试失败：函数不存在）

Run: `cd /data/openpilot && python -m pytest openpilot/common/transformations/tests/test_camera_calib.py -q`
Expected: 新用例 FAIL，老用例 PASS

- [ ] **Step 3: 实现五个函数**，按 Interfaces 语义。

- [ ] **Step 4: 运行确认通过**

Run: `cd /data/openpilot && python -m pytest openpilot/common/transformations/tests/test_camera_calib.py -q`
Expected: PASS（12 tests）

- [ ] **Step 5: 提交**

```bash
git add openpilot/common/transformations/camera_calib.py openpilot/common/transformations/tests/test_camera_calib.py
git commit -m "feat(camera-calib): 工厂构造/序列化/legacy 迁移/to_json (P0)"
```

---

## Task 4: params_keys.h 三个开关 + 重建 params_pyx

**Files:**
- Modify: `openpilot/common/params_keys.h`（`CameraYawTrimDeg` 之后，约 384 行）
- Test: `openpilot/common/tests/test_camera_calib_params.py`（新建）

**Interfaces:**
- Produces: 三个 PERSISTENT BOOL key：

```cpp
{"EnableCameraIntrinsicsAutoCalib", {PERSISTENT, BOOL, "0"}},
{"EnableCameraCalibShadow", {PERSISTENT, BOOL, "0"}},
{"CalibWideWarpPhysical", {PERSISTENT, BOOL, "0"}},
```

- [ ] **Step 1: 写失败测试** `openpilot/common/tests/test_camera_calib_params.py`

```python
from openpilot.common.params import Params

def test_new_params_exist_with_defaults():
  p = Params()
  # R7: 用 get_bool，避免对 PERSISTENT BOOL 的 get() 返回类型做假设
  assert p.get_bool("EnableCameraIntrinsicsAutoCalib") is False
  assert p.get_bool("EnableCameraCalibShadow") is False
  assert p.get_bool("CalibWideWarpPhysical") is False
```

（若本机 `/data/params` 不可读写则跳过此测试，改用 header 内容断言：读取文件文本包含三个字符串。）

- [ ] **Step 2: 运行确认失败**

Run: `cd /data/openpilot && python -m pytest openpilot/common/tests/test_camera_calib_params.py -q`
Expected: FAIL（UnknownKeyName / 断言失败）

- [ ] **Step 3: 在 `params_keys.h` 的 `CameraYawTrimDeg`（约 384 行）后加三行**；`CameraCalibSet` key **不新增**。

- [ ] **Step 4: 重建并运行参数检查**

Run: `cd /data/openpilot && scons -j$(nproc) common/params_pyx 2>&1 | tail -3 && python -m pytest openpilot/common/tests/test_camera_calib_params.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add openpilot/common/params_keys.h openpilot/common/tests/test_camera_calib_params.py common/params_pyx.cpp common/params_pyx.o
git commit -m "feat(camera-calib): 注册 EnableCamera* / CalibWideWarpPhysical 参数 key (P0)"
```

---

## Task 5: `calibrationd` 唯一写入者（P0 写盘）

**Files:**
- Modify: `openpilot/selfdrive/locationd/calibrationd.py`
- Test: `openpilot/selfdrive/locationd/test/test_calibrationd.py`（新建目录）

**Interfaces:**
- Consumes: Task 3（`build_factory_set`、`write_live_calibration`、`camera_calib` 类型）、Task 2 capnp。
- Produces:

```python
# Calibrator 新增
self.calib_set: CameraCalibSet | None = None
def set_calib_set(self, s: CameraCalibSet) -> None
# main() 中
sm = messaging.SubMaster(['cameraOdometry', 'carState', 'deviceState', 'roadCameraState'], poll='cameraOdometry')
# get_msg 内：if self.calib_set is not None: write_live_calibration(liveCalibration, self.calib_set)
# update_status 内：if write_this_cycle and self.calib_set is not None:
#   同步 body_from_calib=rpy、height、cams[WIDE].rpy=wide_from_device_euler；seq += 1  # R8: 与 param_put 无关
```

语义（spec §5.1、§7.1、§18.4）：
- `all_checks(['cameraOdometry','carState'])`，其余订阅不参与有效性聚合；
- 新老字段同一次 `get_msg(True).to_bytes()`；`seq` 单调递增（R8：随 `write_this_cycle` 递增，**不**依赖 `param_put`——calibrationd.py:168-170 的落盘条件含 `param_put`，把 seq 写在那里会让单测永远看不到变化）；
- `wide_warp_physical` 不落在消息里；
- `calib_set` 不存在时（启动早期未收到 `roadCameraState`）只发旧字段，`cams` 为空列表（Review Focus #6）；
- `main()` 在首次 `sm.updated['roadCameraState']` 时 `build_factory_set(HARDWARE.get_device_type(), str(sm['roadCameraState'].sensor))` 并 `set_calib_set`。

- [ ] **Step 1: 写失败测试** `openpilot/selfdrive/locationd/test/test_calibrationd.py`

```python
import numpy as np
from openpilot.selfdrive.locationd.calibrationd import Calibrator
from openpilot.common.transformations.camera_calib import build_factory_set, Cam

def _calibrator_with_set():
  c = Calibrator(param_put=False)
  c.set_calib_set(build_factory_set("pc", "imx390"))
  return c

def test_get_msg_contains_cams():
  c = _calibrator_with_set()
  c.handle_v_ego(20.)
  c.handle_cam_odom([20., 0., 0.], [0., 0., 0.], [0., 0., 0.03], [0., 0., 0.],
                    [0., 0., 1.22], [0., 0., 0.5e-3])
  c.update_status()
  msg = c.get_msg(True)
  assert len(msg.liveCalibration.cams) == 3
  ids = [m.id for m in msg.liveCalibration.cams]
  assert set(ids) == {0, 1, 5}
  assert msg.liveCalibration.calibSchemaVersion == 1

def test_get_msg_no_calib_set_emits_legacy_only():
  c = Calibrator(param_put=False)
  msg = c.get_msg(True)
  assert len(msg.liveCalibration.cams) == 0
  assert msg.liveCalibration.rpyCalib  # 旧字段仍在

def test_seq_monotonic_across_writes():
  # R8：seq 随 write_this_cycle 递增，与 param_put 无关
  # write_this_cycle = (idx==0) and (block_idx % (INPUTS_WANTED//5) == 5)
  c = _calibrator_with_set()
  c.block_idx, c.idx = 5, 0
  c.update_status()
  s1 = c.calib_set.seq
  c.block_idx, c.idx = 15, 0
  c.update_status()
  assert c.calib_set.seq > s1
```

- [ ] **Step 2: 运行确认失败**

Run: `cd /data/openpilot && python -m pytest openpilot/selfdrive/locationd/test/test_calibrationd.py -q`
Expected: FAIL（`set_calib_set` 不存在 / assert `len(cams)==0`）

- [ ] **Step 3: 改 `calibrationd.py`**

按 Interfaces 加 `self.calib_set`/`set_calib_set`/`main()` 订阅扩展；`update_status` 的 `write_this_cycle` 分支里同步 `calib_set`（rpy/height/wide/seq，R8 不依赖 `param_put`）；`get_msg` 填新字段。`all_checks(['cameraOdometry','carState'])`。

- [ ] **Step 4: 运行确认通过**

Run: `cd /data/openpilot && python -m pytest openpilot/selfdrive/locationd/test/test_calibrationd.py -q`
Expected: PASS（3 tests）

- [ ] **Step 5: 提交**

```bash
git add openpilot/selfdrive/locationd/calibrationd.py openpilot/selfdrive/locationd/test/
git commit -m "feat(camera-calib): calibrationd 扩展新字段+seq，all_checks 显式化 (P0)"
```

---

## Task 6: 静态扫描门禁（可执行版本，P0 起生效）

**Files:**
- Create: `openpilot/selfdrive/test/test_no_direct_calib_readers.py`
- Modify: `openpilot/selfdrive/test/` 无需其他改动

**Interfaces:**
- Consumes: 无（独立）。Produces: CI 门禁，spec §10.6 的可执行子集。
- R5：禁读正则分两组。P0 阶段只扫 `camera_calib.py`（它允许 `DEVICE_CAMERAS`，但不得出现 `rpyCalib`/`wideFromDeviceEuler`/`"CalibrationParams"`）；
  再对 `common/transformations/` 与 `selfdrive/locationd/`（白名单 `calibrationd.py`、`camera_calib.py` 除外）跑一次 `BANNED_ANYWHERE` 扫描，验证迁移目标目录已干净。
- Task 11 再把扫描扩到全树并追加 `DEVICE_CAMERAS\[`（`BANNED_CONSUMERS`）。

- [ ] **Step 1: 写失败测试**

```python
import pathlib, re
REPO = pathlib.Path("/data/openpilot/openpilot")
BANNED_ANYWHERE = re.compile(r"rpyCalib|wideFromDeviceEuler|\"CalibrationParams\"")
BANNED_CONSUMERS = re.compile(r"rpyCalib|wideFromDeviceEuler|DEVICE_CAMERAS\[|\"CalibrationParams\"")
WHITELIST = {"openpilot/common/transformations/camera_calib.py",
             "openpilot/selfdrive/locationd/calibrationd.py"}

def test_camera_calib_module_has_no_raw_legacy_refs():
  text = (REPO / "openpilot/common/transformations/camera_calib.py").read_text()
  assert "DEVICE_CAMERAS" in text          # 工厂真值来源（Global Constraints 允许）
  assert not BANNED_ANYWHERE.search(text)

def test_owned_dirs_already_clean_of_legacy_reads():
  # 迁移目标目录必须本就是干净的（calibrationd/camera_calib 白名单除外），
  # 否则 Task 11 全量扫描不可能清零。行为化断言，P0 与 P1 均为真。
  hits = []
  for root in ("openpilot/common/transformations", "openpilot/selfdrive/locationd"):
    for p in (REPO / root).rglob("*.py"):
      rel = p.relative_to(REPO).as_posix()
      if rel in WHITELIST:
        continue
      if BANNED_ANYWHERE.search(p.read_text()):
        hits.append(rel)
  assert hits == [], f"白名单外直读原始字段: {hits}"
```

- [ ] **Step 2: 运行确认失败**

Run: `cd /data/openpilot && python -m pytest openpilot/selfdrive/test/test_no_direct_calib_readers.py -q`
Expected: 若 camera_calib.py 误带旧字段则 FAIL；正常实现下 P0 即通过（Task 3 实现后运行即为验证）。

- [ ] **Step 3: 无产品代码改动**（仅测试文件）；确认 `camera_calib.py` 与 `calibrationd.py` 的工厂表/滚动逻辑不带 `rpyCalib` 字样。

- [ ] **Step 4: 运行确认通过**，随后**提交**

```bash
git add openpilot/selfdrive/test/test_no_direct_calib_readers.py
git commit -m "test(camera-calib): 新代码直读原始字段静态扫描门禁 (P0)"
```

---

## Task 7: `camera_sync.py` 收紧到 15ms + deltaRef 相对判据

**Files:**
- Modify: `openpilot/selfdrive/modeld/camera_sync.py`
- Modify: `openpilot/selfdrive/modeld/tests/test_camera_sync.py`

**Interfaces:**
- Consumes: 无。Produces:

```python
MAX_CAMERA_SKEW_NS = 15_000_000                 # 原 20ms（spec C1/§16.4 第 2 条）
MAX_PAIR_RESIDUAL_NS = 2_000_000                # |Δ − deltaRef| 残差上限
def receive_camera_pair(main, extra=None, *, trace=None, delta_ref: int = 0) -> tuple | None
```

语义（spec §16.4 第 1/2 条）：
- `delta_ref` 默认 0 时行为与现在一致，仅绝对窗口从 20→15ms（modeld 不改调用，零风险）；
- 当 `delta_ref` 非零时，接受条件为 `abs((main_sof − extra_sof) − delta_ref) ≤ MAX_PAIR_RESIDUAL_NS`，同时保留绝对窗口 15ms 作陈旧对兜底——两者都满足才返回；
- 文件头注释更新（去掉 20Hz/50ms 过期表述，写 30fps/15ms 与 deltaRef 语义）；
- **既有用例不受 15ms 影响**：`test_ev9_complete_camera_streams...` 最大 Δ=13.19ms、`test_alternating_exposure_intervals...` Δ=0.1ms、`test_resync_is_bounded...` Δ=50ms（继续拒绝）——均与 15ms 兼容，不改数据，只改 20ms 参数化的两处数值。

- [ ] **Step 1: 更新既有测试边界 + 新增相对判据测试**

```python
@pytest.mark.parametrize('skew', [-15_000_000, 15_000_000])
def test_small_skew_is_symmetric_and_bounded(skew): ...   # 原 20ms→15ms

@pytest.mark.parametrize('skew', [-15_000_001, 15_000_001])
def test_outside_skew_limit_requires_a_fresh_frame(skew): ...  # 原 20ms→15ms

def test_delta_ref_residual_accepts_fixed_offset():
  main = Camera([(1, 100_000_000)])
  wide = Camera([(1, 113_000_000)])          # Δ=13ms，deltaRef=13ms → 残差 0
  assert receive_camera_pair(main, wide, delta_ref=13_000_000) is not None

def test_delta_ref_residual_rejects_large_jitter():
  main = Camera([(1, 100_000_000)])
  wide = Camera([(1, 116_000_000)])          # 残差 3ms > 2ms
  assert receive_camera_pair(main, wide, delta_ref=13_000_000) is None

def test_delta_ref_zero_preserves_absolute_gate():
  main = Camera([(1, 100_000_000)])
  wide = Camera([(1, 113_000_000)])          # 13ms < 15ms → 通过
  assert receive_camera_pair(main, wide, delta_ref=0) is not None
```

- [ ] **Step 2: 运行确认失败**

Run: `cd /data/openpilot && python -m pytest openpilot/selfdrive/modeld/tests/test_camera_sync.py -q`
Expected: FAIL（20ms 参数化因断言失败 / delta_ref 参数不接受）

- [ ] **Step 3: 实现**：常量、签名、相对判据逻辑、头注释。

- [ ] **Step 4: 运行确认通过**

Run: `cd /data/openpilot && python -m pytest openpilot/selfdrive/modeld/tests/test_camera_sync.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add openpilot/selfdrive/modeld/camera_sync.py openpilot/selfdrive/modeld/tests/test_camera_sync.py
git commit -m "fix(camera-sync): 帧对窗口 20→15ms，新增 deltaRef 相对残差判据 (P0/§16.4)"
```

---

## Task 8: `camcalibd` 迁移（去掉写盘，发布候选 + cameraSyncState，P2）

**Files:**
- Create: `openpilot/selfdrive/locationd/camcalibd.py`
- Modify: `openpilot/selfdrive/locationd/__init__.py`（如有导出需求则加，一般不需要）
- Test: `openpilot/selfdrive/locationd/test/test_camcalibd.py`

**Interfaces:**
- Consumes: `intrinsic_calibd.py` 的估计器（`compute_vanishing_point`、`StreamCalib.estimate` 的 vp_offset/joint_lsq 逻辑、全部常量：`MAX_OFFSET=0.15`、`MIN_LINES=20`、`MIN_SAMPLES=30`、`CONVERGE_STD=60`、`ROAD_ROI_TOP_FRAC=0.52`）、Task 1/2（capnp `cameraCalibCandidate`）、Task 7（`receive_camera_pair(delta_ref=...)`）。
- Produces:

```python
CAMERA_CALIB_CANDIDATE_SERVICE = "cameraCalibCandidate"
CAMERA_SYNC_SERVICE = "cameraSyncState"
def main() -> NoReturn   # 由 process_config 拉起，only_onroad
```

行为（spec §5.1 用点、§12 文件表）：
- **不碰 Params**：删除 `seed_prior` 写盘；工厂初值由 `calibrationd` 构造对象时下发，`camcalibd` 不构造 `CameraCalibSet` 持久化部分。`MaybeParams` 读取 `CalibWideWarpPhysical` 只作为校准目标/开关参考。
- 订阅 `['liveCalibration', 'cameraCalibrationCandidate'?no]`：实际订阅 `liveCalibration`、`carState`、`deviceState`、`roadCameraState`、`wideRoadCameraState`；经 `camera_sync.receive_camera_pair(delta_ref=...)` 配对两路帧（非阻塞 `recv(0)`，修复 B1）。
- `cameraSyncState`（10 Hz）：`{cam, deltaNs, deltaP50Ns, deltaP99Ns, jitterNs, skewPpm, missingFrames, streamEpoch, synced, alignedResidualNs}`（spec §16.4 第 5 条）；`missingFrames` 用相邻 `timestamp_sof` 间隔 > 1.5×周期判定，**不依赖 `b.sequence`**（C2）。
- 发布 `cameraCalibCandidate`（≥5 Hz）：`CamEntry` per road/wide，内容 `intrinsics/rpy/blocks/rmsReproj/mode/std/span`，`mode` 为 `vp_offset`/`joint_lsq`/`fov_prior`。
- 只读 Y 平面 + 4× 降采样 320×180（spec §5.1）。

- [ ] **Step 1: 写失败测试** `openpilot/selfdrive/locationd/test/test_camcalibd.py`

```python
import numpy as np
from openpilot.selfdrive.locationd.camcalibd import compute_delta_ref_stats, missing_frames_for, make_camera_calib_candidate

def test_delta_ref_stats_separates_bias_from_jitter():
  # 固定偏置 13ms + 0.5ms 抖动 → deltaRef≈13ms, jitter<1ms
  sof_pairs = [(1_000_000_000 + i * 33_333_400, 1_000_000_000 + i * 33_333_400 + 13_000_000 + int(np.sin(i) * 500_000))
               for i in range(60)]
  ref, jitter, ppm = compute_delta_ref_stats(sof_pairs)
  assert abs(ref - 13_000_000) < 200_000
  assert jitter < 1_000_000

def test_missing_frames_uses_sof_interval():
  # R9：末帧 4*33.3ms（gap 66→133.3ms = 2 周期 → 缺 1 帧）；原 3*66ms 是 4 周期缺 3 帧，与期望矛盾
  sof = [0, 33_000_000, 66_000_000, 4 * 33_333_333]
  assert missing_frames_for(sof, period_ns=33_333_333) == [0, 0, 0, 1]

def test_candidate_message_shape():
  import openpilot.cereal.messaging as messaging
  msg = make_camera_calib_candidate({"f": 2637.0, "pitch_offset": 1e-3, "mode": "joint_lsq",
                                     "std": 0.5, "span": 0.02, "samples": 40})
  assert len(msg.cameraCalibCandidate.cam) >= 2
```

- [ ] **Step 2: 运行确认失败**（模块不存在）

- [ ] **Step 3: 创建 `camcalibd.py`**——复制 `intrinsic_calibd.py` 到 `selfdrive/locationd/camcalibd.py`，按 Interfaces 改造：加 `compute_delta_ref_stats`/`missing_frames_for`/`make_camera_sync_state`/`make_camera_calib_candidate`；`StreamCalib.recv(0)` 非阻塞；删 `Params.put`；`estimate()` 结果改发消息。

- [ ] **Step 4: 运行确认通过**

Run: `cd /data/openpilot && python -m pytest openpilot/selfdrive/locationd/test/test_camcalibd.py -q`
Expected: PASS（3 tests）

- [ ] **Step 5: 提交**

```bash
git add openpilot/selfdrive/locationd/camcalibd.py openpilot/selfdrive/locationd/test/test_camcalibd.py
git commit -m "feat(camera-calib): camcalibd 迁移 intrinsic_calibd，发布候选+cameraSyncState (P2)"
```

---

## Task 9: `process_config.py` 注册 + `test_onroad.py` PROCS 预算

**Files:**
- Modify: `openpilot/system/manager/process_config.py`（calibrationd 行后，约 144 行）
- Modify: `openpilot/selfdrive/test/test_onroad.py`（PROCS 列表）
- Test: `openpilot/selfdrive/test/test_onroad.py` 本身

**Interfaces:**
- Consumes: Task 8 `openpilot.selfdrive.locationd.camcalibd`。
- Produces: `PythonProcess("camcalibd", "openpilot.selfdrive.locationd.camcalibd", only_onroad)` 注册。

- [ ] **Step 1: 修改 `process_config.py`** 在 calibrationd 之后加一行 camcalibd（spec §12 文件表、§18 C4）。先加进程，暂不要求通过 test_onroad（预算断言在 Step 3 再调）。

- [ ] **Step 2: 冒烟运行**

Run: `cd /data/openpilot && python -c "from openpilot.system.manager.process_config import managed_processes; print('camcalibd' in managed_processes)"`
Expected: `True`

- [ ] **Step 3: 更新 `test_onroad.py` PROCS**：把 `camcalibd` 计入并调整预算断言（spec §18.3 C4：现有合计 323%/350%，加 ~4%）；运行确认预算不失败。

Run: `cd /data/openpilot && python -m pytest openpilot/selfdrive/test/test_onroad.py -q -k "procs or budget or 25s" 2>&1 | tail -20`
Expected: PASS（或按输出调整断言值，记录实测合计）

- [ ] **Step 4: 提交**

```bash
git add openpilot/system/manager/process_config.py openpilot/selfdrive/test/test_onroad.py
git commit -m "feat(camera-calib): 注册 camcalibd 进程 + test_onroad 预算 (P2)"
```

---

## Task 10: `modeld.py` 切到 `warp_matrix`（P1，wide 保持旧语义）

**Files:**
- Modify: `openpilot/selfdrive/modeld/modeld.py`（约 520-533 行）
- Test: `openpilot/selfdrive/modeld/tests/test_modeld_warp.py`（新建，纯函数级）

**Interfaces:**
- Consumes: Task 3 `from_live_calibration`、Task 1 `warp_matrix`、`Params().get_bool("CalibWideWarpPhysical")`。
- Produces（R10）:

```python
def build_model_transforms(lc_msg, main_wide_camera: bool, wide_warp_physical: bool) -> tuple[np.ndarray, np.ndarray]:
  """lc_msg 是 liveCalibration 消息；wide_warp_physical 由 Params 注入（§7.1）"""
```

- modeld 不再读 `DEVICE_CAMERAS`/`get_warp_matrix`/`wideFromDeviceEuler`；`CameraYawTrimDeg` 不再在 modeld 内减（spec §7.1、§5.2 B4）。
- 主循环在 `liveCalibration` 更新时调用 `build_model_transforms` 并缓存矩阵（`calib_seq` 变化才重算）；`wide_warp_physical` 从 `Params().get_bool("CalibWideWarpPhysical")` 注入。
- **该文件当前有 187 行未提交的 fork 改动（imx390 适配），必须全部保留，只改 warp 相关段。**

- [ ] **Step 1: 写失败测试**（把 §7.1 的 after 逻辑提取成被测函数）

```python
# openpilot/selfdrive/modeld/tests/test_modeld_warp.py
import numpy as np
from openpilot.selfdrive.modeld.modeld import build_model_transforms
from openpilot.common.transformations.model import get_warp_matrix

def _lc_msg():
  from openpilot.cereal import messaging
  msg = messaging.new_message('liveCalibration')
  lc = msg.liveCalibration
  lc.calibSchemaVersion = 1; lc.calibSeq = 3
  lc.init('cams', 2)                      # R3: init()，不是 .add()
  vals = {0: (2637., 2637., [0., 0.05, 0.01]), 1: (564.6, 564.6, [0., 0., 0.03])}
  for cid in (0, 1):
    fx, fy, rpy = vals[cid]
    c = lc.cams[cid]; c.id = cid; c.intrinsics = [fx, fy, 960., 540.]; c.rpy = rpy
  return msg

def test_build_transforms_gate_off_matches_old_modeld():
  # 旧 modeld 公式对照：main=wide 时用 ecam intrinsics + rpyCalib
  intr_wide = np.array([[564.6, 0, 960.], [0, 564.6, 540.], [0, 0, 1.]])
  main, extra = build_model_transforms(_lc_msg(), main_wide_camera=True, wide_warp_physical=False)
  old_main = get_warp_matrix(np.array([0., 0.05, 0.01]), intr_wide, False)
  old_extra = get_warp_matrix(np.array([0., 0.05, 0.01]), intr_wide, True)
  assert np.allclose(main, old_main) and np.allclose(extra, old_extra)

def test_build_transforms_gate_on_uses_wide_rotation():
  main, _ = build_model_transforms(_lc_msg(), main_wide_camera=True, wide_warp_physical=True)
  legacy = get_warp_matrix(np.array([0., 0.05, 0.01]),
                           np.array([[564.6, 0, 960.], [0, 564.6, 540.], [0, 0, 1.]]), False)
  assert not np.allclose(main, legacy)
```

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 重构 modeld**：抽出 `build_model_transforms(lc_msg, main_wide_camera, wide_warp_physical)`；主循环 `liveCalibration` 分支改为调用并缓存（`calib_seq` 变化才重算）；删 `DEVICE_CAMERAS`/`get_warp_matrix`/`device_from_calib_euler`/trim 代码路径（spec §7.1）；**保留 187 行既有 fork 改动**。

- [ ] **Step 4: 运行确认通过**

Run: `cd /data/openpilot && python -m pytest openpilot/selfdrive/modeld/tests/test_modeld_warp.py openpilot/selfdrive/modeld/tests/test_camera_sync.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add openpilot/selfdrive/modeld/modeld.py openpilot/selfdrive/modeld/tests/test_modeld_warp.py
git commit -m "refactor(camera-calib): modeld 切 warp_matrix（P1，wide 默认旧语义）"
```

---

## Task 11: 消费端收尾 + 全量静态扫描（P1 gate 清零）

**Files:**
- Modify: `openpilot/ui/onroad/augmented_road_view.py`（§7.2）
- Modify: `openpilot/ui/onroad/model_renderer.py`（§5.2）
- Modify: `openpilot/selfdrive/monitoring/policy.py:110`（B11）
- Modify: `openpilot/selfdrive/locationd/helpers.py`、`locationd.py`（§5.2）
- Modify: `openpilot/selfdrive/selfdrived/*`（calStatus 归约，§5.2）
- Modify: `openpilot/selfdrive/test/test_no_direct_calib_readers.py`（放开全量扫描）
- Test: `openpilot/selfdrive/test/test_no_direct_calib_readers.py`

**Interfaces:**
- Consumes: Task 3 `from_live_calibration`/`to_json`、Task 1 `camera_from_calib`/`K`/`device_from_calib`。
- Produces: `selfdrive/` 与 `ui/` 下 `rpyCalib`/`wideFromDeviceEuler`/`DEVICE_CAMERAS[`/`"CalibrationParams"` 全部走白名单；spec §10.6 全量扫描生效。

- [ ] **Step 1: 逐个迁移消费端**（每个文件一个 sub-step，核心用同一 helper）：

1. `augmented_road_view.py`：`_update_calibration` 保存 `CameraCalibSet`+`seq`；`_calc_frame_matrix` 用 `camera_from_calib(cam)`/`K(cam)`；缓存 key 改 `calib_seq`（spec §7.2）。
2. `model_renderer.py`：`set.height`/`camera_from_calib(ROAD)`。
3. `monitoring/policy.py:110`：删除 `DEVICE_CAMERAS[("tici","ar0231")].dcam`，改用 `set.K(DCAM)`/`identity.size(DCAM)`（B11，spec §12）。
4. `locationd/helpers.py` + `locationd.py`：删本地 `rot_from_euler(rpyCalib)`，用 `device_from_calib`/`calib_from_device`。
5. `selfdrived.*`：`calStatus` 改为逐路 `valid` 聚合视图；去旋转取对象。

每处改完跑一次该模块冒烟（`python -c "import ..."` + 若有单测跑之）。

- [ ] **Step 2: 放开全量扫描**：`test_no_direct_calib_readers.py` 改为全 `selfdrive/`、`ui/`、`common/`、`system/` 扫描（排除 `calibrationd.py`、`camera_calib.py`、`intrinsic_calibd.py` 迁移完成后的残留标注、迁移代码 `# calib-legacy-allow`、只按 key 名备份/擦除的 server 文件、`tools/`、`*test*`、`*replay*`、`cereal/gen`, spec §10.6）。白名单外命中即失败。

- [ ] **Step 3: 运行扫描确认清零**

Run: `cd /data/openpilot && python -m pytest openpilot/selfdrive/test/test_no_direct_calib_readers.py -q`
Expected: PASS（无白名单外命中）

- [ ] **Step 4: 提交**

```bash
git add ui/onroad/augmented_road_view.py ui/onroad/model_renderer.py selfdrive/monitoring/policy.py selfdrive/locationd/helpers.py selfdrive/locationd/locationd.py selfdrive/selfdrived/ selfdrive/test/test_no_direct_calib_readers.py
git commit -m "refactor(camera-calib): 全部消费端切 CameraCalibSet，全量静态扫描清零 (P1)"
```

---

## Task 12: `calibrationd` 消费候选 + 影子模式（P2 收尾）

**Files:**
- Modify: `openpilot/selfdrive/locationd/calibrationd.py`
- Test: `openpilot/selfdrive/locationd/test/test_calibrationd.py`

**Interfaces:**
- Consumes: Task 8 `cameraCalibCandidate`、Task 5 的写盘路径。
- Produces（spec §5.1 第 2/3 项；R6——门限是实例属性，不碰 `__init__` 签名）:

```python
sm = messaging.SubMaster(['cameraOdometry','carState','deviceState','roadCameraState','cameraCalibCandidate'], poll='cameraOdometry')
# Calibrator 新增实例属性（main() 从 Params 注入）
self.apply_auto_intrinsics: bool = True    # EnableCameraIntrinsicsAutoCalib
self.shadow_only: bool = False             # EnableCameraCalibShadow
def handle_calib_candidate(self, generation: int, cam_entries: list[dict]) -> None
```

行为：
- 只在 `apply_auto_intrinsics=True` 时应用内参候选到 `cams[ROAD/WIDE]`（`source=AUTO` 的路才接受；DCAM 永不接受——spec §5.1 第 5 项）；
- `shadow_only=True` 时只统计落 `cloudlog` 不写（spec §8）；
- 候选在 `handle_cam_odom` 同周期合并，随 `write_this_cycle` 触发 `seq += 1`；
- 内参硬限幅（spec §6.5）：`|fx/fx0−1| ≤ 0.08`、`|cx/W−0.5| ≤ 0.05`，越界整次丢弃；
- `main()` 里从 `Params` 读两个开关注入实例属性。

- [ ] **Step 1: 写失败测试**（追加到 test_calibrationd.py）

```python
def test_candidate_merge_applies_within_limits():
  c = _calibrator_with_set()
  # fx 偏移 +3% 在限幅内
  c.handle_calib_candidate(gen=1, cam_entries=[{"id": 0, "intrinsics": [2637.0*1.03, 2637.0, 960., 540.],
                                                "blocks": 12, "rmsReproj": 0.4, "mode": "joint_lsq", "std": 0.5, "span": 0.02}])
  assert abs(c.calib_set.cams[Cam.ROAD].fx / 2637.0 - 1.03) < 1e-9

def test_candidate_out_of_limits_rejected():
  c = _calibrator_with_set()
  fx_before = c.calib_set.cams[Cam.ROAD].fx
  c.handle_calib_candidate(gen=1, cam_entries=[{"id": 0, "intrinsics": [2637.0*1.2, 2637.0, 960., 540.],
                                                "blocks": 12, "rmsReproj": 0.4, "mode": "joint_lsq", "std": 0.5, "span": 0.02}])
  assert c.calib_set.cams[Cam.ROAD].fx == fx_before

def test_candidate_disabled_when_attrib_off():
  c = _calibrator_with_set()
  c.apply_auto_intrinsics = False
  fx_before = c.calib_set.cams[Cam.ROAD].fx
  c.handle_calib_candidate(gen=1, cam_entries=[{"id": 0, "intrinsics": [2637.0*1.05, 2637.0, 960., 540.],
                                                "blocks": 12, "rmsReproj": 0.4, "mode": "joint_lsq", "std": 0.5, "span": 0.02}])
  assert c.calib_set.cams[Cam.ROAD].fx == fx_before  # 门限关，不应用

def test_dcam_entry_never_accepted():
  c = _calibrator_with_set()
  fx_before = c.calib_set.cams[Cam.DCAM].fx
  c.handle_calib_candidate(gen=1, cam_entries=[{"id": 5, "intrinsics": [1.0, 1.0, 1., 1.],
                                                "blocks": 1, "rmsReproj": 0., "mode": "x", "std": 0., "span": 0.}])
  assert c.calib_set.cams[Cam.DCAM].fx == fx_before    # R11：断言未变，而非恒真的 extrinsic_valid
```

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现** `handle_calib_candidate` + main() 订阅扩展 + 门限/影子分支。

- [ ] **Step 4: 运行确认通过**

Run: `cd /data/openpilot && python -m pytest openpilot/selfdrive/locationd/test/test_calibrationd.py openpilot/selfdrive/locationd/test/test_camcalibd.py -q`
Expected: PASS（全部）

- [ ] **Step 5: 提交**

```bash
git add openpilot/selfdrive/locationd/calibrationd.py openpilot/selfdrive/locationd/test/test_calibrationd.py
git commit -m "feat(camera-calib): calibrationd 消费 camcalibd 候选（门限+影子+DCAM 护栏） (P2)"
```

---

## Task 13（收尾）: 现存故障修复（B6/B7/B8）与全量回归

**Files:**
- Modify: `openpilot/selfdrive/carrot/web/js/realtime/home_drive.js`（sensor 枚举 + imx390 档位，B6）
- Modify: `openpilot/selfdrive/carrot/web/js/realtime/raw_capnp.js:372`（enum 补 `"imx390"`，B6）
- Modify: `openpilot/tools/replay/ui.py`（B7：`("pc","imx390")` KeyError）
- Modify: `openpilot/selfdrive/carrot/signal_stop_prepare_runtime.py`（B8：尺寸门控 `(1344,760)`）
- Test: 无新单测（web JS 不在 pytest 范围）；B7/B8 各加一条轻量断言或手动验证脚本

**Interfaces:**
- Consumes: 无新接口（纯 bugfix，spec §18.2 B6/B7/B8、§12 表）。
- Produces: 本机 `("pc","imx390")` 下 web AR 可渲染、replay 不 KeyError、signal_stop 生效。

- [ ] **Step 1: `home_drive.js`** 的 `ROAD_CAMERA_PROFILES` 增 `imx390: {1928→1920, 1208→1080, 2648.0*1920/1928}`；`selectRoadCameraProfile` 的 sensor 枚举补映射 `4: "imx390"`；`raw_capnp.js:372` 枚举追加 `"imx390"`（B6）。
- [ ] **Step 2: `tools/replay/ui.py`**（R12 最小修复）：当前 `DEVICE_CAMERAS[("tici", sensor)]` 改为按 `deviceState.deviceType` 取键 + `("unknown","ar0231")` 回退，消除 `("pc","imx390")` KeyError；**不**迁移到 `cams[]`（旧 rlog 无该字段，改了只会把 KeyError 变成空集）。
- [ ] **Step 3: `signal_stop_prepare_runtime.py`**：`fcam.size == (1344,760)` 尺寸门控删除，改用 `K(ROAD)` 尺寸无关判断（B8）。
- [ ] **Step 4: 全量回归**（Python 侧）

Run: `cd /data/openpilot && python -m pytest openpilot/common/transformations/tests/test_camera_calib.py openpilot/cereal/messaging/tests/test_services.py openpilot/selfdrive/modeld/tests/test_camera_sync.py openpilot/selfdrive/modeld/tests/test_modeld_warp.py openpilot/selfdrive/locationd/test/ openpilot/selfdrive/test/test_no_direct_calib_readers.py -q`
Expected: 全 PASS

- [ ] **Step 5: 提交**

```bash
git add openpilot/selfdrive/carrot/web/js selfdrive/carrot/realtime/vision_compact.js openpilot/carrot/realtime/compact_state.py tools/replay/ui.py selfdrive/carrot/signal_stop_prepare_runtime.py
git commit -m "fix(camera-calib): 现存故障 B6/B7/B8（web AR/replay/signal_stop）"
```

---

## 提交顺序与依赖

1. Task 1（模型，纯 Python）
2. Task 2（capnp + scons）
3. Task 3（工厂/序列化/迁移，依赖 1+2）
4. Task 4（params，独立）
5. Task 5（calibrationd 写盘，依赖 3）
6. Task 6（扫描门禁初版，依赖 3）
7. Task 7（camera_sync，独立）
8. Task 8（camcalibd，依赖 2/7）
9. Task 9（process_config，依赖 8）
10. Task 10（modeld P1，依赖 3）
11. Task 11（消费端 + 全量扫描，依赖 3/10）
12. Task 12（candidate 合并，依赖 5/8）
13. Task 13（bugfix + 回归，依赖全部）

每完成一个可独立提交、独立测试；P0=P1（Task 1-6）跑通后即可在设备灰度，P1=P2（Task 7-13）在影子期验证。