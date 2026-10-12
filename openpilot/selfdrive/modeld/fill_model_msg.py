import os
import capnp
import numpy as np
from openpilot.cereal import log
from openpilot.selfdrive.modeld.constants import ModelConstants, Plan, Meta

SEND_RAW_PRED = os.getenv('SEND_RAW_PRED')

ConfidenceClass = log.ModelDataV2.ConfidenceClass


def plan_x_idxs_helper(constants, plan, model_output) -> list[float]:
  """plan 上 X_IDXS 对应的时间序列 (与 sunnypilot `openpilot/sunnypilot/models/helpers.py` 同实现).

  本树 (carrot/egpucp) 没有 openpilot.sunnypilot 包, 所以这里内联一份等价实现, 而不是引入那个
  包 —— 本树 HEAD 版本的 fill_model_msg 本来也是内联算的, 只是被 overlay kit 换成了外部 import。
  """
  # times at X_IDXS according to plan.
  LINE_T_IDXS = [np.nan] * constants.IDX_N
  LINE_T_IDXS[0] = 0.0
  plan_x = model_output['plan'][0, :, plan.POSITION][:, 0].tolist()
  for xidx in range(1, constants.IDX_N):
    tidx = 0
    # increment tidx until we find an element that's further away than the current xidx
    while tidx < constants.IDX_N - 1 and plan_x[tidx + 1] < constants.X_IDXS[xidx]:
      tidx += 1
    if tidx == constants.IDX_N - 1:
      # if the plan doesn't extend far enough, set plan_t to the max value (10s), then break
      LINE_T_IDXS[xidx] = constants.T_IDXS[constants.IDX_N - 1]
      break
    # interpolate to find `t` for the current xidx
    current_x_val = plan_x[tidx]
    next_x_val = plan_x[tidx + 1]
    p = (constants.X_IDXS[xidx] - current_x_val) / (next_x_val - current_x_val) if abs(
      next_x_val - current_x_val) > 1e-9 else float('nan')
    LINE_T_IDXS[xidx] = p * constants.T_IDXS[tidx + 1] + (1 - p) * constants.T_IDXS[tidx]
  return LINE_T_IDXS


class PublishState:
  def __init__(self):
    self.disengage_buffer = np.zeros(ModelConstants.CONFIDENCE_BUFFER_LEN*ModelConstants.DISENGAGE_WIDTH, dtype=np.float32)
    self.prev_brake_5ms2_probs = np.zeros(ModelConstants.FCW_5MS2_PROBS_WIDTH, dtype=np.float32)
    self.prev_brake_3ms2_probs = np.zeros(ModelConstants.FCW_3MS2_PROBS_WIDTH, dtype=np.float32)

def fill_xyzt(builder, t, x, y, z, x_std=None, y_std=None, z_std=None):
  builder.t = t
  builder.x = x.tolist()
  builder.y = y.tolist()
  builder.z = z.tolist()
  if x_std is not None:
    builder.xStd = x_std.tolist()
  if y_std is not None:
    builder.yStd = y_std.tolist()
  if z_std is not None:
    builder.zStd = z_std.tolist()

def fill_xyvat(builder, t, x, y, v, a, x_std=None, y_std=None, v_std=None, a_std=None):
  builder.t = t
  builder.x = x.tolist()
  builder.y = y.tolist()
  builder.v = v.tolist()
  builder.a = a.tolist()
  if x_std is not None:
    builder.xStd = x_std.tolist()
  if y_std is not None:
    builder.yStd = y_std.tolist()
  if v_std is not None:
    builder.vStd = v_std.tolist()
  if a_std is not None:
    builder.aStd = a_std.tolist()

def fill_xyz_poly(builder, degree, x, y, z):
  xyz = np.stack([x, y, z], axis=1)
  coeffs = np.polynomial.polynomial.polyfit(ModelConstants.T_IDXS, xyz, deg=degree)
  builder.xCoefficients = coeffs[:, 0].tolist()
  builder.yCoefficients = coeffs[:, 1].tolist()
  builder.zCoefficients = coeffs[:, 2].tolist()

