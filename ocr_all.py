#!/usr/bin/env python3
"""OCR all JPGs in a directory with easyocr (ru+en).

Outputs JSON: {filename: {W,H,items:[{text,conf,x0,y0,x1,y1,ink,h,w}]}}.

Usage:
    python ocr_all.py --input DIR_WITH_JPGS --output ocr_raw.json
"""
import argparse, json, os, sys
import numpy as np
from PIL import Image

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--input', required=True, help='directory with .jpg/.jpeg/.png files')
    ap.add_argument('--output', default='ocr_raw.json')
    args=ap.parse_args()

    try:
        import easyocr
    except ImportError:
        sys.exit("easyocr not installed. Run:\n  python -m venv venv && venv/bin/pip install easyocr pillow")

    files=sorted(f for f in os.listdir(args.input)
                 if f.lower().endswith(('.jpg','.jpeg','.png')))
    if not files:
        sys.exit(f"no images found in {args.input}")

    print(f"[ocr] {len(files)} images in {args.input}", flush=True)
    reader=easyocr.Reader(['ru','en'], gpu=False, verbose=False)  # models download on first run (~100MB)

    allres={}
    for i,f in enumerate(files):
        path=os.path.join(args.input,f)
        im=Image.open(path).convert("L")
        arr=np.asarray(im); H,W=arr.shape
        res=reader.readtext(path, detail=1, paragraph=False)
        items=[]
        for box,txt,conf in res:
            xs=[p[0] for p in box]; ys=[p[1] for p in box]
            x0=int(max(0,min(xs))); x1=int(min(W,max(xs)))
            y0=int(max(0,min(ys))); y1=int(min(H,max(ys)))
            crop=arr[y0:y1, x0:x1]
            ink=float((crop<128).mean()) if crop.size else 0.0
            items.append({"text":txt,"conf":float(conf),
                          "x0":x0,"y0":y0,"x1":x1,"y1":y1,
                          "ink":ink,"h":y1-y0,"w":x1-x0})
        allres[f]={"W":W,"H":H,"items":items}
        print(f"[ocr] [{i+1}/{len(files)}] {f}: {len(items)} boxes", flush=True)

    with open(args.output,"w",encoding="utf-8") as fh:
        json.dump(allres,fh,ensure_ascii=False,indent=1)
    print(f"[ocr] saved {args.output}")

if __name__=='__main__':
    main()
