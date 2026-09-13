"""User-confirmed package formats; identify printed products, never image IDs."""
from .date_extraction import ProductDateRule


VERIFIED_PRODUCT_RULES = (
    ProductDateRule(
        name='mocha_gold_mix_sticks',
        required_text=('모카골드', '믹스커피', 'STICKS'),
        order='ymd',
        evidence='User confirmed YMD for the reviewed mocha-gold mix product on 2026-09-13.',
    ),
    ProductDateRule(
        name='barilla_multilingual_parma_package',
        required_text=('Barilla', 'Fratelli', 'Parma', 'HOUDBAAR TOT'),
        order='dmy',
        evidence='User confirmed DMY for the reviewed Barilla multilingual package on 2026-09-13.',
    ),
)
