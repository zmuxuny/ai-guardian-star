"""Local-only, normalized posture_v1; never changes the detector's decision."""
from bisect import bisect_right
from datetime import datetime, timedelta, timezone
import math

VERSION = 'posture_v1'
CONFIG_VERSION = 'personal_shadow_v1'
AXES = ('torso_angle', 'hip_height', 'aspect_ratio')
GUARDS = ('long_still', 'no_response', 'radar_fall')


def _number(value):
    # numpy scalar coordinates are accepted; booleans and text are not.
    if isinstance(value, (bool, str, bytes)):
        raise ValueError('invalid number')
    result = float(value)
    if not math.isfinite(result):
        raise ValueError('nonfinite number')
    return result


def validate_feature(value):
    if not isinstance(value, dict) or value.get('version') != VERSION or value.get('valid') is not True:
        raise ValueError('unusable posture')
    expected = {'version','valid','reason','torso_angle','hip_height','aspect_ratio','region_id','time_slot'}
    if set(value) != expected or value['reason'] != 'ok':
        raise ValueError('invalid posture schema')
    angle, hip, ratio = (_number(value[k]) for k in AXES)
    if not 0 <= angle <= 90 or not 0 <= hip <= 1 or not 0 < ratio <= 100:
        raise ValueError('posture out of range')
    region = value['region_id']
    if (not isinstance(region,str) or not region or len(region)>128 or region != region.strip()
            or any(ord(c)<32 or ord(c)==127 for c in region)):
        raise ValueError('invalid region')
    if type(value['time_slot']) is not int or not 0 <= value['time_slot'] <= 5:
        raise ValueError('invalid slot')
    return value


def extract_posture(box, kpts, frame_shape, region_id, at):
    """One event snapshot; invalid inputs return a reason without coordinates."""
    failed = dict(version=VERSION,valid=False,reason='invalid_pose')
    try:
        if len(box)!=4 or len(frame_shape)<2 or len(kpts)<13:
            return failed
        x1,y1,x2,y2 = map(_number,box)
        height,width = map(_number,frame_shape[:2])
        if not 0 < x1 < x2 < width or not 0 < y1 < y2 < height:
            return dict(failed,reason='invalid_or_truncated_box')
        points = []
        for index in (5,6,11,12):
            x,y,confidence = map(_number,kpts[index])
            if not .4 < confidence <= 1 or not x1 <= x <= x2 or not y1 <= y <= y2:
                return dict(failed,reason='unreliable_keypoints')
            points.append((x,y))
        sx,sy = ((points[0][i]+points[1][i])/2 for i in (0,1))
        hx,hy = ((points[2][i]+points[3][i])/2 for i in (0,1))
        if math.hypot(hx-sx,hy-sy) < 1e-8:
            return dict(failed,reason='degenerate_torso')
        instant = datetime.fromtimestamp(_number(at),timezone(timedelta(hours=8)))
        result = dict(version=VERSION,valid=True,reason='ok',
                      torso_angle=math.degrees(math.atan2(abs(hx-sx),abs(hy-sy))),
                      hip_height=(hy-y1)/(y2-y1),aspect_ratio=(x2-x1)/(y2-y1),
                      region_id=region_id,time_slot=instant.hour//4)
        return validate_feature(result)
    except (ValueError,TypeError,IndexError,OverflowError,OSError):
        return failed


def eligible_label(payload, revoked):
    if revoked or not isinstance(payload,dict):
        return None
    if payload.get('feedback') == 'trusted':
        return 'risk'
    if payload.get('feedback') == 'untrusted' and payload.get('reason') in ('not_fall','sitting_or_lying'):
        return 'normal'
    return None


def _similar(left,right):
    validate_feature(right)
    return (left['region_id']==right['region_id'] and left['time_slot']==right['time_slot']
            and abs(left['torso_angle']-right['torso_angle']) <= 10+1e-9
            and abs(left['hip_height']-right['hip_height']) <= .1+1e-9
            and abs(left['aspect_ratio']-right['aspect_ratio'])/left['aspect_ratio'] <= .15+1e-9)


def evaluate(feature, normal, risk, guards):
    validate_feature(feature)
    if not isinstance(guards,dict) or any(guards.get(k) is not False for k in GUARDS):
        return 'protected'
    if any(_similar(feature,row['feature']) for row in risk):
        return 'positive_match'
    unique = {row['event_id']:row['feature'] for row in normal}
    if len(unique)<3:
        return 'insufficient'
    return 'suggest_extend' if sum(_similar(feature,f) for f in unique.values())>=3 else 'no_match'


def histogram_bins(feature):
    validate_feature(feature)
    return dict(torso_angle=min(5,int(feature['torso_angle']//15)),
                hip_height=min(9,int(round(feature['hip_height'],9)*10)),
                aspect_ratio=bisect_right((.5,.75,1.,1.5,2.),feature['aspect_ratio']))
