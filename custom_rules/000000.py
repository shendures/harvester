# custom_rules/000000.py — seq_no=000000(샤브올데이) 전용 커스텀 정제
import re


def refine_row(row: dict) -> dict:
    tel = row.get("tel", "")
    digits = re.sub(r"\D", "", tel)
    if len(digits) == 10:
        row["tel"] = f"{digits[:2]}-{digits[2:6]}-{digits[6:]}"
    elif len(digits) == 11:
        row["tel"] = f"{digits[:3]}-{digits[3:7]}-{digits[7:]}"
    return row
