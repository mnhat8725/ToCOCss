"""Explicit preview strategy; not a reconstruction of AutoCOCVN's scoring."""
import json
import math
from pathlib import Path

WEIGHTS = {"gold_mine_full": 1., "gold_storage_full": 1.5,
           "elixir_collector_full": 1., "elixir_storage_full": 1.5,
           "de_drill_full": 1.2, "de_storage_full": 1.8}


def build_preview_plan(result):
    height, width = result.image.shape[:2]
    scores = {name: 0. for name in ("top_left", "top_right", "bottom_left", "bottom_right")}
    targets = []
    for detection in result.detections:
        if detection.get("candidate_only") or detection["class_name"] not in WEIGHTS:
            continue
        x1, y1, x2, y2 = detection["box_xyxy"]
        cx, cy = (x1 + x2) / (2 * width), (y1 + y2) / (2 * height)
        direction = ("top" if cy < .5 else "bottom") + ("_left" if cx < .5 else "_right")
        area = max(0, (x2 - x1) * (y2 - y1)) / (width * height)
        scores[direction] += detection["confidence"] * math.sqrt(area) * WEIGHTS[detection["class_name"]]
        targets.append({"class_name": detection["class_name"], "center_normalized": [cx, cy]})
    direction = max(scores, key=scores.get) if targets else None
    # Explicitly illustrative perimeter points. They are not a valid deployment
    # mask and are never automatically authorized for live execution.
    actions = []
    if direction:
        x = .15 if direction.endswith("left") else .85
        ys = (.25, .35, .45) if direction.startswith("top") else (.55, .65, .72)
        actions = [{"type": "select", "control": "s_goblin"}]
        actions += [{"type": "drop_troop", "point": [x, y], "count": 1, "interval": .15} for y in ys]
        actions.append({"type": "delay", "seconds": 1.0})
    return {"schema_version": 1, "status": "preview_only" if targets else "no_targets",
            "dry_run_only": True, "coordinate_space": "normalized_device",
            "image_size": [width, height], "model_sha256": result.model_sha256,
            "strategy": "quadrant_preview_v1", "direction": direction, "scores": scores,
            "targets": targets, "actions": actions,
            "note": "Illustrative points, not validated deployment positions. Candidate-only predictions excluded."}


def save_plan(path, plan):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plan, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def capital_deploy_point(result, context):
    """Find a point inside an eroded Capital mask, never a bounding-box center."""
    if context != "clan_capital" or result.model != "deploy_zone":
        raise ValueError("Deploy Zone requires explicit Clan Capital context")
    import cv2
    import numpy as np
    height, width = result.image.shape[:2]
    combined = np.zeros((height, width), np.uint8)
    for _, x, y, mask in result.masks:
        combined[y:y + mask.shape[0], x:x + mask.shape[1]] |= mask.astype(np.uint8)
    # Exclude UI bands; erosion avoids predicting a point directly on a border.
    combined[:round(height * .12)] = 0
    combined[round(height * .78):] = 0
    combined = cv2.erode(combined, np.ones((5, 5), np.uint8))
    if not combined.any():
        return None
    distance = cv2.distanceTransform(combined, cv2.DIST_L2, 5)
    _, clearance, _, point = cv2.minMaxLoc(distance)
    return {"point": [point[0] / width, point[1] / height],
            "clearance_pixels": clearance, "dry_run_only": True,
            "coordinate_space": "normalized_device"}
