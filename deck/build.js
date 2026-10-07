const pptx = require('pptxgenjs');
const P = new pptx();
P.layout = 'LAYOUT_WIDE';              // 13.3 x 7.5 in
P.author = 'Amritha S, Yugeshwaran P, Deepti Annuncia';
P.title  = 'Runtime Parameter Adaptation for fq_codel';

// Ocean Gradient palette — deep blue dominant, teal support, midnight accent
const DEEP = '065A82', TEAL = '1C7293', MID = '21295C';
const INK = '13233B', BODY = '3A4A5F', MUTE = '7B8A9C';
const PAPER = 'FFFFFF', TINT = 'EEF4F8', WARN = 'B23A48', GOOD = '2C7A5A';
const HF = 'Cambria', BF = 'Calibri';

const W = 13.3, H = 7.5, M = 0.7;

function dark(title, kicker) {
  const s = P.addSlide();
  s.background = { color: MID };
  if (kicker) s.addText(kicker, { x: M, y: 1.9, w: W - 2*M, h: 0.4,
    fontSize: 15, color: '9DB8D6', fontFace: BF, isTextBox: true, charSpacing: 2 });
  s.addText(title, { x: M, y: 2.4, w: W - 2*M, h: 1.8, fontSize: 42, bold: true,
    color: PAPER, fontFace: HF, isTextBox: true });
  return s;
}

function light(title) {
  const s = P.addSlide();
  s.background = { color: PAPER };
  s.addText(title, { x: M, y: 0.45, w: W - 2*M, h: 0.8, fontSize: 32, bold: true,
    color: INK, fontFace: HF, isTextBox: true });
  return s;
}

// card with a subtle tint, no edge stripes
function card(s, x, y, w, h, fill) {
  s.addShape(P.ShapeType.roundRect, { x, y, w, h, rectRadius: 0.08,
    fill: { color: fill || TINT }, line: { color: 'D8E4EC', width: 0.75 },
    shadow: { type: 'outer', angle: 90, offset: 1, blur: 4, color: 'BFCEDA', opacity: 0.35 } });
}

function dot(s, x, y, d, col, glyph) {
  s.addShape(P.ShapeType.ellipse, { x, y, w: d, h: d, fill: { color: col }, line: { width: 0 } });
  s.addText(glyph, { x, y, w: d, h: d, fontSize: 13, bold: true, color: PAPER,
    align: 'center', valign: 'middle', fontFace: BF, isTextBox: true, margin: 0 });
}

/* ---------------------------------------------------------------- 1 title */
{
  const s = dark('Runtime Parameter Adaptation\nfor fq_codel', 'VIT CHENNAI  ·  DEPT. OF ECE, SENSE');
  s.addText('A measured evaluation on stock Linux — and what the measurements had to survive',
    { x: M, y: 4.35, w: W - 2*M, h: 0.5, fontSize: 17, color: 'A9C3DE',
      fontFace: BF, italic: true, isTextBox: true });
  s.addText('Amritha S   ·   Yugeshwaran P   ·   Deepti Annuncia',
    { x: M, y: 5.5, w: W - 2*M, h: 0.4, fontSize: 14, color: '8FA8C4', fontFace: BF, isTextBox: true });
  s.addNotes('The deck covers what we built, why we made each design choice, what we found, and what did not survive verification.');
}

/* ------------------------------------------------------- 2 the question */
{
  const s = light('The question');
  s.addText('fq_codel is the default queue discipline on most Linux systems. Four of its parameters are fixed when you configure it and never change afterwards.',
    { x: M, y: 1.35, w: W - 2*M, h: 0.7, fontSize: 16, color: BODY, fontFace: BF, isTextBox: true });

  const ps = [['target', '5 ms', 'acceptable sojourn time'],
              ['interval', '100 ms', 'CoDel observation window'],
              ['limit', '10240 p', 'maximum queue depth'],
              ['quantum', '1514 B', 'per-flow service quantum']];
  ps.forEach((p, i) => {
    const x = M + i * 3.05;
    card(s, x, 2.25, 2.85, 1.5);
    s.addText(p[0], { x: x + 0.2, y: 2.4, w: 2.5, h: 0.35, fontSize: 15, bold: true,
      color: DEEP, fontFace: BF, isTextBox: true, margin: 0 });
    s.addText(p[1], { x: x + 0.2, y: 2.75, w: 2.5, h: 0.5, fontSize: 24, bold: true,
      color: INK, fontFace: HF, isTextBox: true, margin: 0 });
    s.addText(p[2], { x: x + 0.2, y: 3.27, w: 2.5, h: 0.4, fontSize: 11, color: MUTE,
      fontFace: BF, isTextBox: true, margin: 0 });
  });

  card(s, M, 4.25, W - 2*M, 1.5, 'E8F1F6');
  s.addText('Does adapting them at runtime beat leaving them alone?',
    { x: M + 0.35, y: 4.5, w: W - 2*M - 0.7, h: 0.5, fontSize: 24, bold: true,
      color: DEEP, fontFace: HF, isTextBox: true, margin: 0 });
  s.addText('We built the controller, built the apparatus to test it honestly, and measured. The answer matters either way.',
    { x: M + 0.35, y: 5.05, w: W - 2*M - 0.7, h: 0.5, fontSize: 14, color: BODY,
      fontFace: BF, isTextBox: true, margin: 0 });
  s.addNotes('We did not assume the adaptation would help. The design had to be able to show that it does not.');
}

/* ------------------------------------------- 3 rationale section opener */
dark('Why we chose what we chose', 'DESIGN RATIONALE')
  .addText('Every choice below was forced by something that went wrong, or by something that could go wrong undetected.',
    { x: M, y: 4.3, w: W - 2*M, h: 0.6, fontSize: 16, color: 'A9C3DE', fontFace: BF, italic: true, isTextBox: true });

