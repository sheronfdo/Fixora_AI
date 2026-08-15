"""Stage 2 tests — the LLM is mocked; we verify the code enforces every bound."""
from app.predict import llm_assess
from app.predict.llm_assess import Assessment, Factor, assess


def _baseline(confidence="High", score=80.0):
    return {"confidence": confidence, "baseline_score": score, "band": "Good", "breakdown": {}}


def _records():
    return [{"id": "r1", "severity": "Moderate", "work_performed": "x",
             "inspection_notes": "oil seep", "service_parts": []}]


def _mock(monkeypatch, assessment=None, boom=False):
    class _Structured:
        def invoke(self, _):
            if boom:
                raise RuntimeError("llm down")
            return assessment

    class _LLM:
        def with_structured_output(self, _schema):
            return _Structured()

    monkeypatch.setattr(llm_assess, "get_chat_model", lambda temperature=0.0: _LLM())


def test_condition_adjustment_clamped_to_10(monkeypatch):
    a = Assessment(condition_adjustment=-45,
                   factors=[Factor(record_id="r1", observation="seep",
                                   direction="negative", weight="moderate")])
    _mock(monkeypatch, a)
    out = assess(_baseline("High"), _records())
    assert out["condition_adjustment"] == -10.0
    assert out["llm_adjusted"] is True


def test_low_confidence_tighter_cap(monkeypatch):
    a = Assessment(condition_adjustment=-9,
                   factors=[Factor(record_id="r1", observation="x",
                                   direction="negative", weight="minor")])
    _mock(monkeypatch, a)
    out = assess(_baseline("Low"), _records())
    assert out["condition_adjustment"] == -5.0


def test_uncited_factors_discarded_zero_adjustment(monkeypatch):
    a = Assessment(condition_adjustment=-6,
                   factors=[Factor(record_id="does-not-exist", observation="x",
                                   direction="negative", weight="moderate")])
    _mock(monkeypatch, a)
    out = assess(_baseline("High"), _records())
    assert out["condition_adjustment"] == 0.0
    assert out["factors"] == []


def test_value_adjust_clamped_and_requires_citation(monkeypatch):
    a = Assessment(condition_adjustment=-3, value_adjust_pct=20,
                   factors=[Factor(record_id="r1", observation="x",
                                   direction="negative", weight="moderate")])
    _mock(monkeypatch, a)
    out = assess(_baseline("High"), _records())
    assert out["value_adjust_pct"] == 8.0  # clamped from 20

    a2 = Assessment(condition_adjustment=-3, value_adjust_pct=20, factors=[])
    _mock(monkeypatch, a2)
    out2 = assess(_baseline("High"), _records())
    assert out2["value_adjust_pct"] == 0.0  # no citation -> no value move


def test_failsafe_on_llm_error(monkeypatch):
    _mock(monkeypatch, boom=True)
    out = assess(_baseline("High"), _records())
    assert out["llm_adjusted"] is False
    assert out["condition_adjustment"] == 0.0


def test_no_records_no_call(monkeypatch):
    # Should not even reach the LLM.
    _mock(monkeypatch, boom=True)
    out = assess(_baseline("Low"), [])
    assert out["llm_adjusted"] is False
