"""Exclude CTC frames beyond real resized pixels, not date-specific characters."""
import math
import numpy as np


def mask_padding_frames(probabilities, valid_ratios):
    values=np.asarray(probabilities)
    if values.ndim!=3 or len(valid_ratios)!=values.shape[0]:
        raise ValueError('Padding guard CTC batch/geometry mismatch')
    ratios=np.asarray(valid_ratios,dtype=float)
    if not np.isfinite(ratios).all() or np.any(ratios<=0) or np.any(ratios>1):
        raise ValueError('Invalid real-image width ratios')
    if np.all(ratios==1):return probabilities
    result=values.copy()
    for row,ratio in enumerate(ratios):
        # Keep the final partially covered frame; do not erase boundary glyphs.
        end=int(math.ceil(values.shape[1]*ratio))
        result[row,end:,:]=0
        result[row,end:,0]=1  # CTC blank, never a replacement date character.
    return result


class GeometryResize:
    def __init__(self,resize):
        self.resize=resize
        self.valid_ratios=[]

    def __getattr__(self,name):return getattr(self.resize,name)

    @property
    def rec_image_shape(self):return self.resize.rec_image_shape

    @rec_image_shape.setter
    def rec_image_shape(self,value):self.resize.rec_image_shape=value

    def __call__(self,imgs):
        normalized=self.resize(imgs)
        if len(normalized)!=len(imgs):raise ValueError('Resize changed image count')
        ratios=[]
        for image,tensor in zip(imgs,normalized):
            height,width=tensor.shape[-2:]
            if self.resize.input_shape is not None:
                valid_width=width  # Static resize stretches pixels, no right padding.
            else:
                valid_width=min(width,int(math.ceil(height*image.shape[1]/image.shape[0])))
            ratios.append(valid_width/width)
        self.valid_ratios=ratios
        return normalized


class GeometryRunner:
    def __init__(self,runner,resize):self.runner,self.resize=runner,resize
    def __getattr__(self,name):return getattr(self.runner,name)

    def __call__(self,*args,**kwargs):
        output=self.runner(*args,**kwargs)
        if not isinstance(output,(list,tuple)) or len(output)!=1:
            raise ValueError('Unexpected recognizer output contract')
        masked=mask_padding_frames(output[0],self.resize.valid_ratios)
        return (masked,) if isinstance(output,tuple) else [masked]


def install_padding_guard(model):
    resize=model.pre_tfs['ReisizeNorm']
    if isinstance(resize,GeometryResize):return
    if list(resize.rec_image_shape)[:2]!=[3,48] or not hasattr(model,'runner'):
        raise ValueError('Unsupported recognizer padding contract')
    wrapped=GeometryResize(resize)
    model.pre_tfs['ReisizeNorm']=wrapped
    model.runner=GeometryRunner(model.runner,wrapped)
