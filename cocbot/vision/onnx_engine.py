"""Vision engine adapted from ONNX Image Lab 0.3 (see progress/HANDOFF_VI.md)."""
from __future__ import annotations
import ast
import json
import sys
import time
import hashlib
import threading
from dataclasses import dataclass
from pathlib import Path
import cv2
import numpy as np
from cocbot.core.paths import resource_path

MODELS = {
    'smart_farm': ('Smart Farm · Nhà tài nguyên', 'Dự đoán 3 loại kho và 3 loại mỏ ở trạng thái đầy. Không đo lượng tài nguyên; có thể bỏ sót hoặc nhầm loại.'),
    'spell_target': ('Spell Target · Cụm công trình', 'Mô hình tìm cụm công trình, được dùng trong module Clan Capital.'),
    'deploy_zone': ('Deploy Zone · Vùng thả quân', 'Mô hình vùng thả quân cho Clan Capital. Mask dự đoán cần đối chiếu với ảnh đúng ngữ cảnh.'),
}
LABELS = {'gold_mine_full':'Mỏ vàng đầy', 'gold_storage_full':'Kho vàng đầy',
          'elixir_collector_full':'Máy khai thác tiên dược đầy', 'elixir_storage_full':'Kho tiên dược đầy',
          'de_drill_full':'Máy khoan hắc tiên dược đầy', 'de_storage_full':'Kho hắc tiên dược đầy',
          'building_cluster':'Cụm công trình', 'deploy_zone':'Vùng thả quân'}
COLORS = [(65,220,145),(255,190,65),(235,110,205),(80,180,255),(245,130,80),(180,145,255)]
STORAGE_CLASSES = ('gold_storage_full','elixir_storage_full','de_storage_full')
EXTRACTOR_CLASSES = ('gold_mine_full','elixir_collector_full','de_drill_full')

def resource_counts(detections):
    counts={name:0 for name in STORAGE_CLASSES+EXTRACTOR_CLASSES}
    for detection in detections:
        name=detection['class_name']
        if name in counts:counts[name]+=1
    return {'storages':sum(counts[name] for name in STORAGE_CLASSES),
            'extractors':sum(counts[name] for name in EXTRACTOR_CLASSES),'by_class':counts}

def box_overlap(a,b):
    a=np.asarray(a);b=np.asarray(b)
    intersection=np.maximum(np.minimum(a[2:],b[2:])-np.maximum(a[:2],b[:2]),0).prod()
    union=np.maximum(a[2:]-a[:2],0).prod()+np.maximum(b[2:]-b[:2],0).prod()-intersection
    return float(intersection/max(float(union),1e-9))

def merge_region_candidates(baseline,candidates,iou):
    """Preserve baseline; additions need same-class support from distinct views.

    View agreement is a review heuristic, not calibrated confidence or ground truth.
    """
    remaining=sorted(candidates,key=lambda d:-d['confidence']);extras=[]
    while remaining:
        best=remaining.pop(0);group=[best];others=[]
        for item in remaining:
            if box_overlap(best['box_xyxy'],item['box_xyxy'])>iou:group.append(item)
            else:others.append(item)
        remaining=others
        views={d['view_id'] for d in group if d['class_id']==best['class_id']}
        if len(views)<2:continue
        if any(box_overlap(best['box_xyxy'],d['box_xyxy'])>.3 for d in baseline+extras):continue
        extra={k:v for k,v in best.items() if k!='view_id'}
        extra.update(candidate_only=True,supporting_views=len(views))
        extras.append(extra)
    return baseline+extras

def asset_root():
    return Path(resource_path('templates'))

def sample_path(name):
    return asset_root()/name

def read_image(path):
    path=Path(path)
    if not path.is_file(): raise ValueError('Không tìm thấy ảnh đã chọn.')
    if path.stat().st_size>100*1024*1024: raise ValueError('Ảnh vượt giới hạn 100 MB.')
    im=cv2.imdecode(np.fromfile(str(path),dtype=np.uint8),cv2.IMREAD_COLOR)
    if im is None: raise ValueError('Không đọc được ảnh. Hãy chọn PNG, JPG, BMP hoặc WebP hợp lệ.')
    if im.shape[0]*im.shape[1]>24_000_000: raise ValueError('Ảnh vượt 24 megapixel. Hãy giảm kích thước trước khi mở.')
    if min(im.shape[:2])<16: raise ValueError('Ảnh quá nhỏ để phân tích (tối thiểu 16×16 pixel).')
    return im

