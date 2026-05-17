# Events ↔ Task Config Audit

Cross-references every YAML regressor subset against the actual
events.tsv files in both cohorts (discovery, validation).  Findings
are bucketed by severity so the production rerun does not run on
silently broken regressor definitions.

## Critical — regressor matches zero rows cohort-wide

Subset matched 0 rows across every scan in a cohort.  The regressor
is effectively absent for that cohort.

| Task | Regressor | Cohort | Scans | Total matches |
|---|---|---|---|---|
| nBack | break_with_performance_feedback | validation | 410 | 0 |

## Important — duration mismatches (YAML hardcoded ≠ observed)

Regressors where the YAML hardcodes a numeric duration but the
matched events have a different value in the duration column.
Indicates the YAML is stale relative to the task as implemented.

| Task | Regressor | Cohort | YAML duration | Observed range (min..max, median) | Total matches |
|---|---|---|---|---|---|
| cuedTS | break_with_performance_feedback | discovery | 1 | 10.00..10.00, median 10.00 | 6 |
| cuedTS | break_with_performance_feedback | validation | 1 | 10.00..10.00, median 10.00 | 94 |
| directedForgetting | break_with_performance_feedback | discovery | 1 | 10.00..10.00, median 10.00 | 4 |
| directedForgetting | break_with_performance_feedback | validation | 1 | 10.00..10.00, median 10.00 | 10 |
| flanker | break_with_performance_feedback | discovery | 1 | 10.00..10.00, median 10.00 | 8 |
| flanker | break_with_performance_feedback | validation | 1 | 10.00..10.00, median 10.00 | 42 |
| goNogo | break_with_performance_feedback | discovery | 1 | 10.00..10.00, median 10.00 | 2 |
| goNogo | break_with_performance_feedback | validation | 1 | 10.00..10.00, median 10.00 | 46 |
| nBack | break_with_performance_feedback | discovery | 1 | 10.00..10.00, median 10.00 | 2 |
| shapeMatching | break_with_performance_feedback | discovery | 1 | 10.00..10.00, median 10.00 | 6 |
| shapeMatching | break_with_performance_feedback | validation | 1 | 10.00..10.00, median 10.00 | 74 |
| spatialTS | break_with_performance_feedback | discovery | 1 | 10.00..10.00, median 10.00 | 4 |
| spatialTS | break_with_performance_feedback | validation | 1 | 10.00..10.00, median 10.00 | 140 |
| stopSignal | break_with_performance_feedback | discovery | 1 | 10.00..10.00, median 10.00 | 6 |
| stopSignal | break_with_performance_feedback | validation | 1 | 10.00..10.00, median 10.00 | 52 |

## Minor — some scans have zero matches

Regressor matches some but not all scans.  Often legitimate
(e.g. `nogo_failure` rare in good performers) but flagged for review.

| Task | Regressor | Cohort | Scans w/ zero | Total scans |
|---|---|---|---|---|
| cuedTS | break_with_performance_feedback | discovery | 44 | 48 |
| cuedTS | break_with_performance_feedback | validation | 348 | 412 |
| directedForgetting | break_with_performance_feedback | discovery | 48 | 52 |
| directedForgetting | break_with_performance_feedback | validation | 404 | 414 |
| flanker | break_with_performance_feedback | discovery | 46 | 50 |
| flanker | break_with_performance_feedback | validation | 384 | 416 |
| goNogo | nogo_failure | discovery | 8 | 46 |
| goNogo | nogo_failure | validation | 52 | 408 |
| goNogo | break_with_performance_feedback | discovery | 44 | 46 |
| goNogo | break_with_performance_feedback | validation | 372 | 408 |
| nBack | break_with_performance_feedback | discovery | 50 | 52 |
| shapeMatching | break_with_performance_feedback | discovery | 44 | 50 |
| shapeMatching | break_with_performance_feedback | validation | 356 | 408 |
| spatialTS | break_with_performance_feedback | discovery | 46 | 50 |
| spatialTS | break_with_performance_feedback | validation | 318 | 410 |
| stopSignal | break_with_performance_feedback | discovery | 44 | 50 |
| stopSignal | break_with_performance_feedback | validation | 374 | 416 |

