"""Independent parser for Huawei personal-data JSON export shapes.

Unknown fields remain in the immutable source object. Uncertain calorie/distance
units are never guessed. See docs/research.md for references and attribution.
"""

import json
from dataclasses import dataclass, field

from vitaldock.model import milliseconds, number, observation

SCALARS = {
    "DATA_POINT_DYNAMIC_HEARTRATE": ("heart_rate", 0, 300),
    "DATA_POINT_REST_HEARTRATE": ("resting_heart_rate", 0, 300),
    "BLOOD_OXYGEN_SATURATION": ("oxygen_saturation", 0, 100),
}
STAGES = {
    "PROFESSIONAL_SLEEP_SHALLOW": "light",
    "PROFESSIONAL_SLEEP_DEEP": "deep",
    "PROFESSIONAL_SLEEP_DREAM": "rem",
    "PROFESSIONAL_SLEEP_WAKE": "awake",
    "PROFESSIONAL_SLEEP_NOON": "nap",
}


@dataclass
class ParseResult:
    records: list = field(default_factory=list)
    issues: list = field(default_factory=list)
    recognized: bool = False

    def issue(self, code, pointer, severity="warning"):
        # Codes, not raw values or exception messages, keep reports free of payloads.
        self.issues.append({"code": code, "pointer": pointer, "severity": severity})


def parse(data: bytes, profile="self") -> ParseResult:
    result = ParseResult()
    try:
        document = json.loads(data.decode("utf-8-sig"))
    except (UnicodeError, ValueError, RecursionError):
        result.issue("invalid_json", "", "error")
        return result
    if isinstance(document, dict):
        rows = [("", document)]
    elif isinstance(document, list):
        rows = [(f"/{i}", row) for i, row in enumerate(document)]
    else:
        result.issue("unsupported_document_shape", "")
        return result
    for pointer, row in rows:
        if not isinstance(row, dict):
            result.issue("non_object_record", pointer, "error")
            continue
        recognized = False
        for field_name, handler in (("samplePoints", _health),
                                    ("sportDataUserData", _sport),
                                    ("motionPathData", _motion)):
            if field_name in row:
                result.recognized = recognized = True
                entries = row[field_name]
                if not isinstance(entries, list):
                    result.issue("invalid_record_array", pointer + "/" + field_name, "error")
                    continue
                for index, entry in enumerate(entries):
                    path = f"{pointer}/{field_name}/{index}"
                    if not isinstance(entry, dict):
                        result.issue("invalid_record", path, "error")
                        continue
                    try:
                        handler(result, profile, row, entry, path)
                    except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
                        result.issue("invalid_measurement", path, "error")
        if not recognized:
            result.issue("unsupported_record_shape", pointer)
    if not rows:
        result.issue("empty_document", "")
    return result


def _health(result, profile, parent, point, pointer):
    key = point.get("key")
    # "0" is the vendor's default unit. Explicit units must match our adapter.
    unit = str(point.get("unit", "0"))

    def emit(metric, value, hint=None):
        result.records.append(observation(
            profile=profile, parent=parent, point=point, metric=metric, value=value,
            pointer=pointer, source_key=key, subject_hint=hint))

    if key in SCALARS:
        metric, low, high = SCALARS[key]
        accepted = {"0", "bpm"} if "heart_rate" in metric else {"0", "%"}
        if unit not in accepted:
            result.issue("unsupported_unit", pointer, "error")
            return
        value = number(point.get("value"))
        if not low < value <= high:
            raise ValueError("out of adapter range")
        emit(metric, value)
    elif key in STAGES:
        emit("sleep_stage", STAGES[key])
    elif key == "WEIGHT_BODYFAT_BROAD":
        if unit not in {"0", "kg"}:
            result.issue("unsupported_unit", pointer, "error")
            return
        payload = point.get("value")
        payload = json.loads(payload) if isinstance(payload, str) else payload
        if not isinstance(payload, dict):
            raise ValueError("body composition must be an object")
        found = False
        for field_name, metric, low, high in (("bodyWeight", "body_weight", 0, 500),
                                              ("bodyFatRate", "body_fat", 0, 100)):
            if payload.get(field_name) is not None:
                found = True
                value = number(payload[field_name])
                if not low < value <= high:
                    result.issue("out_of_adapter_range", pointer, "error")
                    continue
                emit(metric, value, payload.get("extendAttribute"))
        if not found:
            result.issue("unsupported_body_composition", pointer)
    else:
        result.issue("unsupported_sample_key", pointer)


def _sport(result, profile, parent, entry, pointer):
    infos = entry.get("sportBasicInfos")
    if not isinstance(infos, list) or not infos:
        raise ValueError("missing sportBasicInfos")
    # Preserve the actual source interval; do not invent minute boundaries.
    values = []
    for info in infos:
        if not isinstance(info, dict) or "steps" not in info:
            raise ValueError("missing steps")
        steps = number(info["steps"])
        if steps < 0 or not steps.is_integer():
            raise ValueError("steps must be a nonnegative integer")
        values.append(int(steps))
    merged = {**parent, **entry}
    result.records.append(observation(
        profile=profile, parent=merged, point=entry, metric="steps", value=sum(values),
        pointer=pointer, source_key="sportBasicInfos.steps",
        qualifiers={"aggregation": "sum_of_source_entries", "entries": len(infos)}))
    if any("calorie" in x or "distance" in x for x in infos):
        result.issue("distance_and_calorie_units_unverified_raw_preserved", pointer)


def _motion(result, profile, parent, entry, pointer):
    start = milliseconds(entry.get("startTime"))
    end = milliseconds(entry.get("endTime"))
    merged = {**parent, **entry}
    sport_type = entry.get("sportType")
    if isinstance(sport_type, bool) or not isinstance(sport_type, int):
        raise ValueError("sport type must be integer")
    result.records.append(observation(
        profile=profile, parent=merged, point=entry, metric="workout_duration",
        value=(end - start) / 1000, pointer=pointer, source_key="motionPathData",
        qualifiers={"huawei_sport_type": sport_type, "duration_basis": "elapsed_interval"}))
    if entry.get("attribute"):
        result.issue("hitrack_detail_raw_preserved_not_normalized", pointer)