/* --------------------------------------------- 4 choice: 3-node topology */
{
  const s = light('Why a three-node topology, not two');
  s.addText('CHOICE  ·  client → router → server, with the AQM on the router\'s egress',
    { x: M, y: 1.2, w: W - 2*M, h: 0.4, fontSize: 14, bold: true, color: DEEP,
      fontFace: BF, isTextBox: true, charSpacing: 1 });

  card(s, M, 1.75, 6.0, 3.6, 'FBEEF0');
  s.addText('The two-node setup', { x: M + 0.3, y: 1.95, w: 5.4, h: 0.4, fontSize: 17,
    bold: true, color: WARN, fontFace: HF, isTextBox: true, margin: 0 });
  s.addText([
    { text: 'Bottleneck on veth1 inside ns1; iperf3 runs from ns2.', options: { breakLine: true } },
    { text: 'Data flows ns2 → ns1, but an egress qdisc on veth1 shapes ns1 → ns2.', options: { breakLine: true } },
    { text: 'So it shapes the ACK path, not the data path.', options: { bold: true } },
  ], { x: M + 0.3, y: 2.4, w: 5.4, h: 1.2, fontSize: 13, color: BODY, fontFace: BF,
       isTextBox: true, margin: 0, lineSpacing: 18 });
  s.addText([
    { text: 'Measured:  9,777 Mbps unshaped', options: { breakLine: true, bold: true } },
    { text: '66 bytes/packet — pure TCP ACKs', options: { breakLine: true } },
    { text: '~130,000 drops/s on an 826 pkt/s link', options: {} },
  ], { x: M + 0.3, y: 3.75, w: 5.4, h: 1.3, fontSize: 13, color: WARN, fontFace: BF,
       isTextBox: true, margin: 0, lineSpacing: 18 });

  card(s, 6.9, 1.75, 5.7, 3.6, 'EAF4EE');
  s.addText('The three-node router', { x: 7.2, y: 1.95, w: 5.1, h: 0.4, fontSize: 17,
    bold: true, color: GOOD, fontFace: HF, isTextBox: true, margin: 0 });
  s.addText([
    { text: 'TBF + AQM on the router\'s egress toward the server.', options: { breakLine: true } },
    { text: 'Data traverses it, so the bottleneck is on the data path.', options: { bold: true } },
  ], { x: 7.2, y: 2.4, w: 5.1, h: 1.2, fontSize: 13, color: BODY, fontFace: BF,
       isTextBox: true, margin: 0, lineSpacing: 18 });
  s.addText([
    { text: 'Measured:  9.38 Mbps shaped', options: { breakLine: true, bold: true } },
    { text: '1509 bytes/packet — real data', options: { breakLine: true } },
    { text: '~19 drops/s — physically plausible', options: {} },
  ], { x: 7.2, y: 3.75, w: 5.1, h: 1.3, fontSize: 13, color: GOOD, fontFace: BF,
       isTextBox: true, margin: 0, lineSpacing: 18 });

  s.addText('Diagnostic worth keeping: bytes ÷ packets on the monitored queue. 66 means you are queueing acknowledgements.',
    { x: M, y: 5.65, w: W - 2*M, h: 0.5, fontSize: 14, italic: true, color: INK,
      fontFace: BF, isTextBox: true });
  s.addNotes('This single error invalidated every queueing result in the original Parts 2 to 4.');
}

/* ------------------------------------------ 5 choice: latency measurement */
{
  const s = light('Why we measure latency two different ways');
  s.addText('CHOICE  ·  a 20 Hz sparse probe AND in-band bulk-flow RTT from TCP_INFO',
    { x: M, y: 1.15, w: W - 2*M, h: 0.38, fontSize: 14, bold: true, color: DEEP,
      fontFace: BF, isTextBox: true, charSpacing: 1 });
  s.addText('fq_codel\'s new-flow heuristic deliberately privileges sparse flows. A ping is a sparse flow, so it measures the best case — not what the bulk traffic sees.',
    { x: M, y: 1.58, w: W - 2*M, h: 0.5, fontSize: 14.5, color: BODY, fontFace: BF, isTextBox: true });

  const hdr = ['Discipline', 'Sparse probe', 'Bulk flows', 'Ratio'];
  const rows = [['SFQ  (fair queueing, no AQM)', '30.7 ms', '294.3 ms', '9.6x', WARN],
                ['FQ-PIE', '22.0 ms', '55.2 ms', '2.5x', BODY],
                ['fq_codel', '22.4 ms', '36.4 ms', '1.6x', BODY],
                ['CAKE', '21.8 ms', '33.6 ms', '1.5x', BODY],
                ['CoDel  (single queue)', '39.2 ms', '44.4 ms', '1.1x', GOOD]];
  const cx = [M + 0.3, M + 5.3, M + 7.5, M + 9.8];
  hdr.forEach((h, j) => s.addText(h, { x: cx[j], y: 2.18, w: 2.3, h: 0.3, fontSize: 11.5,
    bold: true, color: MUTE, fontFace: BF, isTextBox: true, margin: 0, charSpacing: 1 }));
  rows.forEach((r, i) => {
    const y = 2.52 + i * 0.6;
    s.addShape(P.ShapeType.roundRect, { x: M, y, w: W - 2*M, h: 0.52, rectRadius: 0.05,
      fill: { color: i === 0 ? 'FBEEF0' : (i % 2 ? 'F6FAFC' : TINT) },
      line: { color: 'E2ECF2', width: 0.5 } });
    s.addText(r[0], { x: cx[0], y: y + 0.11, w: 4.9, h: 0.32, fontSize: 13,
      bold: i === 0, color: INK, fontFace: BF, isTextBox: true, margin: 0 });
    s.addText(r[1], { x: cx[1], y: y + 0.09, w: 2.0, h: 0.36, fontSize: 14, color: TEAL,
      fontFace: HF, isTextBox: true, margin: 0 });
    s.addText(r[2], { x: cx[2], y: y + 0.09, w: 2.0, h: 0.36, fontSize: 14, bold: true,
      color: r[4], fontFace: HF, isTextBox: true, margin: 0 });
    s.addText(r[3], { x: cx[3], y: y + 0.11, w: 1.6, h: 0.32, fontSize: 13, bold: true,
      color: r[4], fontFace: BF, isTextBox: true, margin: 0 });
  });

  card(s, M, 5.65, W - 2*M, 1.25, 'E8F1F6');
  s.addText('Quoting only the probe inverts the ranking.',
    { x: M + 0.35, y: 5.82, w: W - 2*M - 0.7, h: 0.38, fontSize: 17, bold: true,
      color: DEEP, fontFace: HF, isTextBox: true, margin: 0 });
  s.addText('By probe RTT, SFQ (30.7 ms) beats CoDel (39.2 ms). By what the data flows actually experience, SFQ is 294 ms against CoDel\'s 44 ms — nearly 7x worse. SFQ gives the probe its own short queue but has no AQM, so the bulk queues sit at its 127-packet limit throughout.',
    { x: M + 0.35, y: 6.2, w: W - 2*M - 0.7, h: 0.65, fontSize: 12.5, color: BODY,
      fontFace: BF, isTextBox: true, margin: 0 });
  s.addNotes('The probe-to-bulk ratio is a discipline signature. Any AQM paper quoting a single ping number may be ranking systems backwards.');
}