## Trial-id values present in events but referenced by NO YAML subset

Trial_id values that appear in events.tsv but are not the literal
argument of any `trial_id == 'X'` in the YAML.  Often expected
(e.g. fixations, cues are implicit baseline) but worth eyeballing

| Task | Cohort | Unreferenced trial_ids |
|---|---|---|
| cuedTS | discovery | break, end, test_cue, test_fixation |
| cuedTS | validation | break, end, test_cue, test_fixation |
| directedForgetting | discovery | ITI_fixation, break, end, test_fixation |
| directedForgetting | validation | break, end, test_fixation |
| flanker | discovery | break, end, test_fixation |
| flanker | validation | break, end, test_fixation |
| goNogo | discovery | break, end, test_fixation |
| goNogo | validation | break, end, test_fixation |
| nBack | discovery | break, end, test_fixation |
| nBack | validation | break, end, test_fixation |
| shapeMatching | discovery | break, end, test_fixation, test_mask |
| shapeMatching | validation | break, end, test_fixation, test_mask |
| spatialTS | discovery | blank_screen, break, end, test_fixation |
| spatialTS | validation | blank_screen, break, end, test_fixation |
| stopSignal | discovery | break, end, test_fixation |
| stopSignal | validation | break, end, test_fixation |

## Trial-type values present in events but referenced by NO YAML subset

| Task | Cohort | Unreferenced trial_types |
|---|---|---|
| goNogo | discovery | unknown |
| goNogo | validation | unknown |

## Full per-regressor stats

### cuedTS

| Regressor | Cohort | Scans | Total matches | YAML dur | Obs dur (min..max, med) |
|---|---|---|---|---|---|
| task_stay_cue_stay | discovery | 48 | 2580 | 1 | 1.00..1.00, median 1.00 |
| task_stay_cue_stay | validation | 412 | 18690 | 1 | 1.00..1.00, median 1.00 |
| task_stay_cue_switch | discovery | 48 | 2304 | 1 | 1.00..1.00, median 1.00 |
| task_stay_cue_switch | validation | 412 | 18102 | 1 | 1.00..1.00, median 1.00 |
| task_switch_cue_switch | discovery | 48 | 3580 | 1 | 1.00..1.00, median 1.00 |
| task_switch_cue_switch | validation | 412 | 34756 | 1 | 1.00..1.00, median 1.00 |
| task_na_cue_na | discovery | 48 | 172 | 1 | 1.00..1.00, median 1.00 |
| task_na_cue_na | validation | 412 | 1464 | 1 | 1.00..1.00, median 1.00 |
| response_time | discovery | 48 | 8464 | response_time | 1.00..1.00, median 1.00 |
| response_time | validation | 412 | 71548 | response_time | 1.00..1.00, median 1.00 |
| omission | discovery | 48 | 28464 | duration | 0.00..10.00, median 0.15 |
| omission | validation | 412 | 244316 | duration | 0.00..10.00, median 0.15 |
| commission | discovery | 48 | 28464 | duration | 0.00..10.00, median 0.15 |
| commission | validation | 412 | 244316 | duration | 0.00..10.00, median 0.15 |
| rt_fast | discovery | 48 | 28464 | duration | 0.00..10.00, median 0.15 |
| rt_fast | validation | 412 | 244316 | duration | 0.00..10.00, median 0.15 |
| break_with_performance_feedback | discovery | 48 | 6 | 1 | 10.00..10.00, median 10.00 |
| break_with_performance_feedback | validation | 412 | 94 | 1 | 10.00..10.00, median 10.00 |

### directedForgetting

