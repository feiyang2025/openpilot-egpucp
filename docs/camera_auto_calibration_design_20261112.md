# 前视双路摄像头内参/外参自动校准方案

## 1. 背景

当前 openpilot 对前视两路摄像头（road 窄角、wide 广角）的标定分为两块，彼此独立：

| 内容 | 当前位置 | 形式 |
| --- | --- | --- |
| 内参 | `openpilot/common/transformations/camera.py` 的 `DEVICE_CAMERAS` | 按 `(deviceType, sensor)` 硬编码的 `fx = fy = focal_length`、`cx = W/2`、`cy = H/2`，无畸变；本仓库已有 `("pc", "imx390")` 条目（1920×1080，f≈2637/564.6） |
| 内参/安装俯仰的在线估计 | `openpilot/selfdrive/carrot/intrinsic_calibd.py`（v4.1） | 路面 ROI 车道线 → `HoughLinesP` + RANSAC 求消失点 → 稳健 LSQ 联合估 `f` 与 `pitch_offset`，按 `EMIT_INTERVAL=10 s` 尝试写 Params `CamCalibRoad`/`CamCalibWide`（JSON，但**这两个 key 从未注册进 `params_keys.h`，启动即抛 `UnknownKeyName`**，见 §5.1）；**未注册进 `process_config.py`**。另有 `common/transformations/video_camera_calibration.py` 为这两个 key 写了带范围校验的解析器（`f/pitch_offset/yaw_offset/x_shift_px/x_shear`，仅 `USE_WEBCAM` 视频台架生效），但**无任何调用方**；也就是说产物格式已经设计好，链路却没接通 |
| 外参（road 相对车体/路面） | `calibrationd.py` 的 `rpyCalib`、`height` | 运行时估计，存入 `Params["CalibrationParams"]` |
| 外参（wide 相对 road） | `calibrationd.py` 的 `wideFromDeviceEuler` | 取 `cameraOdometry.wideFromDeviceEuler`（模型输出），经块内 `moving_avg_with_linear_decay` 平滑后写入 `LiveCalibrationData`，与 `rpyCalib` 分开存储 |
| 消费方式（模型） | `modeld.py:520-533` | 每次 `liveCalibration` 更新时用 `rpyCalib` + `dc.fcam/ecam.intrinsics` 现算 warp |
| 消费方式（UI） | `ui/onroad/augmented_road_view.py:224-231` | 自己再组合 `view_from_device @ wide_from_device @ device_from_calib` |
| 消费方式（设置页） | `ui/layouts/settings/device.py:103-129` | 直接解析 `CalibrationParams` 的 capnp 字节 |
| 消费方式（DM/监控路径） | `dmonitoringmodeld.py`、`monitoring/*`、`impact_detector.py` | 读 `rpyCalib` 做面部姿态/碰撞去旋转；`monitoring/policy.py:110` 另把 dcam 内参写死为 `DEVICE_CAMERAS[("tici","ar0231")].dcam`（本项目 `("pc","imx390")` 下取到错条目） |
| 消费方式（位姿链） | `locationd.py`、`locationd/helpers.py`、`selfdrived.py` | 用 `rpyCalib` 构造 `device_from_calib` |
| 消费方式（web AR / cluster） | `selfdrive/carrot/web/js/realtime/home_drive.js`、`selfdrive/carrot/cluster/cluster_renderer.py` | `home_drive.js` **复制**了一份 `DEVICE_CAMERAS` 内参表并与 `rpyCalib`/`height` 在浏览器内拼接，是真正的"第二份真值"；`cluster_renderer.py` 直接 `import DEVICE_CAMERAS`（非副本），但仍自行组合 `view_from_device` 与 `rpyCalib`，属于"第二处组合逻辑" |
| 时间同步 | panda `board/drivers/clock_source.h` 的 FSIN（spectra 路径）+ 模组 `FSN`（Orin） | spectra：硬件触发 20 Hz 同相 + 首帧 0.2 ms 校验，运行期不监测；**Orin：模组支持帧同步（IMX390 `FSN` ← MAX9295A MFP7），但 camerad 未配置，当前自由运行，时间戳为 V4L2 收帧戳**。v1 先按系统时钟微秒级交付（§16.4 T0），详见 §16 |

由此产生的问题：

1. **内参在消费链上仍是硬编码**：`DEVICE_CAMERAS` 的 `fx/fy` 同值、主点强制在图像中心。仓库里其实已有在线估计器 `intrinsic_calibd.py`（消失点 + 稳健 LSQ），但它**没被 `process_config` 拉起**，写出的 `CamCalibRoad/CamCalibWide` 也只有一个从未被调用的视频台架解析器，等于不存在；同型号不同模组的镜头差异、装配公差、更换摄像头后依然无法补偿。长焦下几个像素的误差会直接变成车道横向偏差。
2. **外参被拆成三段**（`rpyCalib`、`wideFromDeviceEuler`、`height`），每处消费代码都要自己组合，组合顺序与坐标约定各写一遍。`modeld` 对 wide 直接复用 `rpyCalib` 而只换内参，**完全忽略 `wideFromDeviceEuler`**；UI 则额外乘 `wide_from_device`。同一个量在两条路径上语义不同，这是本方案要消除的核心问题之一。
3. **没有单一数据源**：参数 key、capnp 字段、硬编码表三处都可影响结果；`CameraYawTrimDeg` 在两条链路上语义不同且互不知情——`modeld` 在 warp 前把它从 yaw 里减掉（`modeld.py:523-527`，仅 `calibrated` 时生效），`calibrationd` 则在 trim 非零且已标定时**整体冻结** `handle_cam_odom`（`calibrationd.py:284-285`，rpy/height/wide 都不再更新）。同一参数控制两种行为，属于补丁式叠加。
4. **字节格式无版本、无校验**：`CalibrationParams` 是 capnp `Event` 字节，缺字段时落到默认值，字段含义变化无感知；分辨率/传感器变化后旧值仍会被使用。
5. **无逐相机状态与置信度**：只有全局 `calStatus`，无法表达"road 已收敛、wide 尚未"或"内参已锁定、外参仍在跟踪"。
6. **异常恢复能力弱**：参数损坏、换摄像头、改分辨率都只能靠用户手动"Reset Calibration"。
7. **消费端数量被低估**：实际读标定值的不止模型与两处 UI，还有 DM/monitoring、locationd 位姿链、controlsd/selfdrived/paramsd/lagd/torqued（经 `PoseCalibrator.feed_live_calib`）、cluster、web AR、server/WebRTC 等 15 处以上；其中 web `home_drive.js` 复制了一份 `DEVICE_CAMERAS` 内参表，`cluster_renderer.py` 虽直接 import 共享表却自己再拼一遍投影，等于多出至少两套组合逻辑。**这种副本会立刻漂移**：本次同步新加的 `("pc","imx390")` 只进了 Python 表，`home_drive.js` 的内参表与 `raw_capnp.js` 的 sensor 枚举都还是旧的（`imx390` 在枚举里是第 4 项，JS 侧只映射到 3 项），web AR 在本项目上直接解析不出 profile、不渲染。
8. **时间同步能力按平台分裂**：comma 的 spectra 路径有三路同相的 panda FSIN 硬件触发，但定时器分辨率 0.1 ms、只在启动时校验一次（超时仅打日志）；**本项目 Jetson/Orin 的相机模组本身支持帧同步**（SG2-IMX390C-5200-GMSL2：IMX390 `FSN` ← MAX9295A MFP7，规格书写明 "Multi-Camera synchronization Support"），**但 `camera_jetson.cc` 从未配置 MFP7/FSIN**，相机按自由运行出帧，`timestampSof/timestampEof` 都等于 V4L2 收帧时间戳（1 µs 量化）。即系统有 ns 分辨率的时钟刻度，模组也有同步能力，缺的是"启用它"。v1 因此先按**系统时钟微秒级**路线交付（§16.4 T0），T1（启用硬件触发）只留接口。详见 §16。

本方案把两路相机的内参/外参收敛到**一个数组 + 一个版本号 + 一个写入者**，所有消费端（含跨进程端）全部从同一对象或唯一 JSON 网关派生投影矩阵。

## 2. 目标与非目标

目标：

- 一个按 `CamId` 索引的可变长数组 `cams[]` 保存每路相机**各自独立**的内参与外参，作为唯一数据源（single source of truth）。v1 含 `ROAD/WIDE`（`AUTO`，参与在线估计）与 `DCAM`（`PRIOR`，只带工厂内参、`extrinsic_valid=False`）；`LEFT/RIGHT/REAR` 已预留条目，加入时按 §14.1 逐路独立，不共享任何参数。
- 所有消费方（modeld 的 warp、UI 的相机视图投影与路径绘制、DM/monitoring、locationd 位姿链、selfdrived 告警、设置页状态展示，以及 web/cluster/server 等跨进程端）只读同一个对象，通过同一组派生函数或唯一 JSON 网关得到参数，禁止各自组合。
- 对"是否还有第二份真值"给出可执行判定：运行时不得直读 `rpyCalib / wideFromDeviceEuler / DEVICE_CAMERAS`，由 §10.6 静态扫描门禁强制。
- 上路后自动估计并持续精化：路面/行驶姿态 `body_from_calib` 与 `height`、每路相机安装外参 `cams[i].rpy`（v1 含 wide 相对 road）、两路内参。**复用而非重写**现有 `intrinsic_calibd.py` 的消失点 + 稳健 LSQ 估计器：先收敛安装俯仰（该文件实测表明这是当前链路上真正错位的量），再用车道几何约束精化 `f`。
- 让"两路帧的时间关系"可测量、可对齐、可标注：v1 **统一以系统时钟（`CLOCK_BOOTTIME`，ns 刻度、V4L2 收帧戳 1 µs 量化）为唯一时基**，做逐帧时间差监测 + 帧对筛选 + IMU 姿态时间对齐，交付"系统时钟微秒级"档（§16.3 T0）；硬件触发（FSIN）与绝对时间（1PPS/gPTP）作为 T1/T2 只预留接口，不列入 v1 交付。
- 写入只有一个入口；任何校准结果都要过门限、限幅、连续性检查后才落盘。
- 与现有 `CalibrationParams` 双向兼容，可灰度、可回滚，回滚后行为与原版逐位一致。

非目标（本期不做）：

- 不做鱼眼/广角畸变模型的在线估计（字段预留，v1 固定为 0，见 §6.6）。
- 不改相机分辨率、不做 camerad 端去畸变。
- 不做 DCAM（驾驶员监控）的在线标定：它进入 `cams[]` 但只带工厂内参（`source=PRIOR`、`extrinsic_valid=False`），不参与任何观测器；目的是让 DM 链路也停止直读 `DEVICE_CAMERAS[...].dcam`，而不是给它估计外参。
- 不引入新的定位/建图算法，仍以现有 `cameraOdometry` + 车道几何为约束来源。
- 不在 v1 引入因子图/在线 BA、车队先验、温度/卷帘建模等进阶项；它们列在 §15，按优先级在 v1.1/v2 单独评估，不阻塞 v1。
- 不在 v1 接入硬件触发（FSIN/FSYNC）与纳秒级绝对时间（GNSS 1PPS / gPTP）：模组本身已支持帧同步（IMX390 `FSN` ← MAX9295A MFP7），但当前驱动未配置、Orin 侧也无 1PPS/PTP 代码。v1 只交付系统时钟微秒级（§16.3 T0）；T1/T2 只定义接口、字段与验收条件，等驱动与触发源就绪再开。

## 3. 总体架构

```
                       ┌──────────────────────────────┐
   VisionIPC(road/wide)│  camcalibd (升级 intrinsic_calibd)│
   cameraOdometry ────►│  L1 角速度对齐 / L3 内参拟合  │
   cameraSyncState ───►│  同步不达标 → 不采样          │
                       └──────────────┬───────────────┘
                                      │ cameraCalibCandidate (msg)
                                      ▼
   cameraOdometry ────►┌──────────────────────────────┐
   carState       ────►│  calibrationd (唯一写入者)     │──► Params["CalibrationParams"]
                       │  合并 + 门限 + 限幅 + 持久化   │    （同一 Event，新增 cams[] 字段）
                       └──────────────┬───────────────┘
                                      │ liveCalibration (含 cams[] + seq)
        ┌──────────────┬──────────────┼───────────────┬─────────────────┐
        ▼              ▼              ▼               ▼                 ▼
  modeld warp    UI 投影/绘制   DM/locationd    settings 状态/重置   to_json 网关
  (同一 helper)  (同一 helper)  (同一 helper)   (只读 + 删 key)     (web/cluster/server)
```

五条硬规则：

1. **唯一写入者**：只有 `calibrationd` 能写 `CameraCalibSet`。`camcalibd` 只发布候选，`modeld`/UI 只读。
2. **唯一对象**：所有派生矩阵必须经由 `common/transformations/camera_calib.py` 的 `CameraCalibSet` 方法获得，不允许再直接读 `DEVICE_CAMERAS` 拼矩阵。
3. **版本驱动刷新**：消费方以 `seq`（单调递增写入计数）为缓存键，只有 `seq` 变化才重算矩阵。
4. **参考系统一为 body，数组可扩展**：每路相机只存"相对车体（body/IMU 对齐系）"的内外参，`cams` 是按 `CamId` 索引的可变长列表；新增左/右/后相机时只追加条目与观测器，不改消费侧（见 §14）。
5. **跨进程端只有一个序列化出口**：无法 import Python 对象的端（web/cluster/server）经 `to_json` 网关取数，不得镜像内参或逐字段转发旧 key（§4.4、§7.4）；由 §10.6 静态扫描强制。

## 4. 数据结构

### 4.1 单相机

```python
# openpilot/common/transformations/camera_calib.py
from enum import IntEnum

class Cam(IntEnum):
  ROAD = 0
  WIDE = 1
  LEFT = 2     # 预留：左视
  RIGHT = 3    # 预留：右视
  REAR = 4     # 预留：后视
  DCAM = 5     # 驾驶员监控：只带工厂内参，不做在线估计（extrinsic_valid=False）

@dataclass(frozen=True)
class CameraCalib:
  uid: str                # 位置+序列号，例如 "road:IMX390-1234"；用于热插拔与换模组检测

  # --- 图像尺寸：用于校验参数是否仍适用于当前码流 ---
  width: int
  height: int

  # --- 内参（针孔）---
  fx: float
  fy: float
  cx: float
  cy: float
  dist: np.ndarray        # shape (5,): k1,k2,p1,p2,k3；v1 固定全 0

  # --- 外参：该相机相对 body（车体/IMU 对齐系）的旋转 ---
  rpy: np.ndarray | None  # shape (3,)，即 cam_i_from_body；None = 无外参（DCAM）
  mount_height: float | None   # 该相机相对地面/车体基准的安装高度；ROAD 有值，其余 v1 为 None
  extrinsic_valid: bool   # rpy/mount_height 是否是"可用外参"；DCAM 为 False

  # --- 状态与质量 ---
  valid: bool             # 该路当前是否可用（码流存在、identity 匹配）
  source: CalibSource     # FACTORY / PRIOR / AUTO / MANUAL
  blocks: int             # 已累积的有效块数
  rms_reproj: float       # 像素 RMS 重投影误差，用于置信度
  spread: np.ndarray      # shape (3,)，块间离散度
  updated_at_ns: int      # 最近一次被写入的单调时间
```

字段说明：

- `fx/fy/cx/cy` 直接对应 `K`，不再写 `focal_length` 单一值；允许非方形像素以匹配模组差异。
- `rpy[0]`（roll）在 v1（前视双路）继续固定为 0：现有链路假设 roll 为 0，模型 warp 也未校正 roll。加入侧/后视时放开三轴，由 §6.1 的陀螺-光流求解（不同朝向的相机无法再用"roll=0"的假设）。
- `rpy` 一律是 **body 系 → 该相机系** 的旋转，与相机数量、朝向无关；相对外参 `cam_i_from_cam_j = R_i · R_j^T` 随时可算，无需额外字段。
- `mount_height` 是**逐相机**安装高度。现有 `liveCalibration.height` 只是 road 相机的量，不能当作全局值；加入侧/后视或 DCAM 后必须各存各的（集合顶层的 `height` 仅作为 road 的向下兼容镜像保留，见 §4.2）。
- `extrinsic_valid` 明确区分"有这一路参数"和"这一路的外参可用"：DCAM 是 `False`（只有工厂内参，`rpy` 无物理意义），LEFT/RIGHT/REAR 在观测器收敛前也是 `False`。任何投影代码必须先查这个标志，禁止用默认 0 外参硬算。
- `source=PRIOR` 表示"来自工厂/先验、从未在线估计"；`FACTORY` 是内置默认表，`AUTO` 是观测器写入，`MANUAL` 是人工偏置（如 `CameraYawTrimDeg`）。`blocks=0` 且 `source=PRIOR` 的条目不得被 UI 显示成"已标定"。
- 投影到图像还需要 body 与 calib（路面/行驶系）之间的旋转，该量属于"车体相对路面"，放在集合顶层 `body_from_calib`，不放进单相机条目，避免每路重复存储同一份数据。
- `uid` 用于检测换模组/热插拔：`uid` 变化即该路外参/内参全部作废，回退工厂值。
- `rms_reproj`、`spread` 是落盘门限的判据，也是 UI 展示"标定质量"的依据。
- `dist` 预留，v1 恒为 0；写入非零值需要同时打开 `EnableCameraDistortionCalib`，默认关闭。

### 4.2 标定集合（唯一数据源）

```python
@dataclass(frozen=True)
class CameraCalibSet:
  schema_version: int          # 结构版本，v1 = 1
  seq: int                     # 写入计数，消费者缓存失效用
  identity: CalibIdentity      # device_type / sensor / 各路口径图像尺寸
  height: float                # 兼容字段：仅等于 cams[ROAD].mount_height，禁止其他相机复用
  body_from_calib: np.ndarray  # shape (3,)，body 相对 calib（路面/行驶系）的旋转；v1 即现有 rpyCalib
  cams: list[CameraCalib]      # 按 CamId 索引，长度可变；v1 含 ROAD/WIDE/DCAM（DCAM 为 PRIOR）
  wide_warp_physical: bool = False  # 消费策略（构造时从 Params["CalibWideWarpPhysical"] 注入），不进入消息（§4.3）
```

`body_from_calib` 与 `cam_i.rpy` 的分工：

```
p_body = R_body_from_calib · p_calib
p_img_i = K_i · view_from_device · R_cam_i_from_body · p_body
```

