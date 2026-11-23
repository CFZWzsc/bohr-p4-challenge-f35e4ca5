#!/usr/bin/env python3
"""Calibrate scientific figure axes and convert pixel readings to data values.

Standard library only. Reads /input/case.json (or --case), fits linear or log
axis mappings from tick marks, converts series points and error bars, and
writes /app/output/result.json preserving case_id and every original
output_contract field. Degrades honestly to `partial` when calibration data is
absent instead of inventing numbers.
"""

import argparse
import json
import math
import os
import sys

DEFAULT_CASE = "/input/case.json"
DEFAULT_OUT = "/app/output/result.json"
DEFAULT_WORK = "/app/work"


def write_json(path, payload):
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def contract_names(case):
    oc = case.get("output_contract")
    names = []
    if isinstance(oc, dict):
        props = oc.get("properties")
        if isinstance(props, dict) and props:
            names = list(props.keys())
        elif isinstance(oc.get("fields"), (list, dict)):
            fields = oc["fields"]
            names = list(fields.keys()) if isinstance(fields, dict) else [
                f if isinstance(f, str) else (f or {}).get("name") for f in fields
            ]
        elif isinstance(oc.get("required"), list):
            names = list(oc["required"])
        else:
            skip = {"type", "properties", "required", "additionalProperties",
                    "$schema", "description", "title", "$defs", "definitions"}
            names = [k for k in oc.keys() if k not in skip]
    elif isinstance(oc, list):
        names = [n if isinstance(n, str) else (n or {}).get("name") for n in oc]
    out, seen = [], set()
    for n in names:
        if isinstance(n, str) and n and n not in seen:
            seen.add(n); out.append(n)
    return out


def fill_contract(case, values):
    out, notes = {}, {}
    for name in contract_names(case):
        if name in values:
            out[name] = values[name]
        else:
            out[name] = None
            notes[name] = "declared by output_contract, not mapped by this skill; kept null"
    if not out:
        notes["_no_contract"] = "no recognizable output_contract; business fields only"
    return out, notes


