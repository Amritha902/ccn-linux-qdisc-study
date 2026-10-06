"""Stylometry on the rendered prose, which is what a detector reads.

The repository's style_check.py reads the .tex source, so a table swallows
whole and counts as one 1519-word sentence, which makes the variance
statistics meaningless. This works on pdftotext output with the tables,
captions, headings and reference list stripped.
"""
import re, sys, statistics as st, collections

txt = open(sys.argv[1]).read()
lines = txt.split("\n")
keep = []
for ln in lines:
    s = ln.strip()
    if not s:
        keep.append("")
        continue
    # drop headings, captions, table rows, references, figure furniture
    if re.match(r"^(Figure|Table|Fig\.|TABLE)\s", s): continue
    if re.match(r"^\[\d+\]", s): continue
    if re.match(r"^\d+(\.\d+)*\s+[A-Z]", s): continue
    if re.match(r"^(Abstract|Keywords|References|Contents|Index terms)", s, re.I): continue
    digits = sum(c.isdigit() for c in s)
    if len(s) and digits / len(s) > 0.28: continue      # numeric table row
    if len(s.split()) < 4: continue
    if s.count("  ") > 2: continue                       # column-ish layout
    keep.append(s)

prose = " ".join(keep)
prose = re.sub(r"\s+", " ", prose)
# sentence split on terminal punctuation not inside an abbreviation
sents = [x.strip() for x in re.split(r"(?<=[.!?])\s+(?=[A-Z(])", prose)
         if len(x.split()) >= 3]
lens = [len(x.split()) for x in sents]

print(f"file            {sys.argv[1].split('/')[-1]}")
print(f"prose words     {len(prose.split())}")
print(f"sentences       {len(lens)}")
if lens:
    m, sd = st.fmean(lens), (st.stdev(lens) if len(lens) > 1 else 0)
    print(f"sentence length mean {m:.1f}  sd {sd:.1f}  CV {sd/m:.2f}")
    print(f"                min {min(lens)}  max {max(lens)}")
    buckets = collections.Counter(min(l // 10, 6) for l in lens)
    print("  length spread  " + "  ".join(
        f"{b*10}-{b*10+9 if b<6 else '+'}:{buckets.get(b,0)}" for b in range(7)))
    short = sum(1 for l in lens if l <= 12)
    long_ = sum(1 for l in lens if l >= 40)
    print(f"  short (<=12w) {short} ({100*short/len(lens):.0f}%)   "
          f"long (>=40w) {long_} ({100*long_/len(lens):.0f}%)")

# openers
op = collections.Counter(s.split()[0].lower().strip(",") for s in sents if s.split())
rep = {w: n for w, n in op.items() if n >= 4}
print(f"repeated openers (>=4)  {rep if rep else 'none'}")

# markers detectors weight
markers = ["moreover", "furthermore", "additionally", "notably",
           "it is important to note", "it is worth noting", "crucially",
           "delve", "leverage", "underscore", "pivotal", "robust",
           "comprehensive", "seamless", "nuanced", "myriad", "realm",
           "landscape", "tapestry", "testament", "paradigm",
           "in conclusion", "in summary", "overall,", "ultimately,",
           "this paper presents", "we propose a novel", "state-of-the-art",
           "significantly improve", "cutting-edge", "holistic"]
low = prose.lower()
hits = {m: low.count(m) for m in markers if low.count(m)}
print(f"marker phrases   {hits if hits else 'none'}")

# "X, Y, and Z" triads
tri = len(re.findall(r"\w+, \w+,? and \w+", prose))
print(f"triadic lists    {tri}")