- `body_from_calib` 由 `calibrationd` 的路面/行驶方向估计（会随载重、坡道路面变化）；
- `cam_i.rpy` 是安装外参，近似常量，只在换模组或慢漂移时变化；
- v1 取 `cam_ROAD.rpy = 0`、`cam_WIDE.rpy = wideFromDeviceEuler`，`body_from_calib = rpyCalib`，与现有行为数值等价（见 §5.3）。

`identity` 是防呆字段：

```python
@dataclass(frozen=True)
class CalibIdentity:
  device_type: str   # deviceState.deviceType
  sensor: str        # roadCameraState.sensor
  sizes: dict[CamId, tuple[int, int]]   # 逐路口径，未接入的相机不出现
```

读取时若 `identity` 与当前设备/码流不符，视为**不适用**，整体回退工厂值并标记 `invalid`，不再使用旧参数。

### 4.3 派生矩阵（唯一实现）

```python
class CameraCalibSet:
  def K(self, cam: Cam) -> np.ndarray:
    c = self.cams[cam]
    return np.array([[c.fx, 0.0, c.cx],
                     [0.0, c.fy, c.cy],
                     [0.0, 0.0, 1.0]], dtype=np.float64)

  def camera_from_body(self, cam: Cam) -> np.ndarray:
    # body 系 -> 该相机 view 系的 3x3 投影旋转部分
    return view_frame_from_device_frame @ rot_from_euler(self.cams[cam].rpy)

  def camera_from_calib(self, cam: Cam) -> np.ndarray:
    # calib(路面/行驶) 系 -> 相机 view 系；唯一组合点，消费侧不得自行拼接
    return self.camera_from_body(cam) @ rot_from_euler(self.body_from_calib)

  def device_from_calib(self) -> np.ndarray:
    # 仅车体级旋转，供 locationd / selfdrived / DM 使用（不含相机安装角）
    return rot_from_euler(self.body_from_calib)

  def calib_from_device(self) -> np.ndarray:
    return rot_from_euler(self.body_from_calib).T

  def warp_matrix(self, cam: Cam, bigmodel_frame: bool = False) -> np.ndarray:
    # 模型输入 warp（不含平移）。默认与现有 modeld 逐位一致：
    # 现有 modeld 对 wide 只用 rpyCalib（body_from_calib），从未乘 wideFromDeviceEuler，
    # 所以 wide 的物理安装外参必须由 CalibWideWarpPhysical 显式打开（见 §7.1）。
    calib_from_model = calib_from_sbigmodel if bigmodel_frame else calib_from_medmodel
    rpy_cam = self.cams[Cam.ROAD].rpy if (cam == Cam.WIDE and not self.wide_warp_physical) else self.cams[cam].rpy
    camera_from_body = view_frame_from_device_frame @ rot_from_euler(rpy_cam)
    return (self.K(cam) @ camera_from_body @ rot_from_euler(self.body_from_calib) @ calib_from_model).astype(np.float32)

  def project_calib_points(self, cam: Cam, pts_calib: np.ndarray) -> np.ndarray:
    # UI/诊断用完整投影：先转到 view 系，再乘 K
    ...
```

- `warp_matrix` 的入参由"euler + intrinsics"变成"cam 索引"，`modeld` 不再感知 `DEVICE_CAMERAS`。
- `warp_matrix` 的 wide 分支受 `wide_warp_physical` 控制：该值在构造 `CameraCalibSet` 时从 `Params["CalibWideWarpPhysical"]` 注入（默认 false），**不写入 `liveCalibration` 消息**——它是消费策略而非标定值，序列化它会让不同进程对同一份标定读出不同 warp。`true` 时 wide 用 `cams[WIDE].rpy`（物理外参），`false` 时**旋转部分**退回 `cams[ROAD].rpy`（旧 modeld 语义），内参始终取 `K(WIDE)`。这就是 §7.1 P1/P2 的开关落点。
- `camera_from_body` 与 `camera_from_calib` 是两段不同语义：前者是安装外参（逐路常量），后者引入路面姿态（全局随时间变化）。消费侧只调用需要的那一个，禁止在外部再做矩阵乘法。
- `camera_from_body`/`camera_from_calib`/`warp_matrix` 在 `cams[cam].extrinsic_valid == False` 时必须抛异常（而不是返回单位阵）：DCAM 只有内参，任何"顺带算出来"的投影都会把 0 外参当成真值。需要 dcam 投影的代码只能用 `K(DCAM)` 自建（例如面部反投影到归一化平面），不得走 `camera_from_calib`。
- `project_calib_points` 是 UI 与离线工具的唯一投影入口，`augmented_road_view` 只保留裁剪/缩放逻辑。
- 平移（相机光心偏移）v1 不参与投影，与现状一致；`height` 仍单独用于模型路径的 z 偏移，避免引入未验证的透视变化。

### 4.4 序列化

**消息**：在 `cereal/log.capnp` 的 `LiveCalibrationData` 上追加字段（不改既有字段编号），保证一条消息内两路相机与状态原子一致：

```capnp
struct CameraCalib {
  id @0 :UInt8;                   # 0=ROAD 1=WIDE 2=LEFT 3=RIGHT 4=REAR 5=DCAM
  uid @1 :Text;                   # 位置+序列号，换模组检测
  width @2 :UInt16;
  height @3 :UInt16;
  intrinsics @4 :List(Float32);   # [fx, fy, cx, cy]
  distortion @5 :List(Float32);   # [k1, k2, p1, p2, k3]，v1 全 0
  rpy @6 :List(Float32);          # cam_from_body；空 = 无外参（DCAM）
  valid @7 :Bool;
  source @8 :Source;
  blocks @9 :Int32;
  rmsReproj @10 :Float32;
  spread @11 :List(Float32);
  updatedAtNs @12 :UInt64;
  mountHeight @13 :Float32;       # NaN = 无（wide/dcam/未标定的侧后视）
  extrinsicValid @14 :Bool;       # 该路外参是否可用；DCAM false

  enum Source { factory @0; prior @1; auto @2; manual @3; }
}

struct LiveCalibrationData {
  # ... 既有字段保持不变 ...
  calibSchemaVersion @13 :UInt16;
  calibSeq @14 :UInt32;
  cams @15 :List(CameraCalib);    # 长度可变，按 id 索引；v1 为 ROAD/WIDE/DCAM 三项
}
```

`rpyCalib`（既有字段 @7）继续表示 `body_from_calib`，v1 直接复用、不新增字段；`cams[i].rpy` 才是逐相机安装外参，两者不再混用。

**持久化**：**不新增参数 key**，直接扩展现有 `Params["CalibrationParams"]`（`{PERSISTENT, BYTES}`，内容就是 `liveCalibration` Event 字节）。理由：

- `calibrationd` 已经在 `send_data()` 里写这个 key（`calibrationd.py:170` 的 `put_nonblocking`），新增字段随 `get_msg(True)` 自动落盘，不需要第二套序列化；
- capnp 前向兼容：旧代码读新字节忽略未知字段，新代码读旧字节得到默认值，回滚天然一致；
- **避免双 key 无法原子写**：`Params` 没有事务。若同时写 `CameraCalibSet` 和 `CalibrationParams`，进程在两次写之间被杀死就会留下两份不一致的参数，谁生效取决于读端——这正是本方案要消灭的"多份真值"；
- 方案早期版本曾设计 `Params["CameraCalibSet"]`，内容仍是同一条消息的字节，属于重复落盘，已删除；`schema_version` 作为消息字段（`@13`）随消息持久化，读取时按版本降级。

因此 `CalibrationParams` 不是"镜像"，它就是唯一持久化形式；`CameraCalibSet` 是它的内存投影，`to_json` 是它的 JSON 投影。

**调试/导入导出**：设置页与工具通过同一 struct 转成 JSON（只读展示，或手动导入），JSON 不参与运行时主链路，避免引入第二份真值。

**跨语言/跨进程网关（正式消费者接口）**：web AR、cluster、server 等 JS/C++/独立进程消费端**无法直接读 capnp 或 Python 对象**。为此 `camera_calib.py` 提供唯一导出函数 `to_json(CameraCalibSet) -> {seq, bodyFromCalib, height, cams: [{id, width, height, fx, fy, cx, cy, dist, rpy, mountHeight, extrinsicValid, valid, source}]}`，经既有下行通道（`carrot server` 快照 / `compact_state` / WebRTC）分发。规则：

- `cams[]` 逐路完整导出，宽度/高度/内外参/状态都按相机分开：端内不得用 road 的 `height` 或内参去顶替别的相机（DCAM、左/右/后视各自独立，见 §14.1）；
- JSON 网关是这些端**唯一**的取值入口：任何 JS/C++ 代码不得再镜像 `DEVICE_CAMERAS` 内参或自行拼接 `rpyCalib/wideFromDeviceEuler/height`（现有 `home_drive.js` 的内参镜像属于违反本规则的历史债，见 §7.4）；
- 网关输出必须带 `seq`，端内以 `seq` 为缓存键，与 Python 消费端同一套失效规则；
- 网关不引入第二份真值：它只是序列化形式，运行时主链路仍然只有 `CameraCalibSet` 一份。

## 5. 读写路径

### 5.1 写入

`calibrationd` 是唯一写入者，职责：

1. 沿用现有 `handle_cam_odom`：路面/行驶姿态写入 `set.body_from_calib`（原 `rpyCalib`），高度写入 `set.height`，模型给出的 `wideFromDeviceEuler` 仅作 `cams[WIDE].rpy` 的初值/交叉校验。
2. 新增：订阅 `camcalibd` 的 `cameraCalibCandidate`，拿到内参/相对外参候选。
3. 合并：以 `CameraCalibSet` 为单位整体更新，`seq += 1`，仍由既有 `write_this_cycle` 调 `put_nonblocking("CalibrationParams", get_msg(True).to_bytes())`——新旧字段在同一次 `to_bytes()` 内写出，不存在部分更新；`rpyCalib`/`wideFromDeviceEuler`/`height` 必须由 `get_msg` 从同一份状态派生，不允许在别处单独赋值。
4. 发布 `liveCalibration` 时填充 `cams[]`、`calibSchemaVersion`、`calibSeq`。
5. 负责 `cams[]` 的**全集**：缺失的条目由集合层补齐——`DCAM` 从工厂表取一次内参（`source=PRIOR`、`extrinsic_valid=False`、`rpy=None`、`mount_height=None`），`LEFT/RIGHT/REAR` 若未接入则不出现。候选消息只允许更新 `source=AUTO` 的路，DCAM 条目的任何字段都不接受外部写入（防止 DM 链路被"顺手标定"污染）。

写入节奏沿用现有 block 机制（`BLOCK_SIZE=100` @20Hz = 5 s/块，`INPUTS_WANTED=50`），并把现有 `write_this_cycle` 的频率从"每 10 块"改成"内容变化且通过门限时"，避免无变化时的无效写盘。

