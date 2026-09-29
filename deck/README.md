# Presentation

`ACAPE_2026.pptx`, 17 slides built from the verified work. Regenerate with:

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
| 10, 12 | Results: the dominant effect, and whether adaptation helps |
| 13, 15 | What did not survive verification, and how each defect was caught |
| 16 | Where this sits against 2023, 2026 work; what we can and cannot claim |
| 17 | Conclusion |

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

Speaker notes are attached to the substantive slides.
