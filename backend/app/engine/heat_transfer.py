from __future__ import annotations
import math


def lmtd(
    hot_in_c: float,
    hot_out_c: float,
    cold_in_c: float,
    cold_out_c: float,
    counter_current: bool = True,
) -> float:
    if counter_current:
        dt1 = hot_in_c - cold_out_c
        dt2 = hot_out_c - cold_in_c
    else:
        dt1 = hot_in_c - cold_in_c
        dt2 = hot_out_c - cold_out_c

    if dt1 <= 0 or dt2 <= 0:
        raise ValueError("Temperature cross or non-positive terminal temperature difference.")

    if abs(dt1 - dt2) < 1e-12:
        return dt1

    return (dt1 - dt2) / math.log(dt1 / dt2)


def overall_u_outside_basis(
    hi_w_m2k: float,
    ho_w_m2k: float,
    tube_id_m: float,
    tube_od_m: float,
    tube_k_w_mk: float,
    rf_inside_m2k_w: float = 0.0,
    rf_outside_m2k_w: float = 0.0,
) -> float:
    if min(hi_w_m2k, ho_w_m2k, tube_id_m, tube_od_m, tube_k_w_mk) <= 0:
        raise ValueError("Heat-transfer coefficients, diameters and wall conductivity must be positive.")

    resistance = (
        1.0 / ho_w_m2k
        + rf_outside_m2k_w
        + tube_od_m * math.log(tube_od_m / tube_id_m) / (2.0 * tube_k_w_mk)
        + (tube_od_m / tube_id_m) * (rf_inside_m2k_w + 1.0 / hi_w_m2k)
    )

    return 1.0 / resistance


def required_area_m2(
    duty_w: float,
    u_w_m2k: float,
    lmtd_k: float,
    correction_factor: float = 1.0,
) -> float:
    denominator = u_w_m2k * lmtd_k * correction_factor
    if denominator <= 0:
        raise ValueError("U, LMTD and correction factor must give a positive denominator.")
    return duty_w / denominator