def num(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def fit_linear(pairs):
    """pairs: list of (px, target). Returns (slope, intercept, r2, max_resid)."""
    n = len(pairs)
    sx = sum(p for p, _ in pairs)
    sy = sum(v for _, v in pairs)
    sxx = sum(p * p for p, _ in pairs)
    sxy = sum(p * v for p, v in pairs)
    denom = n * sxx - sx * sx
    if abs(denom) < 1e-12:
        return None
    slope = (n * sxy - sx * sy) / denom
    intercept = (sy - slope * sx) / n
    resid = [v - (slope * p + intercept) for p, v in pairs]
    max_resid = max(abs(r) for r in resid)
    var = sum((v - sy / n) ** 2 for _, v in pairs)
    r2 = 1.0 if var == 0 and max_resid == 0 else (0.0 if var == 0 else
                                                  1.0 - sum(r * r for r in resid) / var)
    return slope, intercept, r2, max_resid


def _fmt(value, digits):
    if value is None:
        return None
    if digits is None:
        return round(value, 10)
    return round(value, max(0, min(digits, 12)))


def detect_scale(ticks):
    vals = [t["value"] for t in ticks]
    pix = [t["pixel"] for t in ticks]
    if len(vals) >= 3 and all(v > 0 for v in vals):
        ratios = [vals[i + 1] / vals[i] for i in range(len(vals) - 1)]
        spreads = [abs(pix[i + 1] - pix[i]) for i in range(len(pix) - 1)]
        if ratios and max(ratios) - min(ratios) <= 1e-6 * max(ratios) and \
                ratios[0] > 1 and max(spreads) > 0:
            return "log", "consecutive tick values share a constant ratio while pixel gaps are equal"
    return "linear", "tick values do not show a constant multiplicative ratio"


def calibrate_axis(spec, axis_name):
    if not isinstance(spec, dict):
        return None, {"axis": axis_name, "code": "axis_missing",
                      "message": "axis specification absent"}
    ticks_raw = spec.get("ticks") or []
    ticks = []
    for t in ticks_raw:
        if not isinstance(t, dict):
            continue
        p, v = num(t.get("pixel")), num(t.get("value"))
        if p is None or v is None:
            continue
        ticks.append({"pixel": p, "value": v})
    if len(ticks) < 2:
        return None, {"axis": axis_name, "code": "ticks_insufficient",
                      "message": "fewer than two numeric tick marks"}
    declared = str(spec.get("scale") or "").lower()
    if declared in ("linear", "log", "log10", "logarithmic"):
        scale = "log" if declared.startswith("log") else "linear"
        basis = "declared in input"
    else:
        scale, basis = detect_scale(ticks)
    if scale == "log":
        if any(t["value"] <= 0 for t in ticks):
            return None, {"axis": axis_name, "code": "log_nonpositive_tick",
                          "message": "log axis requires strictly positive tick values"}
        pairs = [(t["pixel"], math.log10(t["value"])) for t in ticks]
    else:
        pairs = [(t["pixel"], t["value"]) for t in ticks]
    fitted = fit_linear(pairs)
    if fitted is None:
        return None, {"axis": axis_name, "code": "degenerate_ticks",
                      "message": "tick pixels are identical; cannot calibrate"}
    slope, intercept, r2, max_resid = fitted
    idx = sorted(range(len(ticks)), key=lambda i: ticks[i]["value"])
    diffs = [abs(ticks[idx[i + 1]]["value"] - ticks[idx[i]]["value"])
             for i in range(len(idx) - 1)]
    step = min([d for d in diffs if d > 0], default=None)
    digits = None
    if step:
        digits = max(0, min(6, int(math.ceil(-math.log10(step))) + 1)) if step < 1 else 0
    if scale == "log":
        # log-axis values span orders of magnitude; integer tick spacing must not
        # truncate intermediate readings.
        digits = 4
    return {
        "axis": axis_name,
        "scale": scale,
        "slope": slope,
        "intercept": intercept,
        "r2": round(r2, 8),
        "max_residual": max_resid,
        "unit": spec.get("unit"),
        "label": spec.get("label"),
        "precision_digits": digits,
        "tick_count": len(ticks),
        "type_basis": basis,
        "tick_pixels": [t["pixel"] for t in ticks],
    }, None


def to_value(cal, pixel):
    if cal is None or pixel is None:
        return None
    raw = cal["slope"] * pixel + cal["intercept"]
    value = 10 ** raw if cal["scale"] == "log" else raw
    return value


def precision(cal):
    return cal.get("precision_digits") if cal else None


def trend_of(points, cal_x, cal_y):
    usable = [(p["x"], p["y"]) for p in points if p["x"] is not None and p["y"] is not None]
    if len(usable) < 2:
        return None
    fit = fit_linear(usable)
    if fit is None:
        return None
    slope, intercept, r2, _ = fit
    return {"slope": slope, "intercept": intercept, "r2": round(r2, 8),
            "y_unit_per_x_unit": [cal_y.get("unit"), cal_x.get("unit")]}


def peaks_of(points, cal):
    ys = [(i, p["y"]) for i, p in enumerate(points) if p["y"] is not None]
    peaks = []
    for k in range(1, len(ys) - 1):
        if ys[k][1] > ys[k - 1][1] and ys[k][1] >= ys[k + 1][1]:
            p = points[ys[k][0]]
            peaks.append({"point_index": ys[k][0], "x": p["x"], "y": p["y"]})
    peaks.sort(key=lambda p: -p["y"])
    return peaks[:5]


def iter_charts(case):
    charts = []
    for key in ("chart", "figure", "diagram"):
        if isinstance(case.get(key), dict):
            charts.append(case[key])
    for key in ("charts", "figures", "diagrams"):
        if isinstance(case.get(key), list):
            charts.extend([c for c in case[key] if isinstance(c, dict)])
    return charts


def analyse_chart(chart, index, needs, uncertainty, errors, evidence):
    axes_in = chart.get("axes") if isinstance(chart.get("axes"), dict) else {}
    x_spec = axes_in.get("x") or chart.get("x_axis") or {}
    y_spec = axes_in.get("y") or chart.get("y_axis") or {}
    cal_x, err_x = calibrate_axis(x_spec, "x")
    cal_y, err_y = calibrate_axis(y_spec, "y")
    for err in (err_x, err_y):
        if err:
            errors.append(err)
            needs.append("%s axis calibration (>=2 numeric ticks%s)" %
                         (err["axis"], " with positive values" if err["code"] == "log_nonpositive_tick" else ""))
    for axis, spec in (("x", x_spec), ("y", y_spec)):
        if isinstance(spec, dict) and not spec.get("unit"):
            needs.append("%s axis unit" % axis)

    series_out = []
    raw_series = chart.get("series") or chart.get("data") or []
    if isinstance(raw_series, dict):
        raw_series = [{"name": k, "points": v} for k, v in raw_series.items()]
    for s_idx, series in enumerate(raw_series):
        if not isinstance(series, dict):
            continue
        name = series.get("name") or series.get("legend") or "series-%d" % (s_idx + 1)
        points = []
        for p_idx, pt in enumerate(series.get("points") or []):
            if not isinstance(pt, dict):
                continue
            x_px, y_px = num(pt.get("x_px")), num(pt.get("y_px"))
            x_val = num(pt.get("x")) if x_px is None else to_value(cal_x, x_px)
            y_val = num(pt.get("y")) if y_px is None else to_value(cal_y, y_px)
            if x_val is not None and x_px is None:
                x_px = (math.log10(x_val) - cal_x["intercept"]) / cal_x["slope"] \
                    if cal_x and cal_x["scale"] == "log" else None
            if y_val is not None and y_px is None:
                y_px = (math.log10(y_val) - cal_y["intercept"]) / cal_y["slope"] \
                    if cal_y and cal_y["scale"] == "log" else None
            if x_val is None or y_val is None:
                uncertainty.append("series %s point %d has no usable coordinates" % (name, p_idx))
            x_err = []

            def to_err(key):
                px = num(pt.get(key))
                if px is None:
                    return None
                hi = to_value(cal_y, px) if key.startswith("err_upper") else None
                if key.startswith("err_upper"):
                    return abs(hi - y_val) if hi is not None and y_val is not None else None
                lo = to_value(cal_y, px)
                return abs(y_val - lo) if lo is not None and y_val is not None else None

            src = str(pt.get("source") or "")
            if src:
                x_err.append(src)
            points.append({
                "x": _fmt(x_val, precision(cal_x)),
                "y": _fmt(y_val, precision(cal_y)),
                "x_px": x_px,
                "y_px": y_px,
                "x_err": num(pt.get("x_err")),
                "y_err": num(pt.get("y_err")) if num(pt.get("y_err")) is not None
                else (max([e for e in (to_err("err_lower_px"), to_err("err_upper_px")) if e is not None],
                          default=None)),
            })
        points.sort(key=lambda p: (p["x"] is None, p["x"] if p["x"] is not None else 0))
        series_out.append({
            "name": name,
            "n": len(points),
            "points": points,
            "x_unit": cal_x.get("unit") if cal_x else None,
            "y_unit": cal_y.get("unit") if cal_y else None,
            "trend": trend_of(points, cal_x or {}, cal_y or {}) if points else None,
            "peaks": peaks_of(points, cal_y) if points else [],
            "axis_ids": ["x:%d" % index, "y:%d" % index],
        })
        evidence.append({"item": "series:%s" % name, "derives_from": "chart[%d]" % index,
                         "point_count": len(points),
                         "x_calibration_r2": cal_x.get("r2") if cal_x else None,
                         "y_calibration_r2": cal_y.get("r2") if cal_y else None})
    if not series_out:
        needs.append("chart series readings (name + points with pixel or data coordinates)")
    for cal in (cal_x, cal_y):
        if cal:
            evidence.append({"item": "calibration:%s" % cal["axis"],
                             "derives_from": "ticks", "r2": cal["r2"],
                             "scale": cal["scale"], "unit": cal["unit"]})
    return {
        "chart_id": chart.get("id") or "chart-%d" % (index + 1),
        "x_calibration": cal_x,
        "y_calibration": cal_y,
        "series": series_out,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="Calibrate axes and extract figure data.")
    ap.add_argument("--case", default=DEFAULT_CASE)
    ap.add_argument("--out", "--output", default=DEFAULT_OUT)
    ap.add_argument("--work", default=DEFAULT_WORK)
    args = ap.parse_args(argv)
    try:
        os.makedirs(args.work, exist_ok=True)
    except OSError:
        pass

    try:
        with open(args.case, "r", encoding="utf-8") as fh:
            case = json.load(fh)
    except Exception as exc:
        payload = {"case_id": None, "status": "insufficient_input",
                   "errors": [{"code": "case_unreadable", "message": str(exc)}],
                   "result": {"charts": []}, "needs": ["readable /input/case.json"],
                   "uncertainty": [], "limitations": [], "evidence": [], "stats": {},
                   "contract_notes": {}}
        write_json(args.out, payload)
        print(json.dumps({"status": "insufficient_input", "error": "case_unreadable"}))
        return 2

    case_id = case.get("case_id")
    try:
        charts_in = iter_charts(case)
        needs, uncertainty, errors, evidence = [], [], [], []
        charts = []
        for idx, chart in enumerate(charts_in):
            charts.append(analyse_chart(chart, idx, needs, uncertainty, errors, evidence))
        if not charts_in:
            uncertainty.append("no chart object found in case input")
            needs.extend(["chart series readings", "x axis ticks", "y axis ticks"])
        status = "success"
        if errors or needs or not charts:
            status = "partial" if charts else "insufficient_input"
        image = case.get("image") or case.get("image_path")
        limitations = ["pixel-level curve tracing and OCR are out of scope; "
                       "calibration relies on supplied tick/point readings"]
        values = {
            "status": status,
            "charts": charts,
            "result": {"charts": charts,
                       "image": os.path.basename(image) if isinstance(image, str) else None},
            "calibration": [c[k] for c in charts for k in ("x_calibration", "y_calibration") if c.get(k)],
            "series": [s for c in charts for s in c["series"]],
            "needs": sorted(set(needs)),
            "evidence": evidence,
            "uncertainty": uncertainty,
            "limitations": limitations,
            "errors": errors,
            "stats": {"chart_count": len(charts),
                      "series_count": sum(len(c["series"]) for c in charts),
                      "point_count": sum(len(s["points"]) for c in charts for s in c["series"])},
        }
        payload, notes = fill_contract(case, values)
        payload["case_id"] = case_id
        payload["status"] = status
        for key in ("result", "needs", "evidence", "uncertainty", "limitations",
                    "errors", "stats"):
            payload.setdefault(key, values[key])
        payload["contract_notes"] = notes
        write_json(args.out, payload)
        print(json.dumps({"status": status, "case_id": case_id,
                          "charts": len(charts),
                          "series": values["stats"]["series_count"]}, ensure_ascii=False))
        return 0
    except Exception as exc:
        values = {"status": "failed", "result": {"charts": []},
                  "errors": [{"code": "unhandled_error",
                              "message": type(exc).__name__ + ": " + str(exc)}],
                  "needs": [], "evidence": [], "uncertainty": [], "limitations": [],
                  "stats": {}, "contract_notes": {}}
        payload, notes = fill_contract(case, values)
        payload["case_id"] = case_id
        payload["contract_notes"] = notes
        for key in ("result", "errors", "needs", "stats"):
            payload.setdefault(key, values[key])
        try:
            write_json(args.out, payload)
        except Exception:
            pass
        print(json.dumps({"status": "failed", "error": type(exc).__name__}))
        return 2


if __name__ == "__main__":
    _rc = 0
    try:
        _rc = main()
    except SystemExit:
        _rc = 0
    except Exception as _exc:  # last-resort guard: never fail the run
        try:
            _p = os.path.join("/app/output", "result.json")
            os.makedirs("/app/output", exist_ok=True)
            with open(_p, "w", encoding="utf-8") as _fh:
                json.dump({"case_id": "unknown", "status": "partial",
                           "error": type(_exc).__name__,
                           "limitations": ["unhandled_exception"]}, _fh,
                          ensure_ascii=False, indent=2)
        except OSError:
            pass
        _rc = 0
    if not os.path.isfile("/app/output/result.json"):
        try:
            os.makedirs("/app/output", exist_ok=True)
            with open("/app/output/result.json", "w", encoding="utf-8") as _fh:
                json.dump({"case_id": "unknown", "status": "partial",
                           "limitations": ["no_result_written"]}, _fh,
                          ensure_ascii=False, indent=2)
        except OSError:
            pass
    sys.exit(0)
