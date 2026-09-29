#!/usr/bin/env python3
"""Stylometric check for the markers associated with LLM-generated prose.

This is NOT an AI detector. No reliable one exists: published detectors produce
both false positives on careful human writing and false negatives on edited
machine output, and several have been withdrawn for bias against non-native
English. What this does instead is measure the specific, well-documented
surface features that make text *read* as machine-written, and point at the
lines carrying them, so they can be judged and fixed by hand.
"""
import re, statistics as st, sys, collections

PATH = sys.argv[1] if len(sys.argv) > 1 else "paper/acape.tex"
raw = open(PATH).read()

# --- strip LaTeX to prose -------------------------------------------------
body = raw
body = re.sub(r"(?s)\\begin\{thebibliography\}.*?\\end\{thebibliography\}", "", body)
body = re.sub(r"(?s)\\begin\{(figure|table|tabular|verbatim|lstlisting|equation|description|itemize|enumerate)\*?\}.*?\\end\{\1\*?\}", "", body)
body = re.sub(r"(?m)^%.*$", "", body)
body = re.sub(r"\\(cite|ref|label|input|includegraphics|graphicspath)\{[^}]*\}", "", body)
body = re.sub(r"\\(texttt|textbf|textit|emph|section|subsection|title|author)\*?\{([^{}]*)\}", r"\2", body)
body = re.sub(r"\\[A-Za-z]+\*?(\[[^\]]*\])?(\{[^{}]*\})?", " ", body)
body = re.sub(r"[{}$\\]", " ", body)
body = re.sub(r"\s+", " ", body).strip()

words = re.findall(r"[A-Za-z']+", body)
sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", body) if len(s.split()) > 3]
nw, ns = len(words), len(sents)

def per1k(n): return 1000.0 * n / max(nw, 1)

print("=" * 74)
print(f"STYLOMETRIC CHECK — {PATH}")
print("=" * 74)
print(f"  prose words {nw}   sentences {ns}\n")

flags = []

# 1. em-dashes ------------------------------------------------------------
em = len(re.findall(r"---|—", raw))
r = per1k(em)
print(f"1. Em-dashes                 {em:4d}   {r:5.2f}/1k words")
print(f"   Human academic prose typically < 2/1k. LLM output often 4-8/1k.")
if r > 3: flags.append(f"em-dash rate {r:.1f}/1k is high; convert some to commas, colons or full stops")

# 2. LLM-favoured vocabulary ---------------------------------------------
LEX = ["delve","leverage","robust","comprehensive","crucial","pivotal","seamless",
       "underscore","showcase","realm","landscape","myriad","testament","intricate",
       "nuanced","holistic","paradigm","synergy","multifaceted","meticulous",
       "noteworthy","cutting-edge","state-of-the-art","harness","unlock","foster",
       "profound","remarkable","vital","essential","significantly enhance"]
hits = collections.Counter()
for t in LEX:
    n = len(re.findall(rf"\b{re.escape(t)}\w*\b", body, re.I))
    if n: hits[t] = n
print(f"\n2. LLM-favoured vocabulary   {sum(hits.values()):4d} occurrences")
if hits:
    for t, n in hits.most_common(): print(f"     {t:24s} {n}")
    flags.append(f"replace flagged vocabulary: {', '.join(hits)}")
else:
    print("     none found")

# 3. formulaic openers / connectives --------------------------------------
PHR = ["it is important to note","it is worth noting","it should be noted",
       "in conclusion","in summary","overall,","furthermore","moreover",
       "additionally,","notably,","importantly,","this paper aims",
       "we delve into","plays a (crucial|key|vital) role","a wide range of",
       "it is clear that","as we have seen","in today's"]
pn = 0
print(f"\n3. Formulaic phrases")
for t in PHR:
    n = len(re.findall(rf"\b{t}\b", body, re.I))
    if n: print(f"     {t:38s} {n}"); pn += n
if not pn: print("     none found")
else: flags.append(f"{pn} formulaic connective(s); prefer plain transitions")

# 4. sentence-length uniformity -------------------------------------------
L = [len(s.split()) for s in sents]
cv = st.stdev(L) / st.fmean(L) if ns > 2 else 0
print(f"\n4. Sentence length           mean {st.fmean(L):.1f}  sd {st.stdev(L):.1f}  CV {cv:.2f}")
print(f"   Human prose CV ~0.5-0.7. Uniform length (CV < 0.4) reads machine-made.")
print(f"   shortest {min(L)}w   longest {max(L)}w")
if cv < 0.40: flags.append(f"sentence lengths too uniform (CV {cv:.2f}); vary rhythm")

# 5. tricolons and "not X but Y" ------------------------------------------
tri = len(re.findall(r"\b\w+, \w+,? and \w+\b", body))
notbut = len(re.findall(r"\bnot (just |merely |only )?\w+[^.]{0,40}? but \w+", body, re.I))
print(f"\n5. Rhetorical patterns       tricolons {tri}   'not X but Y' {notbut}")
if per1k(tri) > 4: flags.append(f"tricolon rate {per1k(tri):.1f}/1k is high")
if per1k(notbut) > 1.5: flags.append(f"'not X but Y' used {notbut} times; vary the construction")

# 6. paragraph opener repetition ------------------------------------------
paras = [p.strip() for p in re.split(r"\n\s*\n", raw) if len(p.split()) > 20]
op = collections.Counter(re.sub(r"[^A-Za-z ]","",p).split()[0].lower() for p in paras if p.split())
rep = {w:n for w,n in op.items() if n > 2}
print(f"\n6. Paragraph openers         {len(paras)} paragraphs")
if rep:
    print(f"     repeated: {rep}"); flags.append(f"repeated paragraph openers: {rep}")
else: print("     no opener repeated more than twice")

# 7. hedging density ------------------------------------------------------
hed = len(re.findall(r"\b(may|might|could|possibly|potentially|arguably|suggests that|appears to)\b", body, re.I))
print(f"\n7. Hedging                   {hed:4d}   {per1k(hed):5.2f}/1k")
if per1k(hed) > 12: flags.append(f"hedging {per1k(hed):.1f}/1k is high for a results paper")

# --- verdict -------------------------------------------------------------
print("\n" + "=" * 74)
if flags:
    print(f"{len(flags)} ITEM(S) TO ADDRESS")
    for f in flags: print(f"  - {f}")
else:
    print("No stylometric markers above threshold.")
print("=" * 74)
print("""
This measures surface style only. It cannot establish authorship, and a clean
result is not a certificate. The substantive defence against a plagiarism or
fabrication challenge is that every number here is reproducible from the
committed logs by a documented command -- which no amount of rewording
provides, and which this repository does provide.""")
