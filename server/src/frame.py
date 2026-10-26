FRAME_WIDTH = 400
FRAME_HEIGHT = 300
FRAME_CHANNEL_BYTES = ((FRAME_WIDTH + 7) // 8) * FRAME_HEIGHT
FRAME_BYTES = FRAME_CHANNEL_BYTES * 2


def validate_frame(data: bytes) -> bytes:
    if len(data) != FRAME_BYTES:
        raise ValueError(f"点阵大小必须为 {FRAME_BYTES} 字节")
    return data
