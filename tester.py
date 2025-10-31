import serial, serial.tools.list_ports, time

BAUD = 38400  # for HC-05 Bluetooth

# List all COM ports
ports = [p.device for p in serial.tools.list_ports.comports()]
print("Available ports:", ports)

found = None

for port in ports:
    try:
        ser = serial.Serial(port, BAUD, timeout=1)
        print(f"Listening on {port}...")
        time.sleep(2)  # allow device to start sending

        data = ser.readline().decode(errors='ignore').strip()
        if data:
            print(f"\n Data found on {port}: {data}\n")
            found = port
            break
        ser.close()

    except Exception:
        # Ignore "semaphore timeout" and similar errors
        pass

if not found:
    print("\n No active COM port produced data.")