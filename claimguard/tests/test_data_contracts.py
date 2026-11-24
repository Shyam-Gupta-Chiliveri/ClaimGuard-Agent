import pytest

from pipeline.validate import checks

RESULTS = checks()


@pytest.mark.parametrize("name,ok,detail", RESULTS, ids=[r[0] for r in RESULTS])
def test_contract(name, ok, detail):
    assert ok, f"{name}: {detail}"
