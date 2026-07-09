# custom_rules/000000.py — seq_no=000000(샤브올데이) 전용 커스텀 정제
import re


def refine_row(row: dict) -> dict:
    tel = row.get("tel", "")
    normalized_tel = re.sub(r"\)", "-", tel)
    row["tel"] = normalized_tel
    return row
