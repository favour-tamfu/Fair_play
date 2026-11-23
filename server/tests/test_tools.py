"""server/tools: test vectors are reproducible; check_batch reports the right problems."""
import json

from server.tools import check_batch, make_test_vectors


def test_committed_vectors_equal_regenerated():
    for name, doc in make_test_vectors.build().items():
        committed = json.loads((make_test_vectors.OUT / name).read_text(encoding="utf-8"))
        assert committed == doc, f"{name} differs: re-run python -m server.tools.make_test_vectors"


def test_check_batch_reports():
    v = make_test_vectors.build()
    keys = v["tv_keys.json"]
    assert check_batch.check(v["tv_batch_valid.json"], keys) == []
    assert check_batch.check(v["tv_batch_badsig.json"], keys) == ["signature: does NOT verify with this public key"]
    probs = check_batch.check(v["tv_batch_badversion.json"], keys)
    assert probs and all("fp_version" in p for p in probs)
    other = {**v["tv_batch_valid.json"], "meter_id": "M-07"}
    assert any(p.startswith("meter:") for p in check_batch.check(other, keys))