/* ----------------------------------------------- 6 choice: sham control */
{
  const s = light('Why we run a controller that does nothing');
  s.addText('CHOICE  ·  a sham condition — the controller polls at the same cadence but applies no change',
    { x: M, y: 1.2, w: W - 2*M, h: 0.4, fontSize: 14, bold: true, color: DEEP,
      fontFace: BF, isTextBox: true, charSpacing: 1 });
  s.addText('The controller is an extra process polling every 500 ms. In a 2-vCPU emulated VM that alone can add latency. Without a control condition, "the controller made it slower" and "the controller\'s decisions made it slower" are indistinguishable.',
    { x: M, y: 1.7, w: W - 2*M, h: 0.85, fontSize: 15, color: BODY, fontFace: BF, isTextBox: true });

  const cols = [['static fq_codel', 'no controller at all', 'baseline', MUTE],
                ['+ sham controller', 'polls, changes nothing', 'isolates CPU cost', TEAL],
                ['+ ACAPE', 'polls and adapts', 'isolates the decisions', DEEP]];
  cols.forEach((c, i) => {
    const x = M + i * 4.05;
    card(s, x, 2.75, 3.75, 2.1);
    dot(s, x + 0.3, 2.98, 0.42, c[3], String(i + 1));
    s.addText(c[0], { x: x + 0.85, y: 3.0, w: 2.7, h: 0.4, fontSize: 15, bold: true,
      color: INK, fontFace: BF, isTextBox: true, margin: 0 });
    s.addText(c[1], { x: x + 0.3, y: 3.55, w: 3.15, h: 0.4, fontSize: 13, color: BODY,
      fontFace: BF, isTextBox: true, margin: 0 });
    s.addText(c[2], { x: x + 0.3, y: 4.05, w: 3.15, h: 0.6, fontSize: 13, bold: true,
      color: c[3], fontFace: BF, isTextBox: true, margin: 0 });
  });

  s.addText('No published adaptive-AQM paper we found runs this control. It is the reason our null result is credible rather than merely unexplained.',
    { x: M, y: 5.3, w: W - 2*M, h: 0.6, fontSize: 15, italic: true, color: INK,
      fontFace: BF, isTextBox: true });
  s.addNotes('This is the strongest methodological contribution in the work.');
}



/* ------------------------------------------------ 7 choice: eBPF via bpf(2) */
{
  const s = light('Why we read BPF maps with bpf(2), not bpftool');
  s.addText('CHOICE  ·  in-process syscalls instead of spawning a helper each tick',
    { x: M, y: 1.2, w: W - 2*M, h: 0.4, fontSize: 14, bold: true, color: DEEP,
      fontFace: BF, isTextBox: true, charSpacing: 1 });

  card(s, M, 1.8, 5.85, 2.5, 'FBEEF0');
  s.addText('bpftool per tick', { x: M + 0.3, y: 2.0, w: 5.2, h: 0.4, fontSize: 16,
    bold: true, color: WARN, fontFace: HF, isTextBox: true, margin: 0 });
  s.addText([
    { text: '~2.5 s per call under a 9p root', options: { breakLine: true } },
    { text: 'stretched the 0.5 s control interval to 3.17 s', options: { breakLine: true } },
    { text: 'a 20 s run yielded only 7 samples', options: {} },
  ], { x: M + 0.3, y: 2.5, w: 5.2, h: 1.6, fontSize: 13, color: BODY, fontFace: BF,
       isTextBox: true, margin: 0, lineSpacing: 19 });

  card(s, 6.85, 1.8, 5.75, 2.5, 'EAF4EE');
  s.addText('bpf(2) in process', { x: 7.15, y: 2.0, w: 5.1, h: 0.4, fontSize: 16,
    bold: true, color: GOOD, fontFace: HF, isTextBox: true, margin: 0 });
  s.addText([
    { text: 'tick restored to 0.709 s — 4.5× faster', options: { breakLine: true } },
    { text: 'no extra process, so no CPU confound', options: { breakLine: true } },
    { text: 'raw bytes, so no hex-string decode bug', options: {} },
  ], { x: 7.15, y: 2.5, w: 5.1, h: 1.6, fontSize: 13, color: BODY, fontFace: BF,
       isTextBox: true, margin: 0, lineSpacing: 19 });

  card(s, M, 4.6, W - 2*M, 1.5, 'E8F1F6');
  s.addText('The second reason matters more than the first.',
    { x: M + 0.35, y: 4.8, w: W - 2*M - 0.7, h: 0.4, fontSize: 16, bold: true,
      color: DEEP, fontFace: BF, isTextBox: true, margin: 0 });
  s.addText('Spawning a helper process to measure a system whose latency you are measuring is the same confound the sham condition exists to remove. Reading the map in process avoids introducing it at all.',
    { x: M + 0.35, y: 5.2, w: W - 2*M - 0.7, h: 0.7, fontSize: 14, color: BODY,
      fontFace: BF, isTextBox: true, margin: 0 });
  s.addNotes('bpftool JSON also renders byte arrays as hex strings, which is what silently zeroed the original telemetry.');
}

