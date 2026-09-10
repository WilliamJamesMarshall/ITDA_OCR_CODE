import unittest

from src.date_extraction import OCRLine, select_date


def line(text, score=.99, box=(0, 0, 300, 40), variant='original'):
    return OCRLine(text, score, box, 'test', variant)


class ManufacturingExitTest(unittest.TestCase):
    def test_only_explicit_manufacturing_is_not_retried_for_nearby_expiry_heading(self):
        result = select_date([line('제조2020.04.03'), line('유통기한', box=(0, 60, 300, 100))])
        self.assertIsNone(result.final_date)
        self.assertTrue(result.stop_ocr)
        self.assertEqual(result.reason, 'negative-context')

    def test_another_unlabelled_date_prevents_manufacturing_only_exit(self):
        result = select_date([line('MFG 2021.01.01'), line('2021.02.03', score=.3, box=(0, 70, 300, 110))])
        self.assertFalse(result.stop_ocr)

    def test_low_confidence_manufacturing_keeps_recovery(self):
        self.assertFalse(select_date([line('MFG 2021.01.01', score=.5)]).stop_ocr)

    def test_unparsed_expiry_digits_still_require_recovery(self):
        result = select_date([line('MFG 2025.09.23'), line('비기:2E.03.25 까지', box=(0, 60, 300, 100))])
        self.assertFalse(result.stop_ocr)

    def test_explicit_expiry_is_still_selected(self):
        result = select_date([line('MFG 2021.01.01'), line('EXP 2021.12.31', box=(0, 70, 300, 110))])
        self.assertEqual(result.final_date, '2021-12-31')

    def test_existing_product_word_boundary_change_is_preserved(self):
        for heading in ('PRODUCT', 'PRODOTTO', 'PRODUKT'):
            result = select_date([line(heading + ' 2021.12.31')])
            self.assertEqual(result.final_date, '2021-12-31')
        self.assertIsNone(select_date([line('PROD. 2021.01.01')]).final_date)