def fill_lane_line_meta(builder, lane_lines, lane_line_probs):
  builder.leftY = lane_lines[1].y[0]
  builder.leftProb = lane_line_probs[1]
  builder.rightY = lane_lines[2].y[0]
  builder.rightProb = lane_line_probs[2]

def fill_driving_model_data(msg: capnp._DynamicStructBuilder, modelv2_send: capnp._DynamicStructBuilder) -> None:
  msg.valid = modelv2_send.valid
  modelV2 = modelv2_send.modelV2
  driving_model_data = msg.drivingModelData
  driving_model_data.frameId = modelV2.frameId
  driving_model_data.frameIdExtra = modelV2.frameIdExtra
  driving_model_data.frameDropPerc = modelV2.frameDropPerc
  driving_model_data.modelExecutionTime = modelV2.modelExecutionTime
  # 本树 (carrot/egpucp) 的 log.capnp 没有 `big` 字段 —— 移植过来的这行会让 modeld 每帧崩:
  # AttributeError: capnp/schema.c++: struct has no such member; name = big。
  # 树里也没有任何读 drivingModelData.big 的地方, 所以直接不写; 若将来真需要这个字段,
  # 得先在 log.capnp 里给 DrivingModelData/ModelDataV2 加字段再重建 cereal。
  # driving_model_data.big = modelV2.big
  driving_model_data.action = modelV2.action
  driving_model_data.meta.laneChangeState = modelV2.meta.laneChangeState
  driving_model_data.meta.laneChangeDirection = modelV2.meta.laneChangeDirection
  fill_lane_line_meta(driving_model_data.laneLineMeta, modelV2.laneLines, modelV2.laneLineProbs)
  fill_xyz_poly(driving_model_data.path, ModelConstants.POLY_PATH_DEGREE, modelV2.position.x, modelV2.position.y, modelV2.position.z)