| Regressor | Cohort | Scans | Total matches | YAML dur | Obs dur (min..max, med) |
|---|---|---|---|---|---|
| con | discovery | 52 | 1152 | 1 | 1.00..1.00, median 1.00 |
| con | validation | 414 | 7992 | 1 | 1.00..1.00, median 1.00 |
| pos | discovery | 52 | 1888 | 1 | 1.00..1.00, median 1.00 |
| pos | validation | 414 | 14974 | 1 | 1.00..1.00, median 1.00 |
| neg | discovery | 52 | 896 | 1 | 1.00..1.00, median 1.00 |
| neg | validation | 414 | 7594 | 1 | 1.00..1.00, median 1.00 |
| memory_and_cue | discovery | 52 | 8320 | duration | 1.00..2.00, median 1.50 |
| memory_and_cue | validation | 414 | 66240 | duration | 1.00..2.00, median 1.50 |
| response_time | discovery | 52 | 3936 | response_time | 1.00..1.00, median 1.00 |
| response_time | validation | 414 | 30560 | response_time | 1.00..1.00, median 1.00 |
| omission | discovery | 52 | 25116 | duration | 0.00..10.00, median 1.00 |
| omission | validation | 414 | 166842 | duration | 0.00..10.00, median 1.00 |
| commission | discovery | 52 | 25116 | duration | 0.00..10.00, median 1.00 |
| commission | validation | 414 | 166842 | duration | 0.00..10.00, median 1.00 |
| rt_fast | discovery | 52 | 25116 | duration | 0.00..10.00, median 1.00 |
| rt_fast | validation | 414 | 166842 | duration | 0.00..10.00, median 1.00 |
| break_with_performance_feedback | discovery | 52 | 4 | 1 | 10.00..10.00, median 10.00 |
| break_with_performance_feedback | validation | 414 | 10 | 1 | 10.00..10.00, median 10.00 |

### flanker

| Regressor | Cohort | Scans | Total matches | YAML dur | Obs dur (min..max, med) |
|---|---|---|---|---|---|
| congruent | discovery | 50 | 3500 | 1 | 1.00..1.00, median 1.00 |
| congruent | validation | 416 | 28978 | 1 | 1.00..1.00, median 1.00 |
| incongruent | discovery | 50 | 3442 | 1 | 1.00..1.00, median 1.00 |
| incongruent | validation | 416 | 28336 | 1 | 1.00..1.00, median 1.00 |
| response_time | discovery | 50 | 6942 | response_time | 1.00..1.00, median 1.00 |
| response_time | validation | 416 | 57314 | response_time | 1.00..1.00, median 1.00 |
| omission | discovery | 50 | 14650 | duration | 0.00..10.00, median 1.00 |
| omission | validation | 416 | 121888 | duration | 0.00..10.00, median 1.00 |
| commission | discovery | 50 | 14650 | duration | 0.00..10.00, median 1.00 |
| commission | validation | 416 | 121888 | duration | 0.00..10.00, median 1.00 |
| rt_fast | discovery | 50 | 14650 | duration | 0.00..10.00, median 1.00 |
| rt_fast | validation | 416 | 121888 | duration | 0.00..10.00, median 1.00 |
| break_with_performance_feedback | discovery | 50 | 8 | 1 | 10.00..10.00, median 10.00 |
| break_with_performance_feedback | validation | 416 | 42 | 1 | 10.00..10.00, median 10.00 |

### goNogo

| Regressor | Cohort | Scans | Total matches | YAML dur | Obs dur (min..max, med) |
|---|---|---|---|---|---|
| go | discovery | 46 | 7228 | 1 | 1.00..1.00, median 1.00 |
| go | validation | 408 | 70432 | 1 | 1.00..1.00, median 1.00 |
| nogo_success | discovery | 46 | 2176 | 1 | 1.00..10.00, median 1.00 |
| nogo_success | validation | 408 | 14256 | 1 | 1.00..10.00, median 1.00 |
| nogo_failure | discovery | 46 | 142 | 1 | 1.00..1.00, median 1.00 |
| nogo_failure | validation | 408 | 1574 | 1 | 1.00..10.00, median 1.00 |
| response_time | discovery | 46 | 7228 | response_time | 1.00..1.00, median 1.00 |
| response_time | validation | 408 | 70432 | response_time | 1.00..1.00, median 1.00 |
| go_omission | discovery | 46 | 23414 | duration | 0.00..10.00, median 1.00 |
| go_omission | validation | 408 | 207672 | duration | 0.00..10.00, median 1.00 |
| go_commission | discovery | 46 | 23414 | duration | 0.00..10.00, median 1.00 |
| go_commission | validation | 408 | 207672 | duration | 0.00..10.00, median 1.00 |
| go_rt_fast | discovery | 46 | 23414 | duration | 0.00..10.00, median 1.00 |
| go_rt_fast | validation | 408 | 207672 | duration | 0.00..10.00, median 1.00 |
| break_with_performance_feedback | discovery | 46 | 2 | 1 | 10.00..10.00, median 10.00 |
| break_with_performance_feedback | validation | 408 | 46 | 1 | 10.00..10.00, median 10.00 |

