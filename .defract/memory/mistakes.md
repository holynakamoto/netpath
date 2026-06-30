# Mistake Patterns

## Mistakes

- [01KWDAP76RH5KQSR4Z3E9TPKGE] **- **Test isolation failure: calibrated-loss unit test also passes via rate-li...** -- - **Test isolation failure: calibrated-loss unit test also passes via rate-limit suppression** — `test_calibrated_loss_few_probes_no_alarm` (tests/test_diagnosis.py:91) passes for two independent reasons: (1) calibration raises the threshold to 5% so 3% doesn't alarm, AND (2) the clean downstream hop triggers rate-limit suppression. The test does not isolate calibration alone. **Why:** When two separate features both prevent an alarm, a single test can't distinguish which one is doing the work — if calibration regresses, the test still passes via suppression. **How to apply:** For any test that verifies a threshold or calibration feature, ensure the scenario rules out alternative passing mechanisms. Companion test: downstream hops also carry 3% loss (so rate-limit suppression can't apply) — Healthy verdict then requires calibration alone. [source: task-fixing-incomplete-paths-richer-path-01kwcya418n5, importance: 0.7]. [source: task-fixing-incomplete-paths-richer-path-01kwcya418n5, importance: 0.7]

## Anti-Patterns


