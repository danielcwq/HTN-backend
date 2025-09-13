#!/usr/bin/env python3
"""
Monitor Running Speed and Cadence (RSC) data from HRM Pro Plus
This will show accelerometer-derived metrics when moving
"""

import asyncio
import struct
from bleak import BleakClient, BleakScanner

# Service and Characteristic UUIDs
RSC_SERVICE = "00001814-0000-1000-8000-00805f9b34fb"
RSC_MEASUREMENT = "00002a53-0000-1000-8000-00805f9b34fb"
HR_SERVICE = "0000180d-0000-1000-8000-00805f9b34fb"
HR_MEASUREMENT = "00002a37-0000-1000-8000-00805f9b34fb"

# Garmin proprietary service
GARMIN_SERVICE = "6a4e2401-667b-11e3-949a-0800200c9a66"
GARMIN_CHAR1 = "6a4ecd28-667b-11e3-949a-0800200c9a66"  # Notify
GARMIN_CHAR2 = "6a4e4c80-667b-11e3-949a-0800200c9a66"  # Write

def parse_rsc_measurement(data):
    """Parse Running Speed and Cadence measurement"""
    flags = data[0]
    idx = 1
    
    # Bit 0: Instantaneous Stride Length Present
    stride_present = flags & 0x01
    # Bit 1: Total Distance Present  
    distance_present = (flags >> 1) & 0x01
    # Bit 2: Walking or Running (0=Walking, 1=Running)
    is_running = (flags >> 2) & 0x01
    
    # Instantaneous Speed (uint16, 1/256 m/s)
    speed = struct.unpack_from("<H", data, idx)[0] / 256.0
    idx += 2
    
    # Instantaneous Cadence (uint8, 1/min or steps/min)
    cadence = data[idx]
    idx += 1
    
    stride_length = None
    if stride_present and idx < len(data):
        # Stride Length (uint16, cm)
        stride_length = struct.unpack_from("<H", data, idx)[0]
        idx += 2
    
    total_distance = None
    if distance_present and idx + 3 < len(data):
        # Total Distance (uint32, 1/10 m)
        total_distance = struct.unpack_from("<I", data, idx)[0] / 10.0
        idx += 4
    
    return {
        "speed_mps": speed,
        "speed_kph": speed * 3.6,
        "cadence_spm": cadence,
        "stride_length_cm": stride_length,
        "total_distance_m": total_distance,
        "status": "Running" if is_running else "Walking"
    }

def parse_hr_measurement(data):
    """Parse heart rate measurement"""
    flags = data[0]
    idx = 1
    
    if flags & 0x01:  # 16-bit HR
        hr = struct.unpack_from("<H", data, idx)[0]
        idx += 2
    else:  # 8-bit HR
        hr = data[idx]
        idx += 1
    
    # Check for RR intervals
    rr_present = (flags >> 4) & 0x01
    rr_count = 0
    if rr_present:
        rr_count = (len(data) - idx) // 2
    
    return hr, rr_count

async def find_hrm():
    """Find HRM Pro Plus device"""
    print("🔍 Scanning for HRM Pro Plus...")
    devices = await BleakScanner.discover(timeout=5.0)
    
    for device in devices:
        if "hrm" in (device.name or "").lower():
            print(f"✅ Found: {device.name} ({device.address})")
            return device.address
    
    print("❌ No HRM device found")
    return None