/* ------------------------------------------- 8 choice: staged workload */
{
  const s = light('Why the workload changes during the run');
  s.addText('CHOICE  ·  a staged load — 2 flows, then 24, then back to 2',
    { x: M, y: 1.2, w: W - 2*M, h: 0.4, fontSize: 14, bold: true, color: DEEP,
      fontFace: BF, isTextBox: true, charSpacing: 1 });
  s.addText('A controller that classifies congestion into four states can only be tested by a workload that visits more than one of them.',
    { x: M, y: 1.7, w: W - 2*M, h: 0.5, fontSize: 15, color: BODY, fontFace: BF, isTextBox: true });

  card(s, M, 2.4, 5.85, 2.3, 'FBEEF0');
  s.addText('Constant overload (original)', { x: M + 0.3, y: 2.6, w: 5.2, h: 0.4,
    fontSize: 16, bold: true, color: WARN, fontFace: HF, isTextBox: true, margin: 0 });
  s.addText([
    { text: 'HEAVY in 80.9% of samples', options: { breakLine: true } },
    { text: 'MODERATE in 0.04%, LIGHT never', options: { breakLine: true } },
    { text: 'A four-state classifier using two states', options: { bold: true } },
  ], { x: M + 0.3, y: 3.1, w: 5.2, h: 1.4, fontSize: 13, color: BODY, fontFace: BF,
       isTextBox: true, margin: 0, lineSpacing: 19 });

  card(s, 6.85, 2.4, 5.75, 2.3, 'EAF4EE');
  s.addText('Staged load (ours)', { x: 7.15, y: 2.6, w: 5.1, h: 0.4, fontSize: 16,
    bold: true, color: GOOD, fontFace: HF, isTextBox: true, margin: 0 });
  s.addText([
    { text: 'Flow count changes twice during the run', options: { breakLine: true } },
    { text: 'The regime actually transitions', options: { breakLine: true } },
    { text: 'The adaptive logic is exercised, not just saturated', options: {} },
  ], { x: 7.15, y: 3.1, w: 5.1, h: 1.4, fontSize: 13, color: BODY, fontFace: BF,
       isTextBox: true, margin: 0, lineSpacing: 19 });

  s.addText('Under constant overload the original controller ratcheted target to its floor every run and stopped — always exactly 15 adjustments, which is just the number of ×0.9 steps from 5 ms to 1 ms. That is a constant, not a measurement.',
    { x: M, y: 5.0, w: W - 2*M, h: 0.9, fontSize: 14, italic: true, color: INK,
      fontFace: BF, isTextBox: true });
  s.addNotes('15 = ceil(log(1/5)/log(0.9)). It appeared in 24 of 32 runs.');
}

/* ---------------------------------------- 9 choice: metrics and baselines */
{
  const s = light('Why these metrics and these baselines');
  const items = [
    ['Goodput from sum_received', 'iperf3\'s sum_sent counts bytes handed to the socket. Under pfifo it read 12.16 Mbps on a 10 Mbit link — the sender filling a bloated buffer. Only sum_received crossed the bottleneck.', DEEP],
    ['Nine queue disciplines', 'pfifo, SFQ, RED, CoDel, PIE, FQ-PIE, CAKE, fq_codel, fq_codel+ACAPE. A comparison that omits the obvious alternatives is not a comparison — and PIE and CAKE are genuinely competitive.', TEAL],
    ['Three repetitions, exact statistics', 'Confidence intervals from Student\'s t via the incomplete beta function, not a normal approximation — which at n=3 overstates significance and flipped one of our own conclusions.', MID],
  ];
  items.forEach((it, i) => {
    const y = 1.35 + i * 1.62;
    card(s, M, y, W - 2*M, 1.42);
    dot(s, M + 0.32, y + 0.32, 0.5, it[2], String(i + 1));
    s.addText(it[0], { x: M + 1.0, y: y + 0.18, w: 10.8, h: 0.4, fontSize: 16, bold: true,
      color: INK, fontFace: BF, isTextBox: true, margin: 0 });
    s.addText(it[1], { x: M + 1.0, y: y + 0.6, w: 10.8, h: 0.75, fontSize: 13, color: BODY,
      fontFace: BF, isTextBox: true, margin: 0 });
  });
  s.addText('Each of these was added because its absence had already produced a wrong number.',
    { x: M, y: 6.3, w: W - 2*M, h: 0.4, fontSize: 14, italic: true, color: MUTE,
      fontFace: BF, isTextBox: true });
}

/* ------------------------------------------------------ 10 results opener */
dark('What the measurements show', 'RESULTS')
  .addText('Stock Linux · 10 Mbit bottleneck · 8 TCP CUBIC flows · 20 ms base RTT · 3 repetitions',
    { x: M, y: 4.3, w: W - 2*M, h: 0.6, fontSize: 16, color: 'A9C3DE', fontFace: BF, italic: true, isTextBox: true });

