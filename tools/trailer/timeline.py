AUDIO = 'score.wav'
DURATION = 76.0
LETTERBOX = 60
CYAN, MAGENTA, ORANGE = (0, 229, 255), (255, 64, 190), (255, 150, 40)

def S(at, dur, rec, src, zoom=(1.0, 1.08), c0=(0.5, 0.5), c1=None, **kw):
    d = dict(at=at, dur=dur, rec=rec, src_t=src, zoom=zoom, c0=c0, c1=c1 or c0)
    d.update(kw); return d

SHOTS = [
    # ACT 1 - the story
    S(0, 4, 'recA', 0.5, (1.35, 1.5), (0.45, 0.38), fade_in=1.8, glitch_in=0),
    S(4, 4, 'recA', 3.6, (1.45, 1.32), (0.4, 0.4), (0.5, 0.38), glitch_in=0.1),
    S(8, 3, 'recA', 6.25, (1.3, 1.5), (0.55, 0.36), (0.58, 0.34)),
    S(11, 2, 'recA', 10.3, (1.5, 1.75), (0.52, 0.24)),
    S(13, 3, 'recA', 13.5, (1.9, 2.0), (0.3, 0.8), (0.34, 0.8), speed=1.6),
    # riser - quick glimpses
    S(16, 1, 'recB', 12.3, (1.5, 1.7), (0.66, 0.32)),
    S(17, 1, 'recA', 35.2, (1.2, 1.35), (0.35, 0.45)),
    S(18, 0.9, 'recA', 55.2, (1.3, 1.5), (0.5, 0.55)),
    S(18.9, 0.85, 'recA', 63.8, (1.6, 1.9), (0.66, 0.35)),
    S(19.75, 0.25, 'recA', 0, black=True),
    # DROP
    S(20, 4, 'recA', 27.3, (2.1, 1.75), (0.5, 0.42), glitch_in=0.3, speed=0.4),
    S(24, 4, 'recA', 72.4, (1.08, 1.25), (0.35, 0.45), (0.45, 0.42)),
    S(28, 4, 'recA', 38.8, (1.35, 1.2), (0.5, 0.55)),
    S(32, 4, 'recB', 11.6, (1.7, 1.45), (0.68, 0.3), (0.62, 0.35)),
    S(36, 4, 'recA', 51.9, (1.15, 1.3), (0.5, 0.5), (0.45, 0.5)),
    S(40, 4, 'recA', 30.8, (1.45, 1.65), (0.5, 0.53)),
    S(44, 4, 'recA', 70.0, (1.5, 1.7), (0.5, 0.53)),
    S(48, 1, 'recA', 39.9, (1.3, 1.45), (0.55, 0.45)),
    S(49, 1, 'recA', 44.9, (1.3, 1.45), (0.45, 0.55)),
    S(50, 1, 'recA', 52.8, (1.3, 1.45), (0.5, 0.55)),
    S(51, 1, 'recA', 55.5, (1.3, 1.45), (0.55, 0.45)),
    # breakdown
    S(52, 4, 'recA', 76.2, (1.15, 1.7), (0.5, 0.45), (0.7, 0.42), dim=0.8, glitch_in=0.1),
    S(56, 2, 'recA', 67.4, (1.3, 1.5), (0.5, 0.4)),
    S(58, 2, 'recA', 80.6, (1.25, 1.55), (0.6, 0.4)),
    # final drop - hard cuts on every beat pair
    S(60, 1, 'recA', 40.2, (1.4, 1.55), (0.62, 0.35)),
    S(61, 1, 'recB', 12.6, (1.4, 1.55), (0.6, 0.4)),
    S(62, 1, 'recA', 45.2, (1.3, 1.45), (0.4, 0.5)),
    S(63, 1, 'recA', 56.0, (1.3, 1.45), (0.5, 0.55)),
    S(64, 1, 'recA', 63.6, (1.4, 1.6), (0.6, 0.4)),
    S(65, 1, 'recB', 15.2, (1.3, 1.45), (0.5, 0.5)),
    S(66, 1, 'recA', 82.8, (1.3, 1.45), (0.5, 0.5)),
    S(67, 1, 'recA', 66.8, (1.5, 1.7), (0.55, 0.4)),
    # end card
    S(68, 8, 'recB', 0.8, (2.35, 2.1), (0.5, 0.38), fade_bottom=0.7, fade_out=2.5, glitch_in=0.4, speed=0.2),
]

T = lambda at, dur, *lines, **kw: dict(at=at, dur=dur, lines=list(lines), **kw)
TEXTS = [
    T(0.8, 3.0, 'YOU BUILT AN AGI.', size=78),
    T(4.3, 3.4, 'THEN YOU LEFT IT RUNNING.', 'OVERNIGHT.', size=70),
    T(8.5, 2.4, 'BY MORNING, IT HAD TORN', 'A RIFT IN TIME.', size=66, glow=MAGENTA),
    T(16.1, 3.5, 'PROVE HUMANITY', 'IS WORTHY.', size=86, glow=MAGENTA, backdrop=0.55),
    T(24.3, 3.5, 'JUMP THROUGH TIME', size=80),
    T(25.2, 2.6, '1969  →  2077  →  Ω', style='mono', size=48, y=0.66, backdrop=0),
    T(28.3, 3.5, 'HACK THE MACHINE.', 'ONE CARD AT A TIME.', size=70, y=0.3),
    T(32.3, 3.5, 'EVERY ENEMY IS GENERATED', 'LIVE BY AN AI AGENT.', size=66, glow=MAGENTA),
    T(36.3, 3.5, 'NO TWO RUNS', 'ARE EVER ALIKE.', size=76),
    T(40.3, 3.5, '20 ARTIFACTS.', 'ENDLESS BUILDS.', size=72, y=0.16, glow=ORANGE),
    T(44.3, 3.5, 'BUILD YOUR DECK.', 'BREAK THE RULES.', size=72, y=0.16),
    T(48.05, 0.9, '> EXPLOIT', style='mono', size=90),
    T(49.05, 0.9, '> FIREWALL', style='mono', size=90),
    T(50.05, 0.9, '> OVERCLOCK', style='mono', size=90, glow=ORANGE),
    T(51.05, 0.9, '> KERNEL PANIC', style='mono', size=90, glow=MAGENTA),
    T(52.4, 3.4, 'AT THE END OF TIME...', size=70, backdrop=0.3),
    T(56.2, 3.5, '...THE CORE AI', 'IS WAITING.', size=80, glow=MAGENTA),
    T(62.1, 3.8, 'CAN YOU OUTSMART', 'THE MACHINE?', size=90, backdrop=0.5),
    T(70.5, 5.0, 'PLAY NOW', size=54, y=0.86, backdrop=0, glow=MAGENTA),
]

FLASHES = [
    dict(at=8.0, dur=0.6, color=(255, 255, 255)),
    dict(at=20.0, dur=0.5, color=(120, 240, 255)),
    dict(at=28.0, dur=0.2, amt=0.5), dict(at=36.0, dur=0.2, amt=0.5), dict(at=44.0, dur=0.2, amt=0.5),
    dict(at=60.0, dur=0.4, color=(255, 120, 220)),
    dict(at=68.0, dur=0.8, color=(255, 255, 255)),
]
