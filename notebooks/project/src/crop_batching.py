"""Keep pixels/aspect ratio intact; batch similar normalized widths together."""
import math


def width_batches(crops, batch_size=8, height=48, minimum_width=320, bucket_step=160):
    if batch_size < 1 or height < 1 or bucket_step < 1:
        raise ValueError('Positive crop batch dimensions required')
    buckets = {}
    for index, crop in enumerate(crops):
        if crop.ndim != 3 or crop.shape[2] != 3 or min(crop.shape[:2]) < 1:
            raise ValueError('Nonempty three-channel crop required')
        width = max(minimum_width, math.ceil(height * crop.shape[1] / crop.shape[0]))
        # PaddleX caps at 3200; do not change that model contract here.
        bucket = math.ceil(min(width, 3200) / bucket_step)
        buckets.setdefault(bucket, []).append((width, index))
    for bucket in sorted(buckets):
        ordered = [i for _, i in sorted(buckets[bucket])]
        for start in range(0, len(ordered), batch_size):
            yield ordered[start:start + batch_size]