/* --------------------------------------------- 11 the dominant effect */
{
  const s = light('The effect that dominates everything');
  s.addText('Presence or absence of a flow-queueing AQM — not the tuning of one',
    { x: M, y: 1.2, w: W - 2*M, h: 0.4, fontSize: 15, color: BODY, fontFace: BF, isTextBox: true });

  const stats = [['2371 ms', 'p95 RTT\npfifo, no AQM', WARN],
                 ['25 ms', 'p95 RTT\nfq_codel', GOOD],
                 ['~100×', 'latency reduction', DEEP],
                 ['0%', 'goodput cost', MID]];
  stats.forEach((st, i) => {
    const x = M + i * 3.05;
    card(s, x, 1.95, 2.85, 2.0);
    s.addText(st[0], { x: x + 0.15, y: 2.25, w: 2.55, h: 0.75, fontSize: 34, bold: true,
      color: st[2], align: 'center', fontFace: HF, isTextBox: true, margin: 0 });
    s.addText(st[1], { x: x + 0.15, y: 3.05, w: 2.55, h: 0.7, fontSize: 12, color: MUTE,
      align: 'center', fontFace: BF, isTextBox: true, margin: 0 });
  });

  card(s, M, 4.25, W - 2*M, 1.85, 'E8F1F6');
  s.addText('Two orders of magnitude, at no throughput or fairness cost.',
    { x: M + 0.35, y: 4.45, w: W - 2*M - 0.7, h: 0.45, fontSize: 19, bold: true,
      color: DEEP, fontFace: HF, isTextBox: true, margin: 0 });
  s.addText('Every flow-queueing discipline with a delay target — fq_codel, FQ-PIE, CAKE — lands near 23 ms. Single-queue AQMs (CoDel, PIE) land near 45 ms. SFQ, which has fair queueing but no AQM, bloats to 115 packets. The AQM and the scheduler each do a distinct job, and both matter far more than parameter choice.',
    { x: M + 0.35, y: 4.95, w: W - 2*M - 0.7, h: 1.0, fontSize: 14, color: BODY,
      fontFace: BF, isTextBox: true, margin: 0 });
  s.addNotes('This is the clean, defensible, reproducible result of the study.');
}

/* ------------------------------------------ 12 does adaptation help? */
{
  const s = light('Does adapting the parameters help?');
  card(s, M, 1.2, W - 2*M, 0.95, 'E8F1F6');
  s.addText('Nothing separates from zero, under either load.',
    { x: M + 0.35, y: 1.4, w: W - 2*M - 0.7, h: 0.55, fontSize: 18, bold: true,
      color: DEEP, fontFace: HF, isTextBox: true, margin: 0 });

  const hdr = ['Metric', 'Steady workload', 'Staged workload'];
  const cx = [M + 0.3, M + 5.0, M + 8.9];
  hdr.forEach((h, j) => s.addText(h, { x: cx[j], y: 2.3, w: 3.6, h: 0.3, fontSize: 11.5,
    bold: true, color: MUTE, fontFace: BF, isTextBox: true, margin: 0, charSpacing: 1 }));

  const rows = [
    ['Mean backlog',      '-9.6%  CI +-1.00 pkt', MUTE, '+2.2%   n.s.', MUTE],
    ['p95 RTT (probe)',   '-0.5%  n.s.',          MUTE, '+3.2%   n.s.', MUTE],
    ['Mean RTT (probe)',  '+0.4%  n.s.',          MUTE, '+1.6%   n.s.', MUTE],
    ['Mean RTT (bulk)',   '-1.4%  n.s.',          MUTE, '-0.5%   n.s.', MUTE],
    ['Goodput / fairness','unchanged',            MUTE, 'unchanged',    MUTE],
  ];
  rows.forEach((r, i) => {
    const y = 2.65 + i * 0.62;
    s.addShape(P.ShapeType.roundRect, { x: M, y, w: W - 2*M, h: 0.54, rectRadius: 0.05,
      fill: { color: i % 2 ? 'F6FAFC' : TINT }, line: { color: 'E2ECF2', width: 0.5 } });
    s.addText(r[0], { x: cx[0], y: y + 0.13, w: 4.4, h: 0.32, fontSize: 13.5, bold: true,
      color: INK, fontFace: BF, isTextBox: true, margin: 0 });
    s.addText(r[1], { x: cx[1], y: y + 0.13, w: 3.6, h: 0.32, fontSize: 13, bold: true,
      color: r[2], fontFace: BF, isTextBox: true, margin: 0 });
    s.addText(r[3], { x: cx[2], y: y + 0.13, w: 3.6, h: 0.32, fontSize: 13, bold: true,
      color: r[4], fontFace: BF, isTextBox: true, margin: 0 });
  });

  s.addText('The largest movement, backlog, has an interval of +-1.00 packets and covers zero. At three repetitions the design resolves about 3.5%, so these bound the effect rather than disprove it. The sham arm shows the controller\'s processor cost is not detectable either, so this is not a cost masking a benefit. The law explains it: these runs sit at r = 0.25.',
    { x: M, y: 5.85, w: W - 2*M, h: 0.6, fontSize: 13, italic: true, color: INK,
      fontFace: BF, isTextBox: true });
  s.addNotes('Steady load has a stable operating point to converge on; staged load does not, and the adjustments lag the transitions.');
}

/* -------------------------------------- 12b an off-the-shelf alternative wins */
{
  const s = light('CAKE beats the adapted system');
  s.addText('No controller. One configuration argument. Lower latency than tuned fq_codel.',
    { x: M, y: 1.2, w: W - 2*M, h: 0.4, fontSize: 15, color: BODY, fontFace: BF, isTextBox: true });

  const cmp = [['fq_codel (static)', '24.6 ms', '36.4 ms', MUTE],
               ['fq_codel + ACAPE', '24.4 ms', '35.9 ms', TEAL],
               ['CAKE', '22.9 ms', '33.6 ms', GOOD]];
  s.addText('p95 probe RTT', { x: M + 5.3, y: 1.75, w: 3.0, h: 0.3, fontSize: 11.5, bold: true,
    color: MUTE, fontFace: BF, isTextBox: true, margin: 0, charSpacing: 1 });
  s.addText('mean bulk RTT', { x: M + 8.5, y: 1.75, w: 3.0, h: 0.3, fontSize: 11.5, bold: true,
    color: MUTE, fontFace: BF, isTextBox: true, margin: 0, charSpacing: 1 });
  cmp.forEach((c, i) => {
    const y = 2.1 + i * 0.85;
    card(s, M, y, W - 2*M, 0.72, i === 2 ? 'EAF4EE' : TINT);
    s.addText(c[0], { x: M + 0.35, y: y + 0.2, w: 4.7, h: 0.35, fontSize: 15,
      bold: i === 2, color: INK, fontFace: BF, isTextBox: true, margin: 0 });
    s.addText(c[1], { x: M + 5.3, y: y + 0.15, w: 3.0, h: 0.42, fontSize: 19, bold: true,
      color: c[3], fontFace: HF, isTextBox: true, margin: 0 });
    s.addText(c[2], { x: M + 8.5, y: y + 0.15, w: 3.0, h: 0.42, fontSize: 19, bold: true,
      color: c[3], fontFace: HF, isTextBox: true, margin: 0 });
  });

  card(s, M, 4.75, W - 2*M, 1.35, 'E8F1F6');
  s.addText('CAKE beats the adapted system by more than the adaptation beats the defaults  (p < 0.001).',
    { x: M + 0.35, y: 4.95, w: W - 2*M - 0.7, h: 0.4, fontSize: 16, bold: true,
      color: DEEP, fontFace: BF, isTextBox: true, margin: 0 });
  s.addText('For a practitioner wanting lower latency on this class of link, changing queue discipline is a larger and far simpler win than tuning fq_codel\'s parameters. We report this because it is the most useful thing a reader can take away.',
    { x: M + 0.35, y: 5.35, w: W - 2*M - 0.7, h: 0.65, fontSize: 13, color: BODY,
      fontFace: BF, isTextBox: true, margin: 0 });
}