### nBack

| Regressor | Cohort | Scans | Total matches | YAML dur | Obs dur (min..max, med) |
|---|---|---|---|---|---|
| mismatch_1back | discovery | 52 | 6372 | 1 | 1.00..1.00, median 1.00 |
| mismatch_1back | validation | 410 | 45510 | 1 | 1.00..1.00, median 1.00 |
| match_1back | discovery | 52 | 1670 | 1 | 1.00..1.00, median 1.00 |
| match_1back | validation | 410 | 10414 | 1 | 1.00..1.00, median 1.00 |
| mismatch_2back | discovery | 52 | 6268 | 1 | 1.00..1.00, median 1.00 |
| mismatch_2back | validation | 410 | 43880 | 1 | 1.00..1.00, median 1.00 |
| match_2back | discovery | 52 | 1490 | 1 | 1.00..1.00, median 1.00 |
| match_2back | validation | 410 | 9322 | 1 | 1.00..1.00, median 1.00 |
| response_time | discovery | 52 | 16106 | response_time | 1.00..1.00, median 1.00 |
| response_time | validation | 410 | 118624 | response_time | 1.00..1.00, median 1.00 |
| omission | discovery | 52 | 34312 | duration | 0.00..10.00, median 1.00 |
| omission | validation | 410 | 266090 | duration | 0.00..10.00, median 1.00 |
| commission | discovery | 52 | 34312 | duration | 0.00..10.00, median 1.00 |
| commission | validation | 410 | 266090 | duration | 0.00..10.00, median 1.00 |
| rt_fast | discovery | 52 | 34312 | duration | 0.00..10.00, median 1.00 |
| rt_fast | validation | 410 | 266090 | duration | 0.00..10.00, median 1.00 |
| break_with_performance_feedback | discovery | 52 | 2 | 1 | 10.00..10.00, median 10.00 |
| break_with_performance_feedback | validation | 410 | 0 | 1 | _(no matches)_ |

### shapeMatching

| Regressor | Cohort | Scans | Total matches | YAML dur | Obs dur (min..max, med) |
|---|---|---|---|---|---|
| SSS | discovery | 50 | 1080 | 1 | 1.00..1.00, median 1.00 |
| SSS | validation | 408 | 9278 | 1 | 1.00..1.00, median 1.00 |
| SDD | discovery | 50 | 1112 | 1 | 1.00..1.00, median 1.00 |
| SDD | validation | 408 | 8332 | 1 | 1.00..1.00, median 1.00 |
| SNN | discovery | 50 | 1332 | 1 | 1.00..1.00, median 1.00 |
| SNN | validation | 408 | 9298 | 1 | 1.00..1.00, median 1.00 |
| DSD | discovery | 50 | 1100 | 1 | 1.00..1.00, median 1.00 |
| DSD | validation | 408 | 9660 | 1 | 1.00..1.00, median 1.00 |
| DDD | discovery | 50 | 1092 | 1 | 1.00..1.00, median 1.00 |
| DDD | validation | 408 | 9276 | 1 | 1.00..1.00, median 1.00 |
| DDS | discovery | 50 | 1088 | 1 | 1.00..1.00, median 1.00 |
| DDS | validation | 408 | 9394 | 1 | 1.00..1.00, median 1.00 |
| DNN | discovery | 50 | 1254 | 1 | 1.00..1.00, median 1.00 |
| DNN | validation | 408 | 9506 | 1 | 1.00..1.00, median 1.00 |
| response_time | discovery | 50 | 8058 | response_time | 1.00..1.00, median 1.00 |
| response_time | validation | 408 | 64744 | response_time | 1.00..1.00, median 1.00 |
| omission | discovery | 50 | 25370 | duration | 0.00..10.00, median 0.50 |
| omission | validation | 408 | 207672 | duration | 0.00..10.00, median 0.50 |
| commission | discovery | 50 | 25370 | duration | 0.00..10.00, median 0.50 |
| commission | validation | 408 | 207672 | duration | 0.00..10.00, median 0.50 |
| rt_fast | discovery | 50 | 25370 | duration | 0.00..10.00, median 0.50 |
| rt_fast | validation | 408 | 207672 | duration | 0.00..10.00, median 0.50 |
| break_with_performance_feedback | discovery | 50 | 6 | 1 | 10.00..10.00, median 10.00 |
| break_with_performance_feedback | validation | 408 | 74 | 1 | 10.00..10.00, median 10.00 |

