#!/usr/bin/env python3
"""
Barcode scanner WebSocket bridge.
Reads a USB scanner (keyboard wedge mode) via evdev and broadcasts
codes to all connected tablet POS clients.

Usage:
  pip install evdev websockets
  sudo python3 scanner_ws.py [--port 8765]

The scanner auto-detected by matching name containing 'bar' or 'scanner'.
Multiple tablets can connect simultaneously — all receive the same code.
"""

import asyncio
import argparse
import sys
import signal

try:
    from evdev import InputDevice, list_devices, ecodes
except ImportError:
    print("Missing evdev. Install: pip install evdev")
    sys.exit(1)

try:
    import websockets
except ImportError:
    print("Missing websockets. Install: pip install websockets")
    sys.exit(1)

connected = set()
KEY_MAP = {
    'KEY_0': '0', 'KEY_1': '1', 'KEY_2': '2', 'KEY_3': '3', 'KEY_4': '4',
    'KEY_5': '5', 'KEY_6': '6', 'KEY_7': '7', 'KEY_8': '8', 'KEY_9': '9',
    'KEY_MINUS': '-', 'KEY_DOT': '.', 'KEY_SLASH': '/',
}

def find_scanner():
    for path in list_devices():
        dev = InputDevice(path)
        name = dev.name.lower()
        if 'bar' in name or 'scanner' in name or 'handheld' in name:
            return dev
    return None

async def handler(ws):
    connected.add(ws)
    try:
        async for _ in ws:
            pass
    finally:
        connected.discard(ws)

async def main():
    parser = argparse.ArgumentParser(description='Barcode scanner WebSocket bridge')
    parser.add_argument('--port', type=int, default=8765, help='WebSocket port (default: 8765)')
    parser.add_argument('--device', type=str, default=None, help='Input device path (auto-detect if omitted)')
    args = parser.parse_args()

    if args.device:
        dev = InputDevice(args.device)
    else:
        dev = find_scanner()
        if not dev:
            print("No scanner found. Specify device path with --device")
            print("Available devices:")
            for p in list_devices():
                d = InputDevice(p)
                print(f"  {p}  ({d.name})")
            sys.exit(1)

    print(f"Scanner: {dev.name} ({dev.path})")
    print(f"WebSocket server on ws://0.0.0.0:{args.port}")
    print("Waiting for connections...")

    code = []
    stop = asyncio.Future()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            asyncio.get_event_loop().add_signal_handler(sig, lambda: stop.set_result(True))
        except NotImplementedError:
            pass

    async with websockets.serve(handler, "0.0.0.0", args.port):
        async for event in dev.async_read_loop():
            if stop.done():
                break
            if event.type == ecodes.EV_KEY and event.value == 1:
                key_name = ecodes.KEY.get(event.code, '')
                if key_name == 'KEY_ENTER':
                    if code:
                        barcode = ''.join(code)
                        print(f"Scan: {barcode}")
                        if connected:
                            websockets.broadcast(connected, barcode)
                    code = []
                elif key_name in KEY_MAP:
                    code.append(KEY_MAP[key_name])

if __name__ == '__main__':
    asyncio.run(main())
