"""Load an exported model through the existing pipeline on one admitted original."""
import argparse
from pathlib import Path
from scripts.prepare_sequential_rounds import digest, write

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--weights', type=Path, required=True)
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    from src.pipeline import PipelineConfig, PaddleOCRBackend, predict_image
    config = PipelineConfig(weights_dir=args.weights)
    backend = PaddleOCRBackend(config)
    result = predict_image(args.image, backend, config)
    if result.error: raise RuntimeError(result.error)
    write(args.report, {'status': 'passed', 'image_sha256': digest(args.image),
                        'scope': 'loading and inference only; not an independent accuracy test'})

if __name__ == '__main__': main()
