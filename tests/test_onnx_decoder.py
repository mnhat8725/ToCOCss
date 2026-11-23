"""Synthetic regression: class IDs, NMS, letterbox coordinates and crop offset.

These tests deliberately do not claim model accuracy on real game screenshots.
"""
import sys, unittest
from pathlib import Path
from types import SimpleNamespace
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from cocbot.vision.onnx_engine import Engine,resource_counts,merge_region_candidates

NAMES={0:'gold_mine_full',1:'gold_storage_full',2:'elixir_collector_full',
       3:'elixir_storage_full',4:'de_drill_full',5:'de_storage_full'}

class Session:
    def get_inputs(self):return [SimpleNamespace(name='images',type='tensor(float)',shape=[1,3,416,416])]
    def get_modelmeta(self):return SimpleNamespace(custom_metadata_map={'names':repr(NAMES)})
    def run(self,_,inputs):
        assert inputs['images'].shape==(1,3,416,416)
        output=np.zeros((1,10,7),np.float32)
        output[0,:4,:]=np.array([208,208,104,52])[:,None]
        for i in range(6):output[0,4+i,i]=.5+i*.05
        output[0,4,6]=.3 # duplicate gold mine must be suppressed
        return [output]

class DecoderTests(unittest.TestCase):
    def setUp(self):
        self.engine=Engine();self.engine.current='smart_farm';self.engine.session=Session()
        self.image=np.zeros((1000,1600,3),np.uint8)

    def test_class_names_and_full_image_coordinates(self):
        result=self.engine.infer(self.image,'synthetic','smart_farm')
        self.assertEqual(len(result.detections),6)
        self.assertEqual({d['class_id']:d['class_name'] for d in result.detections},NAMES)
        for d in result.detections:np.testing.assert_allclose(d['box_xyxy'],[600,400,1000,600],atol=.001)
        counts=resource_counts(result.detections)
        self.assertEqual((counts['storages'],counts['extractors']),(3,3))
        self.assertTrue(all(n==1 for n in counts['by_class'].values()))

    def test_crop_offset_and_agnostic_suppression(self):
        result=self.engine.infer(self.image,'synthetic','smart_farm',crop=True)
        self.assertEqual(len(result.detections),1)
        self.assertEqual(result.detections[0]['class_name'],'de_storage_full')
        np.testing.assert_allclose(result.detections[0]['box_xyxy'],
                                   [600,349.230769,1000,549.230769],atol=.001)
        self.assertEqual(result.parameters['crop_y_pixels'],[80,820])

    def test_empty_and_unknown_labels_do_not_become_storages(self):
        counts=resource_counts([{'class_name':'building_cluster'}])
        self.assertEqual(counts['storages'],0);self.assertEqual(counts['extractors'],0)
        self.assertEqual(resource_counts([]),counts)

    def test_region_support_must_come_from_distinct_views(self):
        a=dict(class_id=1,class_name='gold_storage_full',confidence=.8,box_xyxy=[10,10,50,50],view_id=0)
        self.assertEqual(merge_region_candidates([],[a,dict(a)],.45),[])
        merged=merge_region_candidates([],[a,dict(a,view_id=1)],.45)
        self.assertEqual(len(merged),1);self.assertTrue(merged[0]['candidate_only'])
        self.assertEqual(merged[0]['supporting_views'],2)

    def test_regions_preserve_baseline_and_reject_conflicting_class_votes(self):
        a=dict(class_id=1,class_name='gold_storage_full',confidence=.8,box_xyxy=[10,10,50,50],view_id=0)
        b=dict(a,class_id=0,class_name='gold_mine_full',view_id=1)
        self.assertEqual(merge_region_candidates([],[a,b],.45),[])
        baseline=[dict(b,confidence=.3)]
        self.assertEqual(merge_region_candidates(baseline,[a,dict(a,view_id=1)],.45),baseline)

    def test_region_mode_rejects_crop_and_other_models(self):
        with self.assertRaises(ValueError):self.engine.infer(self.image,'synthetic','smart_farm',crop=True,scan_regions=True)
        with self.assertRaises(ValueError):self.engine.infer(self.image,'synthetic','deploy_zone',scan_regions=True)

    def test_nonfinite_output_is_rejected(self):
        from unittest.mock import patch
        output = np.zeros((1,10,1),np.float32)
        output[0,4,0] = np.nan
        with patch.object(self.engine.session, 'run', return_value=[output]):
            with self.assertRaises(ValueError):
                self.engine.infer(self.image,'synthetic','smart_farm')

    def test_wrong_output_channels_are_rejected(self):
        from unittest.mock import patch
        with patch.object(self.engine.session, 'run', return_value=[np.zeros((1,11,1),np.float32)]):
            with self.assertRaises(ValueError):
                self.engine.infer(self.image,'synthetic','smart_farm')

    def test_export_does_not_modify_original_pixels(self):
        from cocbot.vision.onnx_engine import rendered_rgb
        result=self.engine.infer(self.image,'synthetic','smart_farm')
        before=result.image.copy()
        rendered_rgb(result)
        np.testing.assert_array_equal(result.image,before)

if __name__=='__main__':unittest.main()
