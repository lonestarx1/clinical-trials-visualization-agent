import sys, os, json; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ctg import call, fetch_all, OUT
def show(label, s, d, rec, extra=""):
    print(f"{label:34} {s} {rec['seconds']}s {rec['bytes']}B {extra}", flush=True)

# 1. pageSize=0 with countTotal
s, d, rec = call("pagesize0", "/studies", {"query.intr": "pembrolizumab", "countTotal": "true", "pageSize": 0, "fields": "NCTId"})
show("pagesize0", s, d, rec, f"n_studies={len(d.get('studies',[]))} total={d.get('totalCount')}")

# 2. fields: piece names vs dotted paths vs search-only fields
for label, f in [("fields_pieces", "NCTId|Phase|StartDate|LeadSponsorClass|InterventionName|LocationCountry"),
                 ("fields_dotted", "protocolSection.identificationModule.nctId|protocolSection.designModule.phases"),
                 ("fields_branch", "NCTId|ArmsInterventionsModule"),
                 ("fields_searchonly", "NCTId|NumLocations|NumPhases"),
                 ("fields_bad", "NCTId|NoSuchField")]:
    s, d, rec = call(label, "/studies", {"query.intr": "pembrolizumab", "pageSize": 2, "fields": f})
    show(label, s, d, rec, json.dumps(d)[:400] if s == 200 else str(d)[:200])

# 3. order determinism: same unsorted query twice; then sorted
ids = []
for i in range(2):
    s, d, rec = call(f"order_unsorted_{i}", "/studies", {"query.cond": "alzheimer disease", "pageSize": 20, "fields": "NCTId"})
    ids.append([x["protocolSection"]["identificationModule"]["nctId"] for x in d["studies"]])
print("unsorted same order twice:", ids[0] == ids[1], ids[0][:5])
s, d, rec = call("order_sorted", "/studies", {"query.cond": "alzheimer disease", "pageSize": 5, "fields": "NCTId|StartDate", "sort": "StartDate:asc"})
show("order_sorted", s, d, rec, json.dumps(d)[:300])
s, d, rec = call("sort_text_field", "/studies", {"query.cond": "alzheimer disease", "pageSize": 2, "fields": "NCTId", "sort": "NCTId"})
show("sort_text_field", s, d, rec, str(d)[:200])

# 4. full fetch, narrow fields: pembrolizumab (query.intr)
F = "NCTId|BriefTitle|OverallStatus|StartDate|StartDateType|CompletionDate|Phase|StudyType|EnrollmentCount|EnrollmentType|LeadSponsorName|LeadSponsorClass|CollaboratorName|CollaboratorClass|InterventionType|InterventionName|InterventionOtherName|ArmGroupType|Condition|LocationCountry|LocationStatus"
import time
t = time.time()
studies, pages, tok = fetch_all("pembro_intr_full", **{"query.intr": "pembrolizumab", "fields": F})
print(f"pembro full fetch: {len(studies)} studies, {pages} pages, {time.time()-t:.1f}s wall (incl. throttle)")
