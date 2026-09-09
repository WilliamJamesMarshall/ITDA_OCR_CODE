from pathlib import Path
from PIL import Image,ImageOps
B=Path(__file__).parent;S=B.parent.parent/'상품사진입니다'
for n,angle,box in [(977,180,(760,500,974,880)),(3032,0,(120,535,470,610)),(3320,0,(100,315,565,475))]:
 im=ImageOps.exif_transpose(Image.open(next(S.glob(f'{n:06d}.*')))).rotate(angle,expand=True)
 crop=im.crop(box);crop.resize((crop.width*3,crop.height*3)).save(B/f'label_{n}.jpg')
