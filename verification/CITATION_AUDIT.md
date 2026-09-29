# Citation Audit

Every reference in `filespr/ACAPE_IEEE_Paper.tex` and `README.md` checked against
the published record. Errors below are corrected in the rewritten bibliography.

| Cited as | Status | Correct record |
|---|---|---|
| Mallick et al., "Machine Learning for Active Queue Management: A Survey", *Comput. Netw.* vol. 240, 2025 | **WRONG — authors, title and volume** | Toopchinezhad, M. P. & Ahmadi, M., "Machine Learning Approaches for Active Queue Management: A Survey, Taxonomy, and Future Directions", *Computer Networks*, vol. **262**, May 2025. arXiv:2410.02563 |
| Ye & Leung, "Analysis and Design of an Adaptive CoDel AQM Algorithm", *IEEE/ACM ToN* 2021 (README) | **WRONG — venue and year** | Ye & Leung, "Adaptive and Stable Delay Control for Combating Bufferbloat: Theory and Algorithms", *IEEE Systems Journal*, vol. 14, no. 1, pp. 1285–1296, 2020 |
| Dery, Krupnik, Keslassy, "QueuePilot: Reviving Small Buffers With a Learned AQM Policy", INFOCOM 2023 | **CORRECT** | IEEE INFOCOM 2023, doi 10.1109/INFOCOM53939.2023.10228975 |
| Sharafzadeh et al., "Self-Clocked Round-Robin Packet Scheduling", USENIX NSDI 2025 | **CORRECT** | Sharafzadeh, Matson, Tourrilhes, Sharma, Ghorbani, USENIX NSDI '25, Philadelphia, Apr. 2025 |
| Floyd, Gummadi, Shenker, "Adaptive RED", ICSI TR 2001 | **CORRECT** | ICSI Technical Report, Aug. 2001 |
| Nichols & Jacobson, "Controlling Queue Delay", *ACM Queue* 10(5), 2012 | **CORRECT** | ACM Queue, vol. 10, no. 5, May 2012 |
| Floyd & Jacobson, "Random Early Detection Gateways", *IEEE/ACM ToN* 1(4), 1993 | **CORRECT** | IEEE/ACM Trans. Netw., vol. 1, no. 4, pp. 397–413, Aug. 1993 |
| Hoeiland-Joergensen et al., RFC 8290 (FlowQueue-CoDel) | **CORRECT** | IETF RFC 8290, Jan. 2018 |
| Cardwell et al., "BBR", *ACM Queue* 14(5), 2016 | **CORRECT** | ACM Queue, vol. 14, no. 5, 2016 |
| Jain, Chiu, Hawe, DEC TR-301, 1984 | **CORRECT** | DEC Research Report TR-301, Sep. 1984 |
| Ha, Rhee, Xu, "CUBIC", *ACM SIGOPS OSR* 42(5), 2008 | **CORRECT** | SIGOPS Oper. Syst. Rev., vol. 42, no. 5, pp. 64–74, 2008 |
| Gettys & Nichols, "Bufferbloat: Dark Buffers in the Internet", *CACM* 55(1), 2012 | **CORRECT** | Commun. ACM, vol. 55, no. 1, pp. 57–65, Jan. 2012 |
| Borkar, "Stochastic Approximation with Two Time Scales", *Syst. Control Lett.* 29(5), 1997 | **CORRECT** | Systems & Control Letters, vol. 29, no. 5, pp. 291–294, 1997 |

## Other reference problems

- The paper's `\bibitem{mallick2025}` and the README's entry 10 cite **the same survey
  under two different author lists**. Only the README's authors are right, and its
  volume/date are still wrong.
- The README's literature table claims the ML-AQM survey "directly confirms: no
  deployable kernel-free adaptive AQM for Linux fq_codel exists". The survey makes
  no such statement; that is an inference presented as a citation.
- `\bibitem{vieira2020}` (eBPF/XDP survey, ACM CSUR 53(1) art. 16, 2020) is cited in
  the bibliography but never referenced in the body.
- The README cites "Hung, Wang (Bytedance), eBPF Qdisc, Netdevconf 0x17, 2023",
  which does not appear in the paper's bibliography at all.


## Recent work added in the 2024–2026 survey update

All verified against the published record, November 2026.

| Reference | Verified |
|---|---|
| Rodriguez et al., "DESiRED — Dynamic, Enhanced, and Smart iRED: A P4-AQM with Deep Reinforcement Learning and In-band Network Telemetry", *Computer Networks* vol. 244, 2024 | ✅ arXiv:2310.18159; ScienceDirect S1389128624001580 |
| Satish et al., "Distilling Large Language Models for Network Active Queue Management", *IEEE Trans. Networking*, 2026 | ✅ arXiv:2501.16734 |
| Ray, Sharma, Marques, Schmitt, Bronzino, Feamster, "Characterizing the Impact of Active Queue Management on Speed Test Measurements", 2025 | ✅ arXiv:2511.19213, 24 Nov 2025 |
| "TCP BBR Performance over Wi-Fi 6: AQM Impacts and Cross-Layer Insights", 2025 | ✅ arXiv:2512.18259 |
| Kundel et al., "P4-CoDel: Active Queue Management in Programmable Data Planes", IEEE NFV-SDN 2018 | ✅ IEEE Xplore 8725736 |
| Hung & Wang, "eBPF Qdisc: A Generic Building Block for Traffic Control", Netdevconf 0x17, 2023 | ✅ netdevconf.info/0x17 |
| Høiland-Jørgensen, Täht, Morton, "Piece of CAKE", IEEE LANMAN 2018 | ✅ arXiv:1804.07617; IEEE Xplore 8475045 |
| RFC 9330 / 9331 / 9332 (L4S), Jan 2023 | ✅ rfc-editor.org |
| RFC 8033 (PIE), RFC 8289 (CoDel), RFC 7567 (AQM recommendations) | ✅ rfc-editor.org |

## Impact on the research-gap claim

**DESiRED (2024) materially narrows the gap this project claims.** It already
performs runtime adaptation of an AQM's *target delay* parameter driven by live
telemetry — the same concept, realised in P4 with deep reinforcement learning
and In-band Network Telemetry rather than in Linux `tc` with AIMD and eBPF.

Any statement that no prior work adapts an AQM's delay target at runtime is
therefore incorrect and must not appear in the paper. What remains distinct is
the deployment surface — stock Linux, no kernel or data-plane modification, a
transparent AIMD rule — which is an engineering distinction, not a conceptual
one.
