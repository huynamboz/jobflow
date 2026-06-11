# 025: the ad-hoc "match a CV" sandbox API was removed on purpose.
#
# Employee matching is DB-driven only: upload → LLM parse → Employee row saved
# → rematch_employee() reads the STORED fields (skills/position/seniority) and
# matches through match_cv_data. A parse-fresh-then-match HTTP surface invited
# confusion with that flow (two ways to "match a CV" with subtly different
# inputs), so it no longer exists. The service-layer functions remain for
# internal use (rematch pipeline, eval harnesses) — they are not exposed here.
