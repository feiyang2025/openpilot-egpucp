#!/usr/bin/env python3
import math
import os
import time
import ctypes
import select
import threading

import openpilot.cereal.messaging as messaging
from openpilot.cereal.services import SERVICE_LIST
from openpilot.common.utils import sudo_write
from openpilot.common.realtime import config_realtime_process, Ratekeeper
from openpilot.common.swaglog import cloudlog
from openpilot.common.gpio import gpiochip_get_ro_value_fd, gpioevent_data

try:
    import serial
except ImportError:
    serial = None

from openpilot.system.sensord.sensors.i2c_sensor import Sensor
from openpilot.system.sensord.sensors.lsm6ds3_accel import LSM6DS3_Accel
from openpilot.system.sensord.sensors.lsm6ds3_gyro import LSM6DS3_Gyro
from openpilot.system.sensord.sensors.lsm6ds3_temp import LSM6DS3_Temp

I2C_BUS_IMU = 1
FRAME_HDR = 0x55
JY62_ACCEL = 0x51
JY62_GYRO = 0x52
JY62_FRAME_LEN = 11


def uart_imu_configure(ser):
    for cmd in (
        bytes([0xFF, 0xAA, 0x69, 0x88, 0xB5]),
        bytes([0xFF, 0xAA, 0x02, 0x06, 0x00]),
        bytes([0xFF, 0xAA, 0x03, 0x09, 0x00]),
        bytes([0xFF, 0xAA, 0x00, 0x00, 0x00]),
    ):
        ser.write(cmd)
        time.sleep(0.05)


def uart_imu_loop(port, baud, stop):
    from openpilot.cereal import log as cereallog
    pm = messaging.PubMaster(["accelerometer", "gyroscope"])
    cloudlog.warning("sensord: UART IMU %s @ %d" % (port, baud))

    try:
        ser = serial.Serial(port, baud, timeout=0.2)
    except Exception as e:
        cloudlog.exception("sensord: serial open failed: %s" % e)
        return

    uart_imu_configure(ser)
    ser.reset_input_buffer()
    cloudlog.warning("sensord: UART IMU configured, parsing")

    buf = bytearray()
    frame_count = 0
    bad_hdr = 0
    bad_sum = 0

    while not stop.is_set():
        try:
            chunk = ser.read(512)
        except Exception:
            cloudlog.exception("sensord: serial err, reopen")
            try:
                ser.close()
            except Exception:
                pass
            time.sleep(1)
            try:
                ser = serial.Serial(port, baud, timeout=0.2)
                uart_imu_configure(ser)
                ser.reset_input_buffer()
            except Exception as e:
                cloudlog.exception("sensord: reopen failed: %s" % e)
            continue

        if not chunk:
            continue
        buf += chunk

        while len(buf) >= JY62_FRAME_LEN:
            if buf[0] != FRAME_HDR:
                buf.pop(0)
                bad_hdr += 1
                continue
            frame = bytes(buf[:JY62_FRAME_LEN])
            if sum(frame[:10]) & 0xFF != frame[10]:
                buf.pop(0)
                bad_sum += 1
                continue
            buf = buf[JY62_FRAME_LEN:]
            frame_count += 1
            typ = frame[1]
            ts = time.monotonic_ns()

            if typ == JY62_ACCEL:
                ax = int.from_bytes(frame[2:4], "little", signed=True) / 32768.0 * 16.0 * 9.81
                ay = int.from_bytes(frame[4:6], "little", signed=True) / 32768.0 * 16.0 * 9.81
                az = int.from_bytes(frame[6:8], "little", signed=True) / 32768.0 * 16.0 * 9.81
                msg = messaging.new_message("accelerometer", valid=True, logMonoTime=ts)
                msg.accelerometer.timestamp = ts
                msg.accelerometer.source = cereallog.SensorEventData.SensorSource.lsm6ds3
                a = msg.accelerometer.init("acceleration")
                a.v = [ay, -ax, az]
                pm.send("accelerometer", msg)
            elif typ == JY62_GYRO:
                wx = int.from_bytes(frame[2:4], "little", signed=True) / 32768.0 * 2000.0 * math.pi / 180.0
                wy = int.from_bytes(frame[4:6], "little", signed=True) / 32768.0 * 2000.0 * math.pi / 180.0
                wz = int.from_bytes(frame[6:8], "little", signed=True) / 32768.0 * 2000.0 * math.pi / 180.0
                msg = messaging.new_message("gyroscope", valid=True, logMonoTime=ts)
                msg.gyroscope.timestamp = ts
                msg.gyroscope.source = cereallog.SensorEventData.SensorSource.lsm6ds3
                g = msg.gyroscope.init("gyroUncalibrated")
                g.v = [wy, -wx, wz]
                pm.send("gyroscope", msg)

            if frame_count % 500 == 0:
                cloudlog.info("sensord: UART IMU frames=%d bad_hdr=%d bad_sum=%d" % (frame_count, bad_hdr, bad_sum))

    try:
        ser.close()
    except Exception:
        pass
    cloudlog.warning("sensord: UART IMU stopped total_frames=%d" % frame_count)