def prepare(im,h,w,truncate=False):
    ih,iw=im.shape[:2];s=min(h/ih,w/iw)
    resize=int if truncate else round
    rw,rh=max(1,resize(iw*s)),max(1,resize(ih*s))
    left,top=(w-rw)//2,(h-rh)//2
    canvas=np.full((h,w,3),114,np.uint8)
    canvas[top:top+rh,left:left+rw]=cv2.resize(im,(rw,rh))
    tensor=np.ascontiguousarray(canvas[:,:,::-1].transpose(2,0,1)[None],dtype=np.float32)/255.0
    return tensor,(s,left,top,rw,rh)

def nms(boxes,scores,classes,iou):
    kept=[]
    for cls in np.unique(classes):
        order=np.flatnonzero(classes==cls)
        order=order[np.argsort(-scores[order],kind='stable')]
        while len(order):
            i=int(order[0]);kept.append(i);rest=order[1:]
            if not len(rest):break
            lt=np.maximum(boxes[i,:2],boxes[rest,:2]);rb=np.minimum(boxes[i,2:],boxes[rest,2:])
            inter=np.maximum(rb-lt,0).prod(axis=1)
            area=np.maximum(boxes[i,2:]-boxes[i,:2],0).prod()
            others=np.maximum(boxes[rest,2:]-boxes[rest,:2],0).prod(axis=1)
            order=rest[inter/np.maximum(area+others-inter,1e-9)<=iou]
    return sorted(kept,key=lambda i:-float(scores[i]))

@dataclass
class Result:
    model: str
    source: str
    image: np.ndarray
    detections: list
    masks: list
    parameters: dict
    inference_ms: float
    total_ms: float
    output_shapes: list
    truncated: bool=False
    model_sha256: str=''

    def metadata(self):
        return {'application':'COC Auto Farm Vision Lab 1','schema_version':1,
                'model_sha256':self.model_sha256,'model':self.model,'source':self.source,
                'image_size':[int(self.image.shape[1]),int(self.image.shape[0])],
                'parameters':self.parameters,'inference_ms':self.inference_ms,'total_ms':self.total_ms,
                'output_shapes':self.output_shapes,'detection_count':len(self.detections),
                'detections':self.detections,'truncated_to_100':self.truncated,
                'resource_predictions':resource_counts(self.detections) if self.model=='smart_farm' else None,
                'baseline_predictions':resource_counts([d for d in self.detections if not d.get('candidate_only')]) if self.model=='smart_farm' else None,
                'candidate_predictions':resource_counts([d for d in self.detections if d.get('candidate_only')]) if self.model=='smart_farm' else None,
                'note':'Predictions from offline inference; not verified game deployment coordinates.'}

