#!/usr/bin/env python3
"""
pcsc_rfid_to_json.py
Use pyscard (smartcard) to read card UIDs and append records into a JSON file.

Usage:
  python3 pcsc_rfid_to_json.py
"""

import json
import os
import tempfile
import time
import signal
from datetime import datetime
from smartcard.System import readers
from smartcard.util import toHexString
from smartcard.CardType import AnyCardType
from smartcard.CardRequest import CardRequest
from smartcard.Exceptions import CardConnectionException, NoReadersException

OUT_FILE = "rfid_pcscreader_records.json"
COOLDOWN_SECONDS = 1.5   # ignore same UID reads within this interval

running = True
last_seen = {"uid": None, "ts": 0.0}

def signal_handler(sig, frame):
    global running
    print("\nShutting down...")
    running = False

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def atomic_append_record(filename, record):
    """Load/append/write JSON array atomically."""
    data = []
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                data = json.load(f)
                if not isinstance(data, list):
                    data = []
        except Exception:
            data = []

    data.append(record)

    dirpath = os.path.dirname(os.path.abspath(filename)) or "."
    fd, tmp_path = tempfile.mkstemp(dir=dirpath, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmpf:
            json.dump(data, tmpf, ensure_ascii=False, indent=2)
            tmpf.flush()
            os.fsync(tmpf.fileno())
        os.replace(tmp_path, filename)
    except Exception as e:
        print("Failed to write file:", e)
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

def read_uid_from_card(service):
    """
    Transmit APDU to get UID. Common APDU used with PC/SC readers:
      FF CA 00 00 00  -> GET DATA / Get UID (many readers)
    Returns (uid_str, raw_bytes) or (None, None) on failure.
    """
    GET_UID_APDU = [0xFF, 0xCA, 0x00, 0x00, 0x00]
    try:
        service.connection.connect()
    except Exception as e:
        # could not connect
        return None, None

    try:
        response, sw1, sw2 = service.connection.transmit(GET_UID_APDU)
        if (sw1, sw2) == (0x90, 0x00) and response:
            uid = toHexString(response)                # "04:A2:3C:5D" style
            return uid, response
        else:
            # Some readers/cards may return non-9000 or empty; still try to format if any bytes returned
            if response:
                uid = toHexString(response)
                return uid, response
            return None, None
    except CardConnectionException:
        return None, None
    except Exception:
        return None, None
    finally:
        try:
            service.connection.disconnect()
        except Exception:
            pass

def main():
    global running, last_seen
    print("PC/SC RFID reader (pyscard) — waiting for cards. Ctrl+C to stop.")
    try:
        r = readers()
    except Exception:
        r = []
    if not r:
        print("No PC/SC readers found. Please connect a reader and try again.")
        return

    # Use AnyCardType to accept any card in any reader.
    cardtype = AnyCardType()

    while running:
        try:
            # This will block until a card is presented in any reader
            request = CardRequest(timeout=1, cardType=cardtype)
            try:
                service = request.waitforcard()
            except Exception:
                # timeout or interruption, loop to check running flag
                continue

            # service has .connection and .reader
            reader_name = getattr(service, "reader", None) or "unknown"
            uid, raw_bytes = read_uid_from_card(service)

            if not uid:
                print(f"[{datetime.now().isoformat()}] Card detected in '{reader_name}', UID read failed.")
                # short sleep to avoid busy loop
                time.sleep(0.2)
                continue

            now_ts = time.time()
            # deduplicate same UID within cooldown
            if last_seen["uid"] == uid and (now_ts - last_seen["ts"]) < COOLDOWN_SECONDS:
                # skip duplicate read
                # update timestamp to extend cooldown window slightly
                last_seen["ts"] = now_ts
                print(f"[{datetime.now().isoformat()}] Duplicate UID {uid} ignored (cooldown).")
                time.sleep(0.2)
                continue

            last_seen = {"uid": uid, "ts": now_ts}

            record = {
                "uid": uid,
                "raw_bytes": [int(b) for b in raw_bytes] if raw_bytes else [],
                "reader": reader_name,
                "timestamp_utc": datetime.utcnow().isoformat() + "Z",
                "timestamp_local": datetime.now().isoformat(),
                "apdu": "FF CA 00 00 00"
            }
            print(f"[{datetime.now().isoformat()}] Read UID: {uid}  (reader: {reader_name})")
            atomic_append_record(OUT_FILE, record)
            print(f"Saved to {OUT_FILE}")

            # wait a moment to avoid immediate re-reads; user should remove card
            time.sleep(COOLDOWN_SECONDS)
        except KeyboardInterrupt:
            break
        except NoReadersException:
            print("No readers found. Retrying in 1s.")
            time.sleep(1)
        except Exception as e:
            # keep running on unexpected errors
            print("Error:", e)
            time.sleep(0.5)

    print("Exiting.")

if __name__ == "__main__":
    main()
