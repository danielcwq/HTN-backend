#!/usr/bin/env python3
"""
BLE Discovery Tool - Find all services and characteristics from HRM Pro Plus
"""

import asyncio
import struct
from bleak import BleakClient, BleakScanner

# Known BLE Service UUIDs
KNOWN_SERVICES = {
    "0000180d-0000-1000-8000-00805f9b34fb": "Heart Rate Service",
    "0000180f-0000-1000-8000-00805f9b34fb": "Battery Service",
    "0000180a-0000-1000-8000-00805f9b34fb": "Device Information Service",
    "00001816-0000-1000-8000-00805f9b34fb": "Cycling Speed and Cadence",
    "00001814-0000-1000-8000-00805f9b34fb": "Running Speed and Cadence",
    "6e400001-b5a3-f393-e0a9-e50e24dcca9e": "Nordic UART Service",
}

# Known Characteristic UUIDs
KNOWN_CHARS = {
    "00002a37-0000-1000-8000-00805f9b34fb": "Heart Rate Measurement",
    "00002a38-0000-1000-8000-00805f9b34fb": "Body Sensor Location",
    "00002a39-0000-1000-8000-00805f9b34fb": "Heart Rate Control Point",
    "00002a19-0000-1000-8000-00805f9b34fb": "Battery Level",
    "00002a53-0000-1000-8000-00805f9b34fb": "RSC Measurement",
    "00002a5b-0000-1000-8000-00805f9b34fb": "CSC Measurement",
    "00002a29-0000-1000-8000-00805f9b34fb": "Manufacturer Name",
    "00002a24-0000-1000-8000-00805f9b34fb": "Model Number",
    "00002a25-0000-1000-8000-00805f9b34fb": "Serial Number",
    "00002a27-0000-1000-8000-00805f9b34fb": "Hardware Revision",
    "00002a26-0000-1000-8000-00805f9b34fb": "Firmware Revision",
    "00002a28-0000-1000-8000-00805f9b34fb": "Software Revision",
}

def parse_hr_measurement(data):
    """Parse Heart Rate Measurement characteristic"""
    flags = data[0]
    idx = 1
    
    hr_16bit = flags & 0x01
    contact_detected = (flags >> 1) & 0x03
    energy_present = (flags >> 3) & 0x01
    rr_present = (flags >> 4) & 0x01
    
    if hr_16bit:
        hr = struct.unpack_from("<H", data, idx)[0]
        idx += 2
    else:
        hr = data[idx]
        idx += 1
    
    energy = None
    if energy_present:
        energy = struct.unpack_from("<H", data, idx)[0]
        idx += 2
    
    rr_intervals = []
    if rr_present:
        while idx + 1 < len(data):
            rr = struct.unpack_from("<H", data, idx)[0]
            rr_intervals.append(rr / 1024.0)
            idx += 2
    
    return {
        "heart_rate": hr,
        "contact_status": ["Not supported", "Not detected", "Detected", "Detected"][contact_detected],
        "energy_expended": energy,
        "rr_intervals": rr_intervals
    }

async def discover_device(name_substring="HRM"):
    """Find HRM device"""
    print(f"Scanning for devices with '{name_substring}' in name...")
    devices = await BleakScanner.discover(timeout=5.0)
    
    for device in devices:
        if name_substring.lower() in (device.name or "").lower():
            print(f"Found: {device.name} ({device.address})")
            return device.address
    
    print(f"No device found with '{name_substring}' in name")
    return None

