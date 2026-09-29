#!/usr/bin/env python3
"""Render a real command's output as a captioned terminal image.

Every figure produced here is a verbatim capture of a command that was actually
run, together with the step number, the command line, and a one-line statement
of what the output demonstrates. Nothing is mocked or re-typed.

Use as a library (capture_step(...)) or from the shell:
    python3 capture.py --step 03 --title "..." --explain "..." -- cmd args...
"""
import argparse, os, subprocess, sys, textwrap, time

from PIL import Image, ImageDraw, ImageFont

MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
MONO_B = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"

BG       = (13, 17, 23)
HEADER   = (22, 27, 34)
BORDER   = (48, 54, 61)
FG       = (201, 209, 217)
ACCENT   = (88, 166, 255)
GREEN    = (63, 185, 80)
YELLOW   = (210, 153, 34)
RED      = (248, 81, 73)
MUTED    = (139, 148, 158)

FS = 15
LH = 21
PAD = 18
WRAP = 104


def _font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


def colour_for(line):
    s = line.strip()
    low = s.lower()
    if any(k in low for k in ("error", "fail", "refuted", "cannot", "traceback")):
        return RED
    if any(k in low for k in ("warning", "warn", "note:")):
        return YELLOW
    if any(k in low for k in ("ok", "confirmed", "pass", "jited", "success", "0% packet loss")):
        return GREEN
    if s.startswith("$") or s.startswith("#"):
        return ACCENT
    if s.startswith("==") or s.startswith("--"):
        return MUTED
    return FG


def capture_step(step, title, explain, command, output, outdir, rc=None):
    """Render one step. `command` is the exact command line, `output` its stdout."""
    os.makedirs(outdir, exist_ok=True)
    f = _font(MONO, FS)
    fb = _font(MONO_B, FS)
    ft = _font(MONO_B, FS + 5)
    fe = _font(MONO, FS - 1)

    cmd_lines = textwrap.wrap(f"$ {command}", WRAP) or ["$"]
    body = []
    for raw in output.rstrip("\n").split("\n"):
        raw = raw.replace("\t", "    ")
        body.extend(textwrap.wrap(raw, WRAP) or [""])
    exp_lines = textwrap.wrap(explain, WRAP - 4)

    head_h = PAD + (FS + 5) + 10 + len(exp_lines) * (LH - 2) + PAD
    body_h = PAD + (len(cmd_lines) + len(body)) * LH + PAD
    W = PAD * 2 + WRAP * 9 + 20
    H = head_h + body_h + 34

    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    d.rectangle([0, 0, W, head_h], fill=HEADER)
    d.line([(0, head_h), (W, head_h)], fill=BORDER, width=2)

    y = PAD
    d.text((PAD, y), f"STEP {step}", font=ft, fill=ACCENT)
    tw = d.textlength(f"STEP {step}", font=ft)
    d.text((PAD + tw + 14, y), title, font=ft, fill=FG)
    y += FS + 5 + 10
    for ln in exp_lines:
        d.text((PAD, y), ln, font=fe, fill=MUTED)
        y += LH - 2

    y = head_h + PAD
    for ln in cmd_lines:
        d.text((PAD, y), ln, font=fb, fill=ACCENT)
        y += LH
    for ln in body:
        d.text((PAD, y), ln, font=f, fill=colour_for(ln))
        y += LH

    foot = f"captured {time.strftime('%Y-%m-%d %H:%M:%S')} UTC"
    if rc is not None:
        foot += f"   exit={rc}"
    foot += f"   kernel {os.uname().release}"
    d.line([(0, H - 30), (W, H - 30)], fill=BORDER, width=1)
    d.text((PAD, H - 24), foot, font=fe, fill=MUTED)

    path = os.path.join(outdir, f"step{step}_{_slug(title)}.png")
    img.save(path)
    return path


def _slug(s):
    return "".join(c if c.isalnum() else "_" for c in s.lower()).strip("_")[:48]


def run_and_capture(step, title, explain, command, outdir, shell=True, max_lines=46):
    r = subprocess.run(command, shell=shell, capture_output=True, text=True)
    out = (r.stdout + r.stderr).rstrip("\n")
    lines = out.split("\n")
    if len(lines) > max_lines:
        keep = max_lines - 1
        out = "\n".join(lines[:keep] + [f"... [{len(lines)-keep} more lines omitted]"])
    path = capture_step(step, title, explain, command, out, outdir, r.returncode)
    print(f"  STEP {step}  {title}  -> {os.path.basename(path)}")
    return path, r.returncode, out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--step", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--explain", required=True)
    p.add_argument("--outdir", default="figures/steps")
    p.add_argument("cmd", nargs=argparse.REMAINDER)
    a = p.parse_args()
    cmd = " ".join(a.cmd[1:] if a.cmd and a.cmd[0] == "--" else a.cmd)
    run_and_capture(a.step, a.title, a.explain, cmd, a.outdir)


if __name__ == "__main__":
    main()
