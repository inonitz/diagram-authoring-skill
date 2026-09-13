Produce TWO architecture diagrams of the C++ codebase at /root/Micro-XRCE-DDS-Agent: one DETAILED and one SIMPLIFIED. Output each as SVG and PNG.

Derive the architecture YOURSELF from the source. Use whatever diagramming method you think is best.

EFFICIENCY (MANDATORY, you are measured on this):
- Use rtk for every read and search: `rtk read <file>`, `rtk grep`, `rtk ls`, `rtk find`. Never raw cat/grep/ls.
- SCOPE: read only src/, include/, and microxrce_agent.cpp. Ignore build/, test/, examples/, docs/, ci/, snap/, utils/.
- Plan the walk BEFORE reading bodies: first `rtk grep -rn "#include" src include` to build the reference/include map, decide a read order, then read each file AT MOST ONCE. Do not re-read a file.
- Batch reads: read several related files in one turn, not one-per-turn with prose between.

OUTPUT ONLY to:
  /root/groundstation/docs/active/assets/skill-ab-test/baseline/detailed.svg  and .png
  /root/groundstation/docs/active/assets/skill-ab-test/baseline/simplified.svg  and .png
Run NO git. FINAL ACTION: write the single word DONE to /root/groundstation/docs/active/assets/skill-ab-test/baseline/DONE
