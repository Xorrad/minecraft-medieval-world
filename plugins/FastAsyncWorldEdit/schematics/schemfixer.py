from pathlib import Path

from nbtlib import load, File, Compound, IntArray, ByteArray, Int

INPUT_DIR = Path("schematics")
OUTPUT_DIR = Path("schematics_fixed")
OUTPUT_DIR.mkdir(exist_ok=True)

BLACKLIST = {
    "minecraft:blue_wool",
    "minecraft:rooted_dirt"
}


def decode_varints(data):
    """Decode Minecraft varints."""
    values = []
    value = 0
    position = 0

    for raw_byte in data:
        # nbtlib's ByteArray is backed by numpy int8 values. Bitwise ops
        # (especially left-shift) on numpy int8 stay 8-bit and silently
        # overflow/wrap once position > 0. Casting to a plain Python int
        # first avoids that corruption.
        byte = int(raw_byte) & 0xFF

        value |= (byte & 0x7F) << position

        if (byte & 0x80) == 0:
            values.append(value)
            value = 0
            position = 0
        else:
            position += 7

    return values


def encode_varints(values):
    """Encode Minecraft varints."""
    out = bytearray()

    for value in values:
        while True:
            temp = value & 0x7F
            value >>= 7

            if value:
                out.append(temp | 0x80)
            else:
                out.append(temp)
                break

    return bytes(out)


def to_signed_byte_array(raw_bytes):
    """Convert unsigned 0-255 byte values into a signed NBT ByteArray."""
    return ByteArray([b - 256 if b > 127 else b for b in raw_bytes])


for schem_file in INPUT_DIR.glob("*.schem"):
    print(f"Processing {schem_file.name}")

    schem = load(schem_file)

    blocks = schem["Schematic"]["Blocks"]
    palette = blocks["Palette"]

    # Reverse lookup: palette id -> block state
    id_to_block = {int(v): k for k, v in palette.items()}

    # IDs that should become air
    replace_ids = {
        pid
        for pid, blockstate in id_to_block.items()
        if blockstate.split("[", 1)[0] in BLACKLIST
    }

    if not replace_ids:
        schem.save(OUTPUT_DIR / schem_file.name)
        continue

    # Ensure air exists in palette
    if "minecraft:air" in palette:
        air_id = int(palette["minecraft:air"])
    else:
        air_id = max(id_to_block) + 1 if id_to_block else 0
        palette["minecraft:air"] = Int(air_id)

        # Keep PaletteMax in sync if the format tracks it
        if "PaletteMax" in blocks:
            blocks["PaletteMax"] = Int(len(palette))

    # Decode BlockData
    block_ids = decode_varints(blocks["Data"])

    # Replace IDs
    block_ids = [
        air_id if pid in replace_ids else pid
        for pid in block_ids
    ]

    # Re-encode and write back as a proper signed NBT ByteArray
    raw_data = encode_varints(block_ids)
    blocks["Data"] = to_signed_byte_array(raw_data)

    schem.save(OUTPUT_DIR / schem_file.name)

print("Done!")