"""回答自检的纯函数测试。不依赖数据库、语料或网络。

单独运行：python tests/unit/test_audit.py
pytest 运行：python -m pytest tests/unit/test_audit.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

_API_ROOT = Path(__file__).resolve().parents[2]
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from app.kb.audit import audit_answer  # noqa: E402


def _doc(doc_id: int, title: str):
    return SimpleNamespace(id=doc_id, title=title, file_name=title)


def _cites(*items):
    return [{"id": doc_id, "title": title, "score": 0.9, "images": []} for doc_id, title in items]


def _codes(result):
    return [item["code"] for item in result["items"]]


def test_grounded_answer_is_ok():
    result = audit_answer(
        "质保期多久",
        "质保期为 12 个月，有效期至 2027-08-31。依据：资料1",
        _cites((1, "协议A")),
        [(_doc(1, "协议A"), 0.9, "质保期为 12 个月，有效期至 2027-08-31。")],
    )
    assert result["status"] == "ok", _codes(result)
    assert result["items"] == []


def test_fabricated_date_is_flagged():
    result = audit_answer(
        "质保期多久",
        "质保期为 12 个月，有效期至 2029-01-01。依据：资料1",
        _cites((1, "协议A")),
        [(_doc(1, "协议A"), 0.9, "质保期为 12 个月，有效期至 2027-08-31。")],
    )
    assert "unsupported_fact" in _codes(result)


def test_citation_out_of_range():
    result = audit_answer(
        "质保期多久",
        "质保期为 12 个月。依据：资料9",
        _cites((1, "协议A")),
        [(_doc(1, "协议A"), 0.9, "质保期为 12 个月。")],
    )
    assert result["status"] == "error"
    assert "citation_out_of_range" in _codes(result)


def test_fact_in_uncited_doc():
    result = audit_answer(
        "质保期多久",
        "质保期为 18 个月。依据：资料1",
        _cites((1, "协议A"), (2, "台账")),
        [(_doc(1, "协议A"), 0.9, "质保期为 12 个月。"), (_doc(2, "台账"), 0.8, "质保期为 18 个月。")],
    )
    assert "fact_in_uncited_doc" in _codes(result)


def test_conflict_missed():
    result = audit_answer(
        "质保期多久",
        "质保期为 12 个月。依据：资料1、资料2",
        _cites((1, "协议A"), (2, "台账")),
        [(_doc(1, "协议A"), 0.9, "质保期为 12 个月。"), (_doc(2, "台账"), 0.8, "质保期为 18 个月。")],
    )
    assert "conflict_missed" in _codes(result)


def test_strict_inference_only_in_strict_mode():
    strict = audit_answer(
        "质保期多久",
        "质保期可能是 12 个月。依据：资料1",
        _cites((1, "协议A")),
        [(_doc(1, "协议A"), 0.9, "质保期为 12 个月。")],
        mode="strict",
    )
    loose = audit_answer(
        "质保期多久",
        "质保期可能是 12 个月。依据：资料1",
        _cites((1, "协议A")),
        [(_doc(1, "协议A"), 0.9, "质保期为 12 个月。")],
        mode="loose",
    )
    assert "strict_inference" in _codes(strict)
    assert "strict_inference" not in _codes(loose)


def test_absolute_claim():
    result = audit_answer(
        "质保期多久",
        "质保期为 12 个月，整个库都没有别的说法。依据：资料1",
        _cites((1, "协议A")),
        [(_doc(1, "协议A"), 0.9, "质保期为 12 个月。")],
    )
    assert "absolute_claim" in _codes(result)


def test_checklist_header_and_conclusion():
    result = audit_answer(
        "逐项核对",
        "| 要素 | 状态 |\n| 质保期 | 命中 |\n可以批准。",
        _cites((1, "协议A")),
        [(_doc(1, "协议A"), 0.9, "质保期为 12 个月。")],
        ask_kind="checklist",
    )
    assert "checklist_missing_header" in _codes(result)
    assert "checklist_conclusion" in _codes(result)


def test_empty_answer():
    result = audit_answer("质保期多久", "   ", _cites((1, "协议A")), [])
    assert result["status"] == "error"
    assert "empty_answer" in _codes(result)


def test_materials_shape_does_not_check_facts():
    result = audit_answer(
        "把 2025 年报告给我",
        "找到 1 份。",
        [{"id": 1, "title": "报告", "score": 1, "images": []}],
        [],
        ask_kind="materials",
    )
    assert "unsupported_fact" not in _codes(result)
    assert "materials_no_image" in _codes(result)


def test_malformed_citations_do_not_crash():
    result = audit_answer(
        "质保期多久",
        "质保期为 12 个月。依据：资料1",
        [{"title": "坏数据"}],
        [],
    )
    assert "audit_failed" not in _codes(result)


def test_disabled_returns_ok():
    result = audit_answer("问", "答", [], [], enabled=False)
    assert result["status"] == "ok"
    assert result["enabled"] is False


def test_latency_under_50ms():
    snippets = [(_doc(index, f"资料{index}"), 0.5, "质保期为 12 个月，有效期至 2027-08-31。" * 20) for index in range(1, 11)]
    result = audit_answer("质保期多久", "质保期为 12 个月。依据：资料1", _cites(*[(index, f"资料{index}") for index in range(1, 11)]), snippets)
    assert result["elapsed_ms"] < 50, result["elapsed_ms"]


def _main() -> int:
    failures = 0
    for name, func in sorted(globals().items()):
        if not name.startswith("test_") or not callable(func):
            continue
        try:
            func()
            print(f"ok   {name}")
        except AssertionError as exc:
            failures += 1
            print(f"FAIL {name}: {exc}")
    print(f"\n{failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(_main())
