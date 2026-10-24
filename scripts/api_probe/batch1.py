import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import json, sys
from ctg import count, call
R = {}
def c(label, **p):
    s, t, rec, data = count(label, **p)
    err = None if s == 200 else str(data)[:200]
    R[label] = {"params": p, "status": s, "total": t, "sec": rec["seconds"], "err": err}
    print(f"{label:42} {s} total={t} {rec['seconds']}s {err or ''}", flush=True)

# --- sizes for appendix-style questions
c("all_studies")
c("intr_pembrolizumab", **{"query.intr": "pembrolizumab"})
c("intr_pembrolizumab_since2015", **{"query.intr": "pembrolizumab", "filter.advanced": "AREA[StartDate]RANGE[2015-01-01,MAX]"})
c("cond_breast_cancer", **{"query.cond": "breast cancer"})
c("cond_lung_cancer", **{"query.cond": "lung cancer"})
c("cond_lung_cancer_quoted", **{"query.cond": '"lung cancer"'})
c("cond_alzheimer", **{"query.cond": "alzheimer disease"})
c("cond_diabetes_t2", **{"query.cond": "type 2 diabetes"})
c("cond_breast_recruiting", **{"query.cond": "breast cancer", "filter.overallStatus": "RECRUITING"})
c("intr_nivolumab", **{"query.intr": "nivolumab"})
# --- synonyms / precision
c("intr_keytruda", **{"query.intr": "keytruda"})
c("intr_mk3475", **{"query.intr": "MK-3475"})
c("adv_intrname_pembrolizumab", **{"filter.advanced": "AREA[InterventionName]pembrolizumab"})
c("adv_intrnamesearch_pembrolizumab", **{"filter.advanced": "AREA[InterventionNameSearch]pembrolizumab"})
c("adv_intrname_keytruda", **{"filter.advanced": "AREA[InterventionName]keytruda"})
c("adv_intrname_none_pembrolizumab", **{"filter.advanced": "EXPANSION[None]AREA[InterventionName]pembrolizumab"})
c("adv_condition_lung_cancer", **{"filter.advanced": 'AREA[Condition]"lung cancer"'})
# --- filter syntax
c("adv_startdate_range_iso", **{"filter.advanced": "AREA[StartDate]RANGE[2015-01-01,MAX]"})
c("adv_startdate_range_us", **{"filter.advanced": "AREA[StartDate]RANGE[01/01/2015,MAX]"})
c("adv_startdate_year", **{"filter.advanced": "AREA[StartDate]2022"})
c("adv_startdate_missing", **{"filter.advanced": "AREA[StartDate]MISSING"})
c("adv_phase_code", **{"filter.advanced": "AREA[Phase]PHASE3"})
c("adv_phase_label", **{"filter.advanced": 'AREA[Phase]"Phase 3"'})
c("adv_phase_missing", **{"filter.advanced": "AREA[Phase]MISSING"})
c("adv_phase_na", **{"filter.advanced": "AREA[Phase]NA"})
c("adv_phase_size2", **{"filter.advanced": "AREA[Phase:size] 2"})
c("adv_leadclass_industry", **{"filter.advanced": "AREA[LeadSponsorClass]INDUSTRY"})
c("adv_locstatus_code", **{"filter.advanced": "AREA[LocationStatus]RECRUITING"})
c("adv_locstatus_label", **{"filter.advanced": "AREA[LocationStatus]Recruiting"})
c("overall_recruiting", **{"filter.overallStatus": "RECRUITING"})
c("adv_search_location_us_recruiting", **{"filter.advanced": "SEARCH[Location](AREA[LocationCountry]United States AND AREA[LocationStatus]Recruiting)"})
c("adv_numinterventions_ge2", **{"filter.advanced": "AREA[NumInterventions]RANGE[2,MAX]"})
c("adv_studytype_obs", **{"filter.advanced": "AREA[StudyType]OBSERVATIONAL"})
c("adv_obs_phase_missing", **{"filter.advanced": "AREA[StudyType]OBSERVATIONAL AND AREA[Phase]MISSING"})
c("spons_merck", **{"query.spons": "Merck"})
c("lead_merck_full", **{"query.lead": '"Merck Sharp & Dohme LLC"'})
# --- errors
c("err_bad_advanced", **{"filter.advanced": "AREA[NoSuchField]foo"})
c("err_bad_syntax", **{"filter.advanced": "AREA[Phase](PHASE3"})
c("err_bad_status", **{"filter.overallStatus": "RUNNING"})
from ctg import OUT
json.dump(R, open(f"{OUT}/batch1_counts.json", "w"), indent=1)