/* ------------------------------------------------- 13a the law opener */
dark('When does adapting pay?', 'THE SCALING LAW');

/* --------------------------------------------- 13b the governing ratio */
{
  const s = light('The answer is a ratio, not a delay');
  s.addText('Sweeping path RTT from 2 to 200 ms showed the benefit is not a function of RTT at all.',
    { x: M, y: 1.2, w: W - 2*M, h: 0.4, fontSize: 15, color: BODY, fontFace: BF, isTextBox: true });

  card(s, M, 1.75, W - 2*M, 1.15, 'E8F1F6');
  s.addText('r  =  target / RTT', { x: M + 0.35, y: 1.95, w: 4.2, h: 0.75,
    fontSize: 30, bold: true, color: DEEP, fontFace: HF, isTextBox: true, margin: 0 });
  s.addText('A dimensionless number an operator already has: the configured target, and an estimate of the path.',
    { x: M + 5.0, y: 2.05, w: 6.6, h: 0.7, fontSize: 13.5, color: BODY,
      fontFace: BF, isTextBox: true, margin: 0 });

  s.addImage({ path: 'figures/comparison/fig16_scaling_law.png',
               x: M, y: 3.05, w: W - 2*M, h: 3.4, sizing: { type: 'contain', w: W - 2*M, h: 3.4 } });
  s.addText('Left: benefit against the ratio, collapsing onto one curve. Right: the same runs against RTT alone, scattered.',
    { x: M, y: 6.55, w: W - 2*M, h: 0.4, fontSize: 12, color: MUTE, fontFace: BF, isTextBox: true });
  s.addNotes('This is the contribution. The mechanism is old; the number at which it starts to matter is what was missing.');
}

/* ------------------------------------------------ 13c the law and its test */
{
  const s = light('b(r) = B / (1 + (r0/r)^k)');
  const stats = [
    ['B  =  20.5 %', 'the ceiling'],
    ['r0  =  0.50', 'half the benefit is reached here'],
    ['k  =  2.6', 'how sharp the transition is'],
    ['R2  =  0.986', 'over 10 cells'],
  ];
  stats.forEach((t, i) => {
    const x = M + (i % 2) * 6.1, y = 1.25 + Math.floor(i / 2) * 1.05;
    card(s, x, y, 5.8, 0.9);
    s.addText(t[0], { x: x + 0.3, y: y + 0.1, w: 3.0, h: 0.4, fontSize: 19, bold: true,
      color: DEEP, fontFace: HF, isTextBox: true, margin: 0 });
    s.addText(t[1], { x: x + 0.3, y: y + 0.52, w: 5.2, h: 0.3, fontSize: 12,
      color: BODY, fontFace: BF, isTextBox: true, margin: 0 });
  });

  card(s, M, 3.5, W - 2*M, 1.5, 'E8F1F6');
  s.addText('Registered before the data existed. Three of four held.',
    { x: M + 0.35, y: 3.68, w: 11.5, h: 0.35, fontSize: 14, bold: true, color: DEEP,
      fontFace: BF, isTextBox: true, margin: 0, charSpacing: 1 });
  s.addText('A crossover exists. The curve is invariant across a 16-fold change in RTT, 2.0 points against a 5-point threshold. Leave-one-out predicts held-out cells to 1.4 points. The form transfers to codel and PIE; the constant does not, and that fourth test failed.',
    { x: M + 0.35, y: 4.05, w: 11.5, h: 0.85, fontSize: 13, color: BODY,
      fontFace: BF, isTextBox: true, margin: 0 });

  card(s, M, 5.25, W - 2*M, 1.35, 'FBEEF0');
  s.addText('What it means', { x: M + 0.35, y: 5.42, w: 11.5, h: 0.32, fontSize: 13,
    bold: true, color: WARN, fontFace: BF, isTextBox: true, margin: 0, charSpacing: 1 });
  s.addText('Correct configuration sits at r between 0.05 and 0.10. Half the available benefit arrives only at r = 0.50, five to ten times outside that. Adaptation repairs misconfiguration; it does not improve a correctly configured link.',
    { x: M + 0.35, y: 5.78, w: 11.5, h: 0.75, fontSize: 13.5, color: INK,
      fontFace: BF, isTextBox: true, margin: 0 });
}