def fill_model_msg(msg: capnp._DynamicStructBuilder, net_output_data: dict[str, np.ndarray], action: log.ModelDataV2.Action,
                   publish_state: PublishState, vipc_frame_id: int, vipc_frame_id_extra: int,
                   frame_id: int, frame_drop: float, timestamp_eof: int, model_execution_time: float,
                   valid: bool) -> None:
  frame_age = frame_id - vipc_frame_id if frame_id > vipc_frame_id else 0
  frame_drop_perc = frame_drop * 100
  msg.valid = valid

  modelV2 = msg.modelV2
  modelV2.frameId = vipc_frame_id
  modelV2.frameIdExtra = vipc_frame_id_extra
  modelV2.frameAge = frame_age
  modelV2.frameDropPerc = frame_drop_perc
  modelV2.timestampEof = timestamp_eof
  modelV2.modelExecutionTime = model_execution_time

  # plan
  fill_xyzt(modelV2.position, ModelConstants.T_IDXS, *net_output_data['plan'][0,:,Plan.POSITION].T, *net_output_data['plan_stds'][0,:,Plan.POSITION].T)
  fill_xyzt(modelV2.velocity, ModelConstants.T_IDXS, *net_output_data['plan'][0,:,Plan.VELOCITY].T)
  fill_xyzt(modelV2.acceleration, ModelConstants.T_IDXS, *net_output_data['plan'][0,:,Plan.ACCELERATION].T)
  fill_xyzt(modelV2.orientation, ModelConstants.T_IDXS, *net_output_data['plan'][0,:,Plan.T_FROM_CURRENT_EULER].T)
  fill_xyzt(modelV2.orientationRate, ModelConstants.T_IDXS, *net_output_data['plan'][0,:,Plan.ORIENTATION_RATE].T)

  # action
  modelV2.action = action

  # times at X_IDXS of edges and lines
  LINE_T_IDXS: list[float] = plan_x_idxs_helper(ModelConstants, Plan, net_output_data)

  # lane lines
  modelV2.init('laneLines', 4)
  for i in range(4):
    lane_line = modelV2.laneLines[i]
    fill_xyzt(lane_line, LINE_T_IDXS, np.array(ModelConstants.X_IDXS), net_output_data['lane_lines'][0,i,:,0], net_output_data['lane_lines'][0,i,:,1])
  modelV2.laneLineStds = net_output_data['lane_lines_stds'][0,:,0,0].tolist()
  modelV2.laneLineProbs = net_output_data['lane_lines_prob'][0,1::2].tolist()

  # road edges
  modelV2.init('roadEdges', 2)
  for i in range(2):
    road_edge = modelV2.roadEdges[i]
    fill_xyzt(road_edge, LINE_T_IDXS, np.array(ModelConstants.X_IDXS), net_output_data['road_edges'][0,i,:,0], net_output_data['road_edges'][0,i,:,1])
  modelV2.roadEdgeStds = net_output_data['road_edges_stds'][0,:,0,0].tolist()

  # leads
  modelV2.init('leadsV3', 3)
  for i in range(3):
    lead = modelV2.leadsV3[i]
    fill_xyvat(lead, ModelConstants.LEAD_T_IDXS, *net_output_data['lead'][0,i].T, *net_output_data['lead_stds'][0,i].T)
    lead.prob = net_output_data['lead_prob'][0,i].tolist()
    lead.probTime = ModelConstants.LEAD_T_OFFSETS[i]

  # meta
  meta = modelV2.meta
  meta.desireState = net_output_data['desire_state'][0].reshape(-1).tolist()
  meta.desirePrediction = net_output_data['desire_pred'][0].reshape(-1).tolist()
  meta.engagedProb = net_output_data['meta'][0,Meta.ENGAGED].item()
  meta.init('disengagePredictions')
  disengage_predictions = meta.disengagePredictions
  disengage_predictions.t = ModelConstants.META_T_IDXS
  disengage_predictions.brakeDisengageProbs = net_output_data['meta'][0,Meta.BRAKE_DISENGAGE].tolist()
  disengage_predictions.gasDisengageProbs = net_output_data['meta'][0,Meta.GAS_DISENGAGE].tolist()
  disengage_predictions.steerOverrideProbs = net_output_data['meta'][0,Meta.STEER_OVERRIDE].tolist()
  disengage_predictions.brake3MetersPerSecondSquaredProbs = net_output_data['meta'][0,Meta.HARD_BRAKE_3].tolist()
  disengage_predictions.brake4MetersPerSecondSquaredProbs = net_output_data['meta'][0,Meta.HARD_BRAKE_4].tolist()
  disengage_predictions.brake5MetersPerSecondSquaredProbs = net_output_data['meta'][0,Meta.HARD_BRAKE_5].tolist()
  disengage_predictions.gasPressProbs = net_output_data['meta'][0,Meta.GAS_PRESS].tolist()
  disengage_predictions.brakePressProbs = net_output_data['meta'][0,Meta.BRAKE_PRESS].tolist()

  publish_state.prev_brake_5ms2_probs[:-1] = publish_state.prev_brake_5ms2_probs[1:]
  publish_state.prev_brake_5ms2_probs[-1] = net_output_data['meta'][0,Meta.HARD_BRAKE_5][0]
  publish_state.prev_brake_3ms2_probs[:-1] = publish_state.prev_brake_3ms2_probs[1:]
  publish_state.prev_brake_3ms2_probs[-1] = net_output_data['meta'][0,Meta.HARD_BRAKE_3][0]
  hard_brake_predicted = (publish_state.prev_brake_5ms2_probs > ModelConstants.FCW_THRESHOLDS_5MS2).all() and \
    (publish_state.prev_brake_3ms2_probs > ModelConstants.FCW_THRESHOLDS_3MS2).all()
  meta.hardBrakePredicted = hard_brake_predicted.item()

  # confidence
  if vipc_frame_id % (2*ModelConstants.MODEL_RUN_FREQ) == 0:
    # any disengage prob
    brake_disengage_probs = net_output_data['meta'][0,Meta.BRAKE_DISENGAGE]
    gas_disengage_probs = net_output_data['meta'][0,Meta.GAS_DISENGAGE]
    steer_override_probs = net_output_data['meta'][0,Meta.STEER_OVERRIDE]
    any_disengage_probs = 1-((1-brake_disengage_probs)*(1-gas_disengage_probs)*(1-steer_override_probs))
    # independent disengage prob for each 2s slice
    ind_disengage_probs = np.r_[any_disengage_probs[0], np.diff(any_disengage_probs) / (1 - any_disengage_probs[:-1])]
    # rolling buf for 2, 4, 6, 8, 10s
    publish_state.disengage_buffer[:-ModelConstants.DISENGAGE_WIDTH] = publish_state.disengage_buffer[ModelConstants.DISENGAGE_WIDTH:]
    publish_state.disengage_buffer[-ModelConstants.DISENGAGE_WIDTH:] = ind_disengage_probs

  score = 0.
  for i in range(ModelConstants.DISENGAGE_WIDTH):
    score += publish_state.disengage_buffer[i*ModelConstants.DISENGAGE_WIDTH+ModelConstants.DISENGAGE_WIDTH-1-i].item() / ModelConstants.DISENGAGE_WIDTH
  if score < ModelConstants.RYG_GREEN:
    modelV2.confidence = ConfidenceClass.green
  elif score < ModelConstants.RYG_YELLOW:
    modelV2.confidence = ConfidenceClass.yellow
  else:
    modelV2.confidence = ConfidenceClass.red

  # raw prediction if enabled
  if SEND_RAW_PRED:
    modelV2.rawPredictions = net_output_data['raw_pred'].tobytes()

