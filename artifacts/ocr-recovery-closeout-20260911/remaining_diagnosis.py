"""Visually read date tokens as diagnostic inputs, never training/submission truth.

Separates recognizing the printed digits from having evidence for their order.
The frozen labels and production image path are never changed.
"""
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from src.date_extraction import OCRLine,select_date

# Date spans read from originals; clock/lot text is kept only in visual notes.
# A single end role below records the visible until/expiry context, NOT order.
READINGS={
    '000018':('26.04.24','B; separate 17:20; until label; multiple background products'),
    '000033':('26.06.17','separate 09:29 F2; until label'),
    '000034':('26.06.30','separate 06:18 F2; until label'),
    '000061':('26.06.04','B; separate 11:32; until label; other packages in background'),
    '000090':('2026.09.01','curved dark bottle; separate 21:05 A; distant expiry heading'),
    '000191':('2026.06.15','curved white panel; explicit expiry heading and until suffix; lower non-date text not transcribed'),
    '000210':('2027.05.20','explicit until suffix; lower clock 10:43 and lot; upper-surface reference'),
    '000255':('26.08.20','A; separate 08:14; until label; slanted rows'),
    '000256':('27.01.02','B; expiry heading and until label; curved bottle'),
    '000305':('26.02.24','expiry heading and until suffix'),
    '003507':('2021.06.17','separate year/month/day legend; lot/clock row overlaps date in vertical projection'),
}


def main():
    live=json.loads((OUT/'live.json').read_text(encoding='utf8'))
    rows=[]
    for row in live['rows']:
        if row['after']['value']==row['expected']:continue
        raw,note=READINGS[row['current_id']]
        # This supplies ideal date text/role for diagnosis only. No fictitious
        # YMD legend is inserted for an ambiguous two-digit date.
        selected=select_date([OCRLine(raw+'까지',.99,(0,0,300,40))],final=True)
        rows.append(dict(id=row['current_id'],path=row['path'],sha256=row['sha256'],
                         frozen_expected=row['expected'],actual_output=row['after']['value'],
                         visually_read_date_span=raw,visual_note=note,
                         ideal_text_diagnostic_output=selected.final_date,
                         ideal_text_order_reason=selected.candidates[0].order_reason if selected.candidates else None,
                         classification='missing_order_evidence_even_with_correct_digits' if selected.final_date!=row['expected']
                         else 'localization_or_recognition_remaining',
                         training_approved=False))
    result=dict(scope='Remaining fixed development errors, not a full-dataset census or learned-model evaluation',
                production_code_sha256=live['code_sha256'],rows=rows,
                order_evidence_needed=[r['id'] for r in rows if r['classification'].startswith('missing_order')],
                localization_or_recognition=[r['id'] for r in rows if not r['classification'].startswith('missing_order')],
                note='Human-readable tokens are diagnostic interventions, not model accuracy gains. Final labels were not edited.')
    (OUT/'remaining_diagnosis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in result.items() if k!='rows'},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
