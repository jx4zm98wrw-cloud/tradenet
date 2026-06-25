# pHash Hamming-distance calibration (Track 1)

Measured over real `trademarks.logo_phash` pairs to set `VISUAL_PHASH_THRESHOLD`.

```
pairs=3000
hd= 5  n=    0  cum%=  0.0
hd=10  n=    0  cum%=  0.0
hd=12  n=    1  cum%=  0.0
hd=16  n=    4  cum%=  0.2
hd=18  n=   15  cum%=  0.7
hd=20  n=   45  cum%=  2.2
hd=22  n=   96  cum%=  5.4
hd=24  n=  217  cum%= 12.6
hd=26  n=  317  cum%= 23.2
hd=28  n=  461  cum%= 38.5
hd=30  n=  535  cum%= 56.4
hd=32  n=  518  cum%= 73.6
hd=34  n=  353  cum%= 85.4
hd=36  n=  249  cum%= 93.7
hd=38  n=  115  cum%= 97.5
hd=40  n=   50  cum%= 99.2
hd=42  n=   17  cum%= 99.8
hd=44  n=    5  cum%= 99.9
hd=46  n=    1  cum%=100.0
hd=48  n=    1  cum%=100.0
```

**Reading:** the distribution peaks at hd≈30 — confirming unrelated images
differ in ~half the 64 bits, which the old `1 - hd/64` curve mapped to ~0.50.
`hd ≤ 10` covers only ~0.0% of pairs (the genuine-similarity tail). We set
`VISUAL_PHASH_THRESHOLD = 10`: any pair past hd=10 scores 0. (Literature: hd≤5
near-duplicate, hd≤10 visually similar.)
