Food Packaging OCR Dataset

Food Packaging OCR Dataset/
|-- det/
|   |-- train/
|   |-- valid/
|   `-- test/
`-- rec/
    |-- train/
    |-- valid/
    `-- test/

This dataset is prepared for two OCR tasks:
- det: text detection
- rec: text recognition

Each task is divided into three subsets:
- Train: 8,736
- Validation: 1,092
- Test: 1,092

Each subset contains:
- images/: image files
- labels.txt: annotations


Label Format

Detection

Format:

0001.jpg    [{"transcription":"MILK","points":[[10,10],[100,10],[100,50],[10,50]]}]

- Image name and annotation are separated by a tab.
- Annotation is a JSON list.
- Each text region contains a transcription and polygon points.

Recognition

Format:

0001.jpg    MILK

- Image name and transcription are separated by a tab.


Usage

- For text detection, use det/<subset>/images together with det/<subset>/labels.txt.
- For text recognition, use rec/<subset>/images together with rec/<subset>/labels.txt.