/* ------------------------------------------ 13d the ceiling is not fixed */
{
  const s = light('The ratio fixes the shape, not the ceiling');
  s.addText('Holding r = 1 and sweeping the link rate 25-fold. Only the rate changes.',
    { x: M, y: 1.2, w: W - 2*M, h: 0.4, fontSize: 15, color: BODY, fontFace: BF, isTextBox: true });

  const hdr = ['Link rate', 'Benefit at r = 1', 'p'];
  const cx = [M + 0.3, M + 4.6, M + 8.8];
  hdr.forEach((h, j) => s.addText(h, { x: cx[j], y: 1.8, w: 3.6, h: 0.3, fontSize: 11.5,
    bold: true, color: MUTE, fontFace: BF, isTextBox: true, margin: 0, charSpacing: 1 }));

  const rows = [['2 Mbit/s', '+13.2 %', '0.0005'], ['5 Mbit/s', '+18.2 %', '< 0.0001'],
                ['10 Mbit/s', '+18.0 %', '< 0.0001'], ['20 Mbit/s', '+14.1 %', '0.0004'],
                ['50 Mbit/s', '+7.1 %', '0.0172']];
  rows.forEach((r, i) => {
    const y = 2.15 + i * 0.6;
    s.addShape(P.ShapeType.roundRect, { x: M, y, w: W - 2*M, h: 0.52, rectRadius: 0.05,
      fill: { color: i % 2 ? 'F6FAFC' : TINT }, line: { color: 'E2ECF2', width: 0.5 } });
    r.forEach((v, j) => s.addText(v, { x: cx[j], y: y + 0.12, w: 4.0, h: 0.32,
      fontSize: 13.5, bold: j < 2, color: j === 0 ? INK : (j === 1 ? GOOD : BODY),
      fontFace: BF, isTextBox: true, margin: 0 }));
  });

  card(s, M, 5.3, W - 2*M, 1.4, 'E8F1F6');
  s.addText('An 11-point spread, against the 5-point threshold we used to call the RTT comparison consistent. Every cell is significant, so this is real. The fitted ceiling of 20.5 % is the ceiling at 10 Mbit/s, not a constant of the mechanism.',
    { x: M + 0.35, y: 5.5, w: 11.5, h: 1.0, fontSize: 14, color: INK,
      fontFace: BF, isTextBox: true, margin: 0 });
  s.addNotes('We had this data and had not looked. A referee would have asked. r governs the RTT dimension; a second group governs the ceiling.');
}

/* --------------------------------------------------- 13 verification opener */
dark('What did not survive verification', 'INTEGRITY')
  .addText('Seven classes of silent failure. Each produced results that were confident, internally consistent, and wrong.',
    { x: M, y: 4.3, w: W - 2*M, h: 0.7, fontSize: 16, color: 'A9C3DE', fontFace: BF, italic: true, isTextBox: true });

/* ------------------------------------------------------- 14 the defects */
{
  const s = light('The seven defects');
  const d = [
    ['Loopback traffic', 'Parts 1–3 ran iperf3 to 127.0.0.1 at 93–219 Gbit/s. No qdisc was ever in the path.'],
    ['ACK-path bottleneck', 'Parts 2–4 shaped the acknowledgement direction. 66 bytes/packet.'],
    ['No RTT ever measured', 'The reported 0.541 / 2.200 / 2.445 ms have no source anywhere in the repository.'],
    ['eBPF telemetry read zero', 'Three decode bugs: hex strings into a bare except, wrong struct offsets, CLOCK_REALTIME vs CLOCK_MONOTONIC (age = 56.8 years).'],
    ['Elephant threshold unreachable', '10 MB threshold, 9.38 MB maximum possible flow share. The classifier could never fire.'],
    ['Prediction had no effect', 'All 375 logged adjustments applied the identical action.'],
    ['Headline figures hardcoded', '"12× faster" is the literal array [120, 70, 60, 5]. No stabilisation time was ever measured.'],
  ];
  d.forEach((it, i) => {
    const col = i % 2, row = Math.floor(i / 2);
    const x = M + col * 6.1, y = 1.25 + row * 1.16;
    if (i === 6) {
      card(s, M, y, W - 2*M, 1.02, 'FBEEF0');
      dot(s, M + 0.28, y + 0.27, 0.46, WARN, String(i + 1));
      s.addText(it[0], { x: M + 0.92, y: y + 0.1, w: 10.9, h: 0.33, fontSize: 14, bold: true,
        color: WARN, fontFace: BF, isTextBox: true, margin: 0 });
      s.addText(it[1], { x: M + 0.92, y: y + 0.44, w: 10.9, h: 0.5, fontSize: 12, color: BODY,
        fontFace: BF, isTextBox: true, margin: 0 });
    } else {
      card(s, x, y, 5.85, 1.02);
      dot(s, x + 0.25, y + 0.27, 0.46, DEEP, String(i + 1));
      s.addText(it[0], { x: x + 0.85, y: y + 0.1, w: 4.85, h: 0.33, fontSize: 14, bold: true,
        color: INK, fontFace: BF, isTextBox: true, margin: 0 });
      s.addText(it[1], { x: x + 0.85, y: y + 0.44, w: 4.85, h: 0.52, fontSize: 11.5, color: BODY,
        fontFace: BF, isTextBox: true, margin: 0 });
    }
  });
  s.addText('All seven are pinned by regression tests that fail against the original behaviour.',
    { x: M, y: 6.4, w: W - 2*M, h: 0.4, fontSize: 13, italic: true, color: MUTE,
      fontFace: BF, isTextBox: true });
}