def interrupt_loop(sensors, event):
    pm = messaging.PubMaster([s for _, s, i in sensors if i])
    fd = gpiochip_get_ro_value_fd("sensord", 0, 84)
    irq_path = "/proc/irq/336/smp_affinity_list"
    if not os.path.exists(irq_path):
        irq_path = "/proc/irq/335/smp_affinity_list"
    if os.path.exists(irq_path):
        sudo_write("1\n", irq_path)
    offset = time.time_ns() - time.monotonic_ns()
    poller = select.poll()
    poller.register(fd, select.POLLIN | select.POLLPRI)
    while not event.is_set():
        events = poller.poll(100)
        if not events:
            continue
        dat = os.read(fd, ctypes.sizeof(gpioevent_data) * 16)
        evd = gpioevent_data.from_buffer_copy(dat)
        cur_offset = time.time_ns() - time.monotonic_ns()
        if abs(cur_offset - offset) > 10 * 1e6:
            offset = cur_offset
            continue
        ts = evd.timestamp - cur_offset
        for sensor, service, intr in sensors:
            if intr:
                try:
                    evt = sensor.get_event(ts)
                    if not sensor.is_data_valid():
                        continue
                    msg = messaging.new_message(service, valid=True)
                    setattr(msg, service, evt)
                    pm.send(service, msg)
                except Sensor.DataNotReady:
                    pass
                except Exception:
                    cloudlog.exception("err %s" % service)


def polling_loop(sensor, service, event):
    pm = messaging.PubMaster([service])
    rk = Ratekeeper(SERVICE_LIST[service].frequency, print_delay_threshold=None)
    while not event.is_set():
        try:
            evt = sensor.get_event()
            if not sensor.is_data_valid():
                continue
            msg = messaging.new_message(service, valid=True)
            setattr(msg, service, evt)
            pm.send(service, msg)
        except Exception:
            cloudlog.exception("err %s" % service)
        rk.keep_time()


def main():
    config_realtime_process([1, ], 1)

    uart_path = os.environ.get("IMU_UART_PATH", "").strip()
    if uart_path:
        if serial is None:
            cloudlog.exception("sensord: IMU_UART_PATH set but pyserial missing")
            return
        baud = int(os.environ.get("IMU_UART_BAUD", "115200"))
        stop = threading.Event()
        try:
            uart_imu_loop(uart_path, baud, stop)
        except KeyboardInterrupt:
            stop.set()
        return

    sensors_cfg = [
        (LSM6DS3_Accel(I2C_BUS_IMU), "accelerometer", True),
        (LSM6DS3_Gyro(I2C_BUS_IMU), "gyroscope", True),
        (LSM6DS3_Temp(I2C_BUS_IMU), "temperatureSensor", False),
    ]
    for sensor, _, _ in sensors_cfg:
        try:
            sensor.reset()
        except Exception:
            cloudlog.exception("init %s" % sensor)

    exit_event = threading.Event()
    threads = [threading.Thread(target=interrupt_loop, args=(sensors_cfg, exit_event), daemon=True)]
    for sensor, service, intr in sensors_cfg:
        try:
            sensor.init()
            if not intr:
                threads.append(threading.Thread(target=polling_loop, args=(sensor, service, exit_event), daemon=True))
        except Exception:
            cloudlog.exception("init %s" % service)

    try:
        for t in threads:
            t.start()
        while any(t.is_alive() for t in threads):
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        exit_event.set()
        for t in threads:
            if t.is_alive():
                t.join()
        for sensor, _, _ in sensors_cfg:
            try:
                sensor.shutdown()
            except Exception:
                pass


if __name__ == "__main__":
    main()
