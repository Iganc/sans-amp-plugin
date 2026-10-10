#!/usr/bin/env python3
"""
render_sweep.py - renderuje biały szum przez wtyczkę referencyjną (VST3/AU) bez DAW-a,
z gałkami ustawianymi LICZBOWO (raw_value 0..1 = pozycja gałki).

Instalacja:  pip install pedalboard

1) Zobacz nazwy parametrów:
    python render_sweep.py --plugin "/Library/Audio/Plug-Ins/VST3/Ref.vst3" --list

2) Render HIGH na zestawie pozycji (pozostałe gałki ustawione przez --set):
    python render_sweep.py --plugin "/Library/Audio/Plug-Ins/VST3/Ref.vst3" \
        --param HIGH --prefix high --level -40 \
        --set GAIN=0 --set DRIVE=0 --set CRUNCH=0 --set LOW=0.5

Nazwy plików: <prefix>_<tag>_<level>.wav, np. high_25_-40.wav (tak jak oczekuje fit_taper.py).
Domyślne pozycje: max=1, min=0, mid=0.5, 25=0.25, 75=0.75, 125, 375, 625, 875.
Własne pozycje: --pos max=1 --pos min=0 --pos 30=0.3
"""
import argparse
import numpy as np
from pedalboard import load_plugin
from pedalboard.io import AudioFile

DEFAULT_POS = {'max': 1.0, 'min': 0.0, 'mid': 0.5, '25': 0.25, '75': 0.75,
               '125': 0.125, '375': 0.375, '625': 0.625, '875': 0.875}


def kv(items):
    out = {}
    for it in items or []:
        k, v = it.rsplit('=', 1)
        out[k] = float(v)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--plugin', required=True)
    ap.add_argument('--list', action='store_true', help='wypisz parametry i wyjdź')
    ap.add_argument('--param', help='nazwa parametru zmienianego (np. HIGH)')
    ap.add_argument('--set', action='append', help='NAZWA=WARTOSC (0..1), stałe ustawienia innych gałek')
    ap.add_argument('--pos', action='append', help='TAG=WARTOSC (0..1); domyślnie zestaw standardowy')
    ap.add_argument('--prefix', default='high')
    ap.add_argument('--level', type=float, default=-40.0, help='poziom RMS szumu w dBFS')
    ap.add_argument('--seconds', type=float, default=40.0)
    ap.add_argument('--sr', type=int, default=48000)
    ap.add_argument('--outdir', default='.')
    args = ap.parse_args()

    plug = load_plugin(args.plugin)
    if args.list:
        for name, p in plug.parameters.items():
            print(f"{name!r}: raw={p.raw_value:.3f}  wartosc={p.string_value}")
        return
    if not args.param:
        ap.error("podaj --param (albo --list)")

    positions = kv(args.pos) or DEFAULT_POS
    fixed = kv(args.set)

    rng = np.random.default_rng(1)
    n = int(args.seconds * args.sr)
    noise = rng.standard_normal(n).astype(np.float32)
    noise *= 10 ** (args.level / 20) / np.sqrt(np.mean(noise ** 2))
    audio = np.stack([noise, noise])  # ten sam szum w obu kanałach, dla każdego renderu identyczny

    for tag, pos in positions.items():
        for name, v in fixed.items():
            plug.parameters[name].raw_value = v
        plug.parameters[args.param].raw_value = pos
        plug.reset()
        out = plug.process(audio, args.sr, reset=True)
        p = plug.parameters[args.param]
        fn = f"{args.outdir}/{args.prefix}_{tag}_{int(args.level)}.wav"
        with AudioFile(fn, 'w', args.sr, 1, bit_depth=24) as f:
            f.write(out[0:1])
        print(f"{fn}: {args.param} raw={p.raw_value:.3f} ({p.string_value}), "
              f"peak {20*np.log10(np.max(np.abs(out[0])) + 1e-12):.1f} dBFS")


if __name__ == '__main__':
    main()