/* --------------------------------------------- 15 how they were caught */
{
  const s = light('How each was caught');
  s.addText('Not one was visible from a summary statistic. Every one was found by checking a physical invariant.',
    { x: M, y: 1.2, w: W - 2*M, h: 0.45, fontSize: 15, color: BODY, fontFace: BF, isTextBox: true });

  const inv = [
    ['Bytes ÷ packets on the monitored queue', '66 B means you are queueing ACKs, not data'],
    ['Drop rate vs the link\'s packet rate', 'A 10 Mbit link passes 826 pkt/s; 130,000 drops/s is impossible'],
    ['Does varying a control input change the output?', 'If not, the control path is inert however it is labelled'],
    ['Is the threshold reachable at all?', '10 MB elephant threshold, 9.38 MB maximum flow share'],
    ['Does the reported value reach the kernel?', 'A float in userspace is not the qdisc parameter'],
  ];
  inv.forEach((it, i) => {
    const y = 1.85 + i * 0.95;
    card(s, M, y, W - 2*M, 0.82);
    s.addText(it[0], { x: M + 0.35, y: y + 0.08, w: 5.9, h: 0.38, fontSize: 14, bold: true,
      color: DEEP, fontFace: BF, isTextBox: true, margin: 0 });
    s.addText(it[1], { x: M + 0.35, y: y + 0.44, w: 11.2, h: 0.34, fontSize: 12.5, color: BODY,
      fontFace: BF, isTextBox: true, margin: 0 });
  });
  s.addText('We think this is the most transferable part of the work.',
    { x: M, y: 6.65, w: W - 2*M, h: 0.4, fontSize: 14, italic: true, color: INK,
      fontFace: BF, isTextBox: true });
}

/* ----------------------------------------------------- 16 novelty */
{
  const s = light('Where this sits against recent work');
  s.addText('2023–2026 · what is taken, and what is not',
    { x: M, y: 1.2, w: W - 2*M, h: 0.4, fontSize: 15, color: BODY, fontFace: BF, isTextBox: true });

  card(s, M, 1.75, 5.85, 2.45, 'FBEEF0');
  s.addText('Already done — cannot claim', { x: M + 0.3, y: 1.95, w: 5.25, h: 0.38,
    fontSize: 15, bold: true, color: WARN, fontFace: HF, isTextBox: true, margin: 0 });
  s.addText([
    { text: 'DESiRED (2024) adapts an AQM target at runtime with DRL + INT on P4', options: { breakLine: true, bullet: true } },
    { text: 'Adaptive RED (2001) is the AIMD rule we borrow', options: { breakLine: true, bullet: true } },
    { text: 'ACoDel (2020) adapts CoDel\'s interval — with a stability proof we lack', options: { breakLine: true, bullet: true } },
    { text: 'QueuePilot (2023), AQM-LLM (2026) learn AQM policies', options: { bullet: true } },
  ], { x: M + 0.3, y: 2.4, w: 5.25, h: 1.7, fontSize: 12, color: BODY, fontFace: BF,
       isTextBox: true, margin: 0, paraSpaceAfter: 6 });

  card(s, 6.85, 1.75, 5.75, 2.45, 'EAF4EE');
  s.addText('Not done by anyone — our claim', { x: 7.15, y: 1.95, w: 5.15, h: 0.38,
    fontSize: 15, bold: true, color: GOOD, fontFace: HF, isTextBox: true, margin: 0 });
  s.addText([
    { text: 'A sham-controller condition separating CPU cost from decisions', options: { breakLine: true, bullet: true } },
    { text: 'Sparse-probe and bulk-flow latency reported separately', options: { breakLine: true, bullet: true } },
    { text: 'Comparison against eight alternative disciplines', options: { breakLine: true, bullet: true } },
    { text: 'A published null result for the adaptation itself', options: { bullet: true } },
  ], { x: 7.15, y: 2.4, w: 5.15, h: 1.7, fontSize: 12, color: BODY, fontFace: BF,
       isTextBox: true, margin: 0, paraSpaceAfter: 6 });

  card(s, M, 4.5, W - 2*M, 1.7, 'E8F1F6');
  s.addText('The claim we can defend', { x: M + 0.35, y: 4.68, w: 11.5, h: 0.35,
    fontSize: 14, bold: true, color: DEEP, fontFace: BF, isTextBox: true, margin: 0, charSpacing: 1 });
  s.addText('A falsifiable predicate for when adapting an AQM\'s parameters pays, pre-registered and tested to destruction, with the controlled apparatus needed to establish it.',
    { x: M + 0.35, y: 5.05, w: 11.5, h: 1.0, fontSize: 17, bold: true, color: INK,
      fontFace: HF, isTextBox: true, margin: 0 });
  s.addNotes('The null result is only credible because of the control condition. That is what makes it a contribution rather than a failure.');
}

/* ------------------------------------------------------ 17 conclusion */
{
  const s = dark('What we are left with', 'CONCLUSION');
  const pts = [
    ['Flow queueing with a delay target is what matters', 'About 100x tail-latency reduction at no goodput cost'],
    ['Whether tuning helps is decided by r = target/RTT', 'Half the benefit at r = 0.50; correct configuration sits five to ten times below that'],
    ['The ratio fixes the shape, not the ceiling', 'At r = 1 the benefit still runs 7.1 to 18.2% across a 25-fold change in link rate'],
    ['Where r is small, switch discipline instead', 'CAKE needs no controller and beats the adapted system at every RTT tested'],
  ];
  pts.forEach((p, i) => {
    const y = 3.78 + i * 0.80;
    s.addShape(P.ShapeType.roundRect, { x: M, y, w: W - 2*M, h: 0.72, rectRadius: 0.07,
      fill: { color: '2C3568' }, line: { width: 0 } });
    dot(s, M + 0.3, y + 0.16, 0.40, TEAL, String(i + 1));
    s.addText(p[0], { x: M + 0.95, y: y + 0.05, w: 11.0, h: 0.34, fontSize: 14, bold: true,
      color: PAPER, fontFace: BF, isTextBox: true, margin: 0 });
    s.addText(p[1], { x: M + 0.95, y: y + 0.38, w: 11.0, h: 0.31, fontSize: 11.5,
      color: 'A9C3DE', fontFace: BF, isTextBox: true, margin: 0 });
  });
  s.addText('github.com/Amritha902/ccn-linux-qdisc-study   ·   every number in the paper generated from the logs',
    { x: M, y: 7.05, w: W - 2*M, h: 0.35, fontSize: 12, color: '7F97B8', fontFace: BF, isTextBox: true });
}

P.writeFile({ fileName: 'deck/ACAPE_2026.pptx' }).then(() => console.log('wrote deck/ACAPE_2026.pptx'));