**订阅新增服务的坑（必须在实现时避开）**：`calibrationd` 现在用 `sm.all_checks()` 生成 `liveCalibration.valid`（[calibrationd.py](file:///data/openpilot_egpucp/openpilot/selfdrive/locationd/calibrationd.py#L299-L300)）。一旦把 `cameraCalibCandidate` 加进 `SubMaster`，`all_checks()` 默认会对它做频率检查；当 `camcalibd` 未启用或降频时，`valid` 会被判 false，进而影响所有读 `valid` 的消费端。因此必须写成 `sm.all_checks([...])` 并显式列出 `cameraOdometry`、`carState` 这两个既有服务，候选服务只按 `sm.updated` 取用，不参与有效性聚合。

同理，`camcalibd` 自己发布的 `cameraSyncState` 也不得进入 `calibrationd` 的检查集合——同步状态只用于 `camcalibd` 内部采样门控。

`camcalibd`（`only_onroad`）**由现有 `selfdrive/carrot/intrinsic_calibd.py` 升级而来**，不是从零新建：

- **保留**它的核心估计器：路面 ROI（`ROAD_ROI_TOP_FRAC=0.52`）取亮车道线 → `Canny` + `HoughLinesP` → RANSAC（60 次迭代、7 px 内点门限）求消失点纵坐标 `v0` → 与 `liveCalibration.rpyCalib[1]` 配对做稳健 LSQ，联合解 `f` 与安装 `pitch_offset`（退化时退到 `vp_offset` 单点反解）；`MAX_OFFSET=0.15 rad`、`MIN_LINES=20`、`MIN_SAMPLES=30`、`CONVERGE_STD=60` 等门限全部沿用；
- **先修一个致命缺陷**：`CamCalibRoad`/`CamCalibWide` 从未注册进 `common/params_keys.h`（全仓引用只有 `intrinsic_calibd.py` 与 `video_camera_calibration.py`），而 Python `Params.get/put` 会先 `check_key`，未注册直接抛 `UnknownKeyName`（[params_pyx.pyx](file:///data/openpilot_egpucp/openpilot/common/params_pyx.pyx#L100-L105)）。因此该进程即使手动启动，也会在 `__init__` 的 `seed_prior()` 处崩溃——现状不是"跑了但没效果"，而是"根本跑不起来"。迁移时要么把这两个 key 注册进 `params_keys.h` 并重建 `params_pyx`，要么按本方案删除这条写盘路径（推荐后者：产物改走 `cameraCalibCandidate`，不再需要 key）；
- **改变产物**：不再直接 `Params.put("CamCalibRoad"/"CamCalibWide")`（今天没人读，且 key 未注册），改为发布 `cameraCalibCandidate`（含 `cams[ROAD/WIDE]` 的 `K`、相对 `rpy`、`blocks`、`rms`、`mode`、`std`、`span`），由 `calibrationd` 统一合并落盘；
- **补齐订阅**：现有实现只订阅 `liveCalibration` + 两路 VisionIPC，升级后追加 `cameraOdometry`、`carState`、`cameraSyncState`（§16），并把帧对配对换成 `receive_camera_pair`；
- **帧对配对复用** `selfdrive/modeld/camera_sync.py` 的 `receive_camera_pair`（迁移到公共模块，`modeld` 与 `camcalibd` 共用），不另写第二套配对逻辑；
- **只读 NV12 的 Y 平面**并 4× 降采样到 320×180 灰度，不做颜色空间转换、不复制整帧（VisionIPC 为多播，与 `modeld` 并存不额外占用带宽）；现有实现取的是同尺寸整帧灰度，降采样是新增的算力优化；
- 在降采样帧上做稀疏光流/直线检测；
- **不碰 Params**（现有实现的 `seed_prior()` 会写一次工厂先验，迁移后这一步改为"由 `calibrationd` 用工厂值初始化对象"，避免两处写盘）；
- 以 5 Hz 运行，单帧耗时预算 < 15 ms（Orin，320×180 灰度 + LK 光流）；超预算自动降频到 2 Hz。LK 用 3 层金字塔、每帧 200 点上限、金字塔 buffer 复用；RANSAC 迭代上限 50 次。
- **注册进 `process_config.py`**：现有文件未出现在进程表（`calibrationd` 在 `L144`，`intrinsic_calibd` 没有对应条目），这是它"等于不存在"的直接原因。

### 5.2 读取

表中路径相对仓库的 `openpilot/`，例如 `selfdrive/modeld/modeld.py` 即 `openpilot/selfdrive/modeld/modeld.py`。

| 消费方 | 读取方式 | 改动 |
| --- | --- | --- |
| `selfdrive/modeld/modeld.py` | `CameraCalibSet.from_live_calibration(sm["liveCalibration"])`，缓存键 `calibSeq` | 删除 `dc.fcam/ecam.intrinsics` 与本地 `device_from_calib_euler` 组合；`CameraYawTrimDeg` 合并进外参后一次性写入对象（不再在 modeld 内二次修改）；wide 的 warp 语义按 §7.1 分阶段切换（P1 保旧语义，P2 A/B 后由 `CalibWideWarpPhysical` 打开） |
| `ui/onroad/augmented_road_view.py`（含 mici 版本） | 同一 helper，缓存键 `calibSeq` | 删除 `DEVICE_CAMERAS` 与 `wide_from_device` 组合，只保留 crop/zoom |
| `ui/onroad/model_renderer.py`（含 mici 版本） | `set.height` / `camera_from_calib(ROAD)` | 不再直接读 `liveCalibration.height`；路径 z 偏移与视角用同一对象，保证与 warp 同源 |
| `dmonitoringmodeld.py`、`monitoring/dm2d.py`、`monitoring/policy.py` | `set.body_from_calib`（替代 `rpyCalib`）+ `set.K(DCAM)` / `identity.size(DCAM)` | DM 的面部姿态反投影只需 `device_from_calib`，属于同一旋转的另一种用法；**dcam 内参从 `cams[DCAM]` 取**（`source=PRIOR`、`extrinsic_valid=False`，只做投影不做外参），删除 `monitoring/policy.py:110` 的 `DEVICE_CAMERAS[("tici","ar0231")].dcam` 硬编码（写死 tici，本项目 `("pc","imx390")` 下取到的是错条目）；**不得**用 road/wide 的内参 |
| `locationd.py`、`locationd/helpers.py` | `set.body_from_calib` | `device_from_calib` / `calib_from_device` 改由 helper 生成，删除本地 `rot_from_euler(rpyCalib)` |
| `selfdrived.py`、`selfdrived/impact_detector.py`、`selfdrived/events.py` | `calibStatus` / `set.body_from_calib` | 告警与碰撞去旋转统一取对象；`calStatus` 保留为聚合视图（由逐路 `valid` 归约得到），不再作为独立真值 |
| `selfdrive/carrot/cluster/cluster_live.py`、`cluster_route_replay.py`、`cluster_renderer.py` | 经 `to_json` 网关（§4.4） | `cluster_live`/`cluster_route_replay` 不再解析 `CalibrationParams` 字节；`cluster_renderer` 现在**直接 import 共享的 `DEVICE_CAMERAS`**（不是副本），保留它作工厂值来源，但投影改用 helper，删除 `wideFromDeviceEuler/height` 手工拼接 |
| `selfdrive/carrot/realtime/compact_state.*`、`selfdrive/carrot/server/live_runtime/snapshot.py`、`system/webrtc/carrot_state.py` | 经 `to_json` 网关 | 只做透传，不得重新解释字段；输出结构固定为 `{seq, bodyFromCalib, height, cams[]}`。**当前 `compact_state.py`/`compact_state_native.cc`/`vision_compact.js` 的字段表里没有 `wideFromDeviceEuler`**，所以 web/WebRTC 今天拿不到 wide 相对外参——网关必须一次带全，不能只补 road |
| `selfdrive/carrot/web/js/.../home_drive.js` 及 `src/.../ar/*.js` | 经 `to_json` 网关 | **删除 JS 侧的 `DEVICE_CAMERAS` 内参镜像**（历史债），浏览器内只做投影矩阵乘法；见 §7.4 |
| `selfdrive/carrot/signal_stop_prepare_runtime.py` | `set.camera_from_calib(ROAD)` + `K(ROAD)` | 路口准备几何改用 helper，不再单独取 `fcam` 与 `rpyCalib`；**注意它当前硬性要求 `fcam.size == (1344,760)`**，在 1920×1080 的 imx390 上 `ok` 永远为 false，迁移时要把尺寸门控改掉，否则该功能在本项目上始终不生效 |
| `ui/layouts/settings/device.py`（含 mici） | 读 `CalibrationParams` 新字段（无则解析旧字段） | 展示每路 `rms/blocks/source`；重置只删 `CalibrationParams` |
| `selfdrive/carrot/server/services/device_info.py`、`features/system.py`、`features/tools/dispatcher.py` | 读 `CalibrationParams`（只读） | 备份/擦除覆盖 `CalibrationParams` 与可能残留的 `CamCalibRoad/Wide`（`system.py` 的 `api_recalibrate` 与 `dispatcher` 都按硬编码 key/路径操作，漏一个就会残留） |
| `selfdrive/carrot/server/features/intro/state.py` | 只列举 key 名做"是否已标定"判断 | 判断 `CalibrationParams` 是否存在且可解析；不引入新 key |
| `selfdrive/carrot/web/src/features/drive/contents/vision/ar/{runtime,odometry,frame_sync}.js` | 经 `to_json` 网关 | 与 `home_drive.js` 同一规则：删除 JS 侧内参镜像与手工拼接，只做矩阵乘法 |
| `common/transformations/video_camera_calibration.py` | 定义了 `CamCalibRoad/CamCalibWide` 的解析器与校验范围，但无调用方（仅 `USE_WEBCAM` 台架预留） | 视频台架也改走 `CameraCalibSet`（`source=PRIOR`），删除这层独立解析；否则它会成为第四个内参真值 |
| `selfdrive/modeld/fill_model_msg.py` | 只写 `cameraOdometry.wideFromDeviceEuler`（模型输出侧），不读标定 | 保持写入不变；改为订阅方读取后仅作交叉校验（§5.1），不作为真值 |
| `tools/replay/ui.py` | 用 `DEVICE_CAMERAS[("tici", sensor)]` + `liveCalibration.rpyCalib` 拼投影，**键写死为 `tici`** | 本项目设备键是 `("pc","imx390")`，回放本车 rlog 会直接 `KeyError`；改为读消息内 `cams[]`，旧 rlog 才回退旧逻辑 |
| `controlsd.py`、`paramsd.py`、`lagd.py`、`torqued.py` | 全部经 `PoseCalibrator.feed_live_calib(liveCalibration)` 使用 `rpyCalib`（身体姿态），不涉及相机内参 | 不需要改代码；只在 §10.6 白名单里登记为"legit body_from_calib 消费者"，避免被误判为直读 |
| `selfdrive/debug/cycle_alerts.py` | 写入随机 `rpyCalib` 造告警（测试工具） | 改为在对象层注入，避免测试代码依赖旧字段 |
| `tools/jotpluggler/generated_event_extractors.h` | 生成物，字段名自动展开 | 重新生成即可，不手工改 |
| 离线工具/日志分析 | 读消息内 `cams[]` | 新增导出函数 |

**唯一性要求的落地判定**：上表每一行都必须满足"只调用 `CameraCalibSet` 的派生方法（或 `to_json` 网关），不再出现 `rot_from_euler(rpyCalib)`、`wideFromDeviceEuler` 直读、`DEVICE_CAMERAS[...]` 运行时直读"。§10.6 用静态扫描测试把这条变成 CI 门禁，避免新增代码又各读各的。

`CameraYawTrimDeg` 的处理：作为**手动偏置**保留，但在合并阶段一次性作用到 road 的 `rpy[2]`（`source=MANUAL`），模型与 UI 都从对象读，不再出现"modeld 里减一次、UI 里不减"的不一致。校准自动收敛期间若 trim 非零，`calibrationd` 冻结整段外参更新（现状即如此：`freeze_calibration = trim_active and calib_done` 时跳过 `handle_cam_odom`，rpy/height/wide 都不再变化），迁移后保持同一语义，避免与人工偏置互相拉扯。

关于该参数的三个实现细节（已核对代码）：

1. **没有代码写入点**：全仓只有 `modeld.py:526` 读它、`calibrationd.py:284-285` 用它做冻结判断，写入来自外部参数工具/设置项（`tools/carrot_assistant/catalog.json` 暴露了它），因此迁移时不能假设"总有人写"。
2. **单位是 0.01°**：`params.get_float("CameraYawTrimDeg") * 0.01`（`params_keys.h` 中类型为 `INT`），直接当弧度或度用会差两个数量级。
3. **符号等价性**：现状是 `device_from_calib_euler[2] -= trim`，新方案是 `road.rpy[2] += trim`。两者在纯 yaw 上严格等价；当 `body_from_calib` 的 roll/pitch 非零时相差 O(trim·roll/pitch) 的二阶小量（1° trim × 3° roll ≈ 0.05° 的三阶项，可忽略），但验收必须用 `trim≠0` 的数据做 A/B，不能只在默认 0 下比对。

### 5.3 迁移顺序

```
读 CalibrationParams（Event 字节）
 ├─ 存在且 schema/identity 校验通过 → 直接用其中的 cams[]
 ├─ 存在但 schema > 支持版本     → 忽略新字段，按旧字段降级（并上报 cloudlog）
 └─ 不存在或新字段缺失 → 用工厂内参 + 旧字段组合出内存对象（不写盘）
                ↓ calibrationd 启动后第一周期
              同一个 key 写回（新字段 + 旧字段由同一次 to_bytes 产出）
```

组合规则（保证 `camera_from_calib` 与旧行为逐位一致）：

- `body_from_calib = legacy.rpyCalib`
- `road.rpy = [0, 0, 0]`（v1 以 road 光轴作为 body 的航向/俯仰基准）
- `wide.rpy = legacy.wideFromDeviceEuler`
- `road.K / wide.K = DEVICE_CAMERAS[(device, sensor)].fcam/ecam.intrinsics`
- `dcam.K = DEVICE_CAMERAS[(device, sensor)].dcam.intrinsics`，`dcam.rpy = None`、`mount_height = None`、`source = PRIOR`、`extrinsic_valid = False`（只在构造时取一次工厂值，此后不再直读 `DEVICE_CAMERAS`）
- `height = legacy.height`（同时作为 `road.mount_height`；wide/dcam 的 `mount_height` 为 `None`）

由此 `road.camera_from_calib == V · rot(legacy.rpyCalib)`，`wide.camera_from_calib == V · rot(legacy.wideFromDeviceEuler) · rot(legacy.rpyCalib)`，前者与旧 modeld 一致，后者与旧 UI 一致。

反之，新字段与旧字段由**同一份内存状态**生成，不存在"镜像写回"这一步：

- `rpyCalib = body_from_calib`
- `wideFromDeviceEuler = wide.rpy`
- `height = set.height`

`get_msg()` 是唯一填充点，禁止在 `send_data` 之外单独给 `rpyCalib`/`wideFromDeviceEuler` 赋值，否则新字段与旧字段会漂移（这正是 `Params` 双 key 方案无法保证的部分）。这样任一版本代码读到的语义都相同。回放验收分两档：P1（`CalibWideWarpPhysical=0`，默认）下 `warp_matrix(WIDE)` 走 §4.3 的 legacy 分支（旋转用 `cams[ROAD].rpy`、内参用 `K(WIDE)`），与旧 `modeld` 差 < 1e-6；`camera_from_calib(WIDE)`（UI 通用投影）仍为 `V · rot(legacy.wideFromDeviceEuler) · rot(legacy.rpyCalib)`，与旧 UI 一致。P2 打开开关后 `warp_matrix(WIDE)` 才乘 `wideFromDeviceEuler`，与旧 `modeld` 的差异恰为该量（已知缺口，见 §7.1）。

### 5.4 失效与重置

- 设置页"Reset Calibration"：删除 `CalibrationParams`（含新字段的那个 key）即可；若迁移期保留了 `CamCalibRoad`/`CamCalibWide`，必须一并删除，否则旧估计值会在下次启动被读回。`calibrationd` 重启后按工厂值重建。
- 检测到 `identity` 不匹配（换摄像头、改分辨率、sensor 变化）：自动回退工厂值，`source=FACTORY`，`valid=false` 直到重新累积。
- 逐路失效：某一路（如 wide）解析失败或 `uid` 变化只回退该路，其余路保持不动；重置是**整份删除**（v1 不提供单路重置），但重建时每路各自回到自己的工厂值，`DCAM` 始终回到 `PRIOR`。
- 解析失败/字段越界：丢弃整份数据（不做部分采用），回退工厂值并记录日志。

## 6. 自动校准算法

分四层，逐层使能，前一层未收敛时后一层不写盘。

### 6.1 L1：相机↔IMU 旋转对齐（相对外参，优先上线）

输入：`gyro`（sensord，device 系角速度）+ 两路相机的旋转光流。

原理：相邻帧之间的旋转光流只由相机角速度决定，与平移、深度无关：

```
ω_cam ≈ R_cam_from_body · ω_body
```

body 与 IMU/device 同轴（v1 中 `road.rpy = 0`，三者一致），因此该式对任意朝向的相机都成立：这是左/右/后相机唯一可直接复用的观测器。

对每个采样帧，用光流拟合单应（远场点）得到 `ω_cam`，与同时间窗的 `gyro` 组对，用 Kabsch/Wahba 求 `R_cam_from_body`，多帧鲁棒平均。

输出：

- 每路 `cam_i.rpy` 的绝对旋转（两路各自独立求解，再交叉校验）；
- `cam_wide_from_cam_road = R_wide_from_body · R_road_from_body^T`，用于替换/校验模型给出的 `wideFromDeviceEuler`。

门限：`|ω| > 5°/s`、光流内点率 > 60%、帧对残差 `|Δts − deltaRef| < 2 ms`（T0，§16.4）；解算残差 < 0.15°/s 才计入 block。

价值：不依赖路面、不需要直线行驶，是双路相对外参最可靠的来源；同时为 L3 提供"外参已知"的前提。

### 6.2 L2：road↔calib 外参（沿用现有 + 收紧）

保留 `calibrationd` 现有做法：`cameraOdometry` 的平移方向给 pitch/yaw，`roadTransformTrans` 给高度；直行 + 高速（> 15 mph）+ 偏航率小是有效条件。

改动：

- 把路面姿态（原 `rpyCalib`）归入 `set.body_from_calib`，`spread`、`valid_blocks` 归入 `CameraCalibSet.cams[ROAD]` 与 `set.height`；安装外参 `road.rpy` 仍为 0；
- 增加**逐块步长限制**：单块 pitch/yaw 变化 ≤ 0.1°，避免一次野值把 warp 拉偏；
- 保留现有 spread 超限自动重置逻辑（`MAX_ALLOWED_PITCH_SPREAD` / `MAX_ALLOWED_YAW_SPREAD`）。

### 6.3 L3：内参自动标定（核心新增）

两路各自独立求解，共享同一套约束。未知量：`fx, fy, cx, cy`（4 个），外参在 L1/L2 收敛后视为已知常量（交替优化：内参收敛后再放开 ±0.05° 的 `rpy` 微调，防止耦合发散）。

#### 约束 A：消失点（弱约束，用于粗收敛）

已知 calib 系下的行驶方向 `u`（由 `cameraOdometry.trans` 归一化，或用 `R_cam_from_calib(ROAD) · [1,0,0]`），消失点应满足：

```
p_vp ≈ π(K · R_cam_from_calib · u)
```

图像上实测消失点 `v` 由两条约束得到：远场车道线拟合直线求交；或对远场稀疏光流做直线拟合求交点。残差 `r = π(K R u) − v`。

有效条件（针对"单帧消失点测量"）：`v_ego > 12 m/s`、`|yaw_rate| < 1°/s`（直行）、车道线连续性 > 3 s。注意两个阶段不要混：直行段只用于**测消失点位置**（此时 `u` 在 calib 系近似不变，单条约束只能定出"过消失点的一条射线"，对 `fx` 的条件数很差）；要辨识 `fx/fy` 必须换到**转弯段**（`u` 的 yaw 分量变化 > 3°），把多组不同方向的射线联合求解。即"直行取点、转弯定焦"，两者分开门控。

**为什么内参必须有约束 B**：`get_warp_matrix` 把主点映射到固定位置，`f` 只是让图像绕主点缩放，而单目几何对该缩放不敏感。既有 `intrinsic_calibd.py` 的文件头记录了本机实测：**把 `f` 从 2087 一路扫到 3600，车道宽只变化 0.02 m**。也就是说，凡是"模型三维点在 calib 系、只靠 `K` 投影"的量，几乎不含 `f` 的信息；`f` 唯有通过与米制车道几何的联合残差（约束 B）才能被真正约束住。这同时解释了为什么既有实现提不出可靠的 `f`、转而把 `pitch_offset` 作为主产物——**安装俯仰才是当前链路上真正错位的量**。本方案因此把 L3 拆成"俯仰先收敛（约束 A + 既有消失点估计器），内参再用约束 B 精化"，而不是指望消失点单独定焦。

#### 约束 B：车道几何（主约束）

模型已在 calib 系输出车道线三维点（`modelV2.laneLines[i].x/y/z`），图像侧用经典 CV 检测车道边缘像素 `p`。构造重投影残差：

```
r_ij = π(K_i, dist_i, R_i, P_ij) − p_ij
```

- 3D 点来自模型（米制、calib 系），2D 点来自图像检测，两者相互独立，避免"用模型标定模型"的循环；
- 对模型点投影后，在 ±5 px 邻域内吸附到最近的强边缘像素，吸附失败则丢弃该点；
- 近场横向点主要约束 `cx`，远场点主要约束 `fx`，按 `1/(depth·σ)` 加权；
- 损失用 Huber（δ = 2 px），Gauss-Newton + 工厂值先验：

```
min  Σ ρ(r_ij) + λ_f·((fx−fx0)/fx0)² + λ_c·((cx−cx0)/W)² + ...
```

先验权重 `λ` 取"偏离工厂值 5% 相当于 1 px 残差"的量级，保证数据不足时结果贴近工厂值。

#### 两路协同

- wide 视野大、边缘畸变与检测噪声大，优先用 road 做内参主解；
- wide 用 L1 得到的 `wide_from_road` 与 road 的 `rpy` 组成先验，仅在其自身约束充足时独立微调；
- 若某路 `rms` 连续 N 块高于阈值，只把该路标记 `valid=false` 并回退该路工厂值，另一路不受影响。

#### 收敛判据

- 累积 ≥ 30 个有效块（约 2.5 min 有效路况）；
- 最近 10 块参数漂移 < 0.1%（`fx`）/ 0.2 px（`cx/cy`）；
- `rms_reproj` ≤ 1.5 px，且相对工厂值初始 `rms` 改善 ≥ 20%；若初始 `rms` 已 ≤ 1.0 px（工厂值本就很好），改善项不适用，只要求不劣化；
- 总偏离在硬限幅内（见 §6.5）。

满足后 `source=AUTO`、`valid=true`，进入慢速跟踪（EMA，时间常数 ~10 min），只在慢漂移时更新。

### 6.4 触发与门控

所有层共用：

| 条件 | 门限 |
| --- | --- |
| 车速 | > 12 m/s（内参）/ > 15 mph（外参，沿用现状） |
| 偏航率 | < 2°/s |
| 光照 | 非夜间、无逆光饱和、曝光未触顶 |
| 图像质量 | 拉普拉斯方差高于阈值、无大面积过曝 |
| 时间同步 | 帧对残差 `\|Δts − deltaRef\|` ≤ 2 ms 且相位无跳变（`cameraSyncState.synced` 且 `timebase=SYSTEM_CLOCK`）；配对后的时间差**必须用 IMU 姿态外推显式扣除**，不得吸收进外参（§16.4）。超限则该帧对丢弃 |
| 模型有效 | `modelV2` 与 `cameraOdometry` 均 valid |
| 参与相机 | 只有 `source ∈ {AUTO}` 且 `extrinsic_valid` 允许被估计的路（v1 = ROAD/WIDE）进入观测器；**DCAM 永不采样**（`PRIOR`、无外参），LEFT/RIGHT/REAR 在接入前不参与任何层 |

不满足时只暂停累积，不清空已有 block；换路段/重启后从持久化值继续。

### 6.5 硬限幅与安全约束

写入前逐项检查，任一越界则整次更新丢弃：

- `|fx/fx0 − 1| ≤ 0.08`，`|fy/fy0 − 1| ≤ 0.08`；
- `|cx/W − 0.5| ≤ 0.05`，`|cy/H − 0.5| ≤ 0.05`；
- `pitch/yaw` 仍受 `PITCH_LIMITS` / `YAW_LIMITS` 约束；
- 单块变化上限：`fx/fy` ≤ 0.3%，`cx/cy` ≤ 0.2 px，`pitch/yaw` ≤ 0.1°；
- `rms_reproj` 比上一次写入变差 > 30% 时拒绝更新（防止把标定带向错误局部极小）；
- 内参自动标定默认关闭（`EnableCameraIntrinsicsAutoCalib=0`），验证通过后按机型开启。

以上是 v1 的固定基线。无论后续把估计器换成协方差门控、因子图或带先验的联合优化（见 §15），**写入前的限幅、单块步长与"拒绝变差"规则一律不变**：先进算法只改变"候选值怎么算"，不改变"候选值能不能落盘"。

### 6.6 畸变（预留）

v1 不估计 `dist`，也不在 camerad 做去畸变。原因：模型 warp 假设针孔，若只给 UI 用畸变会造成"UI 与模型不一致"，与方案目标冲突；若给模型用则需要 camerad 增加 LUT 去畸变，属于独立工程。

预留策略：`dist` 字段存在且为 0；若将来开启 `EnableCameraDistortionCalib`，顺序固定为"camerad 去畸变 → 两路统一按针孔投影"，保证模型与 UI 仍共享同一组值。

## 7. 消费侧改造

### 7.1 modeld

```python
# before
device_from_calib_euler = np.array(sm["liveCalibration"].rpyCalib, dtype=np.float32)
dc = DEVICE_CAMERAS[(str(sm['deviceState'].deviceType), str(sm['roadCameraState'].sensor))]
model_transform_main = get_warp_matrix(device_from_calib_euler, dc.ecam.intrinsics if main_wide_camera else dc.fcam.intrinsics, False)
model_transform_extra = get_warp_matrix(device_from_calib_euler, dc.ecam.intrinsics if has_wide_camera else dc.fcam.intrinsics, True)

# after（wide warp 的物理外参由 CameraCalibSet 内部按 CalibWideWarpPhysical 决定，调用方不变）
calib = CameraCalibSet.from_live_calibration(sm["liveCalibration"])
if calib.seq != cached_seq:
  model_transform_main = calib.warp_matrix(Cam.WIDE if main_wide_camera else Cam.ROAD, False)
  model_transform_extra = calib.warp_matrix(Cam.WIDE if has_wide_camera else Cam.ROAD, True)
  cached_seq = calib.seq
```

同时把 `CameraYawTrimDeg` 从 modeld 移除，改由 `calibrationd` 合并进对象（`source=MANUAL`）。

**既有差异说明（必须显式处理）**：当前 `modeld` 的 wide warp 只用了 `rpyCalib`，没有乘 `wideFromDeviceEuler`；UI 却乘了。新对象里 `cams[WIDE].rpy = wideFromDeviceEuler`、`cams[ROAD].rpy = 0`，投影统一为 `camera_from_body · body_from_calib`，因此切换后 wide 的模型输入会补上此前缺失的相对外参，产生 `wideFromDeviceEuler` 量级的偏移。

处理方式：

- P1 先保持旧语义：`CalibWideWarpPhysical=0` 时 `warp_matrix(WIDE)` 的旋转部分取 `cams[ROAD].rpy`（内参仍取 `K(WIDE)`），只迁移取值来源，保证零回归；
- P2 在 L1 相对外参收敛后，用 A/B 对比（同一段日志分别用两种 warp 跑模型，比较车道/路径输出一致性）确认无退化，再切到物理外参；
- 切换开关 `CalibWideWarpPhysical`（默认 0），出问题可立即回退。

### 7.2 UI

`augmented_road_view._update_calibration` 改为只保存 `CameraCalibSet` 与 `seq`；`_calc_frame_matrix` 用 `set.camera_from_calib(cam)` 与 `set.K(cam)` 计算消失点偏移，crop/zoom、`max_x_offset` 等逻辑保持不变。

缓存 key 由 `sm.recv_frame['liveCalibration']` 改为 `calib_seq`，避免消息帧号变化但内容未变时重复计算。

### 7.3 一致性自检

`calibrationd` 每次写盘后做一次等价性自检：在 calib 系采样一组点 `P`，走两条路径算像素坐标——(a) `warp_matrix(cam)` 作用在"calib→model"变换后的点 `calib_from_model⁻¹·P` 上（模型路径），(b) 直接 `π(K·camera_from_calib(cam)·P)`（UI 路径），断言两者差 < 0.5 px；不一致说明两条路径拼矩阵的方式已分叉，拒绝写入并上报（属于代码缺陷，不应发生）。注意两条路径的输入系不同，自检必须显式做这一步换算，不能直接拿同一组 calib 点喂 `warp_matrix`。**wide 的 legacy 分支（`CalibWideWarpPhysical=0`）下 (a) 用的是 `cams[ROAD].rpy`，(b) 必须用同一路旋转（`V·rot(cams[ROAD].rpy)·rot(body_from_calib)`），否则两者差恒等于 `wideFromDeviceEuler`，会被误判为"分叉"**；自检以 `warp_matrix` 实际采用的那一路旋转为准。

运行时轻量版：`modeld` 与 UI 各自上报所用 `calib_seq` 与 `source`，`selfdrived` 中发现两者超过 2 s 不一致时触发用户提示（"相机标定数据未同步"）。

### 7.4 非 Python 消费端（web / cluster / server）

这三类端与 modeld/UI 并列，同样必须只取一份值，但技术约束不同：它们拿不到 capnp 对象，也无法 import `camera_calib.py`。因此统一走 §4.4 的 `to_json` 网关，规则与 Python 端一一对应：

| 端 | 现状（各自为政） | 改造后 |
| --- | --- | --- |
| `selfdrive/carrot/web/js/.../home_drive.js` | JS 内硬编码一份 `DEVICE_CAMERAS` 内参，与 `rpyCalib`/`height` 在浏览器里拼投影 | 删除内参副本，只消费网关 JSON；投影用 `fx/fy/cx/cy` + `rpy` 现场组 `K` 与旋转（单次矩阵乘，不重复业务逻辑） |
| `selfdrive/carrot/cluster/cluster_renderer.py`、`cluster_live.py` | 独立进程自带 `DEVICE_CAMERAS` 与角度解析 | 启动读网关，`seq` 变化才刷新；不再自行解析 `CalibrationParams` |
| `selfdrive/carrot/server/live_runtime/snapshot.py`、`realtime/compact_state`、`system/webrtc/carrot_state.py` | 透传 `rpyCalib`/`wideFromDeviceEuler`，语义由下游再解释 | 透传网关 JSON 整体，**不再逐字段转发**，避免下游看到半套数据 |

四条附加约束：

1. **版本对齐**：网关 JSON 带 `schema_version`，不识别时端内退回"只用 `body_from_calib` + 出厂内参"的降级路径，并在界面上标注"标定数据不可用"，不得猜测字段含义。
2. **只有一份 JSON 序列化实现**：`to_json` 只允许存在于 `camera_calib.py`；其他语言不做反向解析（只读消费）。
3. **`seq` 单调性**：网关只转发 `seq` 更大的快照，端内丢弃乱序包，保证 web/cluster 与车上模型不会出现"一个用旧值一个用新值"的长时间错配。
4. **按 `id` 迭代，不假设数量**：`cams[]` 可能含 `DCAM`，将来会含 `LEFT/RIGHT/REAR`。端内必须按 `id` 查找自己需要的那一路，`extrinsicValid=false` 的条目只能用于内参（dcam 预览/面部框），不得用于 3D 投影。

**JS 侧的 schema 镜像**：`web/js/realtime/raw_capnp.js:364` 与 `web/js/realtime/vision_compact.js:163` 用手写字段偏移解析 `liveCalibration`，这是第三处"字段结构镜像"。追加字段不会破坏既有偏移（本方案只追加 `@13/@14/@15`），但新增字段（`cams[]` 等）**一律经 `to_json` 网关下发，不得再手写偏移表解析**；否则每加一个字段就要同步三处，回到"多份真值"的老路。

## 8. 持久化与版本兼容

| key | 类型 | 说明 |
| --- | --- | --- |
| `CameraCalibSet` | — | **不新增 key**，只作为内存对象名（§4.4） |
| `CalibrationParams` | `{PERSISTENT, BYTES}` | 唯一持久化 key：旧字段继续有效，新增字段随同一条消息落盘 |
| `EnableCameraIntrinsicsAutoCalib` | `{PERSISTENT, BOOL, "0"}` | 内参自动标定开关 |
| `EnableCameraCalibShadow` | `{PERSISTENT, BOOL, "0"}` | 影子模式：只算不写，落日志 |
| `CalibWideWarpPhysical` | `{PERSISTENT, BOOL, "0"}` | wide 的模型 warp 是否使用物理外参（含相对外参） |
| `EnableCameraDistortionCalib` | `{PERSISTENT, BOOL, "0"}` | 畸变估计开关；v1 关闭，`dist` 恒为 0（见 §6.6） |

版本策略：

- `schema_version` 只在字段语义变化时递增；新增字段一律追加且给默认值，消费者忽略未知字段。
- 消费方支持 `schema_version ≤ 当前版本`；遇到更高版本按"不识别"处理，走旧 key + 工厂内参，绝不猜测。
- 写入必须整份覆盖（不做字段级 merge），保证 `seq` 与内容一致。

## 9. 灰度与实施步骤

| 阶段 | 内容 | 验收 |
| --- | --- | --- |
| P0 | 新增 `camera_calib.py`、capnp 字段、参数 key；`calibrationd` 仅按工厂值+旧参数构造并写盘；modeld/UI 暂不切换 | 回放中 road 与 wide（`CalibWideWarpPhysical=0`，默认）的 `warp_matrix` 均与旧代码差 < 1e-6；若临时打开开关，记录 wide warp 与旧 modeld 的差异量（恰为 `wideFromDeviceEuler`，属于已知缺口） |
| P0b | 时间同步按系统时钟路线实施（§16.4 T0）：统一 `CLOCK_BOOTTIME` 时基、上线 `cameraSyncState`（`timebase=SYSTEM_CLOCK`）、逐帧时间差统计、帧对筛选、IMU 姿态时间对齐；先观测不门控 | 1 h 实车拿到两路时间差 P50/P99.9 与 24 h 相位漂移；帧对可用率 ≥ 95%；对齐后等效角度残差 ≤ 0.02°@10 m；UI 标注"系统时钟同步" |
| P0c（v1.1，驱动启用触发后） | 经 GMSL2 把 FSIN 透传到 MAX9295A MFP7、IMX390 进 slave 模式，`timebase` 切 `FSIN`/`HW_TS`，判定阈值从 2 ms 收到 100 µs；消费端代码不改 | 台架示波器波形达标；两路时间差 P99.9 ≤ 100 µs；切档前后标定结果差异可解释 |
| P1 | modeld、UI（含 model_renderer/augmented_road_view）、DM/locationd/selfdrived 切到 helper（值仍来自旧参数；wide warp 保持旧语义） | 实车/回放行为无变化，`git diff` 可逐条对应；wide 路径输出与改造前一致；§10.6 扫描在 `selfdrive/` 范围先清零 |
| P1b | 跨进程端（cluster/web/server）切到 `to_json` 网关，删除 JS 内参镜像 | 同一时刻三端 `seq` 一致；web AR 投影与车上 UI 差 < 1 px；扫描覆盖 `selfdrive/carrot/` 清零 |
| P2 | `camcalibd` 上线 L1，相对外参自动估计；先影子，再替换 `wideFromDeviceEuler`；A/B 通过后切 wide 物理外参。**由现有 `intrinsic_calibd` 升级：保留其消失点 + 稳健 LSQ 估计器与门限，先把它注册进 `process_config` 跑影子，确认产物正确后再叠加 L1** | 与模型输出的 relative euler 偏差 < 0.3°，不出现横向抖动；A/B 差异在噪声内；`CamCalibRoad/CamCalibWide` 与 `cameraCalibCandidate` 的 `f/pitch_offset` 在同一段数据上一致（迁移等价性） |
| P3 | L3 内参影子模式，落日志统计（在既有 `pitch_offset` 主产物之上补车道几何约束 B，精化 `f`） | 30 min 高速+匝道数据，`fx` 可辨识、残差下降可量化 |
| P4 | 按机型开启内参自动应用（限幅 + 状态展示） | 车道对齐改善、模型 lane offset 无跳变 |
| P5 | 可选畸变、逐机出厂标定导入 | 独立评估 |
| P6 | 进阶项按 §15.9 优先级逐项评估（条件数门控、自适应鲁棒核、退化检测、因子图、车队先验），每项独立开关、先离线+影子再启用 | 各自在 §15.9 的门槛内，不劣化 P0~P4 基线 |

每阶段均可单独回滚：关闭对应 `Enable*` 参数即退回上一阶段路径，`CameraCalibSet` 保持为空时消费者自动走工厂值。

## 10. 测试与验收

### 10.1 单元测试

- 同步：`cameraSyncState` 的 `deltaRef`/抖动/`skewPpm`/`alignedResidualNs` 用合成序列验证（含相位跳变、掉帧、自由运行、单路中断四种输入）；同步不达标时 `camcalibd` 不产出候选。
- 序列化：`CameraCalibSet → liveCalibration bytes → CameraCalibSet` 往返一致（浮点按 1e-6）。
- 迁移：构造旧 `CalibrationParams`，验证 `body_from_calib` + `cams[i].rpy` 组合出的 `camera_from_calib`：road 与旧 `modeld` 路径差 < 1e-6；wide 与旧 UI 路径差 < 1e-6。`warp_matrix(WIDE)` 在 `CalibWideWarpPhysical=0` 时与旧 `modeld` 差 < 1e-6，打开时与旧 `modeld` 的差异等于 `wideFromDeviceEuler`（已知缺口，见 §7.1）。
- 兼容：新字节里的旧字段仍由旧代码正确解析（`rpyCalib`/`wideFromDeviceEuler`/`height` 与迁移前逐位一致），旧字节在新代码里降级为工厂值 + 旧字段组合。
- 门限：越界 `fx`、超步长、`identity` 不匹配、损坏字节 → 均回退工厂值且 `valid=false`。
- 逐相机独立：在 `cams` 里插入 `DCAM`（`PRIOR`、`extrinsic_valid=False`）后，ROAD/WIDE 的往返值与不带 DCAM 时逐位一致；`camera_from_body/camera_from_calib/warp_matrix(DCAM)` 抛异常；修改 DCAM 的 `K` 不影响任何其他路的派生矩阵；模拟"某一路 `uid` 变化"只回退该路。
- 一致性：随机 calib 点按 §7.3 的两条投影路径（model 路径需先做 `calib→model` 换算）比较，像素差异 < 0.5 px。
- 数值：已知真值合成数据（`fx=800, cx=W/2+3`, 含噪声）下，L3 恢复误差 `fx` < 1%、`cx/cy` < 1.5 px。

### 10.2 回放

- 用现有 `process_replay` 跑 3 条含直线、弯道、匝道的路线，对比新旧 warp 矩阵（P1 阶段应完全一致）；离线反复跑的视频素材与 §10.5 离线标定共用同一批 rlog。
- 影子模式统计：每路段输出 `rms` 分布、`fx` 漂移曲线、收敛所需块数。

### 10.3 实车

- 高速直行 10 min + 匝道 3 次：观察 `calStatus` 从 `uncalibrated → calibrated`，`spread` 收敛，无 `recalibrating` 反复。
- UI 相机视图中车道线与实际车道贴合（目视 + 截图对比）；模型路径在车道中心无系统性偏移。
- 断开 wide 相机：road 正常，wide `valid=false`，UI 自动回退 ROAD 流。
- 参数损坏/删除：重启后自动重建，功能不中断。
- 同步（T0）：连续 1 h 记录 `cameraSyncState`，帧对残差 P99.9 ≤ 2 ms 且 `deltaRef` 无跳变；屏蔽一路或强制改帧率后 1 s 内 `synced=false` 且标定停止采样（§16.6）。T1 到位后再按 ≤100 µs 验收。

### 10.4 量化指标

| 指标 | 目标 |
| --- | --- |
| 内参恢复误差（`fx`） | < 1% |
| 主点误差 | < 1.5 px |
| 相对外参误差 | < 0.3° |
| 重投影 RMS | ≤ 1.5 px |
| UI/模型投影差 | < 0.5 px |
| 收敛时间 | ≤ 3 min 有效路况 |
| 两路时间差（T0，P99.9） | 帧对残差 `\|Δ − deltaRef\|` ≤ 2 ms 且相位无跳变（§16.4） |
| 时间对齐后等效角度残差 | ≤ 0.02°@10 m（IMU 外推扣除时间差后，§16.4） |
| 两路时间差（T1，有硬件后） | ≤ 100 µs |

### 10.5 录制视频离线标定（"只有一处参数生效"的测试闭环）

目标：拿一段录制视频（rlog + 图像帧）在 PC 上离线跑完整标定流水线，直接输出优化后的内外参；并证明运行时只有 `CameraCalibSet` 一处参数在起作用。

**离线流水线**（与实车共用同一套观测器与门限，仅输入换为离线帧源）：

1. 回放 rlog：`roadCameraState / wideRoadCameraState` 逐帧喂给 `camcalibd` 的 L1/L3 观测器；`carState / cameraOdometry` 喂给路面姿态（L2）估计；同时从帧时间戳重建两路时间差，先跑 §16.6 的同步健康检查（不通过的片段不参与标定）；
2. 合并候选、过门限/限幅（复用 §6.5 全部规则）；收敛即停止，走完影子校验（§7.3）；
3. 唯一输出：写 `Params["CalibrationParams"]`（新字段与旧字段同一次序列化），或导出 JSON 由设置页手动导入；不存在第二个生效 key；
4. 验证：`test_single_source` 断言 modeld warp、UI 投影、设置页展示、JSON 网关四处读到的值全部来自这一份对象。

**"只有一处参数生效"的保证**：

- 运行时生效参数唯一 = `CalibrationParams` 里的 `cams[]`；`DEVICE_CAMERAS` 仅是工厂初值输入，任何消费方不得在运行时直读它或直读旧字段 `rpyCalib / wideFromDeviceEuler`（`body_from_calib` 例外，见 §5.2 的位姿链行）；
- 改动测试：改写 `CameraCalibSet` 任一字段（如 `fx`），modeld warp 与 UI 投影同步且只随该值变化；反向断言：改 `DEVICE_CAMERAS` 中的数值，运行时行为**零变化**（工厂值只在"新字段缺失/identity 不匹配"的降级路径生效）；
- 该断言固化成自动化测试，防止未来某消费方回退成"各读各的"。

**验收**：

- 同一段视频离线跑 3 次，输出参数逐位一致（确定性）；
- 合成真值视频：恢复误差满足 §10.4 指标；
- 实车录像的离线收敛值，与同一路段实车在线收敛值之差 ≤ §6.5 限幅；
- 单段 2 min 视频全流程耗时预算 < 60 s（桌面机，含光流）。

### 10.6 消费端唯一性门禁（静态扫描）

单测只能覆盖被调用的路径；真正的风险是**新代码又自己读一遍原始字段**。因此增加一个静态扫描测试 `test_no_direct_calib_readers.py`：

- 扫描范围：`selfdrive/`、`ui/`、`selfdrive/carrot/`、`common/`、`system/`（排除 `locationd/calibrationd.py`、`tools/`、`*test*`、`*replay*`、`cereal/gen`）；
- 禁止出现的模式（正则）：`rpyCalib`、`wideFromDeviceEuler`、`CALIBRATION_PARAMS`/`"CalibrationParams"`、`DEVICE_CAMERAS[`；
- 白名单：`common/transformations/camera_calib.py`（唯一实现）、`calibrationd.py`（唯一写入者）、`selfdrive/carrot/intrinsic_calibd.py`（迁移完成前，它把 `liveCalibration.rpyCalib[1]` 作为估计**输入**而非渲染真值，须注明 `# calib-legacy-allow: estimator-input`；迁移到 `camcalibd.py` 后该条移除）、迁移/降级代码（带显式 `# calib-legacy-allow` 注释），以及**只按 key 名做备份/擦除/存在性判断、不解析内容**的代码（`server/features/tools/dispatcher.py`、`server/features/system.py`、`server/features/intro/state.py`、`ui/layouts/settings/device.py` 的删除逻辑）。最后这一类只允许出现字符串 `"CalibrationParams"`，出现 `rpyCalib`/解析 capnp 即判失败；
- **dcam 不设白名单例外**：`monitoring/policy.py` 改为读 `cams[DCAM]`（由 `calibrationd` 在构造时从工厂表取一次并写入对象），`DEVICE_CAMERAS[...].dcam` 在 `selfdrive/` 下同样判失败；工厂表只允许在 `camera_calib.py` 的构造/降级代码里出现一次。这样 DCAM、以及后续的 LEFT/RIGHT/REAR，都只有 `cams[]` 一个入口；
- 任一命中即 CI 失败，并打印文件:行号，要求改走 `CameraCalibSet` 或 `to_json` 网关；
- 同时校验 `selfdrive/carrot/web/js` 下不再出现内参常量表（针对 §7.4 的 JS 历史债）。

这条门禁与 §10.5 的运行时断言互为一对：前者保证"没有第二个读取源"，后者保证"唯一读取源真的生效"。

## 11. 风险与对策

| 风险 | 影响 | 对策 |
| --- | --- | --- |
| 内参与外参耦合导致发散 | warp 被拉偏，横向控制异常 | 交替优化、固定外参解内参、单块步长限制、先验约束、拒绝变差更新 |
| 内参错误直接进模型 | 安全相关 | 默认关闭、硬限幅（±8%）、影子期统计、状态可见、一键重置 |
| wide warp 语义切换 | 模型输入偏移，可能退化 | 分阶段（P1 保旧语义 / P2 A/B 后切换）、独立开关、可回退 |
| 车道检测在夜间/雨雪失效 | 无数据可累积 | 门控丢弃、保留旧值、不降低 `valid` |
| 两路时间不同步 | 相对外参偏差（1 ms ≈ 0.17°@10 m） | v1 走系统时钟路线：帧对窗口 + IMU 姿态外推显式扣除时间差，对齐后残差 ≤ 0.02°@10 m，超限不采样（§16.4）；硬件触发到位后切 T1（≤100 µs） |
| 参数格式演进破坏旧版本 | 降级后读到脏值 | 同一条消息内做版本校验（`schema_version`），不识别即回退；不采用双 key 双写（无法原子，见 §4.4） |
| UI 与模型读取时机不同 | 显示与推理短暂不一致 | 以 `seq` 为唯一缓存键，单条消息原子携带两路 |
| 跨进程端（web/cluster/server）各自取值 | 浏览器/仪表与车上模型不一致，且易长期错配 | 唯一 `to_json` 网关 + `seq` 单调转发 + 端内不识别即降级（§7.4） |
| 新增代码绕过对象直读旧字段 | 长期退化成"多份真值" | §10.6 静态扫描 CI 门禁，白名单外一律失败 |
| Orin 算力占用 | 影响 modeld | `camcalibd` 独立进程、5 Hz、降采样、耗时预算 15 ms，超预算自动降频 |

## 12. 改动清单

以 `openpilot/` 开头的路径从仓库根起算，其余路径相对 `openpilot/`。

| 文件 | 改动 |
| --- | --- |
| `openpilot/cereal/log.capnp` | 新增 `CameraCalib`，`LiveCalibrationData` 追加 `calibSchemaVersion/calibSeq/cams` |
| `openpilot/common/transformations/camera_calib.py` | 新增：可变长 `cams`（按 `CamId` 索引）、body 参考系、序列化、迁移、派生矩阵、投影 |
| `openpilot/common/transformations/camera.py` | 保留 `DEVICE_CAMERAS` 作为工厂默认值来源，不再被消费侧直接引用 |
| `openpilot/common/transformations/video_camera_calibration.py` | 并入 `CameraCalibSet`（视频台架作为 `source=PRIOR` 的初值），删除独立的 key 解析器，避免第四份内参真值；对应测试 `test_video_camera_calibration.py` 同步迁移 |
| `openpilot/common/params_keys.h` | 新增 `EnableCameraIntrinsicsAutoCalib`、`EnableCameraCalibShadow`、`CalibWideWarpPhysical`（**不新增 `CameraCalibSet`**，见 §4.4）；新增后必须重建 `params_pyx`，否则 `params_check` 与运行时 `check_key` 都会失败 |
| `openpilot/selfdrive/locationd/calibrationd.py` | 唯一写入者：合并候选、门限、限幅、扩展字段；只写 `CalibrationParams` 一个 key；`all_checks` 显式列旧服务（§5.1） |
| `openpilot/selfdrive/locationd/camcalibd.py` | 由 `selfdrive/carrot/intrinsic_calibd.py` 迁移/升级：保留既有消失点 + 稳健 LSQ 估计器与全部门限常量，产物从直接写 Params 改为发布 `cameraCalibCandidate`；新增 L1 角速度对齐与约束 B（车道几何）内参精化 |
| `openpilot/selfdrive/carrot/intrinsic_calibd.py` | 迁移后删除（逻辑并入 `camcalibd.py`），避免两份估计器并存；`CamCalibRoad`/`CamCalibWide` **直接删除，不做只读回退**——这两个 key 从未注册进 `params_keys.h`，读回会抛 `UnknownKeyName`（§5.1） |
| `openpilot/system/manager/process_config.py` | 注册 `camcalibd`（`only_onroad`）；其订阅 `cameraSyncState` 作为采样前置条件 |
| `openpilot/selfdrive/modeld/modeld.py` | 改用 `warp_matrix`，移除本地外参组合与 trim |
| `openpilot/selfdrive/ui/onroad/model_renderer.py`、`ui/mici/onroad/model_renderer.py` | 路径 z 偏移改从对象取 `height`，不再直读消息字段 |
| `openpilot/selfdrive/modeld/dmonitoringmodeld.py`、`selfdrive/monitoring/dm2d.py`、`selfdrive/monitoring/policy.py` | `device_from_calib` 由 helper 生成；dcam 内参改为 `set.K(DCAM)`，删除 `monitoring/policy.py:110` 写死的 `DEVICE_CAMERAS[("tici","ar0231")].dcam` |
| `openpilot/selfdrive/locationd/locationd.py`、`locationd/helpers.py` | 删除本地 `rot_from_euler(rpyCalib)`，改取对象 |
| `openpilot/selfdrive/selfdrived/selfdrived.py`、`impact_detector.py`、`events.py` | `calStatus` 改为逐路 `valid` 的归约视图；去旋转取对象 |
| `openpilot/selfdrive/ui/onroad/augmented_road_view.py`、`ui/mici/onroad/augmented_road_view.py` | 改用统一 helper，缓存键改 `calibSeq`；mici 版不再写 `DevicePosition` 拼外参 |
| `openpilot/selfdrive/ui/layouts/settings/device.py`、`ui/mici/layouts/settings/device.py` | 展示逐路状态，重置只删 `CalibrationParams`（新字段同 key），不再有第二个 key |
| `selfdrive/carrot/cluster/cluster_live.py`、`cluster_route_replay.py` | 经 `to_json` 网关取值，不再解析 `CalibrationParams` 字节 |
| `selfdrive/carrot/realtime/compact_state.*`、`selfdrive/carrot/server/live_runtime/snapshot.py`、`system/webrtc/carrot_state.py` | 整体透传网关 JSON（含 `seq`），不逐字段转发 |
| `selfdrive/carrot/server/services/device_info.py`、`selfdrive/carrot/server/features/system.py`、`server/features/tools/dispatcher.py` | 只读尝试解析 `CalibrationParams`；备份/擦除覆盖 `CalibrationParams` 与迁移期可能残留的 `CamCalibRoad/Wide`（`system.py` 的 `api_recalibrate` 是硬编码 key 列表，漏一个就会"清了又回来"） |
| `selfdrive/carrot/web/js/.../home_drive.js`、`selfdrive/carrot/web/src/.../ar/*.js` | 删除 JS 内参镜像，只消费网关 JSON（§7.4）；**当前还缺 `imx390`**：`home_drive.js` 的内参表只有 `ar_ox/os04c10`，sensor 枚举映射只到 index 3，而 `log.capnp` 的 `Sensor.imx390` 是 4 → 本项目上 web AR 解析不出 profile、不渲染（现在就是坏的，不是本方案引入） |
| `selfdrive/carrot/realtime/compact_state.py`、`compact_state_native.cc`、`web/js/realtime/vision_compact.js`、`raw_capnp.js` | 手写字段偏移里**没有 `wideFromDeviceEuler`**，所以 web/WebRTC 今天拿不到 wide 相对外参；新对象一律走 `to_json` 网关，不再往这三处手写偏移表里塞 `cams[]` |
| `tools/replay/ui.py` | 硬编码 `DEVICE_CAMERAS[("tici", sensor)]`，而本项目的键是 `("pc","imx390")` → 回放本车 rlog 会 `KeyError`；改为读消息内 `cams[]`（旧 rlog 再回退） |
| `selfdrive/carrot/cluster/cluster_renderer.py` | 直接 `import DEVICE_CAMERAS`（不是副本），但仍自己拼 `view_from_device`/`rpyCalib`；保留 import 作工厂值，投影改 helper |
| `selfdrive/carrot/signal_stop_prepare_runtime.py` | 用 `fcam.focal_length` + `rpyCalib`，且 `ok` 条件硬性要求 `fcam.size == (1344,760)` → 在 1920×1080 的 imx390 上**始终禁用**；迁移时改为 `K(ROAD)` + 尺寸无关门控，否则功能在本项目永远不生效 |
| `openpilot/selfdrive/test/test_onroad.py` | `PROCS` 必须新增 `selfdrive.locationd.camcalibd`（当前预算合计 323%/350%，加 ~4% 仍有余量），否则新进程不在基线里、总预算断言失真 |
| `openpilot/selfdrive/test/process_replay/` | 适配新 capnp 字段；`process_replay` 会把 `CalibrationParams` 当自定义参数写回，确认新字段不影响其比对。`vision_meta.py:7` 的 `ROAD_CAMERA_FRAME_SIZES` 误用 `v.dcam`（应为 `v.fcam`），在本项目同尺寸设备上潜伏、在 `neo` 上出错，一并修 |
| `openpilot/cereal/log.capnp`、`cereal/services.py` | 新增 `cameraSyncState`（逐路时间差/抖动/skew/丢帧/`synced`），并带 `timebase`（`SYSTEM_CLOCK`/`FSIN`/`HW_TS`）、`timestampSource`、`quantizationNs`、`alignedResidualNs`，10 Hz `only_onroad`（§16.4） |
| `openpilot/system/camerad/cameras/camera_jetson.cc` | v1 不改采集链路：时间戳保持 V4L2 `tv_sec/tv_usec`（1 µs 截断，`timestampSource=kernel_recv`）。**丢帧统计不要依赖 `b.sequence`**：它是 V4L2 出队序号，语义依驱动，且 `start_streaming` 会重新起算（本文件 576-581 行的注释记录了按 `sequence % 3` 丢帧导致两路选到不同物理帧、SOF 偏差 >20 ms 的实测）；改为"单路相邻帧 `timestamp_sof` 间隔 > 1.5×周期即记丢帧 + 记录 `frame_id` 回绕/stream 重启 epoch"。`FrameData.frameIdSensor` 可透出 `b.sequence` 仅作**路内连续性**辅助，不用于跨路配对（两路计数器各自起算，不能按相等配对） |
| `openpilot/selfdrive/modeld/camera_sync.py` | 已在使用的帧对配对实现（`receive_camera_pair`，`MAX_CAMERA_SKEW_NS=20 ms`、按 `timestamp_sof` 只推进较旧一路、最多 10 次）。**窗口本身是个隐患**：两路都是 30 fps，半周期 16.7 ms，20 ms 的绝对窗口会让接近半周期的错配也被接受（文件头注释仍按 20 Hz/50 ms 写，已过期）。迁移时把"绝对上限"收紧到 **15 ms**，判据统一用 `|Δts − deltaRef| ≤ 2 ms`（§16.4）；两路计数器各自起算，禁止按帧号相等配对 |
| 相机驱动/寄存器初始化（`twgmsl` 侧 MAX9296A/MAX9295A 配置，路径以实际驱动为准） | T1（v1.1）：9296 MFP 配 GPIO 输入 + 开启 GMSL2 GPIO 透传，9295 MFP7 配为帧同步输出，IMX390 进 slave 模式；v1 不动 |
| `openpilot/system/camerad/cameras/spectra.cc`、`spectra.h` | T1（有硬件后）：运行期相位误差与丢脉冲统计，把 `syncFirstFrame` 的一次性校验扩展为持续监测；v1 的 T0 统计在 `camcalibd` 侧完成，不改此处 |
| `openpilot/system/camerad/cameras/hw.h` | 明确 `staggered_sof` 依赖固件版本；同步参数集中在此 |
| `panda/board/drivers/clock_source.h`、`clock_source_declarations.h`、`board/main_comms.h` | T1（有硬件后）：FSIN 时基 0.1 ms → 1 µs；周期/脉宽控制请求改为 µs 粒度（现有 `0xe6` 是 ms + `uint8_t`）。v1 不改 |
| `tools/camcalib_offline.py` | 新增：录制视频离线标定入口，复用 `camcalibd` 观测器与 §6.5 门限，先跑 §16.6 同步健康检查，输出 `CameraCalibSet`（rlog 回放 / JSON 导入导出） |
| 新增测试 | `test_camera_calib.py`（往返/迁移/门限/一致性/合成恢复）、`test_single_source.py`（"只有一处参数生效"断言）、`test_no_direct_calib_readers.py`（§10.6 静态扫描门禁）、`test_camera_sync.py`（§16.6 相位/抖动/丢脉冲；扩展现有 `selfdrive/modeld/tests/test_camera_sync.py`） |

## 13. 与现有手工调整的关系

- `CameraYawTrimDeg`：保留为人工偏置，但只在 `calibrationd` 合并阶段作用一次，`source=MANUAL`，modeld 不再二次修改；trim 非零时自动校准整体冻结外参更新（现状语义，见 §5.2）。
- `PathOffset`：与相机标定无关，不动。
- "Reset Calibration"：语义扩展为"清除两路相机全部内参/外参，回工厂值"，但 UI 文案保持"重置标定"，不新增用户概念。删除范围必须同时覆盖 `CameraCalibSet`、`CalibrationParams`，以及迁移期遗留的 `CamCalibRoad`/`CamCalibWide`（否则旧估计值会在下次启动被当作视频台架先验读回，出现"清了又回来"）。

## 14. 扩展到左/右/后相机

能，但**复用程度取决于相机角色**。"可变长数组 + 单一写入者 + body 参考系"这套机制可直接沿用；算法侧需要按朝向补充观测器，因为消失点、车道几何这些约束只对前视有效。

| 相机 | 外参旋转（L1 陀螺-光流） | 路面/地面外参（L2） | 内参自标定（L3） | 建议 |
| --- | --- | --- | --- | --- |
| 前视窄 | 可 | 可（车道/消失点/高度） | 可（消失点+车道几何） | 当前方案 |
| 前视广 | 可 | 可 | 可，需畸变模型 | 当前方案 |
| 左/右视 | 可（需转弯/变道激发） | 部分（可见车道线或地面平面时） | 弱 | 出厂 K + 在线只估外参 |
| 后视 | 可 | 弱（无前向车道） | 很弱 | 同上 |
| 相邻重叠区 | 可（特征匹配求相对外参） | — | — | 作为图边，不单独出绝对解 |

**外参对任何朝向都能自校准**，因为 L1 只依赖陀螺与光流，与相机朝向、路面几何无关；**内参只有前视能稳定自标定**，侧后视缺少消失点与远场车道，纯平移极线约束在实车数据上条件数很差，强行在线估计容易发散。

### 14.1 参数独立性（每路一套，不允许互相借用）

`cams[]` 的每一项都是一套**完整且互不影响**的参数。新增 DCAM 或左/右/后视时，只追加条目，不改动已有条目的任何字段；任何一路的收敛、失效、重置、换模组都不得影响另一路。

| 字段 | 归属 | 说明 |
| --- | --- | --- |
| `uid` | 每路独立 | 位置+序列号；某一路换模组只作废该路 |
| `width/height` | 每路独立 | 进 `identity` 时按路校验；本项目 DCAM 与 wide 同为 1920×1080 也必须各存一份，不能靠"尺寸相同"推断可共用 |
| `fx/fy/cx/cy` | 每路独立 | DCAM 用工厂 fisheye 值（`source=PRIOR`），与前视 f 无任何关系 |
| `dist` | 每路独立 | 前视 v1 恒 0；侧后视接入时必须各自标定 |
| `rpy` | 每路独立 | 均为 `cam_i_from_body`；DCAM 为 `None`（无物理意义），不得填 0 充当"已标定" |
| `mount_height` | 每路独立 | **禁止复用顶层 `height`**；顶层 `height` 只是 `cams[ROAD].mount_height` 的向下兼容镜像 |
| `extrinsic_valid` | 每路独立 | DCAM 与"尚未收敛的 LEFT/RIGHT/REAR"恒为 `False` |
| `valid` | 每路独立 | 码流存在 + identity 匹配，与是否收敛无关 |
| `source` | 每路独立 | `FACTORY/PRIOR/AUTO/MANUAL` 按路记录 |
| `blocks / rms_reproj / spread / updated_at_ns` | 每路独立 | 质量与新鲜度不能跨路借用；UI 必须逐路显示 |

只有三项是**全集合唯一**的：`schema_version`、`seq`、`body_from_calib`，以及 `identity.device_type/sensor`。其中 `body_from_calib` 是"车体相对路面"，属于整车状态而不是相机安装参数——**不得**把它当作某一路的安装外参，也不得为了让某一路看起来对齐而修改它。

### 14.2 已具备、可直接复用

- 数据结构：`cams` 已是按 `CamId` 索引的可变长列表，`LEFT/RIGHT/REAR` 已预留；`uid` 支持换模组检测。
- 写入机制：唯一写入者、`seq` 版本、`identity` 校验、逐路限幅、单 key 一次序列化，均与相机数量无关。
- 参考系：`cam_i.rpy` 是相对 body 的安装外参，新增相机只需给初值，不需要改动已有值。
- 消费侧：UI/模型都按 `cam` 索引取 `K` 与 `camera_from_body`，新增相机不会改变前视公式；跨进程端经 `to_json` 网关的 `cams[]` 自动多出一项，端内按 `id` 分支即可，无需新增参数通道。

### 14.3 需要新增的观测器

| 观测器 | 输入 | 输出 | 用途 |
| --- | --- | --- | --- |
| 陀螺-光流（已有 L1） | gyro + 各相机帧 | 每路 `cam_i.rpy` | 所有相机的绝对旋转 |
| 路面/地面平面 | 车道线或地面点、车身运动 | pitch/roll/高度 | 侧/后视可见地面时 |
| 重叠视场特征 | 相邻相机共视区特征匹配 | `cam_i_from_cam_j` | 相对外参边（手眼标定 AX=XB） |
| 极线/纯平移 | 直线行驶时的光流极点 | 焦距弱约束 | 仅作校验，不做主解 |
| 直线度/畸变 | 车道线直线性 | `dist` | 侧后视广角必需 |

### 14.4 外参图，避免链式累积

不要把侧后视外参写成 `road → left → rear` 的链式组合，否则误差随链路累积。正确做法：

- 节点：每路 `cam_from_body`；
- 边：L1/L2 给绝对边，重叠区给相对边；
- 求解：加权最小二乘 / pose graph，残差与权重由 `camcalibd` 产出；
- 写入：仍由 `calibrationd` 统一落盘，`camcalibd` 永不写 Params。

### 14.5 新增一路相机的步骤

1. `CamId` 增加条目，并在工厂表里补该位置的 `K` 与安装角初值。注意现有 `DeviceCameraConfig` 只有 `fcam/dcam/ecam` 三个槽位，侧后视无法"塞进"其中一项（尤其 `dcam` 已被驾驶员监控占用）：要么扩展为按 `CamId` 索引的字典，要么在 `camera_calib.py` 里维护 `CamId → 工厂值` 的独立映射，`DEVICE_CAMERAS` 只作为前视/DCAM 的兼容来源。
2. 该路 `uid`、图像尺寸进入 `identity` 校验；不匹配即回退工厂值。
3. `body_from_calib` 仍只有一份（车体相对路面），不复制到侧后视。
4. 侧后视放开 `rpy[0]`（roll），前视继续保持 roll=0。
5. `valid` 逐路独立：某路未收敛只影响该路，不拖累前视。
6. 消息与 `Params` 仍是同一个 key、同一个 `seq`，不新增参数通道。

### 14.6 畸变从"可选"变为"必需"

前视广角还能靠 ±5% 限幅兜住；侧后视的边缘畸变会直接把几像素误差换算成米级横向偏差。扩展时必须同时启用 `EnableCameraDistortionCalib`，并在 camerad 增加 LUT 去畸变，保证模型与 UI 仍共享同一组值（顺序固定：去畸变 → 统一针孔投影）。

### 14.7 门控按角色配置

前视沿用"直行 + 高速"；侧后视在高速直行时几乎不可观测，需要转弯、变道、低速挪车来激发旋转与视差；后视主要靠倒车/低速 + 地面纹理。门控必须逐路配置，不能沿用前视的单一准则。

### 14.8 不建议自动化的部分

- 侧后视的焦距与主点：实车数据条件数差，建议出厂标定（标定板）+ 在线只估外参。
- 相机间硬件同步与卷帘：相对外参的主要误差源，靠算法无法补偿，需保证时间戳对齐。
- 夜间/雨雪/无纹理：不累积新数据，保留上次收敛值，不降级 `valid`。

## 15. 进阶与智能化升级（不阻塞 v1）

本节是"还能更先进、更智能"的清单，**全部不纳入 v1 验收**，也不改变 §3 的五条硬规则。之所以能后加，是因为 v1 的接口已经为其留了口：候选消息可以追加可选字段（残差、Jacobian/信息矩阵、协方差），`CameraCalib` 可以追加质量字段，消费侧只依赖 `K/camera_from_calib/warp_matrix`，所以估计器升级对 modeld/UI 透明。

### 15.1 从"逐块批处理 + EMA"到"滑动窗因子图 + IMU 预积分"

现状局限：L1/L3 每块独立求解再指数平滑，块内信息被丢弃；陀螺零偏未建模，长时会被吸收进外参；两路、多类约束（旋转/消失点/车道/高度）无法联合加权。

升级做法：

- 状态 `x = [body_from_calib, height, {cam_i.rpy}, {fx,fy,cx,cy}_i, b_g]`，`b_g` 为陀螺零偏；
- 因子：陀螺-光流相对旋转因子（用 IMU 预积分连接相邻关键帧）、车道重投影因子、消失点因子、高度/路面因子、参数随机游走先验；
- 求解：滑动窗（10~20 个关键帧）+ 边缘化，或 iSAM2 增量求解；Orin 上 1 Hz 批量、其余时间只做门控与累积。

收益：块间一致性显式建模；协方差天然就是置信度（可直接驱动 §15.2 门控与 UI）；零偏分离后 L1 残差下降。代价：引入优化器（或自写 LM + Schur 补）、实现复杂度显著上升。风险：维数上升可能发散——因此保留 v1 的全部限幅与"拒绝变差"作为外层护栏，因子图只负责产出更准的候选。

### 15.2 可观测性驱动的门控（信息增益门控）

现状门控（§6.4）是固定阈值，只能排除"明显不行"的场景，无法区分"合规但没有信息"的样本（例如长时间匀速直行，对 `fx` 几乎无信息）。

做法：对每块样本先算投影雅可比 `J`，用 `JᵀJ`（或因子图的信息矩阵）判断：

- 条件数 `κ = λ_max/λ_min` 超阈值 → 该块对最弱方向无贡献，丢弃；
- 单块信息增益 `ΔI / tr(I) < 1%` → 不计数、不写盘；
- 最弱特征向量若指向 `fx`，则该块只更新 `cx/cy`，不动 `fx`（分方向更新，避免"整体过一次"把弱方向带偏）。

收益：同样里程收敛更快、更稳；写盘次数下降。代价：每块一次 4×4~10×10 特征分解，< 1 ms。风险：模型点系统性偏差时，信息矩阵会"自信地错"，必须与残差检验、CUSUM（§15.3）联合使用。

这是投入产出比最高的一项，建议作为 v1.1 首选（只加门控，不改估计器）。

### 15.3 鲁棒估计与故障隔离

- **RANSAC/MSAC**：消失点用两条以上远场直线做 RANSAC 求交（一点野值即可毁掉最小二乘解）；车道边缘用 MSAC，阈值按残差 MAD 自适应。
- **自适应鲁棒核**：Huber → Cauchy/Tukey，尺度 `σ` 用 MAD 在线估计，抑制护栏、阴影、伸缩缝等强边缘。
- **突变检测（CUSUM / 双样本检验）**：镜头被撞偏、支架松动、碰撞的 signature 是残差均值**阶跃**，不是缓慢漂移。对残差序列做 CUSUM，超门限立即 `valid=false`、回退工厂值并提示重标定，而不是让 EMA 慢慢追。
- **退化运动检测**：L1 需要旋转（已有 `|ω|` 门控），L3 需要平移视差；用 `cameraOdometry.trans` 与特征深度分布判断"纯旋转/纯平移"，纯旋转段不采内参样本，纯平移段不更新 roll。

v1 已含 Huber 损失与"投影后 ±5 px 邻域吸附"作为内建抗噪手段；RANSAC/MSAC、CUSUM 与退化检测建议 v1.1 叠加。

### 15.4 多源联合约束（提升精度上限）

1. **宽窄交叉约束**：两路同 body、同时刻，`wide_from_road` 由 L1 给出。把"`fx_road / fx_wide` 应等于出厂焦比（容差 ±2%）"作为软因子：road 缺远场点时借 wide 定 `fx`，wide 反过来校验 road。仅在相对外参收敛后启用，避免把外参误差混进内参。
2. **高度-俯仰解耦**：直行段 `height` 与 `pitch` 强相关（同一条路面平面）。用不同距离的路面点、坡道变化把两者分离，并把 `height` 的时间常数设得比 `pitch` 长一个量级，以吸收载重、胎压、悬挂的慢变化（现有 `height` 只做常量估计）。
3. **温度漂移建模**：镜头/镜座热胀使 `fx` 随温度单调漂移（量级需实测，典型 0.1%~0.5% / 20 °C）。若 `roadCameraState` 暴露温度，则建模为 `fx(T)=fx0·(1+α(T−T0))`，只估 1 个参数 `α`，避免 `fx` 在冷热机之间来回漂；无温度信号时退化为"冷机段不写盘，热稳态后再累积"。
4. **卷帘/时间偏移联合估计**：相对外参的主要系统误差来自两路曝光时刻差。若日志保留帧时间戳与曝光信息，可在高角速度段把时间偏移 `τ` 与 L1 一起估计（`ω·(t+τ)`）；拿不到就保留现有硬门控（§6.4）。前提是 §16 的同步档位已明确：T0 下 `τ` 初值取 `deltaRef`、搜索范围 ±2 ms（固定偏置已由 `deltaRef` 跟踪，不能再让 `τ` 去重复吸收它），并由 IMU 外推扣除；T1 下可压到 ±0.5 ms；同步不达标时不做该项，否则 `τ` 会把时间误差吸收成外参。

### 15.5 车队先验与产线标定导入

单车冷启动需要 ~30 个有效块。同机型同 sensor 的工厂偏置分布是稳定的，可以把"车队统计的 `fx` 偏差均值/方差"作为**弱先验**（等效 2~3 个观测），替代 §6.3 里"贴工厂值"的先验，显著缩短收敛并抑制个体野值。

- 实现：云端按 `identity(device_type, sensor)` 聚合，只上传统计量（不上传图像），下发 `calib_prior.json`；离线工具与实车共用同一先验接口；
- 同时支持产线标定板结果导入（`source=FACTORY_CALIBRATED`），作为强先验直接写入；
- 风险：先验错了会"集体带偏"。因此先验必须弱、必须先在 P3 影子期验证分布一致性；无网络或校验失败时自动退回工厂值。

### 15.6 质量可解释性与用户可见

- 把协方差翻译成用户能懂的三项：**置信度**（由 `σ_fx/fx` 归一化）、**已用有效里程**、**最近是否退化**；
- 设置页每路一行进度条 + 状态词（学习中 / 已收敛 / 已回退），不暴露矩阵；onroad 不新增打扰，只在"标定数据不同步"或"检测到镜头位移"时提示（沿用 §7.3 的 watchdog）；
- KPI 升级：内部仍看重投影 RMS，但对外验收改用**车道横向偏移残差**（模型车道与图像检测车道的横向差，单位 cm），因为它才直接对应控制误差。

### 15.7 自动化验证与 CI 门禁

- **合成数据生成器**：给定真值内外参与路面几何，合成车道线像素与光流，覆盖 `fx` 偏差、主点偏移、畸变、噪声、夜间；任何算法改动必须在该集合上不退化。
- **离线回归门禁**：固定 5~10 段 rlog，CI 跑 `tools/camcalib_offline.py`，断言输出参数在容差内、`test_single_source` 通过、`test_no_direct_calib_readers` 扫描无命中、warp 与基线差 < 阈值——把"只有一处参数生效"变成每次提交的硬约束。
- **A/B 自动化**：P2 的 wide 语义切换、P4 的内参启用，都用同一批日志离线跑模型，比较车道/路径输出分布，人工只看汇总。
- **回滚演练（混沌测试）**：定期在影子模式注入错误参数，验证 watchdog 能在 N 秒内退回工厂值。

### 15.8 远期探索（明确不承诺）

- **学习式加权**：用车道线分割网络的不确定性（softmax → σ）给像素加权，比固定 Huber 更贴合真实误差分布；仍以几何残差为损失、不做端到端回归，保持可解释与可限幅。
- **语义/结构约束**：停止线、灯杆、路沿等长直线与正交结构可提供消失点、竖直方向的额外约束，城市路段信息量高于车道线。
- **全局快门/事件相机**：若硬件升级，卷帘与运动模糊不再是主要误差源，可放宽 L1 的 `|ω|` 门限。
- **多相机在线 BA**：把 §14 的外参图升级为含内参的完整 BA，仅在侧/后视接入后才有收益。

### 15.9 采纳优先级

| 项 | 收益 | 代价 | 风险 | 建议阶段 |
| --- | --- | --- | --- | --- |
| 系统时钟微秒级同步 + 时间对齐（§16.4 T0） | 高 | 低 | 低 | v1（P0b，标定的前置条件） |
| 硬件触发 FSIN / VI 硬件戳（§16.4 T1） | 中 | 中 | 中 | v1.1，模组已支持，驱动启用即可 |
| 条件数/信息增益门控（§15.2） | 中高 | 低 | 低 | v1.1 首选 |
| 自适应鲁棒核 + RANSAC 升级（§15.3） | 高 | 低 | 低 | v1.1 |
| CUSUM 突变检测 + 退化运动检测（§15.3） | 中 | 低 | 低 | v1.1 |
| 合成数据 + CI 门禁（§15.7） | 高 | 中 | 无 | v1.1（强烈建议） |
| 协方差 → UI 质量展示（§15.6） | 中 | 低 | 无 | v1.1 |
| 温度漂移 `α` 模型（§15.4） | 中 | 中 | 中 | v2 |
| 宽窄交叉约束（§15.4） | 中 | 中 | 中 | v2 |
| 高度慢漂移解耦（§15.4） | 中 | 中 | 低 | v2 |
| 因子图 + IMU 预积分/零偏（§15.1） | 高 | 高 | 中 | v2 |
| 车队先验 / 产线导入（§15.5） | 高 | 中 | 中 | v2（需云端） |
| GNSS 1PPS / gPTP 绝对时间（§16.5） | 低（对标定）；高（对融合） | 高 | 中 | v2，需硬件支持 |
| 学习式/语义约束（§15.8） | 中 | 高 | 中 | 远期 |

采纳原则：**v1 先把"唯一数据源 + 门限限幅 + 影子验证 + 时间同步"做扎实**，再用 §15 逐项提升精度与收敛速度；任何一项上线前都必须通过 §10 的离线闭环与影子期，且不得绕过 §6.5 的落盘护栏。

## 16. 硬件时间同步（多相机 / 多传感器）

标定的精度上限由"两路帧是不是同一时刻曝光"决定，而不只由算法决定。本节先给代码事实，再给分档目标与落地项。

### 16.1 现状核查（有代码证据）

先澄清三个容易混为一谈的东西，否则"有没有微秒级时钟"会答错：

- **时钟分辨率**：Linux `CLOCK_MONOTONIC/BOOTTIME` 由 ARM 架构定时器提供，读数单位是 ns。**这一层不缺**，所有相机、IMU、日志时间戳都基于它。
- **同步信号**：让所有传感器"同一物理时刻开始曝光"的周期性硬件脉冲（FSIN/FSYNC）。**能力在模组里**（IMX390 `FSN` ← MAX9295A MFP7，规格书写明支持多相机同步），**缺的是触发源与驱动配置**，而且按平台不同（见下）。
- **时间戳精度**：时间戳是"谁在什么时刻打的"。kernel 在中断里打戳会引入几十 µs 抖动；V4L2 的 `timeval` 本身量化到 1 µs；只有传感器/VI 输出的硬件戳或 PTP 才能到 ns。**这决定了你能测到多准，而不是触发有多准。**

三个概念的关系：时钟给"刻度"，同步信号给"共同起点"，时间戳给"测量手段"。只有刻度而没共同起点，就无法保证两路帧同时曝光；有共同起点但时间戳抖动大，就无法验证它是否真的同步。

| 平台分支 | 现状 | 证据 |
| --- | --- | --- |
| QCOM / spectra（comma 3X 等） | 有硬件同步：panda TIM1 → FSIN，三路同相，sensor 配为从设备 | 见下表各行 |
| **Jetson / Orin（本项目实际设备）** | **模组支持帧同步，但当前未启用**：SG2-IMX390C-5200-GMSL2 的 sensor 帧同步由 MAX9295A 的 **MFP7** 控制（模组框图信号名 `FSN`），规格书写明 "Multi-Camera synchronization Support"；但 `camera_jetson.cc` 只有 V4L2 采集、NVMM/VIC 转换与曝光/增益闭环，**从未配置 MFP7/FSIN**，所以相机按自由运行出帧。时间戳取 V4L2 buffer 戳（`extra = {frame_id, ts, ts}`） | 模组规格书 SG2-IMX390C-5200-GMSL2（Sensing，Rev.2，2023-03）：Sensor `Frame Sync = Controlled by Max9295A MFP7`、框图 `Sensor Frame Sync → MFP7`、"Multi-Camera synchronization Support"；代码侧 [camera_jetson.cc](file:///data/openpilot_egpucp/openpilot/system/camerad/cameras/camera_jetson.cc#L593-L597)（`ts = b.timestamp.tv_sec*1e9 + tv_usec*1e3`，`extra = {frame_id, ts, ts}`）、[send_state](file:///data/openpilot_egpucp/openpilot/system/camerad/cameras/camera_jetson.cc#L860-L889)（`setTimestampSof/Eof` 同用该 ts）；[camera_event_timing.h](file:///data/openpilot_egpucp/openpilot/system/camerad/cameras/camera_event_timing.h#L5-L7) 明确写 "BOOT_TS ... not an independent sensor timestamp" |

下表按"若走 spectra 路径"列出通用事实；Orin 路径的差异集中在"模组支持外部触发但未启用"与"时间戳来源"两行：

| 项目 | 现状 | 证据 |
| --- | --- | --- |
| 是否有硬件同步触发 | **有**。panda 的 MCU 用 TIM1 PWM 产生 FSIN 帧同步脉冲，默认 50 ms 周期（20 Hz）、2 ms 脉宽，输出在 PB14/PB15（PA8 可选） | [clock_source.h](file:///data/openpilot_egpucp/panda/board/drivers/clock_source.h#L3-L28)、[clock_source_declarations.h](file:///data/openpilot_egpucp/panda/board/drivers/clock_source_declarations.h#L3-L4)（`PERIOD_MS=50`、`PULSE_LEN_MS=2`） |
| 谁使能该信号 | 三种板型启动时都调用 `clock_source_init()`（PB14/PB15 始终输出）；区别只是 PA8 通道：`tres`/`dos` 传 `false`，`cuatro` 传 `true` | [tres.h](file:///data/openpilot_egpucp/panda/board/boards/tres.h#L132)、[cuatro.h](file:///data/openpilot_egpucp/panda/board/boards/cuatro.h#L94)、[dos.h](file:///data/openpilot_egpucp/panda/board/boards/dos.h#L109) |
| 三路是否同相 | 是。三路共用 TIM1 同相位输出；driver 若要半周期错开需要配套 TIM8 固件（当前未启用） | [hw.h](file:///data/openpilot_egpucp/openpilot/system/camerad/cameras/hw.h#L69-L71)，三路 `staggered_sof=false`（L43/L56/L71） |
| Orin 模组是否支持外部触发 | **支持**。IMX390 的 `FSN` 引脚由 MAX9295A MFP7 驱动，规格书写明 "Multi-Camera synchronization Support"；GMSL2 链路可把 9296 侧 MFP 收到的脉冲透传给 9295。缺的是驱动初始化与一路触发源，不是模组能力 | 规格书同上（`Frame Sync = Controlled by Max9295A MFP7`、框图 `Sensor Frame Sync → MFP7`、"Multi-Camera synchronization Support"） |
| 相机是否从设备 | spectra 路径：是。sensor 寄存器显式配置为外部触发（非自由运行）：AR0231 写 `SLAVE_SH_SYNC_MODE` 加 `FRAME_START_MODE`；ox03c10 用 "FSIN with external pulses"；os04c10 有 FSIN 配置段 | [ar0231_registers.h](file:///data/openpilot_egpucp/openpilot/system/camerad/sensors/ar0231_registers.h#L37-L40)、[ox03c10_registers.h](file:///data/openpilot_egpucp/openpilot/system/camerad/sensors/ox03c10_registers.h#L67-L73)、[os04c10_registers.h](file:///data/openpilot_egpucp/openpilot/system/camerad/sensors/os04c10_registers.h#L251) |
| 启动期对齐校验 | 首帧要求非交错相机之间误差 < 0.2 ms；40 帧仍对不齐则放弃校验继续跑（只打日志） | [spectra.cc](file:///data/openpilot_egpucp/openpilot/system/camerad/cameras/spectra.cc#L1587-L1634) |
| 首帧是否有确定相位 | 没有。sensor 的"等第一个脉冲再出帧"寄存器在部分设备上会出问题，已被注释掉 | [ox03c10_registers.h](file:///data/openpilot_egpucp/openpilot/system/camerad/sensors/ox03c10_registers.h#L75-L76)（`// causes issues on some devices` / `// wait for pulse before first frame`） |
| 运行期是否持续监测 | **没有**。`syncFirstFrame` 成功后 `first_frame_synced=true` 直接返回，之后不再检查 | [spectra.cc](file:///data/openpilot_egpucp/openpilot/system/camerad/cameras/spectra.cc#L1588) |
| Orin 上是否已有帧对配对 | **有，但只服务于 modeld 输入**：`receive_camera_pair` 按 `timestamp_sof` 取最近一帧对，超窗时只推进较旧一路，最多重试 10 次；窗口是 **20 ms 绝对阈值**（注释记录 EV9 实测两路偏置 12.6–13.2 ms、Ioniq 恢复期出现 50–150 ms 陈旧对；20 ms 已超过 30 fps 半周期，应收到 15 ms，见 §16.4）。配对失败时 `modeld` 直接跳过该帧（`modeld.py:505-508`）。这说明本项目两路相机的时间差存在**固定偏置 + 慢漂**，不能用绝对窗口当抖动指标，也说明 T0 的配对逻辑已有可复用实现 | [camera_sync.py](file:///data/openpilot_egpucp/openpilot/selfdrive/modeld/camera_sync.py#L4-L56)、[modeld.py](file:///data/openpilot_egpucp/openpilot/selfdrive/modeld/modeld.py#L505-L508) |
| 帧时间戳来源（spectra） | kernel 在 SOF 事件打戳（`BOOT_TS`，即 `CLOCK_BOOTTIME` 纳秒）；`timestampEof = SOF + sensor readout` | [spectra.cc](file:///data/openpilot_egpucp/openpilot/system/camerad/cameras/spectra.cc#L1418-L1420)（`BOOT_TS from the kernel SOF handling path`） |
| IMU 时间戳 | GPIO data-ready 中断（lsm6ds 的 data-ready 脉冲仅 75 µs，故双边沿检测）+ 内核 GPIO 事件时间戳；并做 10 ms 的系统时间跳变保护 | [sensord.py](file:///data/openpilot_egpucp/openpilot/system/sensord/sensord.py#L29-L63) |
| GPS/UTC 对时 | `gpsLocationExternal` 10 Hz 毫秒级时间；`clocks` 10 Hz 只给 wall/boot 两种系统时间，无硬件计数；仓库内无 1PPS 解析、无 RTC 对时 | [services.py](file:///data/openpilot_egpucp/openpilot/cereal/services.py#L65-L70)、[log.capnp Clocks](file:///data/openpilot_egpucp/openpilot/cereal/log.capnp#L2154-L2156) |
| 现有验收门限 | 启动/测试容忍 1.1 ms（camerad 测试）与 2 ms（onroad 测试） | [test_camerad.py](file:///data/openpilot_egpucp/openpilot/system/camerad/test/test_camerad.py#L107-L117)、[test_onroad.py](file:///data/openpilot_egpucp/openpilot/selfdrive/test/test_onroad.py#L344-L349) |
| 标定链路是否用帧对 | 否。`calibrationd` 的 `SubMaster` 只有 `['cameraOdometry', 'carState']`（`poll='cameraOdometry'`），不订阅任何相机帧，也从不配对 road/wide；配对只发生在 `modeld` 的输入路径（`camera_sync.receive_camera_pair`）与测试里 | 本仓库 `selfdrive/locationd/calibrationd.py:265`；`receive_camera_pair` 仅被 `modeld.py` 调用 |

**结论（明确回答"系统有没有微秒级时钟信号"）**：

- **有微秒级（实际是 ns 分辨率）的时钟读数**：ARM 架构定时器 + `CLOCK_MONOTONIC/BOOTTIME`，所有时间戳都基于它，这一层不缺。
- **"微秒级同步信号"在 Orin 上是"能力具备、当前未启用"**：模组侧 IMX390 的 `FSN` 由 MAX9295A MFP7 驱动，规格书写明支持多相机同步；但 camerad 从未配置 MFP7/FSIN，所以相机按自由运行出帧。`timestampSof/timestampEof` 都等于 V4L2 buffer 时间戳（1 µs 量化、驱动收帧时刻），SOF/EOF 无法区分。comma 的 spectra 路径用 panda FSIN，且 panda 定时器被设成 **0.1 ms/tick** —— 这正是"0.1 ms"的来源，它是**触发发生器的分辨率**，不是系统时钟精度，可以改到 1 µs。
- **还缺"能自证同步"的时间戳**：现有戳是 kernel/驱动在收帧时打的，不是传感器 SOF 硬件戳（`camera_event_timing.h` 自己写明 `not an independent sensor timestamp`），所以即便有 FSIN，也只能测到几十 µs 量级，无法声称 ns 级。

所以对 Orin：**µs 级"刻度"有，µs 级"同步"当前未启用但硬件基础具备**——模组支持 `FSN`（MAX9295A MFP7），GMSL2 链路可透传触发，缺的是驱动初始化与一路触发源（panda FSIN 或 SoC PWM）。v1 仍按系统时钟微秒级（§16.3 T0）交付，因为它是纯软件、可立即上线；T1 把触发接起来后只需换 `cameraSyncState` 的生产者与阈值，消费端代码不动。

### 16.2 精度需求量化（为什么是 µs，而不是 ns）

以帧差 `Δt` 造成的等效误差估算（车速 30 m/s、目标距离 10 m）：

- 视觉外参（宽窄相对角度）：`Δt = 1 ms` → 车体位移 3 cm → 10 m 处约 `0.17°`；要把该项压到 `0.02°` 需 `Δt ≤ 0.12 ms`。所以**视觉链路需要亚毫秒、约 100 µs 量级**。
- L1 陀螺-光流：横摆 30 °/s 时 `Δt = 1 ms` → `0.03°` 姿态误差，与 §6.1 的 `0.05°` 收敛目标同量级，因此也要求 `Δt < 0.5 ms`，与视觉约束联合后仍需 `< 0.1 ms`。
- 再往下到纳秒级：对**纯视觉标定没有可测量的收益**（100 ns × 30 m/s = 3 µm）。它的价值在跨硬件/绝对时间场景：雷达、事件相机、V2X、跨车与云端对齐。

因此分档目标按"对谁有收益"来定，避免为指标而过度设计。v1 的系统时钟档（T0）就是按这两条做的取舍：纯视觉要 100 µs，先用"帧对窗口 + IMU 姿态外推扣除"把 2 ms 的物理时间差压到等效 0.02°；等硬件触发（T1）到位，再把物理时间差本身收到 100 µs。

必须区分两个量，否则指标会写错：

- `Δts` 的**均值**（`deltaRef`）：仓库内 `camera_sync.py` 注释记录 EV9 实测 12.6–13.2 ms。这是**固定偏置**，可被精确跟踪并扣除，本身不产生角度误差（两路自由运行但同源时钟时它近似常量）。
- `Δts` 相对 `deltaRef` 的**残差**：逐帧抖动与小时级慢漂，这部分才是无法完全扣除的误差来源。

所以 T0 的所有门限与指标都针对**残差**，而不是 `Δts` 的绝对值；绝对窗口只做"防止拿到陈旧/错配帧对"的兜底，取 15 ms（< 30 fps 半周期 16.7 ms），不能当抖动指标使用。

### 16.3 分档与 v1 取舍

按"时基从哪来"分四档，v1 只交付 T0：

| 档 | 时基来源 | 指标 | 手段 | 阶段 |
| --- | --- | --- | --- | --- |
| T0（系统时钟，**v1 交付**） | `CLOCK_BOOTTIME` ns 刻度；相机时间戳为 V4L2 收帧戳（1 µs 量化，`timestampSource=kernel_recv`） | 两路时间差可测且稳定：**帧对残差** P99.9 ≤ 2 ms；逐帧抖动 P99.9 ≤ 500 µs（首轮实测后收紧，100 µs 是 T1 指标，v1 不承诺）；24 h 相位漂移可跟踪可校正；IMU 对齐后等效角度残差 ≤ 0.02°@10 m | 统一时基 + 逐帧时间差统计 + 相位回归 + 帧对筛选 + IMU 姿态外推 | v1 |
| T1（硬件触发，v1.1 可做） | panda TIM1 FSIN（1 µs tick）→ GMSL2 GPIO 透传 → MAX9295A MFP7 → IMX390 `FSN`；或 VI 硬件时间戳 | 两路 SOF 差 P99.9 ≤ 100 µs，抖动 ≤ 50 µs，24 h 相对漂移 ≤ ±5 ppm，丢触发 1 s 内检出 | 外部触发 + 运行期相位监测 | v1.1/v2，**模组已支持，需驱动启用 + 一路触发源** |
| T2（绝对时间，远期） | GNSS 1PPS / gPTP PHC | 与 UTC ≤ 1 µs（PPS 驯服）；有 PTP 硬件时 ≤ 100 ns | 驯服本地计数器 | 远期，需硬件 |
| T3（全硬件统一时基） | IMU/GPS/CAN/雷达/相机共用同一硬件计数 | 全传感器同源可对齐 | 统一 `TimeBase` 抽象 | 远期 |

T0 与 T1 的差别只有两点：**时间差有多大**、**时间差能否直接测到曝光起点**。二者共用同一套消息、同一套统计、同一套门控代码，所以从 T0 升到 T1 是"换生产者 + 收紧阈值"，不重写消费端。**不得在 UI/文档中把 T0 描述为"µs 级硬件同步"**，正确说法是"系统时钟同步（未硬件同步）"。

### 16.4 T0 落地方案（v1 范围：只用系统时钟）

0. **统一时基与戳的语义**：相机、IMU、`cameraOdometry`、日志一律用 `CLOCK_BOOTTIME` ns（车载不休眠，与 `CLOCK_MONOTONIC` 一致），禁止 wall/UTC 混入估计。`cameraSyncState` 显式写 `timebase=SYSTEM_CLOCK`、`timestampSource=kernel_recv`、`quantizationNs=1000`，让下游无法误把它当硬件戳。
1. **逐帧时间差统计（复用现有配对）**：直接调用 `camera_sync.receive_camera_pair`，按 `timestamp_sof` 取最近一帧对（不假设两路等间隔出帧）；计算 `Δ = ts_road − ts_wide`，滑动窗口（600 对 ≈ 30 s）输出 P50/P99.9 与 MAD；再以时间为自变量做线性回归得 `deltaRef` 与 `skewPpm`。`deltaRef` 只在 `v_ego > 5 m/s`、两路均无丢帧、曝光未触顶的帧对上更新（停车时帧率/曝光变化会污染回归）。注意 `Δ` 的均值里含两路打戳偏置差，**只能用于稳定性判定，不能解释为曝光时刻差**。
2. **帧对窗口（相对量）**：`|Δ − deltaRef| ≤ 2 ms` 时视为可用帧对，`synced=true`；跳变 > 5 ms（换流/重启/掉帧）立即 `synced=false` 并重置 `deltaRef`。窗口判据是**相对 `deltaRef` 的残差**，不是绝对 `Δ`——仓库注释记录的 12.6–13.2 ms 固定偏置应能正常通过。**绝对上限要从现有的 20 ms 收到 15 ms**：两路都是 30 fps，半周期 16.7 ms，20 ms 的窗口会把"错配到相邻帧"的帧对也放进来（`camera_sync.py` 头部按 20 Hz/50 ms 写的注释已过期）。15 ms 仍能容纳 12.6–13.2 ms 的实测偏置，且留 1.7 ms 余量。2 ms 残差在 30 m/s 下对应 6 cm，经 IMU 扣除后对标定无实质影响；100 µs 的要求属 T1，v1 不承诺。
3. **帧对筛选**：取窗口内首个合格帧对（与现有 `receive_camera_pair` 一致），**不插值、不合成帧**。逐 block 记录帧对可用率，低于 95% 判定该段数据不可用。
4. **IMU 时间对齐（T0 的核心）**：用 `cameraOdometry` 的姿态与角速度，把 wide 观测外推到 road 帧时刻（`R(Δt) ≈ exp([ω]× Δt)`），在重投影残差里显式扣除该运动项，并输出 `alignedResidualNs`。**时间差必须作为独立项建模，不允许靠调外参去吸收**——那是把时间误差伪装成角度误差的典型路径。

   外推只能扣除**旋转**项，这一点决定各层能不能用配对数据：
   - L1 相对外参只用远场点，`Δt = 13 ms` 在 30 m/s 下对应 39 cm 平移，远场视差可忽略，扣除旋转后残差在噪声内；
   - L3 每路内参用**本路帧序列**（单目约束，不需要跨路配对），固定偏置根本不进入误差；
   - 只有 wide↔road 联合约束（§15.4 宽窄交叉）用得到近场点，此时 39 cm 平移在 10 m 处约合 2.2°，**必须按 `Δt` 显式计入平移视差**，否则这个固定偏置会整体被换算成外参误差。这也是 §15.4 要求"仅在相对外参收敛后启用"的原因。
5. **`cameraSyncState`（10 Hz，`only_onroad`，发布者是 `camcalibd`）**：逐路 `{cam, deltaNs, deltaP50Ns, deltaP99Ns, jitterNs, skewPpm, missingFrames, streamEpoch, synced, timebase, timestampSource, quantizationNs, alignedResidualNs}`；其中 `jitterNs` 是残差的 MAD（不是 `Δ` 的标准差）。**`missingFrames` 不能靠 V4L2 `b.sequence` 差值统计**：它是出队序号而不是 sensor SOF 计数（丢帧通常不产生缺口），`start_streaming` 还会重新起算；`frame_id` 只反映"已发布帧"（`modeld.py` 的 `vipc_dropped_frames` 且只统计主路），两路计数器各自起算，不能按相等配对。正确做法：**单路相邻帧 `timestampSof` 间隔 > 1.5×帧周期**即记丢帧；`b.sequence` 回绕或时间戳跳变则 `streamEpoch += 1` 并重置统计。该服务只给 `camcalibd` 自用，不放进 `LiveCalibrationData`，也不进入 `calibrationd` 的 `all_checks`。
6. **门控与降级**：`synced=false` → `camcalibd` 停止采样该路、`calibrationd` 不落盘、UI 提示"相机时间同步退化"；恢复后需连续 60 帧合格才重新放行，防止抖动式进出。
7. **可选相位伺服（不加硬件也能调相位）**：若 `deltaRef` 落在坏窗口（仓库注释记录的 12.6–13.2 ms 已接近 16.7 ms 半帧，属需要关注的情形），可通过 V4L2 `VBLANK`/VTS 微调其中一路帧周期，把相位拉进目标窗口；每行约 30 µs@1080p，总调整限制在 1% 帧周期内，调完稳定 10 s 才允许采样。该手段只动相位、不动帧率量级，属可选优化，不阻塞主链路。
8. **漂移与温度**：两路若同源 MCLK，`skewPpm ≈ 0`；若实测有 ppm 级漂移，用 `skewPpm` 跟踪并定期重估 `deltaRef`。温度与晶振的关系留到 T1 再建模。
9. **升级路径（只换生产者）**：T1 到位后 `timebase` 改 `FSIN`/`HW_TS`、`timestampSource` 改 `sensor_sof`，阈值从 2 ms 收到 100 µs，其余字段、订阅关系、门控逻辑全部复用；T2 到位后再把阈值收到 ns 级并启用 `PPS_LOCKED`/`PHC` 标记。这就是"以后有硬件再接纳秒级"的接口设计。

### 16.5 T1/T2（硬件与纳秒级，预留，不在 v1）

T1（µs 级硬件触发）在硬件上已具备条件，是"配置任务"而不是"换硬件"。本项目模组为 SG2-IMX390C-5200-GMSL2：IMX390 的 `FSN` 由 MAX9295A 的 **MFP7** 驱动，规格书写明支持多相机同步；链路是 MAX9295A → MAX9296A → Tegra VI，GMSL2 的 GPIO 透传可把 9296 侧 MFP 收到的脉冲送到 9295 的 MFP7。落地分四步：

1. **触发源**：panda TIM1 FSIN（PB14/PB15；先把 tick 从 0.1 ms 改到 1 µs），或 Orin 侧 PWM/GPIO；
2. **去串化侧**：把 MAX9296A 的 MFP 配成 GPIO 输入并开启链路 GPIO 透传（需确认本机 9296 板是否引出该脚）；
3. **串化侧**：配置 MAX9295A 把 MFP7 设为帧同步输出，IMX390 进 slave/外部触发模式；
4. **采集侧**：`camera_jetson.cc` 出帧逻辑不用改（触发只改变曝光起点），只需把 `timestampSource` 标为硬件触发并接入相位统计。

T1 的验收是两路 SOF 差 P99.9 ≤ 100 µs，不是 ns。厂商整机方案（CCG3-4H/8H 采集卡）还提供 GPS 定时同步与网络 PTP，但那是 x86 + PCIe 卡的能力，本项目 Orin 不适用。

T2（纳秒级绝对时间）的边界：

- 前提硬件：GNSS 模块 1PPS 输出接到 panda/Orin 的 GPIO（中断打戳），或 Orin 侧具备 PTP 硬件时间戳（PHC）。**本仓库当前没有 PPS 解析代码，也没有 PHC 使用**，因此 T2 属于"硬件具备才做"，不能作为 v1 验收项。
- 做法：1PPS 中断 → 记录本地计数 → 用线性回归/PLL 驯服本地计数器（求 offset 与频率修正），把 `TimeBase` 标记为 `PPS_LOCKED`；PTP 场景用 `SO_TIMESTAMPING` 硬件时间戳。
- 达标判定：与 UTC 偏差 ≤ 1 µs 才能标 `PPS_LOCKED`；只有 GPSDO 或 PTP 硬件才能到 100 ns。
- 若硬件不支持：只能做到"设备内相对同步"，绝对时间仍是 ms 级。此时必须在日志与 UI 中明确标注，禁止用"纳秒级同步"措辞。
- T3 需要在各驱动层都拿硬件时间戳：IMU 的 data-ready 已是中断打戳（接近硬件）；CAN 目前是设备侧收包时间（百赫兹轮询，ms 级）；雷达/外设按各自驱动能力评估。此项收益主要在融合感知，不在标定。

### 16.6 验收与门禁

- **T0 基线（v1 必做）**：不改任何硬件，连续记录 1 h，**分开统计**固定偏置 `deltaRef`（预期 12–13 ms）与帧对残差（P50/P99.9/MAD），再统计 24 h 内 `deltaRef` 漂移；最后用 IMU 外推扣除时间差，量测对齐后的等效角度残差。配对直接复用 `camera_sync.receive_camera_pair`，保证基线与 `modeld` 看到的是同一批帧对。这是 v1 的交付基线，也是将来判断"值不值得上 T1"的依据。
- **T0 故障注入**：屏蔽一路 / 强制改帧率 / 拔插设备，要求 1 s 内 `synced=false` 且标定停止采样（不允许静默降级）。
- **T1 台架（驱动启用触发后）**：示波器测 panda PB14/PB15 的 FSIN、MAX9295A MFP7 输出与 IMX390 `FSN`，要求周期 50 ms ± 1 µs、抖动 < 1 µs；同时对比相机时间戳序列。
- **T1 实车 1 h（驱动启用触发后）**：P99.9 两路时间差 ≤ 100 µs；无丢帧；`|skew| ≤ 5 ppm`；相位无单调漂移。
- **离线**：`tools/camcalib_offline.py` 在标定前先跑同步健康检查，不通过的日志段直接标注"不可用于标定"，并输出逐段相位曲线。
- **CI**：新增 `test_camera_sync.py`，用录制 rlog 断言上述指标；`test_onroad` 的 2 ms 门限保留为兜底，不因新机制而放宽。

### 16.7 风险与对策

| 风险 | 对策 |
| --- | --- |
| **v1 未启用硬件触发，两路曝光起点不受控（代码事实）** | 走 T0：不声称硬件同步，用帧对窗口 + IMU 姿态外推扣除时间差 + UI 明确标注"系统时钟同步"；模组已支持 `FSN`（MAX9295A MFP7），T1 只需驱动启用 + 一路触发源（§16.5） |
| 把"系统时钟同步"说成"µs 级硬件同步" | 消息里带 `timebase/timestampSource/quantizationNs`，UI 与文档固定文案；这是对外表述的硬约束 |
| 把绝对 `Δts` 当抖动指标（会把 12–13 ms 的固定偏置误判为"不同步"，或把 20 ms 绝对窗口误当成精度） | 所有门限/指标只针对 `Δts − deltaRef` 的残差；`MAX_CAMERA_SKEW_NS` 仅作陈旧对兜底（§16.2、§16.4） |
| 用调外参去吸收时间差 | `camcalibd` 必须显式输出 `alignedResidualNs`；离线工具检查该项与残差的相关性，强相关即拒绝写入 |
| 把 panda FSIN 经 GMSL2 透传到 MAX9295A MFP7 的兼容性（T1） | 先做单路台架：确认 9296 板 GPIO 引出、示波器量 MFP7 输出与 `FSN` 波形，再上双路；未通过则继续留在 T0 |
| 定时器仍是 0.1 ms tick，改了 tick 却没改控制请求粒度 | 同一次改动里统一 tick 与请求单位，并加台架波形测试（§16.6） |
| 固件/驱动版本不匹配（TIM8 与 staggered driver） | `staggered_sof` 保持 false；启用前要求固件版本校验 |
| FSIN 丢失后传感器静默自由运行 | 运行期相位监测 + 丢脉冲计数，1 s 内检出并停采样 |
| 晶振温漂导致相位慢漂 | `skew` 估计 + 温度记录；超阈值标 `synced=false` |
| 相机 FSIN 最小脉宽/极性要求 | 保持 2 ms 脉宽（现有值），改 tick 时同步验证寄存器配置 |
| BPS 路径的处理延迟（driver 相机）被误当成同步误差 | 只比较帧起始时间戳（T1 下为 SOF）；EOF 不参与同步判定 |
| 为达标过度设计到 ns 级 | 按 §16.3 分档，v1 只交 T0，T2 只定义不承诺 |

### 16.8 与标定主链路的关系

时间同步不是标定参数的一部分，因此**不放进 `CameraCalibSet`**，避免污染唯一数据源；它以 `cameraSyncState` 独立消息存在，作为 `camcalibd` 采样与 `calibrationd` 落盘的前置条件。同步不达标时的正确动作是"不采样、不落盘"，而不是用算法去补偿时间误差——把时间误差当外参误差吸收，正是最难排查的一类标定偏差。

T0→T1 的切换只改 `cameraSyncState` 的生产者与判定阈值，`camcalibd`/`calibrationd` 的订阅关系与门控逻辑不变；因此 v1 写的软件同步代码在硬件到位后不会作废，只是阈值从 2 ms 收紧到 100 µs、再收紧到 ns。

## 17. 结论

用 `CameraCalibSet.cams[CamId]` 这一个可变长数组承载各路相机的全部内外参，配合 body 参考系、`seq` 版本号与唯一写入者，能从机制上消除"各处各算一套"的问题，也为后续加入左/右/后相机留好了扩展点。v1 的实际内容是三项：`ROAD/WIDE`（`AUTO`，在线估计）+ `DCAM`（`PRIOR`，只有工厂内参、`extrinsic_valid=False`）；`LEFT/RIGHT/REAR` 的枚举与字段已预留，接入时按 §14.1 逐路独立追加，不共享任何内参、外参、安装高度或状态。

"所有消费端取同一份参数"已按代码实际清单落成可执行约束：modeld、UI（含 model_renderer）、DM/monitoring、locationd 位姿链、controlsd/selfdrived/paramsd/lagd/torqued（经 `PoseCalibrator`）、cluster、web AR、server/WebRTC 共 15 处以上消费点全部改读 `CameraCalibSet` 或唯一 `to_json` 网关（§5.2、§7.4、§12），并由 §10.6 静态扫描门禁（`test_no_direct_calib_readers.py`）阻止新增代码再直读 `rpyCalib/wideFromDeviceEuler/DEVICE_CAMERAS`。写入端仍只有 `calibrationd`，没有任何第二写者。

自动校准按"相对外参 → 路面外参 → 内参 → 可选畸变"分层推进，每层都有门限、限幅、影子期与独立开关，保证在真正影响控制之前先拿到可量化证据；旧字段与新字段在同一条消息内一次序列化写出，任何阶段都能回滚到当前行为。

精度与收敛速度的上限不靠 v1 一次做满：§15 给出了信息增益门控、自适应鲁棒核、CUSUM 故障隔离、宽窄交叉约束、温度漂移、因子图 + IMU 预积分、车队先验等升级路径，并标注了收益/代价/风险与建议阶段。它们共用同一套数据结构与落盘护栏，可按 v1.1、v2 逐项叠加，不影响本方案的机制正确性。

时间同步单列一节（§16），因为它是精度的物理前提而不是算法技巧。核查结论是：**系统时钟本身不缺**（`CLOCK_BOOTTIME`，ns 刻度，所有时间戳共用）；**模组本身也支持帧同步**（SG2-IMX390C-5200-GMSL2：IMX390 `FSN` ← MAX9295A MFP7，"Multi-Camera synchronization Support"）——spectra 路径的 panda FSIN 只是其中一种实现，且 tick 只有 0.1 ms、仅启动校验一次；**Orin 侧缺的是"启用"**：`camera_jetson.cc` 从未配置 MFP7/FSIN，相机按自由运行出帧，`timestampSof/timestampEof` 同为 V4L2 收帧戳（1 µs 量化）。

因此 v1 按"先系统微秒级、后硬件纳秒级"推进：v1 交付 T0——统一时基、复用 `camera_sync.receive_camera_pair` 做帧对配对、统计 `Δts − deltaRef` 残差（≤2 ms，固定偏置 12–13 ms 另行跟踪，不当作抖动）、IMU 姿态外推显式扣除旋转项（平移项仅在宽窄联合约束中按 `Δt` 计入）、`cameraSyncState` 门控与 UI 标注，验收指标是"对齐后等效角度残差 ≤ 0.02°@10 m"，而不是声称硬件同步；T1（FSIN 或 VI 硬件戳，≤100 µs）与 T2（1PPS/gPTP，ns）只预留接口与字段，有硬件后换生产者、收紧阈值即可，消费端代码不动。**任何档位都不允许把时间误差吸收成外参误差。**

## 18. 实施前审计清单（2026-11-12，逐条核对代码）

本节只记录**开工前必须知道的事实**，每条都有代码位置。P0 未清零前不进入实现，否则会在联调阶段返工。

### 18.1 P0：会直接崩溃或让新机制失效

| # | 位置 | 事实（已核对） | 后果 | 处理 |
| --- | --- | --- | --- | --- |
| A1 | `selfdrive/carrot/intrinsic_calibd.py`、`common/params_keys.h` | `CamCalibRoad`/`CamCalibWide` **从未注册**；`Params.get/put/remove` 均先 `check_key`，未注册抛 `UnknownKeyName`（[params_pyx.pyx](file:///data/openpilot_egpucp/openpilot/common/params_pyx.pyx#L100-L105)） | 进程在 `__init__` 的 `seed_prior()` 就崩，不是"跑了没效果" | 按 §5.1 删除这条写盘路径；若短期要跑影子，先在 `params_keys.h` 注册两个 key 并重建 `params_pyx` |
| A2 | `selfdrive/locationd/calibrationd.py:300` | `send_data` 用 `sm.all_checks()` 生成 `liveCalibration.valid` | 新增 `cameraCalibCandidate` 订阅后，`camcalibd` 未启用/降频会让 `valid` 变 false，波及 modeld/selfdrived/UI | 改成 `sm.all_checks(['cameraOdometry','carState'])`，候选只按 `sm.updated` 取 |
| A3 | 设计原稿 §4.4 | 曾设计 `Params["CameraCalibSet"]` + `CalibrationParams` 双写 | `Params` 无事务，两次写之间掉电/被杀会留下两份不一致参数 | 已改为**只写 `CalibrationParams`**，新字段与旧字段同一次 `to_bytes()`（§4.4、§5.1） |
| A4 | `common/params_keys.h`、`system/manager/params_check.py` | 新 key（开关参数）必须登记并重建 `params_pyx`；`params_check` 会把代码里用到的 key 与注册表对齐 | 漏登记时启动即报 `UnknownKeyName`/CI 失败 | 见 §12 文件表；重建后跑 `params_check` 与 `test_settings_schema.py` |
| A5 | `cereal/services.py`、`cereal/services.h` | 新服务必须先登记再启动发布；`services.h` 由 codegen 生成 | 未登记时 `SubMaster` 直接抛未知服务 | 登记 `cameraCalibCandidate`、`cameraSyncState` 后重新生成并跑 `test_services.py` |

### 18.2 P1：现有代码的确定性缺陷（迁移时必须一起修）

| # | 位置 | 事实 | 影响 | 处理 |
| --- | --- | --- | --- | --- |
| B1 | `selfdrive/carrot/intrinsic_calibd.py:324` | `VisionIpcClient.recv()` 默认 `timeout_ms=100`，且两路串行调用 | 单次循环最多阻塞 200 ms，采样率掉到 ~5 Hz，且帧与 `rpyCalib` 最多错配 100 ms | 改 `recv(0)` 非阻塞；用 `buf.timestamp_sof` 与 `liveCalibration` 做时间关联，不用"最新值"硬配 |
| B2 | 同上 `:314` | `abs(pitch) < MIN_PITCH(0.001 rad)` 时整轮跳过 | 安装俯仰接近 0 的车永远不采样 | 迁移后以 `camcalibd` 的 L1 是否收敛为准，不再用绝对 pitch 门槛 |
| B3 | 同上 `:336` | `cy = buf.height/2`、`s.cy` 首次采样后缓存 | 主点非中心或分辨率变化时消失点先验错位，`offset` 系统性偏差 | 用 `K(ROAD/WIDE)` 的 `cy`，`identity.sizes` 变化时重置 `cy` 与样本 |
| B4 | `selfdrive/modeld/modeld.py:526`、`ui/onroad/augmented_road_view.py` | `CameraYawTrimDeg` 只在 modeld 里减，UI 不减；单位为 0.01°（`INT`） | 设过 trim 的车，模型与 UI 投影不一致；按度/弧度误用会差 2 个数量级 | 合并进 `cams[ROAD].rpy[2]`，模型/UI 同源；验收必须用 `trim≠0` 数据（§5.2） |
| B5 | `selfdrive/carrot/realtime/compact_state.py`、`compact_state_native.cc`、`web/js/realtime/vision_compact.js` | 字段表里没有 `wideFromDeviceEuler` | web/WebRTC 从来拿不到 wide 相对外参，wide 可视化只能退回"与 road 同向" | 网关一次带全 `cams[]`；不再手写偏移表 |
| B6 | `web/js/realtime/raw_capnp.js:372`、`home_drive.js:623`、`home_drive.js:137` | sensor 枚举只映射到 index 3，内参表只有 `ar_ox/os04c10`；`log.capnp` 的 `imx390` 是 4 | 本项目 web AR 解析不出 profile、**不渲染**（现存故障） | 短期补 index 4 + imx390 档位；长期删镜像改网关（§7.4） |
| B7 | `tools/replay/ui.py` | 写死 `DEVICE_CAMERAS[("tici", sensor)]` | 回放本项目 rlog 直接 `KeyError` | 读消息内 `cams[]`，旧 rlog 回退 |
| B8 | `selfdrive/carrot/signal_stop_prepare_runtime.py` | `ok` 条件要求 `fcam.size == (1344,760)`，取 `fcam.focal_length` | 1920×1080 的 imx390 上该功能永远禁用 | 改 `K(ROAD)` + 尺寸无关门控 |
| B9 | `selfdrive/modeld/modeld.py:543` | `vipc_dropped_frames` 只看主路 `frame_id` | wide 掉帧不可见，同步统计缺一路 | 由 `camcalibd` 按 `timestamp_sof` 间隔自算（§16.4 第 5 条） |
| B10 | `selfdrive/locationd/calibrationd.py:280` | trim 非零且已标定时整体跳过 `handle_cam_odom`（rpy/height/wide 全冻结） | 冻结期间 `intrinsic_calibd` 的输入 pitch 恒定，联合 LSQ 退化 | 冻结期 `camcalibd` 只允许 `vp_offset` 模式且**不更新 `f`**（§5.1、§6.3） |
| B11 | `selfdrive/monitoring/policy.py:110` | `ref_undistorted_cam = DEVICE_CAMERAS[("tici", "ar0231")].dcam`，设备键写死 `tici` | 本项目 `("pc","imx390")` 下取的是 `_ar_ox_fisheye`（1928×1208、f=567），与真实 dcam（1920×1080）尺寸/焦距都不符，面部反投影尺度系统性偏差；且是 DM 链路上第二份硬编码真值 | 改为 `set.K(DCAM)` / `identity.size(DCAM)`（`source=PRIOR`），删除该行；§10.6 不再给它白名单 |

### 18.3 P2：统计口径与验收口径的修正

| # | 事实 | 处理 |
| --- | --- | --- |
| C1 | `MAX_CAMERA_SKEW_NS=20 ms` > 30 fps 半周期 16.7 ms；`camera_sync.py` 头注释按 20 Hz/50 ms 写 | 收紧到 15 ms；判据统一为 `\|Δ−deltaRef\| ≤ 2 ms`（§16.4 第 2 条） |
| C2 | `b.sequence` 是 V4L2 出队序号，`start_streaming` 重新起算；本文件注释记录按 `sequence%3` 丢帧导致两路选到不同物理帧、SOF 偏 >20 ms | `missingFrames` 用"相邻 `timestampSof` 间隔 >1.5×周期"；`sequence` 只做路内辅助；增加 `streamEpoch` |
| C3 | `frame_id` 跨重启不回绕，`sequence` 会 | 所有缓存/连续性判断以 `(streamEpoch, timestampSof)` 为键 |
| C4 | `test_onroad.py` 的 `PROCS` 合计 323%/350%，未含 `camcalibd` | 新增 `selfdrive.locationd.camcalibd ≈ 4%`，重跑 25 s 基线 |
| C5 | `cluster_live.py` 自己解析 `CalibrationParams`，`cluster_renderer.py` 直接 import 共享 `DEVICE_CAMERAS`（非副本） | 前者改网关；后者保留 import 但投影改 helper（§5.2） |
| C6 | `selfdrive/test/process_replay/vision_meta.py:7` 的 `ROAD_CAMERA_FRAME_SIZES` 取的是 `v.dcam`（应为 `v.fcam`） | 在 `ar_ox`/`imx390` 上 fcam 与 dcam 同尺寸，故一直潜伏；`neo` 上是 1164×874 vs 816×612，会直接算错。改为 `v.fcam`，并在迁移后由 `identity.size(ROAD)` 提供 |

### 18.4 审计结论

- **写入端**：`calibrationd` 仍是唯一写入者；新增字段必须与旧字段出自同一次 `get_msg(True).to_bytes()`，否则就是新的双写。
- **消费端**：实际清单比原稿多 5 类（`PoseCalibrator` 四进程、`signal_stop`、`tools/replay`、web sensor 枚举、`compact_state` 的 wide 缺失），且已有 3 个现存故障（web AR 不渲染、replay KeyError、signal_stop 永远禁用）会在迁移后被误认为"新方案引入"。DM 链路另有两处独立缺陷：`monitoring/policy.py:110` 写死 `("tici","ar0231").dcam`（本项目取到错条目，B11），`process_replay/vision_meta.py:7` 用 `v.dcam` 算 road 尺寸（C6）。
- **同步端**：T0 的 2 ms 残差判据成立，但绝对窗口、丢帧统计口径、`streamEpoch` 三处必须按 §16.4 修正，否则统计会把重启/掉帧误判为相位漂移。
- P0 条目（A1–A5）清零、P1 中 B1/B2/B5/B6 修完后，才具备开始实施的最小条件；其余可作为实施过程中的子任务并行。若同期接入 `cams[DCAM]`，B11 必须一起改，否则 DM 会拿新数组里的 dcam 与旧的错条目两套值混用。
