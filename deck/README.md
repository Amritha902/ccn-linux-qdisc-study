# Presentation

`ACAPE_2026.pptx`, 22 slides built from the verified work. Regenerate with:

```bash
npm install pptxgenjs     # once
node deck/build.js
```

`build.js` is the source of truth; the .pptx is generated from it, so the deck
cannot drift from what the script says.

## Structure

| Slides | Section |
|---|---|
| 1, 2 | The question: should fq_codel's four fixed parameters adapt? |
| 3, 9 | **Design rationale**, why each choice was made |
| 10, 13 | Results: the dominant effect, whether adaptation helps, and CAKE |
| 14, 17 | **The scaling law**: the governing ratio, the fit and its pre-registered tests, and the finding that the ceiling is not fixed |
| 18, 20 | What did not survive verification, and how each defect was caught |
| 21 | Where this sits against recent work |
| 22 | Conclusion |

## The scaling-law section

Added after the campaign that produced it; the earlier deck predates the law
and framed the work as a null result.

- **The governing ratio** is `target/RTT`, with the figure showing the
  measurements collapsing onto one curve under it and scattering under RTT
- **The fit and its tests**: ceiling 20.5%, half-benefit at r = 0.50, over ten
  cells, with the three pre-registered tests that held and the fourth that
  failed
- **The ceiling is not fixed**: holding r = 1 and sweeping the link rate
  25-fold moves the benefit from 7.1 to 18.2%, so the fitted ceiling belongs
  to the operating point and not the mechanism

## The design-rationale section

Each slide states the choice, then the measurement or failure that forced it:

- **Three-node topology**, the two-node alternative shapes the ACK path;
  measured 9,777 Mbps unshaped at 66 bytes/packet
- **Two latency measurements**, fq_codel privileges sparse flows by design, so
  a ping reads 22.4 ms while the bulk flows read 36.3 ms
- **Sham controller**, otherwise the controller's CPU cost and its control
  decisions are indistinguishable in any latency comparison
- **bpf(2) instead of bpftool**, 4.5× faster, and avoids introducing the very
  CPU confound the sham condition exists to remove
- **Staged workload**, a four-state classifier can only be tested by a load
  that visits more than one state
- **Goodput from sum_received, nine disciplines, exact statistics**, each
  added because its absence had already produced a wrong number

The results slides state the null honestly: the largest movement, mean
backlog, carries an interval of plus or minus 1.00 packets and covers zero,
and at three repetitions the design resolves about 3.5%, so the measurements
bound the effect rather than disprove it.

Speaker notes are attached to the substantive slides.