class Engine:
    def __init__(self):
        self.current=None;self.session=None
        self.model_sha256=''
        self._lock=threading.RLock()

    def infer(self,image,source,model,confidence=.25,iou=.45,crop=False,scan_regions=False):
        with self._lock:
            return self._infer(image,source,model,confidence,iou,crop,scan_regions)

    def _infer(self,image,source,model,confidence=.25,iou=.45,crop=False,scan_regions=False):
        if not isinstance(image,np.ndarray) or image.dtype!=np.uint8 or image.ndim!=3 or image.shape[2]!=3:
            raise ValueError('Expected uint8 BGR image')
        if min(image.shape[:2])<16 or image.shape[0]*image.shape[1]>24_000_000:
            raise ValueError('Image must be at least 16x16 and at most 24 megapixels')
        if model not in MODELS:raise ValueError('Mô hình không được hỗ trợ.')
        if not 0<confidence<=1 or not 0<iou<=1:raise ValueError('Ngưỡng phải thuộc khoảng (0, 1].')
        if crop and model!='smart_farm':raise ValueError('Crop chỉ áp dụng cho Smart Farm.')
        if scan_regions:
            if model!='smart_farm' or crop:raise ValueError('Quét thêm vùng chỉ dùng Smart Farm toàn ảnh.')
            return self.infer_regions(image,source,confidence,iou)
        started=time.perf_counter();cv2.setNumThreads(1)
        if self.current!=model:
            import onnxruntime as ort
            self.session=None;self.current=None
            path=asset_root()/'models'/(model+'.onnx')
            if not path.is_file():raise FileNotFoundError(path)
            options=ort.SessionOptions();options.intra_op_num_threads=4;options.inter_op_num_threads=1;options.log_severity_level=3
            self.session=ort.InferenceSession(str(path),sess_options=options,providers=['CPUExecutionProvider'])
            self.model_sha256=hashlib.sha256(path.read_bytes()).hexdigest()
            self.current=model
        session=self.session;inp=session.get_inputs()[0]
        if inp.type!='tensor(float)' or inp.shape[:2]!=[1,3]:raise ValueError('Input ONNX không tương thích.')
        h,w=inp.shape[2:]
        if not all(isinstance(v,int) and 16<=v<=4096 for v in (h,w)):raise ValueError('Unsupported input dimensions')
        names={int(k):v for k,v in ast.literal_eval(session.get_modelmeta().custom_metadata_map['names']).items()}
        if set(names)!=set(range(len(names))) or not names or not all(isinstance(v,str) for v in names.values()):
            raise ValueError('Class metadata must use contiguous integer IDs')
        ih,iw=image.shape[:2];y1,y2=(int(ih*.08),int(ih*.82)) if crop else (0,ih)
        view=image[y1:y2];tensor,geo=prepare(view,h,w,crop)
        begin=time.perf_counter();outputs=session.run(None,{inp.name:tensor});elapsed=(time.perf_counter()-begin)*1000
        if len(outputs) not in (1,2) or outputs[0].ndim!=3 or outputs[0].shape[0]!=1:
            raise ValueError('Unexpected model output shapes')
        if len(outputs)==2 and (outputs[1].ndim!=4 or outputs[1].shape[0]!=1):
            raise ValueError('Unexpected mask prototype shape')
        nc=len(names);nm=outputs[1].shape[1] if len(outputs)==2 else 0
        if outputs[0].shape[1]!=4+nc+nm:raise ValueError('Output ONNX không tương thích với bộ giải mã.')
        if not all(np.isfinite(x).all() for x in outputs):raise ValueError('Mô hình trả về số không hữu hạn.')
        pred=outputs[0][0].T.astype(np.float32);scores=pred[:,4:4+nc].max(axis=1)
        pred=pred[scores>=confidence];scores=scores[scores>=confidence]
        classes=pred[:,4:4+nc].argmax(axis=1)
        boxes=np.concatenate((pred[:,:2]-pred[:,2:4]/2,pred[:,:2]+pred[:,2:4]/2),axis=1)
        keep=nms(boxes,scores,np.zeros_like(classes) if crop else classes,iou)
        truncated=len(keep)>100;keep=keep[:100]
        scale,left,top,rw,rh=geo;detections=[];masks=[]
        for i in keep:
            box=boxes[i].copy()
            box[[0,2]]=np.clip((box[[0,2]]-left)/scale,0,iw)
            box[[1,3]]=np.clip((box[[1,3]]-top)/scale,0,y2-y1)
            if box[2]<=box[0] or box[3]<=box[1]:continue
            item={'class_id':int(classes[i]),'class_name':names[int(classes[i])],
                  'confidence':float(scores[i]),'box_xyxy':[float(box[0]),float(box[1]+y1),float(box[2]),float(box[3]+y1)]}
            if nm:
                proto=outputs[1][0].astype(np.float32)
                logits=(pred[i,4+nc:]@proto.reshape(nm,-1)).reshape(proto.shape[1:])
                logits=cv2.resize(logits,(w,h))[top:top+rh,left:left+rw]
                logits=cv2.resize(logits,(iw,y2-y1))
                x0,z0,x2,z2=int(np.ceil(box[0])),int(np.ceil(box[1])),int(np.ceil(box[2])),int(np.ceil(box[3]))
                mask=logits[z0:z2,x0:x2]>0
                item['mask_pixels']=int(mask.sum());item['mask_fraction']=float(mask.sum()/(ih*iw))
                masks.append((len(detections),x0,z0+y1,mask))
            detections.append(item)
        return Result(model,str(source),image,detections,masks,
                      {'confidence':confidence,'nms_iou':iou,'smart_farm_crop':crop,'crop_y_pixels':[y1,y2],
                       'class_agnostic_nms':crop,'provider':'CPUExecutionProvider'},elapsed,
                      (time.perf_counter()-started)*1000,[list(x.shape) for x in outputs],truncated,self.model_sha256)

    def infer_regions(self,image,source,confidence,iou):
        started=time.perf_counter()
        result=self.infer(image,source,'smart_farm',confidence,iou)
        height,width=image.shape[:2];candidates=[];views=[];visited=set();elapsed=result.inference_ms
        extra_threshold=max(.35,confidence)
        for fraction in [.9,.75]:
            w,h=max(16,round(width*fraction)),max(16,round(height*fraction))
            positions=[(0,0),(width-w,0),(0,height-h),(width-w,height-h),((width-w)//2,(height-h)//2)]
            for x,y in positions:
                key=(x,y,w,h)
                if key in visited or key==(0,0,width,height):continue
                visited.add(key);view_id=len(views);views.append(list(key))
                sub=self.infer(image[y:y+h,x:x+w],source,'smart_farm',extra_threshold,iou)
                elapsed+=sub.inference_ms
                for d in sub.detections:
                    a,b,c,e=d['box_xyxy']
                    if ((x>0 and a<3) or (y>0 and b<3) or
                        (x+w<width and c>w-3) or (y+h<height and e>h-3)):continue
                    candidates.append(dict(d,box_xyxy=[a+x,b+y,c+x,e+y],view_id=view_id))
        merged=merge_region_candidates(result.detections,candidates,iou)
        result.truncated=result.truncated or len(merged)>100;result.detections=merged[:100]
        result.parameters.update(scan_regions=True,region_views=views,region_confidence=extra_threshold,
                                 region_min_support=2,additional_candidates=sum(d.get('candidate_only',False) for d in result.detections))
        result.inference_ms=elapsed;result.total_ms=(time.perf_counter()-started)*1000
        return result

def rendered_rgb(result,show_masks=True,show_boxes=True,compact_labels=True):
    rgb=np.ascontiguousarray(result.image[:,:,::-1])
    if show_masks:
        for idx,x,y,mask in result.masks:
            roi=rgb[y:y+mask.shape[0],x:x+mask.shape[1]]
            color=np.array(COLORS[idx%len(COLORS)])
            roi[mask]=(roi[mask]*.58+color*.42).astype(np.uint8)
    if show_boxes:
        scale=max(.45,min(1.1,rgb.shape[1]/2200));thickness=max(1,round(rgb.shape[1]/950))
        for idx,d in enumerate(result.detections):
            color=COLORS[(idx if result.masks else d['class_id'])%len(COLORS)]
            x1,y1,x2,y2=[round(v) for v in d['box_xyxy']]
            cv2.rectangle(rgb,(x1,y1),(x2,y2),color,thickness)
            marker='?' if d.get('candidate_only') else ''
            label=f'{idx+1}{marker}' if compact_labels else f"{idx+1}{marker}. {d['class_name']} {d['confidence']:.2f}"
            (tw,th),_=cv2.getTextSize(label,cv2.FONT_HERSHEY_SIMPLEX,scale,1)
            tx=min(x1,max(0,rgb.shape[1]-tw-8));ty=max(th+8,y1)
            cv2.rectangle(rgb,(tx,ty-th-6),(tx+tw+6,ty+3),(16,24,39),-1)
            cv2.putText(rgb,label,(tx+3,ty-2),cv2.FONT_HERSHEY_SIMPLEX,scale,color,1,cv2.LINE_AA)
    return rgb

def save_png(path,rgb):
    ok,data=cv2.imencode('.png',rgb[:,:,::-1])
    if not ok:raise ValueError('Không mã hóa được ảnh PNG.')
    data.tofile(str(path))

def save_json(path,result):
    Path(path).write_text(json.dumps(result.metadata(),ensure_ascii=False,indent=2),encoding='utf-8')


def export_result(directory,result,show_masks=True,show_boxes=True,compact_labels=True):
    """Export precisely the selected overlay plus full-size mask PNGs and metadata."""
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    save_png(directory/'source.png',result.image[:,:,::-1])
    save_png(directory/'overlay.png',rendered_rgb(result,show_masks,show_boxes,compact_labels))
    metadata=result.metadata()
    metadata['display']={'show_masks':show_masks,'show_boxes':show_boxes,'compact_labels':compact_labels}
    metadata['mask_files']=[]
    for idx,x,y,mask in result.masks:
        full=np.zeros(result.image.shape[:2],np.uint8)
        full[y:y+mask.shape[0],x:x+mask.shape[1]]=mask.astype(np.uint8)*255
        filename=f'mask_{idx+1}.png'
        ok,data=cv2.imencode('.png',full)
        if not ok:raise ValueError('Cannot encode segmentation mask')
        data.tofile(str(directory/filename))
        metadata['mask_files'].append({'detection_index':idx,'file':filename,'coordinate_space':'original_image'})
    (directory/'result.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    return directory