async def monitor_device(address):
    """Monitor RSC and HR data"""
    print(f"\n📡 Connecting to {address}...")
    
    async with BleakClient(address) as client:
        print("✅ Connected!")
        print("\n" + "=" * 60)
        print("MONITORING RUNNING METRICS")
        print("Move around to see accelerometer-based metrics!")
        print("=" * 60)
        
        # Data storage
        hr_samples = []
        rsc_samples = []
        garmin_samples = []
        
        # Heart Rate callback
        def hr_callback(sender, data):
            hr, rr_count = parse_hr_measurement(data)
            hr_samples.append(hr)
            print(f"❤️  HR: {hr:3d} bpm | RR intervals: {rr_count}")
        
        # RSC callback
        def rsc_callback(sender, data):
            parsed = parse_rsc_measurement(data)
            rsc_samples.append(parsed)
            
            print(f"🏃 {parsed['status']:7} | "
                  f"Speed: {parsed['speed_kph']:4.1f} km/h | "
                  f"Cadence: {parsed['cadence_spm']:3d} spm", end="")
            
            if parsed['stride_length_cm']:
                print(f" | Stride: {parsed['stride_length_cm']} cm", end="")
            if parsed['total_distance_m']:
                print(f" | Distance: {parsed['total_distance_m']:.1f} m", end="")
            print()
        
        # Garmin proprietary callback
        def garmin_callback(sender, data):
            garmin_samples.append(data)
            print(f"🔧 Garmin data: {data.hex()} (length: {len(data)} bytes)")
            
            # Try to interpret the data
            if len(data) >= 4:
                # Possible accelerometer values (guessing)
                try:
                    val1 = struct.unpack_from("<h", data, 0)[0]  # Signed 16-bit
                    val2 = struct.unpack_from("<h", data, 2)[0] if len(data) >= 4 else 0
                    print(f"   Possible accel values: X={val1}, Y={val2}")
                except:
                    pass
        
        # Subscribe to notifications
        print("\n📊 Starting monitoring (30 seconds)...")
        print("-" * 60)
        
        # Start HR monitoring
        try:
            await client.start_notify(HR_MEASUREMENT, hr_callback)
            print("✓ Heart Rate monitoring active")
        except Exception as e:
            print(f"✗ Could not start HR monitoring: {e}")
        
        # Start RSC monitoring
        try:
            await client.start_notify(RSC_MEASUREMENT, rsc_callback)
            print("✓ Running Speed & Cadence monitoring active")
        except Exception as e:
            print(f"✗ Could not start RSC monitoring: {e}")
        
        # Try Garmin proprietary characteristic
        try:
            await client.start_notify(GARMIN_CHAR1, garmin_callback)
            print("✓ Garmin proprietary monitoring active")
        except Exception as e:
            print(f"✗ Could not start Garmin monitoring: {e}")
        
        print("-" * 60)
        print("🏃 Try walking or running in place to generate data!")
        print("-" * 60)
        
        # Monitor for 30 seconds
        await asyncio.sleep(30)
        
        # Stop notifications
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        
        if hr_samples:
            print(f"\n❤️  Heart Rate:")
            print(f"   Samples: {len(hr_samples)}")
            print(f"   Range: {min(hr_samples)}-{max(hr_samples)} bpm")
            print(f"   Average: {sum(hr_samples)/len(hr_samples):.1f} bpm")
        
        if rsc_samples:
            print(f"\n🏃 Running Metrics:")
            print(f"   Samples: {len(rsc_samples)}")
            
            speeds = [s['speed_kph'] for s in rsc_samples if s['speed_kph'] > 0]
            if speeds:
                print(f"   Speed range: {min(speeds):.1f}-{max(speeds):.1f} km/h")
            
            cadences = [s['cadence_spm'] for s in rsc_samples if s['cadence_spm'] > 0]
            if cadences:
                print(f"   Cadence range: {min(cadences)}-{max(cadences)} spm")
            
            strides = [s['stride_length_cm'] for s in rsc_samples if s['stride_length_cm']]
            if strides:
                print(f"   Stride length range: {min(strides)}-{max(strides)} cm")
        
        if garmin_samples:
            print(f"\n🔧 Garmin Proprietary Data:")
            print(f"   Samples: {len(garmin_samples)}")
            print(f"   Sample sizes: {set(len(s) for s in garmin_samples)} bytes")
        
        # Clean up
        try:
            await client.stop_notify(HR_MEASUREMENT)
        except:
            pass
        try:
            await client.stop_notify(RSC_MEASUREMENT)
        except:
            pass
        try:
            await client.stop_notify(GARMIN_CHAR1)
        except:
            pass
        
        print("\n✅ Monitoring complete!")

async def main():
    print("HRM Pro Plus - Running & Accelerometer Monitor")
    print("=" * 60)
    
    address = await find_hrm()
    if not address:
        print("Please ensure your HRM Pro Plus is on and in range")
        return
    
    await monitor_device(address)

if __name__ == "__main__":
    asyncio.run(main())