async def explore_device(address):
    """Explore all services and characteristics of the device"""
    print(f"\nConnecting to {address}...")
    
    async with BleakClient(address) as client:
        print("Connected!\n")
        print("=" * 60)
        print("DISCOVERED SERVICES AND CHARACTERISTICS")
        print("=" * 60)
        
        # Get all services
        services = client.services
        
        for service in services:
            service_name = KNOWN_SERVICES.get(service.uuid, "Unknown Service")
            print(f"\n📦 Service: {service_name}")
            print(f"   UUID: {service.uuid}")
            
            # Get all characteristics for this service
            for char in service.characteristics:
                char_name = KNOWN_CHARS.get(char.uuid, "Unknown Characteristic")
                print(f"\n   📊 Characteristic: {char_name}")
                print(f"      UUID: {char.uuid}")
                print(f"      Properties: {', '.join(char.properties)}")
                
                # Try to read the characteristic if readable
                if "read" in char.properties:
                    try:
                        value = await client.read_gatt_char(char.uuid)
                        print(f"      Raw Value: {value.hex()}")
                        
                        # Special parsing for known characteristics
                        if char.uuid == "00002a19-0000-1000-8000-00805f9b34fb":  # Battery
                            print(f"      Parsed: {int(value[0])}%")
                        elif char.uuid in ["00002a29-0000-1000-8000-00805f9b34fb",  # Manufacturer
                                          "00002a24-0000-1000-8000-00805f9b34fb",  # Model
                                          "00002a25-0000-1000-8000-00805f9b34fb",  # Serial
                                          "00002a26-0000-1000-8000-00805f9b34fb",  # Hardware Rev
                                          "00002a27-0000-1000-8000-00805f9b34fb",  # Firmware Rev
                                          "00002a28-0000-1000-8000-00805f9b34fb"]: # Software Rev
                            try:
                                print(f"      Parsed: {value.decode('utf-8')}")
                            except:
                                pass
                        elif char.uuid == "00002a38-0000-1000-8000-00805f9b34fb":  # Body Sensor Location
                            locations = ["Other", "Chest", "Wrist", "Finger", "Hand", "Ear Lobe", "Foot"]
                            loc_idx = int(value[0]) if value else 0
                            print(f"      Parsed: {locations[loc_idx] if loc_idx < len(locations) else 'Unknown'}")
                    except Exception as e:
                        print(f"      Could not read: {e}")
                
                # Subscribe to notifications if available
                if "notify" in char.properties:
                    print(f"      ✅ Supports notifications (real-time data)")
                    
                    # Sample notification data for HR measurement
                    if char.uuid == "00002a37-0000-1000-8000-00805f9b34fb":
                        print("\n      📈 Subscribing to Heart Rate for 5 seconds...")
                        
                        samples = []
                        def callback(sender, data):
                            parsed = parse_hr_measurement(data)
                            samples.append(parsed)
                            print(f"         HR: {parsed['heart_rate']} bpm | "
                                  f"Contact: {parsed['contact_status']} | "
                                  f"RR intervals: {len(parsed['rr_intervals'])}")
                        
                        await client.start_notify(char.uuid, callback)
                        await asyncio.sleep(5)
                        await client.stop_notify(char.uuid)
                        
                        if samples:
                            print(f"\n      📊 Summary from {len(samples)} samples:")
                            hrs = [s['heart_rate'] for s in samples]
                            print(f"         HR Range: {min(hrs)}-{max(hrs)} bpm")
                            print(f"         Avg HR: {sum(hrs)/len(hrs):.1f} bpm")
                            
                            all_rr = []
                            for s in samples:
                                all_rr.extend(s['rr_intervals'])
                            if all_rr:
                                print(f"         Total RR intervals: {len(all_rr)}")
                                print(f"         Avg RR: {sum(all_rr)/len(all_rr)*1000:.1f} ms")

        print("\n" + "=" * 60)
        print("ADDITIONAL CAPABILITIES")
        print("=" * 60)
        
        # Check for Garmin-specific services
        garmin_services = [s for s in services if "6a4e" in s.uuid.lower() or "6a4d" in s.uuid.lower()]
        if garmin_services:
            print("\n🔧 Garmin-specific services detected:")
            for service in garmin_services:
                print(f"   - {service.uuid}")
        
        # Check for accelerometer data (HRM Pro Plus has accelerometer)
        accel_chars = [c for s in services for c in s.characteristics 
                      if "accel" in str(c.uuid).lower() or "motion" in str(c.uuid).lower()]
        if accel_chars:
            print("\n🏃 Motion/Accelerometer characteristics found:")
            for char in accel_chars:
                print(f"   - {char.uuid}")
        
        print("\n✅ Discovery complete!")

async def main():
    print("HRM Pro Plus BLE Discovery Tool")
    print("=" * 60)
    
    # Find device
    address = await discover_device("HRM")
    if not address:
        print("Please ensure your HRM Pro Plus is on and in range")
        return
    
    # Explore device
    await explore_device(address)

if __name__ == "__main__":
    asyncio.run(main())
