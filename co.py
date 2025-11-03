from smartcard.System import readers
from smartcard.util import toHexString
import json
import time
 
def wait_for_card():
    """Wait until an RFID card is detected."""
    while True:
        r = readers()
        if not r:
            print("❌ No reader found. Make sure it's connected.")
            time.sleep(2)
            continue
 
        reader = r[0]
        connection = reader.createConnection()
        try:
            connection.connect()
            print(f"✅ Card detected on: {reader}")
            return connection
        except:
            print("⌛ Waiting for card...")
            time.sleep(1)
 
def read_card_data(connection):
    """Read basic data from the RFID card."""
    # Get ATR (Answer to Reset)
    atr = connection.getATR()
    print(f"ATR: {toHexString(atr)}")
 
    # Example: Get UID (common for many RFID cards)
    # APDU: FF CA 00 00 00 (standard command for UID)
    get_uid_apdu = [0xFF, 0xCA, 0x00, 0x00, 0x00]
    data, sw1, sw2 = connection.transmit(get_uid_apdu)
 
    uid = toHexString(data)
    print(f"Card UID: {uid}")
    print(f"SW1 SW2: {hex(sw1)} {hex(sw2)}")
 
    # Example: Read binary block 0x04 (MIFARE Classic / NFC)
    # ⚠️ May fail if the card type is not supported or not authenticated.
    read_apdu = [0xFF, 0xB0, 0x00, 0x04, 0x10]  # read 16 bytes from block 4
    try:
        block_data, sw1, sw2 = connection.transmit(read_apdu)
        block_hex = toHexString(block_data)
        print(f"Block 0x04 data: {block_hex}")
    except:
        block_hex = "N/A"
        print("❌ Failed to read block 0x04 (authentication may be needed)")
 
    return {
        "ATR": toHexString(atr),
        "UID": uid,
        "Block_04": block_hex
    }
 
def save_to_file(data, filename="rfid_data3.json"):
    """Save card data to a JSON file."""
    with open(filename, "a") as f:
        json.dump(data, f)
        f.write("\n")
    print(f"💾 Data saved to {filename}")
 
if __name__ == "__main__":
    print("📡 Waiting for RFID card...")
    conn = wait_for_card()
    card_info = read_card_data(conn)
    save_to_file(card_info)
