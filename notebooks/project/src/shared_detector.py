"""Reuse the mobile pipeline's Korean recognizer in serial secondary-detector passes."""


def inner_ocr_pipeline(model):
    """Resolve actual storage, not AutoParallel's forwarding __getattr__."""
    pipeline = model.paddlex_pipeline
    seen = set()
    while id(pipeline) not in seen:
        seen.add(id(pipeline))
        attributes = vars(pipeline)
        if 'text_rec_model' in attributes and 'text_det_model' in attributes:
            return pipeline
        pipeline = attributes.get('_pipeline')
        if pipeline is None:
            break
    raise TypeError('Unsupported PaddleX OCR pipeline structure; refusing a shadow model assignment')


class SharedDetectorView:
    def __init__(self, mobile, detector, side_limit):
        self.mobile, self.detector, self.side_limit = mobile, detector, side_limit

    def predict(self, image):
        pipeline = inner_ocr_pipeline(self.mobile)
        original = pipeline.text_det_model
        try:
            pipeline.text_det_model = self.detector
            return list(self.mobile.predict(image, text_det_limit_side_len=self.side_limit))
        finally:
            pipeline.text_det_model = original