def get_action_from_plan(net_output_data: dict[str, np.ndarray]) -> log.ModelDataV2.Action:
  """action 的 plan 回退路径 —— 与移植前 fill_model_msg 的语义逐位一致 (yaw_rate / max(vx, 0.01))。

  只在 caller 里每帧算一次(两次取值+一次除法), 不进 TRT 引擎 → 热路径零额外开销。
  兼容性: 本树下游没有任何地方消费 action.desiredAcceleration/shouldStop
  (cruise.py 只用 getattr 取 desiredVelocity, 缺失即 0.0 —— 与旧行为相同),
  所以这里只填 desiredCurvature, 与移植前的输出保持一致, 不引入新行为。
  """
  plan = net_output_data['plan']
  plan_last = plan[0, -1] if plan.ndim == 3 else plan[0, 0, -1]
  vx = float(plan_last[Plan.VELOCITY][0])
  yaw_rate = float(plan_last[Plan.ORIENTATION_RATE][2])
  return log.ModelDataV2.Action(desiredCurvature=yaw_rate / max(vx, 0.01))


def fill_pose_msg(msg: capnp._DynamicStructBuilder, net_output_data: dict[str, np.ndarray],
                  vipc_frame_id: int, vipc_dropped_frames: int, timestamp_eof: int, extrinsics_calibration_seen: bool) -> None:
  msg.valid = extrinsics_calibration_seen & (vipc_dropped_frames < 1)
  cameraOdometry = msg.cameraOdometry

  cameraOdometry.frameId = vipc_frame_id
  cameraOdometry.timestampEof = timestamp_eof

  cameraOdometry.trans = net_output_data['pose'][0,:3].tolist()
  cameraOdometry.rot = net_output_data['pose'][0,3:].tolist()
  cameraOdometry.wideFromDeviceEuler = net_output_data['wide_from_device_euler'][0,:].tolist()
  cameraOdometry.roadTransformTrans = net_output_data['road_transform'][0,:3].tolist()
  cameraOdometry.transStd = net_output_data['pose_stds'][0,:3].tolist()
  cameraOdometry.rotStd = net_output_data['pose_stds'][0,3:].tolist()
  cameraOdometry.wideFromDeviceEulerStd = net_output_data['wide_from_device_euler_stds'][0,:].tolist()
  cameraOdometry.roadTransformTransStd = net_output_data['road_transform_stds'][0,:3].tolist()
