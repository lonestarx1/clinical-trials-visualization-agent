"""Start-year slices of the whole registry (design Q22): the load pages each one on its own."""

from app.mirror.slices import YearSlice, mirror_fields, start_year, year_slices
from app.registry import BASE_FIELDS, DIMENSIONS, MEASURES


def test_slices_cover_every_start_date_once() -> None:
    slices = year_slices(now_year=2026)
    assert slices[0] == YearSlice(None, 1999)
    assert [s.lo for s in slices[1:-2]] == list(range(2000, 2029))
    assert all(s.lo == s.hi for s in slices[1:-2])
    assert slices[-2] == YearSlice(2029, None)
    assert slices[-1] == YearSlice(None, None, missing=True)


def test_each_slice_is_a_start_date_search() -> None:
    assert YearSlice(None, 1999).search().params == {
        "filter.advanced": "AREA[StartDate]RANGE[MIN,1999-12-31]"
    }
    assert YearSlice(2015, 2015).search().params == {
        "filter.advanced": "AREA[StartDate]RANGE[2015-01-01,2015-12-31]"
    }
    assert YearSlice(2029, None).search().params == {
        "filter.advanced": "AREA[StartDate]RANGE[2029-01-01,MAX]"
    }
    assert YearSlice(None, None, missing=True).search().params == {
        "filter.advanced": "AREA[StartDate]MISSING"
    }


def test_a_slice_knows_which_start_years_it_holds() -> None:
    assert YearSlice(None, 1999).holds(1980) and not YearSlice(None, 1999).holds(2000)
    assert YearSlice(2015, 2015).holds(2015) and not YearSlice(2015, 2015).holds(None)
    assert YearSlice(None, None, missing=True).holds(None)
    assert not YearSlice(None, None, missing=True).holds(2015)


def test_start_year_reads_full_and_partial_dates() -> None:
    def study(date: str | None) -> dict:
        status = {"startDateStruct": {"date": date}} if date else {}
        return {"protocolSection": {"statusModule": status}}

    assert [start_year(study(d)) for d in ("2015-03-02", "2015-03", None)] == [2015, 2015, None]


def test_the_mirror_keeps_every_field_the_registry_uses_and_the_update_date() -> None:
    fields = mirror_fields()
    used = [*BASE_FIELDS, *(f for d in DIMENSIONS.values() for f in d.fields)]
    used += [f for m in MEASURES.values() for f in m.fields]
    assert set(fields) == {*used, "LastUpdatePostDate"}
    assert len(fields) == len(set(fields))
    assert not any("mail" in f.lower() for f in fields)  # terms of use: no email addresses
