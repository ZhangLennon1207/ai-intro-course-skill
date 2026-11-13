"""Optional project knowledge-point map; bundled data is an example, never a default."""
from __future__ import annotations
import csv
from pathlib import Path


def load(path: str | Path | None = None) -> dict[str, dict]:
    if path is None:
        return {}
    source = Path(path)
    result, names = {}, set()
    with source.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not {"kp_id", "name"} <= set(reader.fieldnames or []):
            raise ValueError("知识点映射需要kp_id,name列")
        for line, row in enumerate(reader, 2):
            kid, name = (row.get("kp_id") or "").strip(), (row.get("name") or "").strip()
            if not kid or not name or kid in result or name in names:
                raise ValueError(f"知识点映射第{line}行缺值或编号/名称重复")
            result[kid] = {"id": kid, "name": name, "section": (row.get("section") or "").strip(),
                           "order": int(row.get("order") or len(result) + 1)}
            names.add(name)
    if not result:
        raise ValueError("显式知识点映射为空")
    return result


def by_name(table):
    return {value["name"]: key for key, value in table.items()}


def resolve(name, table):
    value = str(name).strip()
    return value if value in table else by_name(table).get(value)


def label(kid, table, name=""):
    return f"{kid} {table[kid]['name']}" if kid in table else " ".join(str(x) for x in (kid, name) if x)


def validate(table):
    if not table:
        return [("warn", "知识点", "未提供项目编码表，仅保留输入中的名称与编号，不自动套用示例")]
    return []


def check_refs(ids, table, where=""):
    if not table:
        return []
    return [("error", where or "引用", f"编号{kid}不在本次显式映射中")
            for kid in ids or [] if str(kid).strip() and str(kid).strip() not in table]