### spatialTS

| Regressor | Cohort | Scans | Total matches | YAML dur | Obs dur (min..max, med) |
|---|---|---|---|---|---|
| task_stay_cue_stay | discovery | 50 | 2344 | 1 | 1.00..1.00, median 1.00 |
| task_stay_cue_stay | validation | 410 | 18250 | 1 | 1.00..1.00, median 1.00 |
| task_stay_cue_switch | discovery | 50 | 2964 | 1 | 1.00..1.00, median 1.00 |
| task_stay_cue_switch | validation | 410 | 18156 | 1 | 1.00..1.00, median 1.00 |
| task_switch_cue_switch | discovery | 50 | 3570 | 1 | 1.00..1.00, median 1.00 |
| task_switch_cue_switch | validation | 410 | 33524 | 1 | 1.00..1.00, median 1.00 |
| response_time | discovery | 50 | 9044 | response_time | 1.00..1.00, median 1.00 |
| response_time | validation | 410 | 71224 | response_time | 1.00..1.00, median 1.00 |
| omission | discovery | 50 | 29650 | duration | 0.00..10.00, median 0.15 |
| omission | validation | 410 | 243130 | duration | 0.00..10.00, median 0.15 |
| commission | discovery | 50 | 29650 | duration | 0.00..10.00, median 0.15 |
| commission | validation | 410 | 243130 | duration | 0.00..10.00, median 0.15 |
| rt_fast | discovery | 50 | 29650 | duration | 0.00..10.00, median 0.15 |
| rt_fast | validation | 410 | 243130 | duration | 0.00..10.00, median 0.15 |
| break_with_performance_feedback | discovery | 50 | 4 | 1 | 10.00..10.00, median 10.00 |
| break_with_performance_feedback | validation | 410 | 140 | 1 | 10.00..10.00, median 10.00 |

### stopSignal

| Regressor | Cohort | Scans | Total matches | YAML dur | Obs dur (min..max, med) |
|---|---|---|---|---|---|
| go | discovery | 50 | 7610 | 1 | 1.00..1.00, median 1.00 |
| go | validation | 416 | 70724 | 1 | 1.00..1.00, median 1.00 |
| stop_success | discovery | 50 | 2656 | 1 | 1.00..1.00, median 1.00 |
| stop_success | validation | 416 | 18590 | 1 | 1.00..1.00, median 1.00 |
| stop_failure | discovery | 50 | 2392 | 1 | 1.00..1.00, median 1.00 |
| stop_failure | validation | 416 | 17602 | 1 | 1.00..1.00, median 1.00 |
| response_time | discovery | 50 | 7610 | response_time | 1.00..1.00, median 1.00 |
| response_time | validation | 416 | 70724 | response_time | 1.00..1.00, median 1.00 |
| go_omission | discovery | 50 | 26462 | duration | 0.00..10.00, median 1.00 |
| go_omission | validation | 416 | 221728 | duration | 0.00..10.00, median 1.00 |
| go_commission | discovery | 50 | 26462 | duration | 0.00..10.00, median 1.00 |
| go_commission | validation | 416 | 221728 | duration | 0.00..10.00, median 1.00 |
| go_rt_fast | discovery | 50 | 26462 | duration | 0.00..10.00, median 1.00 |
| go_rt_fast | validation | 416 | 221728 | duration | 0.00..10.00, median 1.00 |
| break_with_performance_feedback | discovery | 50 | 6 | 1 | 10.00..10.00, median 10.00 |
| break_with_performance_feedback | validation | 416 | 52 | 1 | 10.00..10.00, median 10.00 |

